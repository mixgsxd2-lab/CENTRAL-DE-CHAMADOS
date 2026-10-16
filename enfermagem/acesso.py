# -*- coding: utf-8 -*-
import secrets
from datetime import datetime, timedelta

from flask import session

from andares import leito_valido
from db import get_db
from timeutils import agora

CHAVE_TOKEN = "acesso_paciente_token"
CHAVE_EXPIRADO_TODOS = "acesso_expirado_todos_em"

SESSAO_ACESSO = "enfermagem_acesso_leito"


def _texto(dt):
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


def obter_token():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT valor FROM enfermagem_config WHERE chave = %s", (CHAVE_TOKEN,))
        row = cursor.fetchone()
        if row is not None:
            return row["valor"]

        token = secrets.token_urlsafe(24)
        cursor.execute("INSERT INTO enfermagem_config (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING", (CHAVE_TOKEN, token))
        db.commit()

        cursor.execute("SELECT valor FROM enfermagem_config WHERE chave = %s", (CHAVE_TOKEN,))
        return cursor.fetchone()["valor"]


def token_valido(token):
    return bool(token) and secrets.compare_digest(str(token), obter_token())


def _expirado_todos_em(db):
    with db.cursor() as cursor:
        cursor.execute("SELECT valor FROM enfermagem_config WHERE chave = %s", (CHAVE_EXPIRADO_TODOS,))
        row = cursor.fetchone()
    return _dt(row["valor"]) if row else None


def _linha_leito(db, andar, leito):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT ultimo_acesso_em, expirado_em FROM enfermagem_acesso_leitos WHERE andar = %s AND leito = %s",
            (andar, leito),
        )
        return cursor.fetchone()


def _liberacao_vale(desde, expirado_leito, expirado_todos, momento):
    if desde is None or desde < inicio_do_dia(momento) or desde > momento:
        return False
    if expirado_leito is not None and desde <= expirado_leito:
        return False
    if expirado_todos is not None and desde <= expirado_todos:
        return False
    return True


def expirar_leito(andar, leito):
    if not leito_valido(andar, leito):
        return False
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO enfermagem_acesso_leitos (andar, leito, expirado_em) VALUES (%s, %s, %s) "
            "ON CONFLICT (andar, leito) DO UPDATE SET expirado_em = EXCLUDED.expirado_em",
            (andar, leito, _texto(agora())),
        )
    db.commit()
    return True


def expirar_todos():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO enfermagem_config (chave, valor) VALUES (%s, %s) "
            "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor",
            (CHAVE_EXPIRADO_TODOS, _texto(agora())),
        )
    db.commit()


def conceder_acesso(andar, leito):
    momento = agora()
    session[SESSAO_ACESSO] = {"andar": andar, "leito": leito, "desde": _texto(momento)}
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO enfermagem_acesso_leitos (andar, leito, ultimo_acesso_em) VALUES (%s, %s, %s) "
            "ON CONFLICT (andar, leito) DO UPDATE SET ultimo_acesso_em = EXCLUDED.ultimo_acesso_em",
            (andar, leito, _texto(momento)),
        )
    db.commit()


def tinha_acesso():
    return bool(session.get(SESSAO_ACESSO))


def acesso_atual():
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


def status_leitos():
    momento = agora()
    db = get_db()
    expirado_todos = _expirado_todos_em(db)
    liberados = {}
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT andar, leito, ultimo_acesso_em, expirado_em FROM enfermagem_acesso_leitos "
            "WHERE ultimo_acesso_em >= %s",
            (_texto(inicio_do_dia(momento)),),
        )
        linhas = cursor.fetchall()

    for row in linhas:
        desde = _dt(row["ultimo_acesso_em"])
        if _liberacao_vale(desde, _dt(row["expirado_em"]), expirado_todos, momento):
            liberados[(row["andar"], row["leito"])] = desde.strftime("%H:%M")
    return liberados