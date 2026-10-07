# -*- coding: utf-8 -*-
"""API JSON do Chamador de Enfermagem — SQLite puro (sem ORM).

Concorrência: as transições de status (`assumir`, `finalizar`) usam
`UPDATE ... WHERE status = <status esperado>`. Se dois profissionais
tentarem assumir o mesmo chamado ao mesmo tempo, apenas o primeiro UPDATE
afeta uma linha (`cursor.rowcount`); o segundo recebe HTTP 409 com uma
mensagem clara — a regra vive no banco, não apenas no JavaScript, e
continua válida mesmo com vários administradores em dispositivos
diferentes ao mesmo tempo. `PRAGMA journal_mode=WAL` (ver db.py) permite
que essas escritas convivam com as leituras constantes da Central e da TV
sem bloqueios.
"""
from datetime import datetime

from flask import Blueprint, abort, g, jsonify, request, session, url_for

from db import get_db
from timeutils import (
    agora, para_texto, limite_periodo, janela_comparativa_anterior,
    agrupar_por_dia, agrupar_por_hora, duracao_minutos,
    serie_periodo, inicio_janela_24h,
)

from enfermagem.acesso import (
    acesso_atual, expirar_leito, expirar_todos, obter_token, proxima_meia_noite, status_leitos,
)
from enfermagem.auth import acesso_paciente_requerido, login_requerido
from enfermagem.constants import (
    ANDARES, CATEGORIAS, CATEGORIA_OUTROS,
    leito_valido, categoria_valida, opcao_valida,
    gravidade_da_opcao, servico_hotelaria_da_opcao,
    STATUS_PENDENTE, STATUS_EM_ATENDIMENTO, STATUS_FINALIZADO,
)
from enfermagem.leitos import leito_ativo, listar_leitos, definir_status_leito
from enfermagem.models import ChamadoEnfermagem
from enfermagem.serializers import chamado_to_dict
from enfermagem.priority import calcular_prioridade, excedeu_sla, _tier, TEMPO_MINIMO_ATENDIMENTO_SEG

from hotelaria.services import criar_chamado_hotelaria

api_bp = Blueprint("enfermagem_api", __name__, url_prefix="/api/enfermagem")

# Limites de tamanho de texto livre — nenhuma tela pede mais que isso, e
# barra abuso/payloads gigantes (mitigação barata, ver auditoria de
# segurança). Espelhados em `maxlength` no frontend.
MAX_DETALHE = 280
MAX_COMENTARIO = 300

# Teto de segurança para listagens sem paginação explícita — protege o
# servidor (e o navegador, que teria que desenhar tudo) de um crescimento
# ilimitado do histórico ao longo dos anos. Não se aplica a `metricas`, que
# precisa do conjunto completo filtrado para calcular totais corretos.
LIMITE_SEGURANCA_LISTAGEM = 500

# Ordem das faixas na fila da Central (ver `_preparar_lista`).
ORDEM_FAIXA = {"critica": 0, "media": 1, "baixa": 2}


def _row_para_chamado(row):
    return ChamadoEnfermagem(row) if row is not None else None


def _buscar_ou_404(chamado_id):
    db = get_db()
    row = db.execute("SELECT * FROM enfermagem_chamados WHERE id = ?", (chamado_id,)).fetchone()
    if row is None:
        abort(404, description="Chamado não encontrado.")
    return _row_para_chamado(row)


def _construir_filtros(args, ignorar_periodo=False):
    """Monta a lista de cláusulas SQL (sem o `WHERE`) e os parâmetros a
    partir dos query params compartilhados por `listar_chamados` e
    `metricas` — evita manter duas cópias quase idênticas do mesmo bloco de
    filtros (como havia antes)."""
    clausulas = []
    params = []

    status = args.get("status")
    andar = args.get("andar")
    leito = (args.get("leito") or "").strip()
    categoria = args.get("categoria")
    q = (args.get("q") or "").strip()

    if status:
        clausulas.append("status = ?")
        params.append(status)
    elif args.get("status_ativos"):
        # Central de Enfermagem: só quem ainda precisa de ação (finalizados
        # ficam apenas no Histórico). Ignorado quando um `status` explícito
        # foi passado.
        clausulas.append(f"status IN ('{STATUS_PENDENTE}', '{STATUS_EM_ATENDIMENTO}')")
    if andar:
        clausulas.append("andar = ?")
        params.append(andar)
    if leito:
        # Busca parcial (antes era comparação exata — bastava faltar um
        # dígito para o filtro não achar nada).
        clausulas.append("leito LIKE ?")
        params.append(f"%{leito}%")
    if categoria:
        clausulas.append("categoria = ?")
        params.append(categoria)
    if q:
        termo = f"%{q}%"
        clausulas.append("(leito LIKE ? OR categoria LIKE ? OR subcategoria LIKE ? OR detalhe LIKE ?)")
        params.extend([termo, termo, termo, termo])

    if not ignorar_periodo:
        periodo = args.get("periodo")
        data_inicio = (args.get("data_inicio") or "").strip()
        data_fim = (args.get("data_fim") or "").strip()
        if periodo:
            limite = limite_periodo(periodo)
            if limite is not None:
                clausulas.append("criado_em >= ?")
                params.append(para_texto(limite))
        if data_inicio:
            clausulas.append("criado_em >= ?")
            params.append(f"{data_inicio} 00:00:00")
        if data_fim:
            clausulas.append("criado_em <= ?")
            params.append(f"{data_fim} 23:59:59")

    return clausulas, params


def _serializar_lista(chamados):
    """Serializa sem se preocupar com ordenação (usado nas métricas, onde a
    ordem não importa)."""
    return [chamado_to_dict(c) for c in chamados]


def _preparar_lista(chamados, ordenar="prioridade"):
    """Ordena e serializa uma lista de chamados. `ordenar`:
      - "prioridade" (padrão): ativos primeiro — agrupados por faixa
        (Crítico → Médio → Baixo) e, dentro de cada faixa, quem está
        esperando há mais tempo primeiro; finalizados depois (finalizados
        mais recentemente primeiro);
      - "recentes"/"antigos": por data de criação, ignorando status.
    A ordenação é sempre feita sobre objetos com datetime real, nunca sobre
    texto já formatado. A prioridade de cada chamado é calculada uma única
    vez e reaproveitada tanto para ordenar quanto para serializar."""
    pares = [(c, calcular_prioridade(c)) for c in chamados]

    if ordenar == "recentes":
        pares.sort(key=lambda par: par[0].criado_em, reverse=True)
    elif ordenar == "antigos":
        pares.sort(key=lambda par: par[0].criado_em)
    else:
        ativos = [par for par in pares if par[0].status != STATUS_FINALIZADO]
        finalizados = [par for par in pares if par[0].status == STATUS_FINALIZADO]
        ativos.sort(key=lambda par: (ORDEM_FAIXA.get(par[1]["tier"], len(ORDEM_FAIXA)), -par[1]["tempo_espera_min"]))
        finalizados.sort(key=lambda par: par[0].finalizado_em or par[0].criado_em, reverse=True)
        pares = ativos + finalizados

    resultado = []
    for chamado, prioridade in pares:
        d = chamado_to_dict(chamado, incluir_prioridade=False)
        d.update({
            "prioridade": prioridade["tier"],
            "prioridade_label": prioridade["tier_label"],
            "prioridade_emoji": prioridade["tier_emoji"],
            "prioridade_score": prioridade["score"],
            "tempo_espera_min": prioridade["tempo_espera_min"],
            "sla_min": prioridade["sla_min"],
            "acima_do_tempo_esperado": excedeu_sla(prioridade["tier"], prioridade["tempo_espera_min"]),
        })
        resultado.append(d)
    return resultado


# ---------------------------------------------------------------------------
# Criação e consulta
# ---------------------------------------------------------------------------
def _chamado_ativo_no_leito(andar, leito):
    """Regra "um chamado por vez": enquanto o leito já tiver um chamado
    pendente ou em atendimento (qualquer categoria), uma nova tentativa de
    abrir chamado não cria um segundo — devolve o chamado já em aberto. Além
    de refletir o pedido do hospital (evita o mesmo leito acumular vários
    chamados simultâneos), isso também cobre o caso de duplo-clique/retry de
    rede que antes só era tratado dentro de uma janela de alguns segundos."""
    db = get_db()
    row = db.execute(
        """SELECT * FROM enfermagem_chamados
           WHERE andar = ? AND leito = ? AND status IN (?, ?)
           ORDER BY criado_em DESC LIMIT 1""",
        (andar, leito, STATUS_PENDENTE, STATUS_EM_ATENDIMENTO),
    ).fetchone()
    return _row_para_chamado(row)


@api_bp.route("/chamados", methods=["POST"])
@acesso_paciente_requerido
def criar_chamado():
    dados = request.get_json(silent=True) or {}

    andar = (dados.get("andar") or "").strip()
    leito = (dados.get("leito") or "").strip()
    categoria = (dados.get("categoria") or "").strip()
    subcategoria = (dados.get("subcategoria") or "").strip()
    detalhe = (dados.get("detalhe") or "").strip() or None

    if not leito_valido(andar, leito):
        return jsonify({"erro": "Andar ou leito inválido."}), 400
    # Só o leito cujo QR Code foi escaneado (ver enfermagem/acesso.py).
    if (andar, leito) != (g.acesso_paciente["andar"], g.acesso_paciente["leito"]):
        return jsonify({"erro": "Escaneie o QR Code do seu leito para abrir um chamado."}), 403
    if not leito_ativo(andar, leito):
        return jsonify({"erro": "Este leito está desativado no momento."}), 400
    if not categoria_valida(categoria):
        return jsonify({"erro": "Categoria inválida."}), 400
    if not opcao_valida(categoria, subcategoria):
        return jsonify({"erro": "Opção selecionada é inválida para esta categoria."}), 400
    if detalhe and len(detalhe) > MAX_DETALHE:
        return jsonify({"erro": f"Detalhe muito longo (máx. {MAX_DETALHE} caracteres)."}), 400

    # Categoria "Outros": NÃO entra na fila de enfermagem — é encaminhada
    # imediatamente para a Central de Hotelaria (especificação, item 5).
    if categoria == CATEGORIA_OUTROS:
        servico = servico_hotelaria_da_opcao(subcategoria)
        if not servico:
            return jsonify({"erro": "Não foi possível encaminhar esta solicitação."}), 400

        # O andar/leito e a origem ("enfermagem") já vão como campos próprios
        # para `criar_chamado_hotelaria` — não precisam ser repetidos dentro
        # do texto da descrição, que fica só com a solicitação em si.
        descricao = subcategoria
        if detalhe:
            descricao += f" — {detalhe}"

        chamado_hotelaria = criar_chamado_hotelaria(leito, servico, descricao, origem="enfermagem", andar=andar)
        return jsonify({
            "encaminhado_hotelaria": True,
            "hotelaria_chamado_id": chamado_hotelaria["id"],
            "leito": leito,
            "servico": servico,
            "servico_nome": chamado_hotelaria["servico_nome"],
        }), 201

    chamado_ativo = _chamado_ativo_no_leito(andar, leito)
    if chamado_ativo is not None:
        payload = chamado_to_dict(chamado_ativo)
        payload["encaminhado_hotelaria"] = False
        payload["duplicado"] = True
        return jsonify(payload), 200

    gravidade = gravidade_da_opcao(categoria, subcategoria)
    texto_agora = para_texto(agora())

    db = get_db()
    cur = db.execute(
        """INSERT INTO enfermagem_chamados
           (andar, leito, categoria, subcategoria, detalhe, gravidade_base, status, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (andar, leito, categoria, subcategoria, detalhe, gravidade, STATUS_PENDENTE, texto_agora),
    )
    db.commit()

    chamado = _buscar_ou_404(cur.lastrowid)
    payload = chamado_to_dict(chamado)
    payload["encaminhado_hotelaria"] = False
    return jsonify(payload), 201


@api_bp.route("/chamados", methods=["GET"])
@login_requerido
def listar_chamados():
    db = get_db()
    clausulas, params = _construir_filtros(request.args)
    sql_base = "SELECT * FROM enfermagem_chamados"
    if clausulas:
        sql_base += " WHERE " + " AND ".join(clausulas)

    ordenar = request.args.get("ordenar", "prioridade")
    prioridade = request.args.get("prioridade")
    limite = request.args.get("limite", type=int)
    offset = request.args.get("offset", type=int) or 0

    if prioridade:
        # A prioridade é calculada dinamicamente (não é coluna do banco) —
        # não dá para filtrar por ela em SQL nem paginar antes de calculá-la.
        # Busca o conjunto filtrado inteiro (limitado ao teto de segurança),
        # calcula prioridade, filtra, e só então pagina em memória. No
        # volume real de um único hospital isso é sempre barato.
        linhas = db.execute(sql_base + " ORDER BY criado_em DESC LIMIT ?", params + [LIMITE_SEGURANCA_LISTAGEM]).fetchall()
        chamados = [_row_para_chamado(r) for r in linhas]
        serializados = [c for c in _preparar_lista(chamados, ordenar) if c["prioridade"] == prioridade]
        total = len(serializados)
        if limite:
            serializados = serializados[offset:offset + limite]
    else:
        total = db.execute(f"SELECT COUNT(*) FROM ({sql_base})", params).fetchone()[0]
        limite_sql = limite or LIMITE_SEGURANCA_LISTAGEM
        linhas = db.execute(
            sql_base + " ORDER BY criado_em DESC LIMIT ? OFFSET ?", params + [limite_sql, offset]
        ).fetchall()
        chamados = [_row_para_chamado(r) for r in linhas]
        serializados = _preparar_lista(chamados, ordenar)

    resposta = jsonify(serializados)
    resposta.headers["X-Total-Count"] = str(total)
    return resposta


@api_bp.route("/chamados/<int:chamado_id>", methods=["GET"])
def detalhe_chamado(chamado_id):
    chamado = _buscar_ou_404(chamado_id)
    return jsonify(chamado_to_dict(chamado))


# ---------------------------------------------------------------------------
# Transições de status
# ---------------------------------------------------------------------------
def _transicao_atomica(chamado_id, status_esperado, novo_status, campos_extra):
    db = get_db()
    colunas = ["status = ?"]
    valores = [novo_status]
    for coluna, valor in campos_extra.items():
        colunas.append(f"{coluna} = ?")
        valores.append(valor)
    valores.extend([chamado_id, status_esperado])

    sql = f"UPDATE enfermagem_chamados SET {', '.join(colunas)} WHERE id = ? AND status = ?"
    cur = db.execute(sql, valores)
    db.commit()
    return cur.rowcount > 0


@api_bp.route("/chamados/<int:chamado_id>/assumir", methods=["POST"])
@login_requerido
def assumir_chamado(chamado_id):
    chamado = _buscar_ou_404(chamado_id)
    if chamado.status != STATUS_PENDENTE:
        return jsonify({"erro": "Este chamado já foi assumido por outro profissional ou não está mais pendente."}), 409

    # O responsável é sempre o usuário autenticado na sessão — não um nome
    # digitado livremente. Além de tirar uma etapa/campo da interface (o
    # nome não é mais mostrado em nenhuma tela), evita responsáveis
    # inventados/em branco e vincula a ação a quem de fato está logado.
    profissional = session.get("enfermagem_usuario") or "Equipe de Enfermagem"

    ok = _transicao_atomica(
        chamado_id, STATUS_PENDENTE, STATUS_EM_ATENDIMENTO,
        {"profissional_responsavel": profissional, "inicio_atendimento": para_texto(agora())},
    )
    if not ok:
        return jsonify({"erro": "Este chamado já foi assumido por outro profissional."}), 409

    chamado = _buscar_ou_404(chamado_id)
    return jsonify(chamado_to_dict(chamado))


@api_bp.route("/chamados/<int:chamado_id>/finalizar", methods=["POST"])
@login_requerido
def finalizar_chamado(chamado_id):
    chamado = _buscar_ou_404(chamado_id)
    if chamado.status != STATUS_EM_ATENDIMENTO:
        return jsonify({"erro": "O chamado precisa estar em atendimento antes de ser finalizado."}), 409

    restante = chamado.segundos_ate_poder_finalizar()
    if restante > 0:
        return jsonify({
            "erro": f"O atendimento precisa durar pelo menos 2 minutos. Aguarde mais {restante}s para finalizar.",
            "segundos_restantes": restante,
        }), 409

    ok = _transicao_atomica(
        chamado_id, STATUS_EM_ATENDIMENTO, STATUS_FINALIZADO,
        {"finalizado_em": para_texto(agora())},
    )
    if not ok:
        return jsonify({"erro": "Não foi possível finalizar o atendimento agora."}), 409

    chamado = _buscar_ou_404(chamado_id)
    return jsonify(chamado_to_dict(chamado))


@api_bp.route("/chamados/<int:chamado_id>/avaliar", methods=["POST"])
def avaliar_chamado(chamado_id):
    chamado = _buscar_ou_404(chamado_id)
    if chamado.status != STATUS_FINALIZADO:
        return jsonify({"erro": "Só é possível avaliar um chamado já finalizado."}), 409
    if chamado.avaliacao is not None:
        return jsonify({"erro": "Este chamado já foi avaliado."}), 409

    dados = request.get_json(silent=True) or {}
    try:
        nota = int(dados.get("avaliacao"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Avaliação inválida."}), 400
    if nota < 1 or nota > 5:
        return jsonify({"erro": "A avaliação deve ser de 1 a 5 estrelas."}), 400

    comentario = (dados.get("comentario") or "").strip() or None
    if comentario and len(comentario) > MAX_COMENTARIO:
        return jsonify({"erro": f"Comentário muito longo (máx. {MAX_COMENTARIO} caracteres)."}), 400

    db = get_db()
    cur = db.execute(
        "UPDATE enfermagem_chamados SET avaliacao = ?, comentario_avaliacao = ? "
        "WHERE id = ? AND status = 'finalizado' AND avaliacao IS NULL",
        (nota, comentario, chamado_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"erro": "Este chamado já foi avaliado."}), 409

    chamado = _buscar_ou_404(chamado_id)
    return jsonify(chamado_to_dict(chamado))


# ---------------------------------------------------------------------------
# Dashboard da TV / painel "Atenção imediata" (endpoint único, já agregado,
# para minimizar round-trips na Central e nos cartões de status)
# ---------------------------------------------------------------------------
@api_bp.route("/tv", methods=["GET"])
@login_requerido
def dashboard_tv():
    db = get_db()
    linhas_ativas = db.execute(
        "SELECT * FROM enfermagem_chamados WHERE status IN ('pendente', 'em_atendimento')"
    ).fetchall()
    ativos = [_row_para_chamado(r) for r in linhas_ativas]
    fila = _preparar_lista(ativos)

    hoje = agora().replace(hour=0, minute=0, second=0, microsecond=0)
    hoje_texto = para_texto(hoje)

    linhas_finalizados = db.execute(
        "SELECT * FROM enfermagem_chamados WHERE status = 'finalizado' AND finalizado_em >= ? "
        "ORDER BY finalizado_em DESC LIMIT 8",
        (hoje_texto,),
    ).fetchall()
    finalizados_hoje = [_row_para_chamado(r) for r in linhas_finalizados]
    ultimos_finalizados = _preparar_lista(finalizados_hoje)

    total_hoje = db.execute(
        "SELECT COUNT(*) FROM enfermagem_chamados WHERE criado_em >= ?", (hoje_texto,)
    ).fetchone()[0]
    total_finalizados_hoje = db.execute(
        "SELECT COUNT(*) FROM enfermagem_chamados WHERE status = 'finalizado' AND finalizado_em >= ?",
        (hoje_texto,),
    ).fetchone()[0]

    contagem_prioridade = {"critica": 0, "media": 0, "baixa": 0}
    for c in fila:
        contagem_prioridade[c["prioridade"]] = contagem_prioridade.get(c["prioridade"], 0) + 1

    atrasados = [c for c in fila if c["acima_do_tempo_esperado"]]

    return jsonify({
        "atualizado_em": agora().strftime("%H:%M:%S"),
        "fila": fila,
        "ultimos_finalizados": ultimos_finalizados,
        "contadores": {
            "pendentes": sum(1 for c in fila if c["status"] == STATUS_PENDENTE),
            "em_atendimento": sum(1 for c in fila if c["status"] == STATUS_EM_ATENDIMENTO),
            "criticos": contagem_prioridade["critica"],
            "atrasados": len(atrasados),
            "total_hoje": total_hoje,
            "finalizados_hoje": total_finalizados_hoje,
        },
        "por_prioridade": contagem_prioridade,
        # "Atenção imediata": os chamados que mais precisam de ação agora —
        # críticos e/ou já acima do tempo esperado, na ordem de prioridade
        # que a fila já usa. Reaproveita a mesma lista já calculada acima
        # (nenhuma consulta nova ao banco).
        "atencao_imediata": [c for c in fila if c["prioridade"] == "critica" or c["acima_do_tempo_esperado"]][:6],
    })


# ---------------------------------------------------------------------------
# Métricas / histórico / dashboard
# ---------------------------------------------------------------------------
def _serie_periodo(db, args, chamados):
    """Série do gráfico "Chamados por período" (ver timeutils.serie_periodo).
    Para "Hoje", busca as últimas 24h com os mesmos filtros, exceto o
    período (a janela de 24h pode começar antes da meia-noite)."""
    datas_24h = []
    if args.get("periodo") == "hoje":
        clausulas, params = _construir_filtros(args, ignorar_periodo=True)
        clausulas.append("criado_em >= ?")
        params.append(para_texto(inicio_janela_24h()))
        prioridade = args.get("prioridade")
        for r in db.execute(
            "SELECT criado_em, gravidade_base, categoria FROM enfermagem_chamados WHERE " + " AND ".join(clausulas), params
        ).fetchall():
            if prioridade and _tier(r["gravidade_base"], r["categoria"]) != prioridade:
                continue
            datas_24h.append(datetime.fromisoformat(r["criado_em"]))
    return serie_periodo(
        args.get("periodo"), [c.criado_em for c in chamados], datas_24h,
        (args.get("data_inicio") or "").strip(), (args.get("data_fim") or "").strip(),
    )


@api_bp.route("/metricas", methods=["GET"])
@login_requerido
def metricas():
    db = get_db()
    clausulas, params = _construir_filtros(request.args)
    sql = "SELECT * FROM enfermagem_chamados"
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)

    linhas = db.execute(sql, params).fetchall()
    chamados = [_row_para_chamado(r) for r in linhas]
    serializados = _serializar_lista(chamados)

    # O filtro de prioridade precisa ser aplicado depois da serialização —
    # assim como em `listar_chamados` — porque a prioridade é calculada
    # dinamicamente (não é uma coluna do banco).
    prioridade = request.args.get("prioridade")
    if prioridade:
        serializados = [c for c in serializados if c["prioridade"] == prioridade]
        ids_mantidos = {s["id"] for s in serializados}
        chamados = [c for c in chamados if c.id in ids_mantidos]

    total = len(serializados)

    def conta(status):
        return sum(1 for c in serializados if c["status"] == status)

    pendentes = conta(STATUS_PENDENTE)
    em_atendimento = conta(STATUS_EM_ATENDIMENTO)
    finalizados = conta(STATUS_FINALIZADO)

    tempos_atendimento = [c["tempo_atendimento_min"] for c in serializados if c["tempo_atendimento_min"] is not None]
    tempos_espera = [c["tempo_espera_min"] for c in serializados if c["status"] != STATUS_PENDENTE]
    avaliacoes = [c["avaliacao"] for c in serializados if c["avaliacao"] is not None]

    def media(lista):
        return round(sum(lista) / len(lista), 1) if lista else None

    por_categoria = {}
    por_prioridade = {"critica": 0, "media": 0, "baixa": 0}
    por_andar = {}
    for c in serializados:
        por_categoria[c["categoria"]] = por_categoria.get(c["categoria"], 0) + 1
        por_prioridade[c["prioridade"]] = por_prioridade.get(c["prioridade"], 0) + 1
        por_andar[c["andar"]] = por_andar.get(c["andar"], 0) + 1

    # Chamados por andar, já separados por faixa de prioridade (gráfico
    # "Chamados por andar" do Dashboard). Todos os andares aparecem, mesmo
    # com zero, para a comparação entre eles ficar estável.
    por_andar_prioridade = {
        nome: {"critica": 0, "media": 0, "baixa": 0}
        for nome in ANDARES if not request.args.get("andar") or nome == request.args.get("andar")
    }
    for c in serializados:
        faixas = por_andar_prioridade.setdefault(c["andar"], {"critica": 0, "media": 0, "baixa": 0})
        faixas[c["prioridade"]] = faixas.get(c["prioridade"], 0) + 1

    por_dia = agrupar_por_dia(c.criado_em for c in chamados)
    por_hora = agrupar_por_hora(c.criado_em for c in chamados)

    pendentes_agora = [c for c in chamados if c.status == STATUS_PENDENTE]
    mais_antigo_pendente = None
    if pendentes_agora:
        c = min(pendentes_agora, key=lambda x: x.criado_em)
        mais_antigo_pendente = {
            "id": c.id,
            "leito": c.leito,
            "andar": c.andar,
            "tempo_espera_min": duracao_minutos(c.criado_em, agora()),
        }

    # Comparativo com a janela equivalente imediatamente anterior — só
    # calculado quando existe um atalho de período reconhecido (ver
    # timeutils.janela_comparativa_anterior); sem isso, não há uma base de
    # comparação clara, e o comparativo fica None (o frontend simplesmente
    # não mostra o selo de tendência).
    comparativo = None
    periodo = request.args.get("periodo")
    janela_anterior = janela_comparativa_anterior(periodo) if periodo else None
    if janela_anterior is not None:
        inicio_anterior, fim_anterior = janela_anterior
        clausulas_ant, params_ant = _construir_filtros(request.args, ignorar_periodo=True)
        clausulas_ant = clausulas_ant + ["criado_em >= ?", "criado_em < ?"]
        params_ant = params_ant + [para_texto(inicio_anterior), para_texto(fim_anterior)]
        total_anterior = db.execute(
            "SELECT COUNT(*) FROM enfermagem_chamados WHERE " + " AND ".join(clausulas_ant), params_ant
        ).fetchone()[0]
        if total_anterior > 0:
            delta_percentual = round(((total - total_anterior) / total_anterior) * 100, 1)
        else:
            delta_percentual = 100.0 if total > 0 else 0.0
        comparativo = {"total_anterior": total_anterior, "delta_percentual": delta_percentual}

    return jsonify({
        "total": total,
        "pendentes": pendentes,
        "em_atendimento": em_atendimento,
        "finalizados": finalizados,
        "taxa_finalizacao": round((finalizados / total) * 100, 1) if total else None,
        "criticos_ativos": sum(1 for c in serializados if c["status"] != STATUS_FINALIZADO and c["prioridade"] == "critica"),
        "acima_do_tempo_esperado": sum(1 for c in serializados if c["acima_do_tempo_esperado"]),
        "mais_antigo_pendente": mais_antigo_pendente,
        "tempo_medio_atendimento_min": media(tempos_atendimento),
        "tempo_medio_espera_min": media(tempos_espera),
        "avaliacao_media": media(avaliacoes),
        "total_avaliacoes": len(avaliacoes),
        "por_categoria": por_categoria,
        "por_prioridade": por_prioridade,
        "por_andar": por_andar,
        "por_andar_prioridade": por_andar_prioridade,
        "por_dia": por_dia,
        "por_hora": por_hora,
        "serie_periodo": _serie_periodo(db, request.args, chamados),
        "comparativo_periodo_anterior": comparativo,
    })


@api_bp.route("/opcoes", methods=["GET"])
def opcoes():
    """Metadados fixos (andares/leitos e categorias/subopções), para o
    front-end montar a interface sem duplicar essas listas em JS."""
    categorias_json = {
        nome: {
            "cor": dados["cor"],
            "icone": dados["icone"],
            "descricao": dados["descricao"],
            "opcoes": [texto for texto, _peso in dados["opcoes"]],
        }
        for nome, dados in CATEGORIAS.items()
    }
    return jsonify({"andares": ANDARES, "categorias": categorias_json})


@api_bp.route("/leitos", methods=["GET"])
@login_requerido
def listar_leitos_admin():
    """Todos os leitos com status ativo/inativo — usado pela tela
    Configurações → Controle de Leitos."""
    return jsonify({"andares": listar_leitos()})


@api_bp.route("/leitos/status", methods=["POST"])
@login_requerido
def definir_status_leito_admin():
    dados = request.get_json(silent=True) or {}
    andar = (dados.get("andar") or "").strip()
    leito = (dados.get("leito") or "").strip()
    ativo = bool(dados.get("ativo"))

    if not definir_status_leito(andar, leito, ativo):
        return jsonify({"erro": "Andar ou leito inválido."}), 400
    return jsonify({"andar": andar, "leito": leito, "ativo": ativo})


# ---------------------------------------------------------------------------
# Acesso da tela do Paciente (QR Code) — Configurações
# ---------------------------------------------------------------------------
def _url_acesso_paciente(token, andar=None, leito=None):
    params = {"acesso": token}
    if andar and leito:
        params.update(andar=andar, leito=leito)
    return url_for("enfermagem_pages.paciente_inicio", _external=True, **params)


@api_bp.route("/acesso", methods=["GET"])
@login_requerido
def acesso_paciente_info():
    """Link/QR Code de acesso — genérico (card principal de Configurações)
    ou, com `?andar=&leito=`, já apontando para um leito específico (ver
    "Gerador de QR Code por Leito")."""
    andar = (request.args.get("andar") or "").strip()
    leito = (request.args.get("leito") or "").strip()
    if andar and leito and not leito_valido(andar, leito):
        return jsonify({"erro": "Andar ou leito inválido."}), 400
    return jsonify({"url": _url_acesso_paciente(obter_token(), andar or None, leito or None)})


@api_bp.route("/acesso/status", methods=["GET"])
def acesso_paciente_status():
    """Consultado periodicamente pelas telas do paciente: assim que passa da
    meia-noite ou a Central expira o acesso, a tela troca para "Acesso
    expirado" sem o paciente precisar recarregar. `segundos_restantes` vem
    do relógio do servidor (o do celular pode estar errado)."""
    acesso = acesso_atual()
    if acesso is None:
        resposta = jsonify({"valido": False})
    else:
        restantes = max(0, int((acesso["expira_em"] - agora()).total_seconds()))
        resposta = jsonify({"valido": True, "segundos_restantes": restantes})
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@api_bp.route("/acesso/leitos", methods=["GET"])
@login_requerido
def acesso_leitos():
    """Leitos por andar + quais estão com acesso liberado hoje + segundos
    até o reset da meia-noite (cartão "Acesso pelo QR Code" de Configurações)."""
    liberados = status_leitos()
    andares = [
        {
            "andar": grupo["andar"],
            "andar_label": grupo["andar_label"],
            "leitos": [
                {"leito": l["leito"], "ativo": l["ativo"], "liberado_desde": liberados.get((grupo["andar"], l["leito"]))}
                for l in grupo["leitos"]
            ],
        }
        for grupo in listar_leitos()
    ]
    restantes = max(0, int((proxima_meia_noite() - agora()).total_seconds()))
    return jsonify({"andares": andares, "segundos_ate_reset": restantes})


@api_bp.route("/acesso/expirar", methods=["POST"])
@login_requerido
def expirar_acesso_leito():
    """Derruba na hora o acesso de quem escaneou o QR Code deste leito. Quem
    escanear de novo entra, mas só até a mesma meia-noite."""
    dados = request.get_json(silent=True) or {}
    andar = (dados.get("andar") or "").strip()
    leito = (dados.get("leito") or "").strip()
    if not expirar_leito(andar, leito):
        return jsonify({"erro": "Andar ou leito inválido."}), 400
    return jsonify({"andar": andar, "leito": leito, "expirado": True})


@api_bp.route("/acesso/expirar-todos", methods=["POST"])
@login_requerido
def expirar_acesso_todos():
    expirar_todos()
    return jsonify({"expirado": True})
