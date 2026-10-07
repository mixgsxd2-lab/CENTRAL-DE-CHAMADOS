# -*- coding: utf-8 -*-
import io

from flask import (
    Blueprint, Response, abort, current_app, flash, g, make_response, redirect, render_template, request,
    session, url_for,
)

from db import get_db
from ratelimit import permitido as rate_limit_permitido
from andares import leito_valido as _leito_valido_andares
from enfermagem.acesso import conceder_acesso, obter_token, token_valido
from enfermagem.auth import acesso_paciente_requerido, login_requerido
from enfermagem.constants import ANDARES, CATEGORIAS
from enfermagem.leitos import leito_ativo, listar_leitos

pages_bp = Blueprint("enfermagem_pages", __name__, url_prefix="/enfermagem")


def url_acesso_paciente(andar=None, leito=None):
    """URL completa (com o token fixo de acesso) que o QR Code deve
    apontar — usada tanto para gerar o QR quanto para mostrar o link em
    texto na tela de Configurações. Quando `andar`/`leito` são passados
    (QR Code impresso e afixado num leito específico), a tela do paciente
    já abre com esse leito pré-selecionado (ver `paciente_inicio`)."""
    params = {"acesso": obter_token()}
    if andar and leito:
        params.update(andar=andar, leito=leito)
    return url_for("enfermagem_pages.paciente_inicio", _external=True, **params)


def _categorias_publicas():
    """Versão das categorias sem os pesos de gravidade (uso interno do
    motor de prioridade) — só o que a tela do paciente precisa exibir."""
    return {
        nome: {
            "cor": dados["cor"],
            "icone": dados["icone"],
            "descricao": dados["descricao"],
            "opcoes": [texto for texto, _peso in dados["opcoes"]],
        }
        for nome, dados in CATEGORIAS.items()
    }


def _sem_cache(resposta):
    # Telas do paciente nunca podem vir do cache do navegador (botão Voltar
    # / reabrir a aba): depois da meia-noite ou de uma revogação, o servidor
    # precisa ser consultado de novo para mostrar "Acesso expirado".
    resposta = make_response(resposta)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@pages_bp.route("/")
def paciente_inicio():
    # Entrada pelo QR Code afixado no leito: `?acesso=<token fixo>&andar=...
    # &leito=...`. Libera este navegador até a próxima meia-noite e
    # redireciona para a URL sem o token — recarregar a página depois NÃO
    # renova o acesso; só escanear o QR Code de novo (ver enfermagem/acesso.py).
    token = request.args.get("acesso")
    if token is not None:
        if not token_valido(token):
            return render_template(
                "erro.html", codigo=403,
                mensagem="Acesso restrito. Use o QR Code fornecido pela equipe de enfermagem para abrir um chamado.",
            ), 403
        andar = (request.args.get("andar") or "").strip()
        leito = (request.args.get("leito") or "").strip()
        if not _leito_valido_andares(andar, leito):
            return render_template(
                "erro.html", codigo=400,
                mensagem="Leito não identificado. Escaneie o QR Code afixado no seu leito para abrir um chamado.",
            ), 400
        if not leito_ativo(andar, leito):
            return render_template("enfermagem/qr_desativado.html"), 200
        conceder_acesso(andar, leito)
        return _sem_cache(redirect(url_for("enfermagem_pages.paciente_inicio")))
    return _tela_paciente()


@acesso_paciente_requerido
def _tela_paciente():
    # O leito vem SEMPRE da liberação gravada ao escanear o QR Code — não
    # existe tela de "escolha seu leito" no fluxo do paciente.
    andar, leito = g.acesso_paciente["andar"], g.acesso_paciente["leito"]
    if not leito_ativo(andar, leito):
        return _sem_cache(render_template("enfermagem/qr_desativado.html"))

    return _sem_cache(render_template(
        "enfermagem/paciente.html",
        categorias=_categorias_publicas(),
        leito_preenchido={"andar": andar, "leito": leito},
    ))


@pages_bp.route("/acompanhar-hotelaria/<int:chamado_id>")
@acesso_paciente_requerido
def acompanhar_hotelaria(chamado_id):
    """Acompanhamento de um pedido de Hotelaria feito pelo paciente (categoria
    "Outros") — vive aqui, na área do paciente da Enfermagem, no lugar da
    antiga tela /hotelaria/paciente."""
    db = get_db()
    row = db.execute("SELECT id FROM hotelaria_chamados WHERE id = ?", (chamado_id,)).fetchone()
    if row is None:
        abort(404, description="Chamado não encontrado.")
    return _sem_cache(render_template("enfermagem/acompanhar_hotelaria.html", chamado_id=chamado_id))


@pages_bp.route("/acompanhar/<int:chamado_id>")
@acesso_paciente_requerido
def acompanhar(chamado_id):
    db = get_db()
    row = db.execute("SELECT id FROM enfermagem_chamados WHERE id = ?", (chamado_id,)).fetchone()
    if row is None:
        abort(404, description="Chamado não encontrado.")
    return _sem_cache(render_template("enfermagem/acompanhar.html", chamado_id=chamado_id))


# ---------------------------------------------------------------------------
# Autenticação da área administrativa (mesmo padrão da Central de
# Hotelaria — ver enfermagem/auth.py e hotelaria/routes.py).
# ---------------------------------------------------------------------------
@pages_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not rate_limit_permitido(f"enfermagem:{request.remote_addr}"):
            flash("Muitas tentativas de login. Aguarde alguns minutos e tente novamente.")
            return render_template("enfermagem/login.html"), 429

        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()
        if (
            usuario == current_app.config["ENFERMAGEM_USUARIO_TESTE"]
            and senha == current_app.config["ENFERMAGEM_SENHA_TESTE"]
        ):
            session["enfermagem_logado"] = True
            session["enfermagem_usuario"] = usuario
            proximo = request.args.get("proximo") or url_for("enfermagem_pages.central")
            return redirect(proximo)
        flash("Usuário ou senha inválidos.")
    return render_template("enfermagem/login.html")


@pages_bp.route("/logout")
def logout():
    session.pop("enfermagem_logado", None)
    session.pop("enfermagem_usuario", None)
    return redirect(url_for("portal.inicio"))


@pages_bp.route("/dashboard")
@login_requerido
def dashboard():
    return render_template(
        "enfermagem/dashboard.html",
        andares=list(ANDARES.keys()),
        categorias=list(CATEGORIAS.keys()),
    )


@pages_bp.route("/central")
@login_requerido
def central():
    return render_template(
        "enfermagem/central.html",
        andares=list(ANDARES.keys()),
        categorias=list(CATEGORIAS.keys()),
    )


@pages_bp.route("/historico")
@login_requerido
def historico():
    return render_template(
        "enfermagem/historico.html",
        andares=list(ANDARES.keys()),
        categorias=list(CATEGORIAS.keys()),
    )


@pages_bp.route("/configuracoes")
@login_requerido
def configuracoes():
    return render_template(
        "enfermagem/configuracoes.html",
        leitos_por_andar=listar_leitos(),
        url_acesso_paciente=url_acesso_paciente(),
    )


@pages_bp.route("/configuracoes/qrcode.svg")
@login_requerido
def qrcode_acesso_paciente():
    """QR Code (SVG) do link atual — para a equipe imprimir e afixar no
    leito/quarto. Gerado na hora a cada acesso (nunca salvo em disco); o
    token é fixo, então o QR Code de um leito nunca muda. Aceita `?andar=...&leito=...` opcionais
    para gerar o QR Code JÁ COM O LEITO daquele quarto (ver
    `paciente_inicio`); sem eles, gera o QR Code genérico usado no card de
    Configurações."""
    import qrcode
    import qrcode.image.svg

    andar = (request.args.get("andar") or "").strip()
    leito = (request.args.get("leito") or "").strip()
    if not _leito_valido_andares(andar, leito):
        andar = leito = None

    imagem = qrcode.make(
        url_acesso_paciente(andar, leito), image_factory=qrcode.image.svg.SvgPathImage, box_size=10,
    )
    buffer = io.BytesIO()
    imagem.save(buffer)
    resposta = Response(buffer.getvalue(), mimetype="image/svg+xml")
    resposta.headers["Cache-Control"] = "no-store"
    return resposta
