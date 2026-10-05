# -*- coding: utf-8 -*-
"""Controle de acesso da tela do PACIENTE via QR Code do leito.

Regras (pedido do hospital):
  1. O QR Code de cada leito é FIXO — nunca muda. Ele aponta para
     `/enfermagem/?acesso=<token>&andar=...&leito=...`, e o token é um só,
     gerado uma vez e guardado em `enfermagem_config` (nunca é trocado).
  2. Ao escanear, o paciente entra sem senha: o servidor grava na SESSÃO do
     navegador (cookie assinado) qual leito foi liberado e QUANDO — sempre
     pelo relógio do servidor (America/Fortaleza), nunca o do celular — e
     redireciona para a URL "limpa" (sem o token). Assim, recarregar a
     página depois da meia-noite NÃO libera o acesso de novo: só escanear o
     QR Code (que abre a URL com o token) libera.
  3. A liberação vale até a próxima meia-noite (00:00 de Fortaleza), igual
     para todo mundo — não importa a hora em que o paciente escaneou.
  4. "Expirar acesso" (um leito) e "Expirar todos" (Central) gravam o
     horário da revogação. Toda liberação ANTERIOR a esse horário deixa de
     valer na hora; quem escanear DEPOIS entra normalmente, mas continua
     valendo só até a mesma meia-noite (revogar não abre um novo período).

Nada sobre o paciente é guardado: só andar/leito e horários.
"""
import secrets
from datetime import datetime, timedelta

from flask import session

from andares import leito_valido
from db import get_db
from timeutils import agora

CHAVE_TOKEN = "acesso_paciente_token"
CHAVE_EXPIRADO_TODOS = "acesso_expirado_todos_em"

# Chave da sessão do navegador do paciente: {"andar", "leito", "desde"}.
SESSAO_ACESSO = "enfermagem_acesso_leito"


def _texto(dt):
    # Sempre com microssegundos: um "Expirar acesso" e um novo escaneamento
    # no mesmo segundo precisam continuar distinguíveis.
    return dt.isoformat(sep=" ", timespec="microseconds")


def _dt(texto):
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def inicio_do_dia(momento=None):
    return (momento or agora()).replace(hour=0, minute=0, second=0, microsecond=0)


def proxima_meia_noite(momento=None):
    return inicio_do_dia(momento) + timedelta(days=1)


# ---------------------------------------------------------------------------
# Token fixo dos QR Codes
# ---------------------------------------------------------------------------
def obter_token():
    """Token dos QR Codes — criado uma única vez e nunca trocado (trocar o
    token invalidaria todos os QR Codes impressos)."""
    db = get_db()
    row = db.execute("SELECT valor FROM enfermagem_config WHERE chave = ?", (CHAVE_TOKEN,)).fetchone()
    if row is not None:
        return row["valor"]

    token = secrets.token_urlsafe(24)
    db.execute("INSERT OR IGNORE INTO enfermagem_config (chave, valor) VALUES (?, ?)", (CHAVE_TOKEN, token))
    db.commit()
    return db.execute("SELECT valor FROM enfermagem_config WHERE chave = ?", (CHAVE_TOKEN,)).fetchone()["valor"]


def token_valido(token):
    return bool(token) and secrets.compare_digest(str(token), obter_token())


# ---------------------------------------------------------------------------
# Revogações
# ---------------------------------------------------------------------------
def _expirado_todos_em(db):
    row = db.execute("SELECT valor FROM enfermagem_config WHERE chave = ?", (CHAVE_EXPIRADO_TODOS,)).fetchone()
    return _dt(row["valor"]) if row else None


def _linha_leito(db, andar, leito):
    return db.execute(
        "SELECT ultimo_acesso_em, expirado_em FROM enfermagem_acesso_leitos WHERE andar = ? AND leito = ?",
        (andar, leito),
    ).fetchone()


def _liberacao_vale(desde, expirado_leito, expirado_todos, momento):
    if desde is None or desde < inicio_do_dia(momento) or desde > momento:
        return False
    if expirado_leito is not None and desde <= expirado_leito:
        return False
    if expirado_todos is not None and desde <= expirado_todos:
        return False
    return True


def expirar_leito(andar, leito):
    """Retorna False se o andar/leito não existir."""
    if not leito_valido(andar, leito):
        return False
    db = get_db()
    db.execute(
        "INSERT INTO enfermagem_acesso_leitos (andar, leito, expirado_em) VALUES (?, ?, ?) "
        "ON CONFLICT(andar, leito) DO UPDATE SET expirado_em = excluded.expirado_em",
        (andar, leito, _texto(agora())),
    )
    db.commit()
    return True


def expirar_todos():
    db = get_db()
    db.execute(
        "INSERT INTO enfermagem_config (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (CHAVE_EXPIRADO_TODOS, _texto(agora())),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Sessão do paciente
# ---------------------------------------------------------------------------
def conceder_acesso(andar, leito):
    """Chamado quando o QR Code do leito é escaneado (token válido)."""
    momento = agora()
    session[SESSAO_ACESSO] = {"andar": andar, "leito": leito, "desde": _texto(momento)}
    db = get_db()
    db.execute(
        "INSERT INTO enfermagem_acesso_leitos (andar, leito, ultimo_acesso_em) VALUES (?, ?, ?) "
        "ON CONFLICT(andar, leito) DO UPDATE SET ultimo_acesso_em = excluded.ultimo_acesso_em",
        (andar, leito, _texto(momento)),
    )
    db.commit()


def tinha_acesso():
    """True se este navegador já escaneou algum QR Code (mesmo que a
    liberação já tenha expirado) — só muda o texto da tela de bloqueio."""
    return bool(session.get(SESSAO_ACESSO))


def acesso_atual():
    """Liberação vigente deste navegador ({"andar", "leito", "expira_em"})
    ou None se nunca escaneou / passou da meia-noite / foi revogada."""
    dados = session.get(SESSAO_ACESSO)
    if not isinstance(dados, dict):
        return None
    andar, leito = dados.get("andar"), dados.get("leito")
    if not leito_valido(andar, leito):
        return None

    momento = agora()
    db = get_db()
    linha = _linha_leito(db, andar, leito)
    expirado_leito = _dt(linha["expirado_em"]) if linha else None
    if not _liberacao_vale(_dt(dados.get("desde")), expirado_leito, _expirado_todos_em(db), momento):
        return None
    return {"andar": andar, "leito": leito, "expira_em": proxima_meia_noite(momento)}


# ---------------------------------------------------------------------------
# Painel da Central
# ---------------------------------------------------------------------------
def status_leitos():
    """{(andar, leito): "HH:MM"} dos leitos cujo último escaneamento ainda
    vale hoje (não expirou nem foi revogado). Um celular pode ter perdido o
    cookie, então isto é só indicativo: "alguém escaneou e ainda vale"."""
    momento = agora()
    db = get_db()
    expirado_todos = _expirado_todos_em(db)
    liberados = {}
    for row in db.execute(
        "SELECT andar, leito, ultimo_acesso_em, expirado_em FROM enfermagem_acesso_leitos "
        "WHERE ultimo_acesso_em >= ?",
        (_texto(inicio_do_dia(momento)),),
    ):
        desde = _dt(row["ultimo_acesso_em"])
        if _liberacao_vale(desde, _dt(row["expirado_em"]), expirado_todos, momento):
            liberados[(row["andar"], row["leito"])] = desde.strftime("%H:%M")
    return liberados
