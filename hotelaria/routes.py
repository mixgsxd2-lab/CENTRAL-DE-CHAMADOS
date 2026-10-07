# -*- coding: utf-8 -*-
"""Central de Hotelaria — sistema já existente, portado para dentro do
projeto unificado como um Blueprint independente (rotas e modelos
próprios). Comportamento e fluxo preservados do projeto original: login,
chat entre paciente e Central, confirmação de resolução em até 30 minutos,
avaliação por estrelas. A única mudança de fundo é a camada de dados —
trocada de SQLAlchemy para SQLite puro (mesma técnica já usada no restante
do projeto) — e o tempo real, que passou de Socket.IO para atualização por
polling (a cada poucos segundos), evitando uma dependência externa a mais
sem abrir mão de um chat que "parece" instantâneo.
"""
import threading
import time
from datetime import timedelta
from functools import wraps

from flask import (
    Blueprint, abort, current_app, render_template, request, redirect, url_for,
    session, jsonify, flash,
)

from db import get_db, nova_conexao_standalone
from timeutils import (
    agora, para_texto, parse_dt, limite_periodo, janela_comparativa_anterior,
    agrupar_por_dia, agrupar_por_hora, serie_periodo, inicio_janela_24h,
)
from andares import ANDARES, leito_valido
from ratelimit import permitido as rate_limit_permitido
from hotelaria.models import (
    SERVICOS, META_ESPERA_MIN,
    STATUS_PENDENTE, STATUS_ANDAMENTO, STATUS_FINALIZADO,
    CONFIRMACAO_PENDENTE, CONFIRMACAO_RESOLVIDO, CONFIRMACAO_NAO_RESOLVIDO,
    CONFIRMACAO_EXPIRADA, CONFIRMACAO_NA,
    chamado_to_dict, mensagem_to_dict, avaliacao_to_dict,
)
from hotelaria.services import criar_chamado_hotelaria

hotelaria_pages = Blueprint("hotelaria_pages", __name__, url_prefix="/hotelaria")
hotelaria_api = Blueprint("hotelaria_api", __name__, url_prefix="/hotelaria/api")

CONFIRMACAO_MINUTOS = 30

# Limites de texto livre e teto de segurança de listagem — mesmo racional já
# usado na Enfermagem (ver enfermagem/api.py).
MAX_DESCRICAO = 500
MAX_MENSAGEM = 500
MAX_COMENTARIO = 300
LIMITE_SEGURANCA_LISTAGEM = 500


def _construir_filtros_dashboard(args, ignorar_periodo=False):
    """Cláusulas SQL (sem o `WHERE`) + parâmetros compartilhados entre o
    resumo do dashboard e (quando aplicável) seu comparativo com o período
    anterior — evita duas cópias quase idênticas do mesmo bloco de filtros."""
    clausulas = []
    params = []

    servico = args.get("servico")
    status = args.get("status")
    andar = args.get("andar")
    q = (args.get("q") or "").strip()

    if servico and servico != "todos":
        clausulas.append("servico = ?")
        params.append(servico)
    if status and status != "todos":
        clausulas.append("status = ?")
        params.append(status)
    if andar:
        clausulas.append("andar = ?")
        params.append(andar)
    if q:
        termo = f"%{q}%"
        clausulas.append("(leito LIKE ? OR descricao LIKE ?)")
        params.extend([termo, termo])

    if not ignorar_periodo:
        periodo = args.get("periodo")
        if periodo:
            limite = limite_periodo(periodo)
            if limite is not None:
                clausulas.append("criado_em >= ?")
                params.append(para_texto(limite))
        # Intervalo manual (De/Até) — mesmo comportamento do Dashboard de
        # Enfermagem.
        data_inicio = (args.get("data_inicio") or "").strip()
        data_fim = (args.get("data_fim") or "").strip()
        if data_inicio:
            clausulas.append("criado_em >= ?")
            params.append(f"{data_inicio} 00:00:00")
        if data_fim:
            clausulas.append("criado_em <= ?")
            params.append(f"{data_fim} 23:59:59")

    return clausulas, params


# ---------------------------------------------------------------------------
# Autenticação (credenciais de teste, preservadas do sistema original)
# ---------------------------------------------------------------------------
def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("hotelaria_logado"):
            return redirect(url_for("hotelaria_pages.login", proximo=request.path))
        return f(*args, **kwargs)
    return decorated


@hotelaria_pages.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not rate_limit_permitido(f"hotelaria:{request.remote_addr}"):
            flash("Muitas tentativas de login. Aguarde alguns minutos e tente novamente.")
            return render_template("hotelaria/login.html"), 429

        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()
        if (
            usuario == current_app.config["HOTELARIA_USUARIO_TESTE"]
            and senha == current_app.config["HOTELARIA_SENHA_TESTE"]
        ):
            session["hotelaria_logado"] = True
            session["hotelaria_usuario"] = usuario
            proximo = request.args.get("proximo") or url_for("hotelaria_pages.central")
            return redirect(proximo)
        flash("Usuário ou senha inválidos.")
    return render_template("hotelaria/login.html")


@hotelaria_pages.route("/logout")
def logout():
    session.pop("hotelaria_logado", None)
    session.pop("hotelaria_usuario", None)
    return redirect(url_for("portal.inicio"))


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------
@hotelaria_pages.route("/paciente")
def paciente():
    # A área do paciente da Hotelaria deixou de existir: o paciente usa só a
    # área do paciente da Enfermagem (a categoria "Outros" já encaminha os
    # pedidos para a Hotelaria). Links/QR codes antigos continuam levando a
    # pessoa para o lugar certo em vez de dar "página não encontrada".
    return redirect(url_for("enfermagem_pages.paciente_inicio"))


@hotelaria_pages.route("/central")
@login_requerido
def central():
    return render_template("hotelaria/central.html", servicos=SERVICOS, andares=list(ANDARES.keys()))


@hotelaria_pages.route("/dashboard")
@login_requerido
def dashboard():
    return render_template("hotelaria/dashboard.html", servicos=SERVICOS, andares=list(ANDARES.keys()))


@hotelaria_pages.route("/historico")
@login_requerido
def historico():
    return render_template("hotelaria/historico.html", servicos=SERVICOS, andares=list(ANDARES.keys()))


# ---------------------------------------------------------------------------
# Helpers de leitura
# ---------------------------------------------------------------------------
def _buscar_chamado_ou_404(chamado_id):
    db = get_db()
    row = db.execute("SELECT * FROM hotelaria_chamados WHERE id = ?", (chamado_id,)).fetchone()
    if row is None:
        abort(404, description="Chamado não encontrado.")
    return row


def _mensagens_do_chamado(chamado_id):
    db = get_db()
    linhas = db.execute(
        "SELECT * FROM hotelaria_mensagens WHERE chamado_id = ? ORDER BY criado_em ASC, id ASC",
        (chamado_id,),
    ).fetchall()
    return [mensagem_to_dict(r) for r in linhas]


def _avaliacao_do_chamado(chamado_id):
    db = get_db()
    return db.execute("SELECT * FROM hotelaria_avaliacoes WHERE chamado_id = ?", (chamado_id,)).fetchone()


def _tem_mensagem_nao_lida(chamado_id):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) FROM hotelaria_mensagens WHERE chamado_id = ? AND remetente = 'paciente' AND lida_central = 0",
        (chamado_id,),
    ).fetchone()
    return row[0] > 0


def _chamado_completo_dict(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    mensagens = _mensagens_do_chamado(chamado_id)
    avaliacao_row = _avaliacao_do_chamado(chamado_id)
    nao_lida = any(m["remetente"] == "paciente" and not m["lida_central"] for m in mensagens)
    return chamado_to_dict(row, mensagens=mensagens, avaliacao_row=avaliacao_row, nao_lida=nao_lida)


# ---------------------------------------------------------------------------
# API - Paciente
# ---------------------------------------------------------------------------
@hotelaria_api.route("/chamados", methods=["POST"])
def api_criar_chamado():
    dados = request.get_json(silent=True) or {}
    andar = (dados.get("andar") or "").strip()
    leito = (dados.get("leito") or "").strip()
    servico = (dados.get("servico") or "").strip()
    descricao = (dados.get("descricao") or "").strip()

    if not andar or not leito or not leito_valido(andar, leito):
        return jsonify({"erro": "Informe o andar e o leito corretamente."}), 400
    if servico not in SERVICOS or servico == "outros":
        return jsonify({"erro": "Serviço inválido."}), 400
    if not descricao:
        return jsonify({"erro": "Descreva sua solicitação."}), 400
    if len(descricao) > MAX_DESCRICAO:
        return jsonify({"erro": f"Descrição muito longa (máx. {MAX_DESCRICAO} caracteres)."}), 400

    chamado = criar_chamado_hotelaria(leito, servico, descricao, origem="hotelaria", andar=andar)
    return jsonify(chamado), 201


@hotelaria_api.route("/chamados/<int:chamado_id>", methods=["GET"])
def api_obter_chamado(chamado_id):
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/chamados/leito/<leito>", methods=["GET"])
def api_chamados_por_leito(leito):
    db = get_db()
    linhas = db.execute(
        "SELECT * FROM hotelaria_chamados WHERE leito = ? ORDER BY criado_em DESC LIMIT 20", (leito,)
    ).fetchall()
    return jsonify([chamado_to_dict(r) for r in linhas])


@hotelaria_api.route("/chamados/<int:chamado_id>/mensagens", methods=["POST"])
def api_enviar_mensagem(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    dados = request.get_json(silent=True) or {}
    remetente = dados.get("remetente")
    texto = (dados.get("mensagem") or "").strip()

    if remetente not in ("paciente", "central"):
        return jsonify({"erro": "Remetente inválido."}), 400
    if not texto:
        return jsonify({"erro": "Mensagem vazia."}), 400
    if len(texto) > MAX_MENSAGEM:
        return jsonify({"erro": f"Mensagem muito longa (máx. {MAX_MENSAGEM} caracteres)."}), 400
    if row["status"] == STATUS_FINALIZADO:
        return jsonify({"erro": "Este chamado foi finalizado e não aceita novas mensagens."}), 409

    db = get_db()
    db.execute(
        "INSERT INTO hotelaria_mensagens (chamado_id, remetente, mensagem, criado_em, lida_central) VALUES (?, ?, ?, ?, ?)",
        (chamado_id, remetente, texto, para_texto(agora()), 1 if remetente == "central" else 0),
    )
    db.commit()
    return jsonify(_chamado_completo_dict(chamado_id)), 201


@hotelaria_api.route("/chamados/<int:chamado_id>/confirmar", methods=["POST"])
def api_confirmar_resolucao(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    dados = request.get_json(silent=True) or {}
    resolvido = dados.get("resolvido")

    if row["status"] != STATUS_FINALIZADO:
        return jsonify({"erro": "Chamado ainda não foi finalizado."}), 400
    if row["confirmacao_resolucao"] != CONFIRMACAO_PENDENTE:
        return jsonify({"erro": "Este chamado já possui uma confirmação registrada."}), 400

    novo_valor = CONFIRMACAO_RESOLVIDO if resolvido else CONFIRMACAO_NAO_RESOLVIDO
    db = get_db()
    db.execute("UPDATE hotelaria_chamados SET confirmacao_resolucao = ? WHERE id = ?", (novo_valor, chamado_id))
    db.commit()
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/chamados/<int:chamado_id>/avaliacao", methods=["POST"])
def api_criar_avaliacao(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    dados = request.get_json(silent=True) or {}
    try:
        estrelas = int(dados.get("estrelas"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Número de estrelas inválido."}), 400
    if estrelas < 1 or estrelas > 5:
        return jsonify({"erro": "A avaliação deve ser entre 1 e 5 estrelas."}), 400

    comentario = (dados.get("comentario") or "").strip() or None
    if comentario and len(comentario) > MAX_COMENTARIO:
        return jsonify({"erro": f"Comentário muito longo (máx. {MAX_COMENTARIO} caracteres)."}), 400

    db = get_db()
    if _avaliacao_do_chamado(chamado_id) is not None:
        return jsonify({"erro": "Este chamado já foi avaliado."}), 400

    cur = db.execute(
        "INSERT INTO hotelaria_avaliacoes (chamado_id, estrelas, comentario, criado_em) VALUES (?, ?, ?, ?)",
        (chamado_id, estrelas, comentario, para_texto(agora())),
    )
    db.commit()
    nova = db.execute("SELECT * FROM hotelaria_avaliacoes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(avaliacao_to_dict(nova)), 201


# ---------------------------------------------------------------------------
# API - Central
# ---------------------------------------------------------------------------
@hotelaria_api.route("/central/resumo", methods=["GET"])
@login_requerido
def api_central_resumo():
    """Contadores em tempo real para os cartões de estatística no topo da
    Central — mesmo papel do `/api/enfermagem/tv` da Enfermagem, mas com
    métricas que fazem sentido para a Hotelaria: pendentes, em andamento,
    acima da meta de espera (30 min), setor mais requisitado hoje e
    finalizados hoje."""
    db = get_db()
    ativos = db.execute(
        f"SELECT * FROM hotelaria_chamados WHERE status IN ('{STATUS_PENDENTE}', '{STATUS_ANDAMENTO}')"
    ).fetchall()
    pendentes = sum(1 for c in ativos if c["status"] == STATUS_PENDENTE)
    andamento = sum(1 for c in ativos if c["status"] == STATUS_ANDAMENTO)
    # Chamados ativos que passaram da meta de 30 min para serem assumidos
    # (mesmo indicador "Acima do tempo esperado" da Central de Enfermagem).
    acima_do_tempo = sum(1 for c in ativos if chamado_to_dict(c)["acima_do_tempo_esperado"])

    hoje_texto = para_texto(agora().replace(hour=0, minute=0, second=0, microsecond=0))
    finalizados_hoje = db.execute(
        "SELECT COUNT(*) FROM hotelaria_chamados WHERE status = ? AND finalizado_em >= ?",
        (STATUS_FINALIZADO, hoje_texto),
    ).fetchone()[0]

    # "outros" não é um serviço de hotelaria de fato (ver por_servico em
    # api_dashboard_resumo) — não entra na disputa por "mais requisitado".
    linha_top = db.execute(
        """SELECT servico, COUNT(*) as total FROM hotelaria_chamados
           WHERE criado_em >= ? AND servico != 'outros'
           GROUP BY servico ORDER BY total DESC LIMIT 1""",
        (hoje_texto,),
    ).fetchone()
    setor_mais_requisitado_hoje = SERVICOS[linha_top["servico"]]["nome"] if linha_top else None

    return jsonify({
        "pendentes": pendentes,
        "acima_do_tempo": acima_do_tempo,
        "meta_espera_min": META_ESPERA_MIN,
        "andamento": andamento,
        "setor_mais_requisitado_hoje": setor_mais_requisitado_hoje,
        "finalizados_hoje": finalizados_hoje,
    })


@hotelaria_api.route("/central/chamados", methods=["GET"])
@login_requerido
def api_listar_chamados():
    db = get_db()
    clausulas = []
    params = []

    servico = request.args.get("servico")
    status = request.args.get("status")
    andar = request.args.get("andar")
    leito = (request.args.get("leito") or "").strip()
    q = (request.args.get("q") or "").strip()

    if servico and servico != "todos":
        clausulas.append("servico = ?")
        params.append(servico)
    if status and status != "todos":
        clausulas.append("status = ?")
        params.append(status)
    elif request.args.get("status_ativos"):
        # Central: pede apenas quem ainda precisa de ação. Finalizados ficam
        # só no Histórico. Ignorado quando `status` explícito foi passado.
        clausulas.append(f"status IN ('{STATUS_PENDENTE}', '{STATUS_ANDAMENTO}')")
    if andar:
        clausulas.append("andar = ?")
        params.append(andar)
    if leito:
        clausulas.append("leito LIKE ?")
        params.append(f"%{leito}%")
    if q:
        termo = f"%{q}%"
        clausulas.append("(leito LIKE ? OR descricao LIKE ?)")
        params.extend([termo, termo])

    periodo = request.args.get("periodo")
    if periodo:
        limite_data = limite_periodo(periodo)
        if limite_data is not None:
            clausulas.append("criado_em >= ?")
            params.append(para_texto(limite_data))

    sql = "SELECT * FROM hotelaria_chamados"
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)

    # Sem faixas de prioridade/SLA na Hotelaria (ver api_central_resumo) — só
    # há ordenação por data, ao contrário da Enfermagem (que também ordena
    # por "prioridade").
    ordenar = request.args.get("ordenar", "recentes")
    ordem_sql = "criado_em ASC" if ordenar == "antigos" else "criado_em DESC"

    limite = request.args.get("limite", type=int)
    offset = request.args.get("offset", type=int) or 0
    total = db.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    limite_sql = limite or LIMITE_SEGURANCA_LISTAGEM
    linhas = db.execute(
        sql + f" ORDER BY {ordem_sql} LIMIT ? OFFSET ?", params + [limite_sql, offset]
    ).fetchall()

    resultado = []
    for row in linhas:
        nao_lida = _tem_mensagem_nao_lida(row["id"])
        avaliacao_row = _avaliacao_do_chamado(row["id"])
        resultado.append(chamado_to_dict(row, avaliacao_row=avaliacao_row, nao_lida=nao_lida))

    resposta = jsonify(resultado)
    resposta.headers["X-Total-Count"] = str(total)
    return resposta


@hotelaria_api.route("/central/chamados/<int:chamado_id>/assumir", methods=["POST"])
@login_requerido
def api_assumir_chamado(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    if row["status"] == STATUS_PENDENTE:
        db = get_db()
        db.execute(
            "UPDATE hotelaria_chamados SET status = ?, iniciado_em = ? WHERE id = ?",
            (STATUS_ANDAMENTO, para_texto(agora()), chamado_id),
        )
        db.commit()
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/central/chamados/<int:chamado_id>/status", methods=["POST"])
@login_requerido
def api_alterar_status(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    dados = request.get_json(silent=True) or {}
    novo_status = dados.get("status")

    if novo_status not in (STATUS_PENDENTE, STATUS_ANDAMENTO, STATUS_FINALIZADO):
        return jsonify({"erro": "Status inválido."}), 400

    db = get_db()
    campos = ["status = ?"]
    valores = [novo_status]
    if novo_status == STATUS_ANDAMENTO and not row["iniciado_em"]:
        campos.append("iniciado_em = ?")
        valores.append(para_texto(agora()))
    if novo_status == STATUS_FINALIZADO:
        campos.append("finalizado_em = ?")
        valores.append(para_texto(agora()))
        campos.append("confirmacao_resolucao = ?")
        valores.append(CONFIRMACAO_PENDENTE)
        campos.append("prazo_confirmacao = ?")
        valores.append(para_texto(agora() + timedelta(minutes=CONFIRMACAO_MINUTOS)))
    valores.append(chamado_id)

    db.execute(f"UPDATE hotelaria_chamados SET {', '.join(campos)} WHERE id = ?", valores)
    db.commit()
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/central/chamados/<int:chamado_id>/marcar_lido", methods=["POST"])
@login_requerido
def api_marcar_lido(chamado_id):
    _buscar_chamado_ou_404(chamado_id)
    db = get_db()
    db.execute(
        "UPDATE hotelaria_mensagens SET lida_central = 1 WHERE chamado_id = ? AND remetente = 'paciente' AND lida_central = 0",
        (chamado_id,),
    )
    db.commit()
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/dashboard/resumo", methods=["GET"])
@login_requerido
def api_dashboard_resumo():
    db = get_db()
    clausulas, params = _construir_filtros_dashboard(request.args)
    sql = "SELECT * FROM hotelaria_chamados"
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)

    linhas = db.execute(sql, params).fetchall()
    total = len(linhas)
    pendentes = sum(1 for c in linhas if c["status"] == STATUS_PENDENTE)
    andamento = sum(1 for c in linhas if c["status"] == STATUS_ANDAMENTO)
    finalizados = sum(1 for c in linhas if c["status"] == STATUS_FINALIZADO)

    tempos_totais, tempos_espera, tempos_atendimento = [], [], []
    for c in linhas:
        criado = parse_dt(c["criado_em"])
        iniciado = parse_dt(c["iniciado_em"])
        finalizado = parse_dt(c["finalizado_em"])
        if criado and finalizado:
            tempos_totais.append((finalizado - criado).total_seconds() / 60)
        if criado and iniciado:
            tempos_espera.append((iniciado - criado).total_seconds() / 60)
        if iniciado and finalizado:
            tempos_atendimento.append((finalizado - iniciado).total_seconds() / 60)

    def media(lista, casas=1):
        return round(sum(lista) / len(lista), casas) if lista else None

    # `tempo_medio_min` é mantido pelo nome/formato de sempre (número, nunca
    # None) para não quebrar quem já consome este campo; os dois novos —
    # tempo até ser assumido e tempo de atendimento em si — são mais
    # precisos e vêm como `None` quando não há dado (nunca inventados).
    tempo_medio_min = round(sum(tempos_totais) / len(tempos_totais), 1) if tempos_totais else 0

    # Avaliação média não aparece mais no Dashboard, mas o Histórico usa este
    # mesmo endpoint para seus cartões de estatística (ver
    # hotelaria/historico.js) e precisa dela.
    ids_filtrados = [c["id"] for c in linhas]
    if ids_filtrados:
        marcadores = ",".join("?" for _ in ids_filtrados)
        avaliacoes = db.execute(
            f"SELECT * FROM hotelaria_avaliacoes WHERE chamado_id IN ({marcadores})", ids_filtrados
        ).fetchall()
    else:
        avaliacoes = []
    media_avaliacao = round(sum(a["estrelas"] for a in avaliacoes) / len(avaliacoes), 2) if avaliacoes else 0

    # "outros" não é um serviço de hotelaria de fato — é só a caixa de
    # entrada de chamados encaminhados pelo Chamador de Enfermagem — então
    # não entra no gráfico "Chamados por serviço".
    por_servico = {chave: 0 for chave in SERVICOS if chave != "outros"}
    for c in linhas:
        if c["servico"] in por_servico:
            por_servico[c["servico"]] += 1

    por_status = {"pendente": pendentes, "em_andamento": andamento, "finalizado": finalizados}

    datas_criacao = [parse_dt(c["criado_em"]) for c in linhas]
    por_dia = agrupar_por_dia(datas_criacao)
    por_hora = agrupar_por_hora(datas_criacao)

    por_andar = {}
    chamados_sem_andar = 0
    # Chamados por andar separados por status (gráfico "Chamados por andar",
    # mesmo formato do Dashboard de Enfermagem, que separa por prioridade).
    # Todos os andares aparecem, mesmo com zero.
    filtro_andar = request.args.get("andar")
    por_andar_status = {
        nome: {"pendente": 0, "em_andamento": 0, "finalizado": 0}
        for nome in ANDARES if not filtro_andar or nome == filtro_andar
    }
    for c in linhas:
        valor_andar = c["andar"] if "andar" in c.keys() else None
        if valor_andar:
            por_andar[valor_andar] = por_andar.get(valor_andar, 0) + 1
            faixa = por_andar_status.setdefault(valor_andar, {"pendente": 0, "em_andamento": 0, "finalizado": 0})
            faixa[c["status"]] = faixa.get(c["status"], 0) + 1
        else:
            chamados_sem_andar += 1

    # Série "Chamados por período" (ver timeutils.serie_periodo). Para
    # "Hoje": últimas 24h com os mesmos filtros, exceto o período.
    datas_24h = []
    if request.args.get("periodo") == "hoje":
        clausulas_24h, params_24h = _construir_filtros_dashboard(request.args, ignorar_periodo=True)
        clausulas_24h.append("criado_em >= ?")
        params_24h.append(para_texto(inicio_janela_24h()))
        datas_24h = [parse_dt(r["criado_em"]) for r in db.execute(
            "SELECT criado_em FROM hotelaria_chamados WHERE " + " AND ".join(clausulas_24h), params_24h
        ).fetchall()]
    serie = serie_periodo(
        request.args.get("periodo"), datas_criacao, datas_24h,
        (request.args.get("data_inicio") or "").strip(), (request.args.get("data_fim") or "").strip(),
    )

    # Comparativo com a janela equivalente imediatamente anterior — mesmo
    # racional da Enfermagem (ver enfermagem/api.py::metricas): só calculado
    # quando há um atalho de período reconhecido, para nunca inventar uma
    # base de comparação arbitrária.
    comparativo = None
    periodo = request.args.get("periodo")
    janela_anterior = janela_comparativa_anterior(periodo) if periodo else None
    if janela_anterior is not None:
        inicio_anterior, fim_anterior = janela_anterior
        clausulas_ant, params_ant = _construir_filtros_dashboard(request.args, ignorar_periodo=True)
        clausulas_ant = clausulas_ant + ["criado_em >= ?", "criado_em < ?"]
        params_ant = params_ant + [para_texto(inicio_anterior), para_texto(fim_anterior)]
        total_anterior = db.execute(
            "SELECT COUNT(*) FROM hotelaria_chamados WHERE " + " AND ".join(clausulas_ant), params_ant
        ).fetchone()[0]
        if total_anterior > 0:
            delta_percentual = round(((total - total_anterior) / total_anterior) * 100, 1)
        else:
            delta_percentual = 100.0 if total > 0 else 0.0
        comparativo = {"total_anterior": total_anterior, "delta_percentual": delta_percentual}

    return jsonify({
        "total": total,
        "pendentes": pendentes,
        "andamento": andamento,
        "finalizados": finalizados,
        "taxa_finalizacao": round((finalizados / total) * 100, 1) if total else None,
        "tempo_medio_min": tempo_medio_min,
        "tempo_medio_espera_min": media(tempos_espera),
        "tempo_medio_atendimento_min": media(tempos_atendimento),
        "media_avaliacao": media_avaliacao,
        "total_avaliacoes": len(avaliacoes),
        "por_servico": {SERVICOS[k]["nome"]: v for k, v in por_servico.items()},
        "por_status": por_status,
        "por_dia": por_dia,
        "por_hora": por_hora,
        "por_andar": por_andar,
        "por_andar_status": por_andar_status,
        "chamados_sem_andar": chamados_sem_andar,
        "serie_periodo": serie,
        "comparativo_periodo_anterior": comparativo,
    })


# ---------------------------------------------------------------------------
# Tarefa de segundo plano: expira confirmações após 30 minutos
# ---------------------------------------------------------------------------
def _verificar_confirmacoes_expiradas(app):
    while True:
        time.sleep(30)
        conn = nova_conexao_standalone(app)
        try:
            agora_texto = para_texto(agora())
            linhas = conn.execute(
                "SELECT id FROM hotelaria_chamados WHERE status = ? AND confirmacao_resolucao = ? "
                "AND prazo_confirmacao IS NOT NULL AND prazo_confirmacao <= ?",
                (STATUS_FINALIZADO, CONFIRMACAO_PENDENTE, agora_texto),
            ).fetchall()
            if linhas:
                ids = [r["id"] for r in linhas]
                conn.executemany(
                    "UPDATE hotelaria_chamados SET confirmacao_resolucao = ? WHERE id = ?",
                    [(CONFIRMACAO_EXPIRADA, i) for i in ids],
                )
                conn.commit()
        except Exception:
            # Thread de segundo plano, fora de qualquer contexto de
            # requisição — não é possível usar `current_app` aqui, por isso
            # o logger vem do `app` recebido como parâmetro.
            app.logger.exception("Falha ao verificar confirmações expiradas da Hotelaria")
        finally:
            conn.close()


def iniciar_tarefa_background(app):
    thread = threading.Thread(target=_verificar_confirmacoes_expiradas, args=(app,), daemon=True)
    thread.start()
