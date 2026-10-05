# -*- coding: utf-8 -*-
"""Central de Hotelaria — dados fixos e serialização (SQLite puro).

Preservado do projeto original `hospital_rio_grande-main`, adaptado de
SQLAlchemy para SQLite puro (mesma técnica já usada no restante do
projeto) e com um serviço novo, "outros", usado exclusivamente para
receber solicitações encaminhadas pelo Chamador de Enfermagem quando o
paciente escolhe a opção "OUTROS".
"""
import re

from timeutils import parse_dt, formata_data_br, formata_hora, duracao_minutos, agora

SERVICOS = {
    "hotelaria": {
        "nome": "Hotelaria",
        "descricao": "Acomodação do paciente: poltrona, colchão, mezanino, controles de ar-condicionado e TV, e outros itens do quarto.",
        "icone": "bed",
    },
    "nutricao": {
        "nome": "Nutrição",
        "descricao": "Alimentação: visita da nutricionista, troca de refeição/lanche, alimentação seletiva e reclamações.",
        "icone": "utensils",
    },
    "lavanderia": {
        "nome": "Lavanderia",
        "descricao": "Enxoval: travesseiro, lençol e enxovais em geral.",
        "icone": "shirt",
    },
    "manutencao": {
        "nome": "Manutenção",
        "descricao": "Infraestrutura: chuveiro quente, iluminação, ar-condicionado e problemas hidráulicos.",
        "icone": "wrench",
    },
    "higienizacao": {
        "nome": "Higienização",
        "descricao": "Limpeza e desinfecção: limpeza de quarto e banheiro, reposição de papel higiênico e sabonete.",
        "icone": "limpeza",
    },
    "outros": {
        "nome": "Solicitação geral",
        "descricao": "Solicitações diversas encaminhadas pelo Chamador de Enfermagem (opção \"Outros\").",
        "icone": "help-circle",
    },
}

# Meta de tempo de espera (SLA) de TODOS os chamados da Hotelaria: minutos
# desde a abertura até a equipe assumir o chamado. Mesmo papel das metas por
# prioridade da Enfermagem (enfermagem/priority.py::SLA_MINUTOS) — a
# Hotelaria não tem faixas de prioridade, então a meta é única.
META_ESPERA_MIN = 30

STATUS_PENDENTE = "pendente"
STATUS_ANDAMENTO = "em_andamento"
STATUS_FINALIZADO = "finalizado"

CONFIRMACAO_PENDENTE = "pendente"
CONFIRMACAO_RESOLVIDO = "resolvido"
CONFIRMACAO_NAO_RESOLVIDO = "nao_resolvido"
CONFIRMACAO_EXPIRADA = "expirada"
CONFIRMACAO_NA = "nao_aplicavel"


def servico_nome(servico):
    return SERVICOS.get(servico, {}).get("nome", servico)


# Chamados encaminhados automaticamente pelo Chamador de Enfermagem gravam a
# descrição já com o prefixo "Encaminhado pelo Chamador de Enfermagem ·
# <andar>, Leito <leito> · " (ver enfermagem/api.py) — era assim que a
# origem e o local apareciam nos cartões antes de leito/andar virarem campos
# próprios em destaque no cartão. Hoje esse prefixo só repete informação que
# já aparece em local separado, então é removido na exibição (o texto bruto
# continua salvo no banco, sem perda de histórico).
_RE_PREFIXO_ENCAMINHADO = re.compile(r"^Encaminhado pelo Chamador de Enfermagem · [^·]+ · ")


def descricao_exibicao(descricao):
    """Versão enxuta da descrição para os cartões: só a solicitação em si,
    sem repetir origem/andar/leito que já aparecem em destaque à parte."""
    if not descricao:
        return descricao
    return _RE_PREFIXO_ENCAMINHADO.sub("", descricao, count=1)


def chamado_to_dict(row, mensagens=None, avaliacao_row=None, nao_lida=None):
    """`row`: linha de hotelaria_chamados. `mensagens`: lista opcional de
    linhas de hotelaria_mensagens já serializadas (mensagem_to_dict).
    `avaliacao_row`: linha opcional de hotelaria_avaliacoes.
    `nao_lida`: bool pré-calculado (evita reconsultar mensagens quando o
    chamador já as tem em mãos)."""
    finalizado_em = parse_dt(row["finalizado_em"])
    criado_em = parse_dt(row["criado_em"])
    iniciado_em = parse_dt(row["iniciado_em"])
    tempo_atendimento = duracao_minutos(criado_em, finalizado_em) if finalizado_em else None
    # Tempo de espera = da abertura até ser assumido (ou até agora, se ainda
    # pendente) — mesma definição da Enfermagem; não inclui o atendimento.
    fim_espera = iniciado_em or finalizado_em or agora()
    tempo_espera = duracao_minutos(criado_em, fim_espera) if criado_em else None

    dados = {
        "id": row["id"],
        "leito": row["leito"],
        "andar": row["andar"] if "andar" in row.keys() else None,
        "servico": row["servico"],
        "servico_nome": servico_nome(row["servico"]),
        "descricao": row["descricao"],
        "descricao_exibicao": descricao_exibicao(row["descricao"]),
        "status": row["status"],
        "origem": row["origem"],
        "criado_em": formata_data_br(criado_em),
        "iniciado_em": formata_data_br(parse_dt(row["iniciado_em"])),
        "finalizado_em": formata_data_br(finalizado_em),
        "confirmacao_resolucao": row["confirmacao_resolucao"],
        "prazo_confirmacao": row["prazo_confirmacao"],
        "tem_avaliacao": avaliacao_row is not None,
        "nao_lida": bool(nao_lida) if nao_lida is not None else False,
        "nao_resolvido": row["status"] != STATUS_FINALIZADO,
        "tempo_atendimento_min": tempo_atendimento,
        "tempo_espera_min": tempo_espera,
        "sla_min": META_ESPERA_MIN,
        "acima_do_tempo_esperado": tempo_espera is not None and tempo_espera > META_ESPERA_MIN,
    }
    if mensagens is not None:
        dados["mensagens"] = mensagens
    if avaliacao_row is not None:
        dados["avaliacao"] = avaliacao_to_dict(avaliacao_row)
    return dados


def mensagem_to_dict(row):
    criado_em = parse_dt(row["criado_em"])
    return {
        "id": row["id"],
        "chamado_id": row["chamado_id"],
        "remetente": row["remetente"],
        "mensagem": row["mensagem"],
        "criado_em": formata_hora(criado_em),
        "criado_em_data": criado_em.strftime("%d/%m/%Y") if criado_em else None,
        "lida_central": bool(row["lida_central"]),
    }


def avaliacao_to_dict(row):
    return {
        "id": row["id"],
        "chamado_id": row["chamado_id"],
        "estrelas": row["estrelas"],
        "comentario": row["comentario"],
        "criado_em": formata_data_br(parse_dt(row["criado_em"])),
    }
