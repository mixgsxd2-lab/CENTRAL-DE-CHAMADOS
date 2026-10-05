# -*- coding: utf-8 -*-
"""Função central de criação de chamados de Hotelaria.

Usada tanto pela própria API da Hotelaria (paciente abre um chamado
diretamente em `/hotelaria`) quanto pelo Chamador de Enfermagem, quando o
paciente escolhe a opção "OUTROS" (seção 5 da especificação) — nesse caso o
Chamador de Enfermagem chama esta função diretamente (mesmo processo,
mesmo banco), sem passar pela fila de enfermagem, garantindo que o chamado
apareça imediatamente na Central de Hotelaria.
"""
from datetime import timedelta

from db import get_db
from timeutils import agora, para_texto
from andares import andar_do_leito
from hotelaria.models import SERVICOS, STATUS_PENDENTE, CONFIRMACAO_NA, chamado_to_dict

# Mesma ideia de deduplicação já usada na Enfermagem (ver enfermagem/api.py):
# um duplo-clique ou um retry de rede não deve virar um segundo chamado.
JANELA_DEDUPLICACAO_SEGUNDOS = 15


def _chamado_duplicado_recente(leito, servico, descricao):
    db = get_db()
    limite = para_texto(agora() - timedelta(seconds=JANELA_DEDUPLICACAO_SEGUNDOS))
    return db.execute(
        """SELECT * FROM hotelaria_chamados
           WHERE leito = ? AND servico = ? AND descricao = ? AND status = ? AND criado_em >= ?
           ORDER BY criado_em DESC LIMIT 1""",
        (leito, servico, descricao, STATUS_PENDENTE, limite),
    ).fetchone()


def criar_chamado_hotelaria(leito, servico, descricao, origem="hotelaria", andar=None):
    if servico not in SERVICOS:
        raise ValueError(f"Serviço de hotelaria inválido: {servico!r}")

    duplicado = _chamado_duplicado_recente(leito, servico, descricao)
    if duplicado is not None:
        return chamado_to_dict(duplicado)

    # Se quem chamou não informou o andar mas o leito corresponde a um leito
    # oficial conhecido, deriva o andar automaticamente — permite métricas de
    # "distribuição por andar" mesmo para chamados antigos do fluxo direto da
    # Hotelaria que só enviaram o leito.
    andar = andar or andar_do_leito(leito)

    db = get_db()
    cur = db.execute(
        """INSERT INTO hotelaria_chamados
           (leito, servico, descricao, status, origem, criado_em, confirmacao_resolucao, andar)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (leito, servico, descricao, STATUS_PENDENTE, origem, para_texto(agora()), CONFIRMACAO_NA, andar),
    )
    db.commit()

    row = db.execute("SELECT * FROM hotelaria_chamados WHERE id = ?", (cur.lastrowid,)).fetchone()
    return chamado_to_dict(row)
