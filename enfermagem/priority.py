# -*- coding: utf-8 -*-
"""Motor de prioridade do Chamador de Enfermagem.

A prioridade de um chamado é definida SOMENTE pela gravidade da subopção
escolhida pelo paciente (0-100), definida em enfermagem/constants.py —
ex.: "Dor no peito" pesa mais que "Dor leve". Essa gravidade é recalculada
(na verdade, apenas relida) a cada consulta, nunca fica "congelada" de
outra forma no banco além do campo `gravidade_base` do próprio chamado.

O resultado é convertido em uma das três faixas exigidas pela especificação:
🔴 CRÍTICO, 🟡 MÉDIO, 🟢 BAIXO — ver `LIMIAR_CRITICA_BASE` e `LIMIAR_MEDIA`.

Esta pontuação é uma priorização OPERACIONAL da fila de atendimento. Ela
nunca substitui a avaliação clínica da equipe de enfermagem.
"""
from enfermagem.constants import (
    PRIORIDADE_LABELS, PRIORIDADE_EMOJI, CATEGORIA_OUTROS,
)

# ---------------------------------------------------------------------------
# Parâmetros do algoritmo (ajustáveis conforme protocolo do hospital)
# ---------------------------------------------------------------------------
# Piso de gravidade a partir do qual um chamado é considerado CRÍTICO. Cobre
# toda a categoria "Urgência" (90-100) e "Dor no peito" (88, possível sinal
# cardíaco).
LIMIAR_CRITICA_BASE = 85
LIMIAR_MEDIA = 40

# ---------------------------------------------------------------------------
# Meta operacional de tempo de espera (SLA) por faixa de prioridade — em
# minutos, desde a criação do chamado até o início do atendimento. É uma
# meta de GESTÃO DA FILA (ajuda a equipe a enxergar o que já está atrasado),
# não uma diretriz clínica; ajustável pelo hospital conforme seu protocolo.
# Usada para o indicador "chamados acima do tempo esperado" dos dashboards e
# para o destaque "Atenção imediata" da Central.
# ---------------------------------------------------------------------------
SLA_MINUTOS = {
    "critica": 10,
    "media": 20,
    "baixa": 40,
}

# Tempo mínimo (em segundos) de atendimento: depois que o profissional
# assume o chamado, ele só pode finalizá-lo após esse intervalo.
TEMPO_MINIMO_ATENDIMENTO_SEG = 120

# Categorias cujos chamados são SEMPRE de alta criticidade, qualquer que
# seja a subopção escolhida (ex.: toda "Dor" é Alta).
CATEGORIAS_SEMPRE_CRITICAS = ("Dor",)


def excedeu_sla(tier, tempo_espera_min):
    """True se `tempo_espera_min` já ultrapassa a meta de tempo da faixa de
    prioridade `tier`. `tempo_espera_min` deve ser o tempo até o início do
    atendimento (ou o tempo de espera corrente, se ainda pendente) — nunca o
    tempo total incluindo o atendimento em si."""
    limite = SLA_MINUTOS.get(tier)
    if limite is None or tempo_espera_min is None:
        return False
    return tempo_espera_min > limite


def _tier(gravidade_base, categoria=None):
    if categoria in CATEGORIAS_SEMPRE_CRITICAS or gravidade_base >= LIMIAR_CRITICA_BASE:
        return "critica"
    if gravidade_base >= LIMIAR_MEDIA:
        return "media"
    return "baixa"


def calcular_prioridade(chamado, referencia=None):
    """Calcula a prioridade de um chamado (pendente, em atendimento ou já
    finalizado — usado no histórico para mostrar a faixa que ele atingiu).

    chamado: instância de ChamadoEnfermagem.
    referencia: datetime usado como "agora" para calcular o tempo de
        espera. Por padrão: agora() para chamados ativos, ou o horário em
        que o chamado foi assumido/finalizado para chamados já concluídos
        (assim o histórico mostra o tempo de espera real até o
        atendimento, sem continuar contando depois disso).
    """
    from timeutils import agora, duracao_minutos

    if chamado.categoria == CATEGORIA_OUTROS:
        # Nunca deveria acontecer (Outros não entra na fila de enfermagem),
        # mas devolvemos algo seguro em vez de estourar um erro.
        return {"score": 0, "tier": "baixa", "tempo_espera_min": 0}

    if referencia is None:
        if chamado.status == "finalizado":
            referencia = chamado.inicio_atendimento or chamado.finalizado_em or agora()
        elif chamado.status == "em_atendimento":
            referencia = chamado.inicio_atendimento or agora()
        else:
            referencia = agora()

    tempo_espera_min = duracao_minutos(chamado.criado_em, referencia) or 0.0

    score = float(chamado.gravidade_base)
    tier = _tier(chamado.gravidade_base, chamado.categoria)

    return {
        "score": score,
        "tier": tier,
        "tier_label": PRIORIDADE_LABELS[tier],
        "tier_emoji": PRIORIDADE_EMOJI[tier],
        "tempo_espera_min": round(tempo_espera_min, 1),
        "sla_min": SLA_MINUTOS.get(tier),
    }
