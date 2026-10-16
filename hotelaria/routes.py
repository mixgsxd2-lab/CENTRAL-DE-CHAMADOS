# -*- coding: utf-8 -*-
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

MAX_DESCRICAO = 500
MAX_MENSAGEM = 500
MAX_COMENTARIO = 300
LIMITE_SEGURANCA_LISTAGEM = 500


def _construir_filtros_dashboard(args, ignorar_periodo=False):
    clausulas = []
    params = []

    servico = args.get("servico")
    status = args.get("status")
    andar = args.get("andar")
    q = (args.get("q") or "").strip()

    if servico and servico != "todos":
        clausulas.append("servico = %s")
        params.append(servico)
    if status and status != "todos":
        clausulas.append("status = %s")
        params.append(status)
    if andar:
        clausulas.append("andar = %s")
        params.append(andar)
    if q:
        termo = f"%{q}%"
        clausulas.append("(leito LIKE %s OR descricao LIKE %s)")
        params.extend([termo, termo])

    if not ignorar_periodo:
        periodo = args.get("periodo")
        if periodo:
            limite = limite_periodo(periodo)
            if limite is not None:
                clausulas.append("criado_em >= %s")
                params.append(para_texto(limite))

        data_inicio = (args.get("data_inicio") or "").strip()
        data_fim = (args.get("data_fim") or "").strip()
        if data_inicio:
            clausulas.append("criado_em >= %s")
            params.append(f"{data_inicio} 00:00:00")
        if data_fim:
            clausulas.append("criado_em <= %s")
            params.append(f"{data_fim} 23:59:59")

    return clausulas, params

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

@hotelaria_pages.route("/paciente")
def paciente():
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

def _buscar_chamado_ou_404(chamado_id):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM hotelaria_chamados WHERE id = %s", (chamado_id,))
        row = cursor.fetchone()
    if row is None:
        abort(404, description="Chamado não encontrado.")
    return row


def _mensagens_do_chamado(chamado_id):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM hotelaria_mensagens WHERE chamado_id = %s ORDER BY criado_em ASC, id ASC", (chamado_id,))
        linhas = cursor.fetchall()
    return [mensagem_to_dict(r) for r in linhas]


def _avaliacao_do_chamado(chamado_id):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM hotelaria_avaliacoes WHERE chamado_id = %s", (chamado_id,))
        return cursor.fetchone()


def _tem_mensagem_nao_lida(chamado_id):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM hotelaria_mensagens WHERE chamado_id = %s AND remetente = 'paciente' AND lida_central = 0", (chamado_id,))
        row = cursor.fetchone()
    return row["total"] > 0


def _chamado_completo_dict(chamado_id):
    row = _buscar_chamado_ou_404(chamado_id)
    mensagens = _mensagens_do_chamado(chamado_id)
    avaliacao_row = _avaliacao_do_chamado(chamado_id)
    nao_lida = any(m["remetente"] == "paciente" and not m["lida_central"] for m in mensagens)
    return chamado_to_dict(row, mensagens=mensagens, avaliacao_row=avaliacao_row, nao_lida=nao_lida)

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
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM hotelaria_chamados WHERE leito = %s ORDER BY criado_em DESC LIMIT 20", (leito,))
        linhas = cursor.fetchall()
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
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO hotelaria_mensagens (chamado_id, remetente, mensagem, criado_em, lida_central) VALUES (%s, %s, %s, %s, %s)",
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
    with db.cursor() as cursor:
        cursor.execute("UPDATE hotelaria_chamados SET confirmacao_resolucao = %s WHERE id = %s", (novo_valor, chamado_id))
    db.commit()
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/chamados/<int:chamado_id>/avaliacao", methods=["POST"])
def api_criar_avaliacao(chamado_id):
    _buscar_chamado_ou_404(chamado_id)
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

    with db.cursor() as cursor:
        cursor.execute(
             "INSERT INTO hotelaria_avaliacoes (chamado_id, estrelas, comentario, criado_em) VALUES (%s, %s, %s, %s) RETURNING id",
            (chamado_id, estrelas, comentario, para_texto(agora())),
        )
        avaliacao_id = cursor.fetchone()["id"]
    db.commit()

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM hotelaria_avaliacoes WHERE id = %s", (avaliacao_id,))
        nova = cursor.fetchone()
    return jsonify(avaliacao_to_dict(nova)), 201

@hotelaria_api.route("/central/resumo", methods=["GET"])
@login_requerido
def api_central_resumo():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(f"SELECT * FROM hotelaria_chamados WHERE status IN ('{STATUS_PENDENTE}', '{STATUS_ANDAMENTO}')")
        ativos = cursor.fetchall()
    pendentes = sum(1 for c in ativos if c["status"] == STATUS_PENDENTE)
    andamento = sum(1 for c in ativos if c["status"] == STATUS_ANDAMENTO)
    acima_do_tempo = sum(1 for c in ativos if chamado_to_dict(c)["acima_do_tempo_esperado"])

    hoje_texto = para_texto(agora().replace(hour=0, minute=0, second=0, microsecond=0))
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM hotelaria_chamados WHERE status = %s AND finalizado_em >= %s",
            (STATUS_FINALIZADO, hoje_texto),
        )
        finalizados_hoje = cursor.fetchone()["total"]

    with db.cursor() as cursor:
        cursor.execute(
            """SELECT servico, COUNT(*) as total FROM hotelaria_chamados
            WHERE criado_em >= %s AND servico != 'outros'
            GROUP BY servico ORDER BY total DESC LIMIT 1""",
            (hoje_texto,)
        )
        linha_top = cursor.fetchone()
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
        clausulas.append("servico = %s")
        params.append(servico)
    if status and status != "todos":
        clausulas.append("status = %s")
        params.append(status)
    elif request.args.get("status_ativos"):
        clausulas.append(f"status IN ('{STATUS_PENDENTE}', '{STATUS_ANDAMENTO}')")
    if andar:
        clausulas.append("andar = %s")
        params.append(andar)
    if leito:
        clausulas.append("leito LIKE %s")
        params.append(f"%{leito}%")
    if q:
        termo = f"%{q}%"
        clausulas.append("(leito LIKE %s OR descricao LIKE %s)")
        params.extend([termo, termo])

    periodo = request.args.get("periodo")
    if periodo:
        limite_data = limite_periodo(periodo)
        if limite_data is not None:
            clausulas.append("criado_em >= %s")
            params.append(para_texto(limite_data))

    sql = "SELECT * FROM hotelaria_chamados"
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)

    ordenar = request.args.get("ordenar", "recentes")
    ordem_sql = "criado_em ASC" if ordenar == "antigos" else "criado_em DESC"

    limite = request.args.get("limite", type=int)
    offset = request.args.get("offset", type=int) or 0
    with db.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM ({sql}) AS contagem", params)
        total = cursor.fetchone()["total"]

    limite_sql = limite or LIMITE_SEGURANCA_LISTAGEM
    with db.cursor() as cursor:
        cursor.execute(sql + f" ORDER BY {ordem_sql} LIMIT %s OFFSET %s", params + [limite_sql, offset])
        linhas = cursor.fetchall()

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
        with db.cursor() as cursor:
            cursor.execute(
                "UPDATE hotelaria_chamados SET status = %s, iniciado_em = %s WHERE id = %s",
                (STATUS_ANDAMENTO, para_texto(agora()), chamado_id)
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
    campos = ["status = %s"]
    valores = [novo_status]
    if novo_status == STATUS_ANDAMENTO and not row["iniciado_em"]:
        campos.append("iniciado_em = %s")
        valores.append(para_texto(agora()))
    if novo_status == STATUS_FINALIZADO:
        campos.append("finalizado_em = %s")
        valores.append(para_texto(agora()))
        campos.append("confirmacao_resolucao = %s")
        valores.append(CONFIRMACAO_PENDENTE)
        campos.append("prazo_confirmacao = %s")
        valores.append(para_texto(agora() + timedelta(minutes=CONFIRMACAO_MINUTOS)))
    valores.append(chamado_id)

    with db.cursor() as cursor:
        cursor.execute(f"UPDATE hotelaria_chamados SET {', '.join(campos)} WHERE id = %s", valores)
    db.commit()
    return jsonify(_chamado_completo_dict(chamado_id))


@hotelaria_api.route("/central/chamados/<int:chamado_id>/marcar_lido", methods=["POST"])
@login_requerido
def api_marcar_lido(chamado_id):
    _buscar_chamado_ou_404(chamado_id)
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("UPDATE hotelaria_mensagens SET lida_central = 1 WHERE chamado_id = %s AND remetente = 'paciente' AND lida_central = 0", (chamado_id,))
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

    with db.cursor() as cursor:
        cursor.execute(sql, params)
        linhas = cursor.fetchall()
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

    tempo_medio_min = round(sum(tempos_totais) / len(tempos_totais), 1) if tempos_totais else 0

    ids_filtrados = [c["id"] for c in linhas]
    if ids_filtrados:
        marcadores = ",".join("%s" for _ in ids_filtrados)
        with db.cursor() as cursor:
            cursor.execute(f"SELECT * FROM hotelaria_avaliacoes WHERE chamado_id IN ({marcadores})", ids_filtrados)
            avaliacoes = cursor.fetchall()
    else:
        avaliacoes = []
    media_avaliacao = round(sum(a["estrelas"] for a in avaliacoes) / len(avaliacoes), 2) if avaliacoes else 0

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

    datas_24h = []
    if request.args.get("periodo") == "hoje":
        clausulas_24h, params_24h = _construir_filtros_dashboard(request.args, ignorar_periodo=True)
        clausulas_24h.append("criado_em >= %s")
        params_24h.append(para_texto(inicio_janela_24h()))
        with db.cursor() as cursor:
            cursor.execute("SELECT criado_em FROM hotelaria_chamados WHERE " + " AND ".join(clausulas_24h), params_24h)
            datas_24h = [parse_dt(r["criado_em"]) for r in cursor.fetchall()]
    serie = serie_periodo(
        request.args.get("periodo"), datas_criacao, datas_24h,
        (request.args.get("data_inicio") or "").strip(), (request.args.get("data_fim") or "").strip(),
    )

    comparativo = None
    periodo = request.args.get("periodo")
    janela_anterior = janela_comparativa_anterior(periodo) if periodo else None
    if janela_anterior is not None:
        inicio_anterior, fim_anterior = janela_anterior
        clausulas_ant, params_ant = _construir_filtros_dashboard(request.args, ignorar_periodo=True)
        clausulas_ant = clausulas_ant + ["criado_em >= %s", "criado_em < %s"]
        params_ant = params_ant + [para_texto(inicio_anterior), para_texto(fim_anterior)]
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM hotelaria_chamados WHERE " + " AND ".join(clausulas_ant), params_ant)
            total_anterior = cursor.fetchone()["total"]
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

def _verificar_confirmacoes_expiradas(app):
    while True:
        time.sleep(30)
        conn = nova_conexao_standalone(app)
        try:
            agora_texto = para_texto(agora())
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM hotelaria_chamados WHERE status = %s AND confirmacao_resolucao = %s "
                    "AND prazo_confirmacao IS NOT NULL AND prazo_confirmacao <= %s",
                    (STATUS_FINALIZADO, CONFIRMACAO_PENDENTE, agora_texto)
                )
                linhas = cursor.fetchall()
                if linhas:
                    ids = [r["id"] for r in linhas]
                    cursor.executemany(
                        "UPDATE hotelaria_chamados SET confirmacao_resolucao = %s WHERE id = %s",
                        [(CONFIRMACAO_EXPIRADA, i) for i in ids],
                    )
                    conn.commit()
        except Exception:
            app.logger.exception("Falha ao verificar confirmações expiradas da Hotelaria")
        finally:
            conn.close()


def iniciar_tarefa_background(app):
    thread = threading.Thread(target=_verificar_confirmacoes_expiradas, args=(app,), daemon=True)
    thread.start()