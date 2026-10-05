# -*- coding: utf-8 -*-
"""Dados fixos do Chamador de Enfermagem: leitos, categorias e subopções.

A ordem das CATEGORIAS abaixo é a ordem exigida pela especificação e é
preservada em toda a interface (tela do paciente, filtros, relatórios):
  1. Urgência
  2. Dor
  3. Soro
  4. Falar com enfermagem
  5. Outros

Cada subopção carrega um peso de "gravidade" (0-100) usado pelo motor de
prioridade (ver enfermagem/priority.py). Esses pesos são uma priorização
OPERACIONAL — ajudam a equipe a decidir o que atender primeiro — e nunca
substituem o julgamento clínico do profissional de enfermagem.

A categoria "Outros" não tem fila própria: qualquer chamado registrado
nela é encaminhado imediatamente para a Central de Hotelaria (ver
enfermagem/api.py) e nunca entra na fila/priorização da enfermagem.
"""

# ---------------------------------------------------------------------------
# Andares e leitos — agora definidos em `andares.py` (raiz do projeto), pois
# a Hotelaria também passou a usá-los (seletor Andar → Leito unificado entre
# os dois módulos, em vez de leito digitado livremente). Reexportados aqui
# para não quebrar nenhum import já existente (`from enfermagem.constants
# import ANDARES, leito_valido`) no restante do código.
# ---------------------------------------------------------------------------
from andares import ANDARES, leito_valido, andar_label  # noqa: F401


# ---------------------------------------------------------------------------
# Categorias e subopções — fila de enfermagem (Urgência, Dor, Soro, Falar)
# ---------------------------------------------------------------------------
# Cada entrada de "opcoes": (texto, gravidade)
CATEGORIAS = {
    "Urgência": {
        "chave": "urgencia",
        "icone": "urgencia",
        "cor": "critica",
        "descricao": "Situações que exigem atendimento imediato.",
        "opcoes": [
            ("Não consigo respirar bem", 100),
            ("Sangramento intenso", 98),
            ("Queda ou acidente no quarto", 95),
            ("Confusão mental ou desmaio", 96),
            ("Dor súbita e muito intensa", 92),
            ("Outra emergência", 90),
        ],
    },
    "Dor": {
        "chave": "dor",
        "icone": "dor",
        "cor": "critica",
        "descricao": "Toque no rosto que mostra como você está se sentindo.",
        # A ordem aqui vai do MAIS grave para o MENOS grave — a UI do paciente
        # renderiza uma escala visual (rostos + cores) usando essa mesma ordem
        # e o campo `gravidade` para escolher o ícone/cor de cada opção.
        "opcoes": [
            ("Dor no peito", 88),
            ("Dor muito forte", 87),
            ("Dor moderada", 86),
            ("Dor leve", 85),
        ],
    },
    "Soro": {
        "chave": "soro",
        "icone": "soro",
        "cor": "media",
        "descricao": "Problemas com o soro ou com o acesso venoso.",
        "opcoes": [
            ("Está retornando sangue", 75),
            ("Problema no acesso", 65),
            ("Acabou", 55),
            ("Está perto do fim", 20),
            ("Outro problema", 40),
        ],
    },
    "Falar com Enfermagem": {
        "chave": "falar_enfermagem",
        "icone": "falar",
        "cor": "baixa",
        "descricao": "Dúvidas ou assuntos gerais com a equipe.",
        "opcoes": [
            ("Dúvida sobre medicação", 30),
            ("Dúvida sobre procedimento ou alta", 25),
            ("Preciso de orientação", 25),
            ("Assunto geral", 20),
        ],
    },
    "Outros": {
        "chave": "outros",
        "icone": "outros",
        "cor": "hotelaria",
        "descricao": "Hotelaria, nutrição, lavanderia, manutenção e higienização.",
        # Cada subopção de "Outros" é mapeada 1:1 para um serviço já existente
        # na Central de Hotelaria (hotelaria/models.py::SERVICOS). Nenhum
        # chamado desta categoria entra na fila de enfermagem.
        "opcoes": [
            ("Acomodação (cama, travesseiro, TV, ar-condicionado)", "hotelaria"),
            ("Alimentação", "nutricao"),
            ("Roupa de cama / Enxoval", "lavanderia"),
            ("Manutenção do quarto", "manutencao"),
            ("Limpeza do quarto ou banheiro", "higienizacao"),
        ],
    },
}

CATEGORIAS_ORDEM = list(CATEGORIAS.keys())
CATEGORIA_OUTROS = "Outros"


def categoria_valida(categoria):
    return categoria in CATEGORIAS


def opcoes_categoria(categoria):
    return CATEGORIAS.get(categoria, {}).get("opcoes", [])


def opcao_valida(categoria, subopcao):
    return any(texto == subopcao for texto, _peso in opcoes_categoria(categoria))


def gravidade_da_opcao(categoria, subopcao):
    """Gravidade base (0-100) da subopção escolhida. Não se aplica à
    categoria 'Outros', que não tem gravidade de enfermagem."""
    for texto, peso in opcoes_categoria(categoria):
        if texto == subopcao:
            return peso
    return 0


def servico_hotelaria_da_opcao(subopcao):
    """Para a categoria 'Outros': devolve a chave do serviço de Hotelaria
    correspondente à subopção escolhida pelo paciente."""
    for texto, servico in opcoes_categoria(CATEGORIA_OUTROS):
        if texto == subopcao:
            return servico
    return None


# ---------------------------------------------------------------------------
# Status e prioridade
# ---------------------------------------------------------------------------
STATUS_PENDENTE = "pendente"
STATUS_EM_ATENDIMENTO = "em_atendimento"
STATUS_FINALIZADO = "finalizado"

STATUS_LABELS = {
    STATUS_PENDENTE: "Pendente",
    STATUS_EM_ATENDIMENTO: "Em atendimento",
    STATUS_FINALIZADO: "Finalizado",
}

PRIORIDADES = ["critica", "media", "baixa"]

PRIORIDADE_LABELS = {
    "critica": "Crítico",
    "media": "Médio",
    "baixa": "Baixo",
}

PRIORIDADE_EMOJI = {
    "critica": "🔴",
    "media": "🟡",
    "baixa": "🟢",
}
