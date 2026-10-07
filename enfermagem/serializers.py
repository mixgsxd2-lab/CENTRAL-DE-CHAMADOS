# -*- coding: utf-8 -*-
from timeutils import formata_data_br, formata_hora, duracao_minutos
from enfermagem.constants import STATUS_LABELS
from enfermagem.priority import calcular_prioridade, excedeu_sla


def chamado_to_dict(chamado, incluir_prioridade=True):
    dados = {
        "id": chamado.id,
        "andar": chamado.andar,
        "leito": chamado.leito,
        "categoria": chamado.categoria,
        "subcategoria": chamado.subcategoria,
        "detalhe": chamado.detalhe,
        "status": chamado.status,
        "status_label": STATUS_LABELS.get(chamado.status, chamado.status),
        "profissional_responsavel": chamado.profissional_responsavel,
        "criado_em": formata_data_br(chamado.criado_em),
        "criado_em_hora": formata_hora(chamado.criado_em),
        "inicio_atendimento": formata_data_br(chamado.inicio_atendimento),
        "finalizado_em": formata_data_br(chamado.finalizado_em),
        "tempo_atendimento_min": chamado.tempo_atendimento_min(),
        "tempo_total_min": chamado.tempo_total_min(),
        "segundos_ate_finalizar": chamado.segundos_ate_poder_finalizar(),
        "avaliacao": chamado.avaliacao,
        "comentario_avaliacao": chamado.comentario_avaliacao,
    }

    if incluir_prioridade:
        prioridade = calcular_prioridade(chamado)
        dados["prioridade"] = prioridade["tier"]
        dados["prioridade_label"] = prioridade["tier_label"]
        dados["prioridade_emoji"] = prioridade["tier_emoji"]
        dados["prioridade_score"] = prioridade["score"]
        dados["tempo_espera_min"] = prioridade["tempo_espera_min"]
        dados["sla_min"] = prioridade["sla_min"]
        dados["acima_do_tempo_esperado"] = excedeu_sla(prioridade["tier"], prioridade["tempo_espera_min"])

    return dados
