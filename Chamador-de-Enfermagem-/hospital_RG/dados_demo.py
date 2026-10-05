# -*- coding: utf-8 -*-
"""Dados fictícios de demonstração — Enfermagem E Hotelaria.

Popula o banco com ~60 dias de histórico realista (volumes por dia da
semana e hora, prioridades, tempos de espera/atendimento, avaliações,
comentários, mensagens da Hotelaria, encaminhamentos "Outros") mais um
conjunto de chamados ATIVOS agora (pendentes e em atendimento, alguns já
acima do tempo esperado) — para que todas as telas (Central, Histórico,
Dashboards) mostrem uma experiência completa.

Regras:
  • NUNCA apaga nada — só insere.
  • Na inicialização do app (`db.init_db`) só roda se as duas tabelas de
    chamados estiverem VAZIAS (ex.: primeira execução, ou após um reinício
    do Render Free, que perde o arquivo .db). Desligue com DADOS_DEMO=0.
  • Nenhum dado pessoal de paciente: como no resto do sistema, a única
    identificação é andar + leito.

Uso manual (na pasta hospital_rio_grande):
    python dados_demo.py            # popula só se o banco estiver vazio
    python dados_demo.py --ativos   # acrescenta um novo lote de chamados
                                    # ativos "de agora" (sem apagar nada)
"""
import random
from datetime import timedelta

from andares import ANDARES
from timeutils import agora, para_texto

DIAS_HISTORICO = 60

# ---------------------------------------------------------------------------
# Enfermagem — (categoria, subcategoria, gravidade, peso de sorteio)
# Gravidades idênticas às de enfermagem/constants.py.
# ---------------------------------------------------------------------------
_OPCOES_ENF = [
    ("Urgência", "Não consigo respirar bem", 100, 1.6),
    ("Urgência", "Sangramento intenso", 98, 0.9),
    ("Urgência", "Queda ou acidente no quarto", 95, 1.3),
    ("Urgência", "Confusão mental ou desmaio", 96, 1.0),
    ("Urgência", "Dor súbita e muito intensa", 92, 1.2),
    ("Urgência", "Outra emergência", 90, 0.7),
    ("Dor", "Dor no peito", 88, 2.2),
    ("Dor", "Dor muito forte", 87, 6.0),
    ("Dor", "Dor moderada", 86, 10.0),
    ("Dor", "Dor leve", 85, 7.5),
    ("Soro", "Está retornando sangue", 75, 3.4),
    ("Soro", "Problema no acesso", 65, 5.8),
    ("Soro", "Acabou", 55, 10.2),
    ("Soro", "Está perto do fim", 20, 7.4),
    ("Soro", "Outro problema", 40, 2.4),
    ("Falar com Enfermagem", "Dúvida sobre medicação", 30, 12.0),
    ("Falar com Enfermagem", "Dúvida sobre procedimento ou alta", 25, 8.6),
    ("Falar com Enfermagem", "Preciso de orientação", 25, 8.2),
    ("Falar com Enfermagem", "Assunto geral", 20, 5.0),
]

_DETALHES_ENF = {
    "Urgência": ["Paciente muito ofegante", "Caiu ao levantar para o banheiro", "Sangramento no curativo",
                 "Está muito confuso e sonolento", "Chamem rápido, por favor"],
    "Dor": ["Dor na região da cirurgia", "Dor de cabeça forte", "Dor nas costas desde a madrugada",
            "A medicação não fez efeito", "Dor na barriga", "Dor no local do acesso"],
    "Soro": ["Bomba de infusão apitando", "Braço inchado perto da agulha", "Equipo com bolhas de ar",
             "O esparadrapo soltou", "Sangue subindo pelo equipo"],
}

_COMENTARIOS_ENF = {
    5: ["Equipe muito atenciosa, chegaram rápido!", "Atendimento excelente, obrigado.", "Enfermeira muito carinhosa.",
        "Resolveram na hora.", "Nota 10 para o plantão da noite."],
    4: ["Bom atendimento, só demorou um pouco.", "Gostei, foram educados.", "Atendimento bom."],
    3: ["Demorou mais do que eu esperava.", "Razoável, poderiam explicar melhor."],
    2: ["Esperei bastante tempo com dor.", "Demora grande para trocar o soro."],
    1: ["Ninguém veio por muito tempo.", "Precisei chamar duas vezes."],
}

# Tempo até assumir (min) e tempo de atendimento (min) por faixa/categoria.
_ESPERA_FAIXA = {"critica": (1.5, 11, 0.08, 16, 28), "media": (4, 34, 0.14, 41, 75), "baixa": (8, 70, 0.10, 91, 150)}
_ATENDIMENTO_CAT = {"Urgência": (14, 48), "Dor": (6, 24), "Soro": (4, 16), "Falar com Enfermagem": (3, 14)}

# ---------------------------------------------------------------------------
# Hotelaria — serviço: (peso, textos do paciente, (espera min/máx), (atendimento min/máx))
# ---------------------------------------------------------------------------
_SERVICOS_HOT = {
    "hotelaria": (2.6, ["Controle da TV não funciona", "Ar-condicionado muito frio, não consigo ajustar",
                        "Preciso de mais um travesseiro para o acompanhante", "Poltrona do acompanhante quebrada",
                        "Colchão desconfortável, pode trocar?"], (5, 35), (8, 30)),
    "nutricao": (3.0, ["Gostaria de trocar o jantar", "Sou diabético, a refeição veio com açúcar",
                       "Pedido de visita da nutricionista", "O lanche da tarde não chegou",
                       "Posso receber a dieta pastosa?"], (4, 30), (10, 40)),
    "lavanderia": (2.0, ["Troca de lençol, por favor", "Precisamos de toalhas limpas",
                         "Cobertor extra para a noite", "Roupa de cama molhada"], (6, 40), (8, 25)),
    "manutencao": (1.6, ["Chuveiro sem água quente", "Lâmpada do banheiro queimada", "Vaso sanitário vazando",
                         "Tomada perto da cama não funciona", "Janela não fecha direito"], (10, 60), (20, 95)),
    "higienizacao": (2.2, ["Limpeza do banheiro, por favor", "Acabou o papel higiênico",
                           "Derramou suco no chão", "Reposição de sabonete", "Lixo do quarto cheio"], (5, 30), (10, 35)),
}

# Opções "Outros" da Enfermagem → serviço (mesmo mapa de enfermagem/constants.py).
_OUTROS_PARA_SERVICO = {
    "hotelaria": "Acomodação (cama, travesseiro, TV, ar-condicionado)",
    "nutricao": "Alimentação",
    "lavanderia": "Roupa de cama / Enxoval",
    "manutencao": "Manutenção do quarto",
    "higienizacao": "Limpeza do quarto ou banheiro",
}

_COMENTARIOS_HOT = {
    5: ["Muito rápido, obrigado!", "Equipe de limpeza excelente.", "Resolveram o chuveiro na hora."],
    4: ["Bom serviço.", "Atenderam bem, só demorou um pouco."],
    3: ["Demorou, mas resolveram.", "Ok."],
    2: ["Demorou demais para trocar a roupa de cama."],
    1: ["O problema continuou.", "Ninguém apareceu por horas."],
}

_MSG_CENTRAL = ["Olá! Já recebemos sua solicitação.", "A equipe está a caminho.",
                "Pode confirmar se o problema continua?", "Já estamos providenciando, só um instante."]
_MSG_PACIENTE = ["Obrigado!", "Ainda não chegou ninguém.", "Tudo certo agora.", "Pode ser o mais rápido possível?"]

# Distribuição de demanda por hora do dia (picos em troca de plantão,
# refeições e início da noite).
_PESO_HORA_ENF = [2, 1.4, 1.1, 1, 1.1, 1.6, 3.2, 5.4, 6.2, 5.5, 4.8, 4.6, 5.2, 4.4, 4.1, 4.3, 4.6, 5.1,
                  5.6, 6.3, 6.1, 5.2, 3.9, 2.8]
_PESO_HORA_HOT = [0.3, 0.2, 0.1, 0.1, 0.1, 0.3, 1.2, 3.2, 4.8, 5.2, 5.0, 5.6, 6.2, 4.8, 4.2, 4.0, 4.3, 4.8,
                  5.5, 5.2, 4.2, 2.8, 1.4, 0.6]
_PESO_ANDAR = {"1º ANDAR — ONCOLOGIA": 0.9, "5º ANDAR — LEITOS": 1.25, "3º ANDAR — LEITOS": 1.0}


def _escolher(rng, pares):
    total = sum(p for _, p in pares)
    alvo = rng.uniform(0, total)
    acumulado = 0
    for item, peso in pares:
        acumulado += peso
        if alvo <= acumulado:
            return item
    return pares[-1][0]


def _leito_aleatorio(rng, leitos_quentes):
    # ~30% dos chamados vêm de um pequeno grupo de leitos "reincidentes"
    # (pacientes que chamam muito) — deixa a distribuição por leito mais realista.
    if rng.random() < 0.3:
        return rng.choice(leitos_quentes)
    andar = _escolher(rng, list(_PESO_ANDAR.items()))
    return andar, rng.choice(ANDARES[andar])


def _tier(gravidade, categoria=None):
    if gravidade >= 85 or categoria == "Dor":
        return "critica"
    if gravidade >= 40:
        return "media"
    return "baixa"


def _nota(rng, atrasou):
    if atrasou:
        return _escolher(rng, [(5, 1.5), (4, 2.5), (3, 3), (2, 2), (1, 1)])
    return _escolher(rng, [(5, 6.5), (4, 2.6), (3, 0.6), (2, 0.2), (1, 0.1)])


def _horario_no_dia(rng, dia, pesos):
    hora = _escolher(rng, list(enumerate(pesos)))
    return dia + timedelta(hours=hora, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))


def _gerar_enfermagem(rng, criado, andar, leito, opcao=None, estado=None, agora_ref=None):
    """Monta a tupla de colunas de um chamado de enfermagem. `estado`
    força o status (usado nos cenários ativos); caso contrário, o status é
    deduzido comparando os horários sorteados com `agora_ref`."""
    categoria, subcategoria, gravidade = opcao or _escolher(rng, [((c, s, g), p) for c, s, g, p in _OPCOES_ENF])
    tier = _tier(gravidade, categoria)
    base_min, base_max, prob_atraso, atraso_min, atraso_max = _ESPERA_FAIXA[tier]
    # Madrugada: equipe reduzida, espera um pouco maior.
    fator = 1.25 if criado.hour < 6 else 1.0
    if rng.random() < prob_atraso:
        espera = rng.uniform(atraso_min, atraso_max) * fator
    else:
        espera = rng.uniform(base_min, base_max) * fator
    at_min, at_max = _ATENDIMENTO_CAT[categoria]
    atendimento = rng.uniform(at_min, at_max)

    detalhe = None
    if categoria in _DETALHES_ENF and rng.random() < 0.3:
        detalhe = rng.choice(_DETALHES_ENF[categoria])

    inicio = criado + timedelta(minutes=espera)
    fim = inicio + timedelta(minutes=atendimento)

    if estado is None:
        if fim <= agora_ref:
            estado = "finalizado"
        elif inicio <= agora_ref:
            estado = "em_atendimento"
        else:
            estado = "pendente"

    avaliacao = comentario = None
    if estado == "pendente":
        inicio = fim = None
    elif estado == "em_atendimento":
        fim = None
    else:
        sla = {"critica": 10, "media": 20, "baixa": 40}[tier]
        if rng.random() < 0.62:
            avaliacao = _nota(rng, espera > sla)
            if rng.random() < 0.35:
                comentario = rng.choice(_COMENTARIOS_ENF[avaliacao])

    return (
        andar, leito, categoria, subcategoria, detalhe, gravidade, estado,
        "enfermagem" if estado != "pendente" else None,
        para_texto(criado), para_texto(inicio), para_texto(fim), avaliacao, comentario,
    )


_SQL_ENF = """INSERT INTO enfermagem_chamados
    (andar, leito, categoria, subcategoria, detalhe, gravidade_base, status, profissional_responsavel,
     criado_em, inicio_atendimento, finalizado_em, avaliacao, comentario_avaliacao)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

_SQL_HOT = """INSERT INTO hotelaria_chamados
    (leito, servico, descricao, status, origem, criado_em, iniciado_em, finalizado_em,
     confirmacao_resolucao, prazo_confirmacao, andar)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def _inserir_hotelaria(conn, rng, criado, andar, leito, agora_ref, servico=None, estado=None, origem=None):
    servico = servico or _escolher(rng, [(k, v[0]) for k, v in _SERVICOS_HOT.items()])
    _peso, textos, (esp_min, esp_max), (at_min, at_max) = _SERVICOS_HOT[servico]
    origem = origem or ("enfermagem" if rng.random() < 0.26 else "hotelaria")
    if origem == "enfermagem":
        descricao = _OUTROS_PARA_SERVICO[servico]
        if rng.random() < 0.5:
            descricao += f" — {rng.choice(textos)}"
    else:
        descricao = rng.choice(textos)

    espera = rng.uniform(esp_min, esp_max) * (1.6 if rng.random() < 0.1 else 1.0)
    iniciado = criado + timedelta(minutes=espera)
    fim = iniciado + timedelta(minutes=rng.uniform(at_min, at_max))

    if estado is None:
        if fim <= agora_ref:
            estado = "finalizado"
        elif iniciado <= agora_ref:
            estado = "em_andamento"
        else:
            estado = "pendente"

    confirmacao, prazo = "nao_aplicavel", None
    if estado == "pendente":
        iniciado = fim = None
    elif estado == "em_andamento":
        fim = None
    else:
        prazo = fim + timedelta(minutes=30)
        if prazo > agora_ref:
            confirmacao = "pendente"
        else:
            confirmacao = _escolher(rng, [("expirada", 6.8), ("resolvido", 2.6), ("nao_resolvido", 0.6)])

    cur = conn.execute(_SQL_HOT, (
        leito, servico, descricao, estado, origem, para_texto(criado), para_texto(iniciado),
        para_texto(fim), confirmacao, para_texto(prazo), andar,
    ))
    chamado_id = cur.lastrowid

    # Conversa com a Central em parte dos chamados (a Central mostra o
    # histórico e o selo de "não lida").
    if rng.random() < (0.55 if estado != "finalizado" else 0.14):
        momento = criado + timedelta(minutes=rng.uniform(1, 4))
        for i in range(rng.randint(1, 3)):
            remetente = "central" if i % 2 == 0 else "paciente"
            texto = rng.choice(_MSG_CENTRAL if remetente == "central" else _MSG_PACIENTE)
            if momento > agora_ref:
                break
            conn.execute(
                "INSERT INTO hotelaria_mensagens (chamado_id, remetente, mensagem, criado_em, lida_central) VALUES (?, ?, ?, ?, ?)",
                (chamado_id, remetente, texto, para_texto(momento), 1 if estado == "finalizado" or remetente == "central" else 0),
            )
            momento += timedelta(minutes=rng.uniform(2, 9))

    if estado == "finalizado" and rng.random() < 0.48:
        estrelas = _nota(rng, espera > 45)
        comentario = rng.choice(_COMENTARIOS_HOT[estrelas]) if rng.random() < 0.4 else None
        conn.execute(
            "INSERT INTO hotelaria_avaliacoes (chamado_id, estrelas, comentario, criado_em) VALUES (?, ?, ?, ?)",
            (chamado_id, estrelas, comentario, para_texto(min(fim + timedelta(minutes=rng.uniform(2, 25)), agora_ref))),
        )
    return chamado_id


def _lote_ativos(conn, rng, agora_ref):
    """Cenários ativos "de agora", garantindo variedade na Central e nos
    alertas: críticos dentro/fora do tempo esperado, médios e baixos
    atrasados, atendimentos em andamento e pedidos da Hotelaria."""
    opc = {s: (c, s, g) for c, s, g, _p in _OPCOES_ENF}
    cenarios_enf = [
        # (subcategoria, minutos atrás, status, andar, leito)
        ("Não consigo respirar bem", 3, "pendente", "5º ANDAR — LEITOS", "507 A"),
        ("Dor no peito", 19, "pendente", "3º ANDAR — LEITOS", "315 A"),
        ("Queda ou acidente no quarto", 9, "em_atendimento", "1º ANDAR — ONCOLOGIA", "110 A"),
        ("Sangramento intenso", 6, "em_atendimento", "5º ANDAR — LEITOS", "511 A"),
        ("Está retornando sangue", 47, "pendente", "5º ANDAR — LEITOS", "502 A"),
        ("Problema no acesso", 22, "pendente", "3º ANDAR — LEITOS", "320"),
        ("Acabou", 12, "pendente", "1º ANDAR — ONCOLOGIA", "103 A"),
        ("Dor muito forte", 55, "pendente", "5º ANDAR — LEITOS", "505 A"),
        ("Dor moderada", 16, "em_atendimento", "3º ANDAR — LEITOS", "316 A"),
        ("Está perto do fim", 8, "pendente", "1º ANDAR — ONCOLOGIA", "107 A"),
        ("Dúvida sobre medicação", 96, "pendente", "3º ANDAR — LEITOS", "312"),
        ("Preciso de orientação", 31, "pendente", "5º ANDAR — LEITOS", "509 A"),
        ("Dúvida sobre procedimento ou alta", 14, "em_atendimento", "1º ANDAR — ONCOLOGIA", "105 A"),
        ("Assunto geral", 4, "pendente", "3º ANDAR — LEITOS", "318"),
    ]
    for sub, min_atras, estado, andar, leito in cenarios_enf:
        criado = agora_ref - timedelta(minutes=min_atras, seconds=rng.randint(0, 50))
        valores = list(_gerar_enfermagem(rng, criado, andar, leito, opcao=opc[sub], estado=estado, agora_ref=agora_ref))
        if estado == "em_atendimento":
            # Assumido há pouco, depois de uma espera coerente.
            valores[9] = para_texto(criado + timedelta(minutes=min(min_atras * 0.4, 12)))
        conn.execute(_SQL_ENF, valores)

    cenarios_hot = [
        ("manutencao", 74, "pendente", "5º ANDAR — LEITOS", "504 A", "hotelaria"),
        ("nutricao", 18, "pendente", "3º ANDAR — LEITOS", "313", "enfermagem"),
        ("higienizacao", 7, "pendente", "1º ANDAR — ONCOLOGIA", "101 A", "hotelaria"),
        ("lavanderia", 26, "em_andamento", "5º ANDAR — LEITOS", "510 A", "hotelaria"),
        ("hotelaria", 41, "pendente", "3º ANDAR — LEITOS", "314", "enfermagem"),
        ("manutencao", 35, "em_andamento", "1º ANDAR — ONCOLOGIA", "108 A", "hotelaria"),
        ("nutricao", 5, "pendente", "5º ANDAR — LEITOS", "512 A", "hotelaria"),
        ("higienizacao", 22, "em_andamento", "3º ANDAR — LEITOS", "319", "enfermagem"),
    ]
    for servico, min_atras, estado, andar, leito, origem in cenarios_hot:
        criado = agora_ref - timedelta(minutes=min_atras, seconds=rng.randint(0, 50))
        chamado_id = _inserir_hotelaria(conn, rng, criado, andar, leito, agora_ref, servico=servico, estado=estado, origem=origem)
        if estado == "em_andamento":
            conn.execute("UPDATE hotelaria_chamados SET iniciado_em = ? WHERE id = ?",
                         (para_texto(criado + timedelta(minutes=min_atras * 0.45)), chamado_id))


def banco_vazio(conn):
    enf = conn.execute("SELECT COUNT(*) FROM enfermagem_chamados").fetchone()[0]
    hot = conn.execute("SELECT COUNT(*) FROM hotelaria_chamados").fetchone()[0]
    return enf == 0 and hot == 0


def popular(conn, semente=2026):
    """Insere o histórico completo + o lote de chamados ativos. Não apaga
    nada; quem chama decide se deve rodar (ver `popular_se_vazio`)."""
    rng = random.Random(semente)
    agora_ref = agora()
    hoje = agora_ref.replace(hour=0, minute=0, second=0, microsecond=0)
    leitos_quentes = [("5º ANDAR — LEITOS", "505 A"), ("5º ANDAR — LEITOS", "508 A"), ("3º ANDAR — LEITOS", "315 A"),
                      ("1º ANDAR — ONCOLOGIA", "103 A"), ("3º ANDAR — LEITOS", "321"), ("5º ANDAR — LEITOS", "511 A")]

    for dias_atras in range(DIAS_HISTORICO, -1, -1):
        dia = hoje - timedelta(days=dias_atras)
        fim_de_semana = dia.weekday() >= 5
        # Leve tendência de alta ao longo das semanas + sazonalidade semanal.
        tendencia = 1 + (DIAS_HISTORICO - dias_atras) * 0.004
        n_enf = int(rng.gauss(17, 3) * tendencia * (0.82 if fim_de_semana else 1))
        n_hot = int(rng.gauss(9, 2) * tendencia * (1.12 if fim_de_semana else 1))

        for _ in range(max(n_enf, 4)):
            criado = _horario_no_dia(rng, dia, _PESO_HORA_ENF)
            if criado >= agora_ref - timedelta(minutes=2):
                continue
            andar, leito = _leito_aleatorio(rng, leitos_quentes)
            valores = _gerar_enfermagem(rng, criado, andar, leito, agora_ref=agora_ref)
            conn.execute(_SQL_ENF, valores)

        for _ in range(max(n_hot, 2)):
            criado = _horario_no_dia(rng, dia, _PESO_HORA_HOT)
            if criado >= agora_ref - timedelta(minutes=2):
                continue
            andar, leito = _leito_aleatorio(rng, leitos_quentes)
            _inserir_hotelaria(conn, rng, criado, andar, leito, agora_ref)

    _lote_ativos(conn, rng, agora_ref)
    conn.commit()


def popular_se_vazio(conn):
    if not banco_vazio(conn):
        return False
    popular(conn)
    return True


def acrescentar_ativos(conn):
    rng = random.Random()
    _lote_ativos(conn, rng, agora())
    conn.commit()


if __name__ == "__main__":
    import sys
    import sqlite3

    from config import Config
    from db import SCHEMA

    conexao = sqlite3.connect(Config.DATABASE_PATH, timeout=15)
    conexao.execute("PRAGMA journal_mode = WAL")
    conexao.executescript(SCHEMA)
    if "--ativos" in sys.argv:
        acrescentar_ativos(conexao)
        print("Novo lote de chamados ativos acrescentado.")
    elif popular_se_vazio(conexao):
        print("Dados de demonstração inseridos.")
    else:
        print("O banco já tem chamados — nada foi alterado. Use --ativos para acrescentar chamados ativos.")
    conexao.close()
