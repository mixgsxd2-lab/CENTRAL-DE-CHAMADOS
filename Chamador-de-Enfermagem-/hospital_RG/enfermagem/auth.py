# -*- coding: utf-8 -*-
"""Autenticação da área administrativa do Chamador de Enfermagem.

Mesmo padrão já usado pela Central de Hotelaria (hotelaria/routes.py):
sessão simples de servidor + credenciais de teste configuráveis por
variável de ambiente. Fica num módulo próprio (em vez de dentro de
routes.py) porque tanto as PÁGINAS (enfermagem/routes.py) quanto a API
usada só pela equipe (enfermagem/api.py) precisam do mesmo decorator —
proteger só a tela e deixar a API aberta não protegeria de verdade os
dados dos pacientes.
"""
from functools import wraps

from flask import g, jsonify, make_response, redirect, render_template, request, session, url_for

from enfermagem.acesso import acesso_atual, tinha_acesso


def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("enfermagem_logado"):
            if request.path.startswith("/api/"):
                return jsonify({"erro": "Login necessário."}), 401
            return redirect(url_for("enfermagem_pages.login", proximo=request.path))
        return f(*args, **kwargs)
    return decorated


def tela_acesso_expirado():
    """Tela mostrada no celular do paciente quando a liberação do QR Code
    acabou (meia-noite ou "Expirar acesso" na Central) ou nunca existiu."""
    resposta = make_response(render_template("enfermagem/acesso_expirado.html", expirado=tinha_acesso()), 403)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def acesso_paciente_requerido(f):
    """Protege as telas/ações do paciente: só quem escaneou o QR Code do
    leito HOJE (e não foi revogado depois) pode usar — ver
    enfermagem/acesso.py. A liberação vigente fica em `g.acesso_paciente`."""
    @wraps(f)
    def decorated(*args, **kwargs):
        acesso = acesso_atual()
        if acesso is None:
            if request.path.startswith("/api/"):
                return jsonify({
                    "erro": "Acesso expirado. Escaneie o QR Code do seu leito.",
                    "acesso_expirado": True,
                }), 403
            return tela_acesso_expirado()
        g.acesso_paciente = acesso
        return f(*args, **kwargs)
    return decorated
