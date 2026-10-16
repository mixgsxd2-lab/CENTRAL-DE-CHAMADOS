# -*- coding: utf-8 -*-
"""Função central de criação de chamados de Hotelaria.

Usada tanto pela própria API da Hotelaria (paciente abre um chamado
diretamente em `/hotelaria`) quanto pela Central de Chamados, quando o
paciente escolhe a opção "OUTROS" (seção 5 da especificação) — nesse caso a Central
de Chamados chama esta função diretamente (mesmo processo,
mesmo banco), sem passar pela fila de enfermagem, garantindo que o chamado
apareça imediatamente na Central de Hotelaria.
"""
from datetime import timedelta

from db import get_db
from timeutils import agora, para_texto
from andares import andar_do_leito
from hotelaria.models import SERVICOS, STATUS_PENDENTE, CONFIRMACAO_NA, chamado_to_dict

JANELA_DEDUPLICACAO_SEGUNDOS = 15


def _chamado_duplicado_recente(leito, servico, descricao):
    db = get_db()
    limite = para_texto(agora() - timedelta(seconds=JANELA_DEDUPLICACAO_SEGUNDOS))
    with db.cursor() as cursor:
        cursor.execute(
            """SELECT * FROM hotelaria_chamados
               WHERE leito = %s AND servico = %s AND descricao = %s AND status = %s AND criado_em >= %s
               ORDER BY criado_em DESC LIMIT 1""",
            (leito, servico, descricao, STATUS_PENDENTE, limite),
        )
        return cursor.fetchone()


def criar_chamado_hotelaria(leito, servico, descricao, origem="hotelaria", andar=None):
    if servico not in SERVICOS:
        raise ValueError(f"Serviço de hotelaria inválido: {servico!r}")

    duplicado = _chamado_duplicado_recente(leito, servico, descricao)
    if duplicado is not None:
        return chamado_to_dict(duplicado)

    andar = andar or andar_do_leito(leito)

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """INSERT INTO hotelaria_chamados
               (leito, servico, descricao, status, origem, criado_em, confirmacao_resolucao, andar)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id
               """,
            (leito, servico, descricao, STATUS_PENDENTE, origem, para_texto(agora()), CONFIRMACAO_NA, andar),
        )
        chamado_id = cursor.fetchone()["id"]
    db.commit()

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM hotelaria_chamados WHERE id = %s", (chamado_id,))
        row = cursor.fetchone()

    return chamado_to_dict(row)