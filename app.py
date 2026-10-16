# -*- coding: utf-8 -*-
import logging
import os

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import Config
from db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.jinja_env.policies["json.dumps_kwargs"] = {"sort_keys": False}

    init_db(app)

    from portal.routes import portal_bp
    from enfermagem.routes import pages_bp as enfermagem_pages_bp
    from enfermagem.api import api_bp as enfermagem_api_bp
    from hotelaria.routes import hotelaria_pages, hotelaria_api

    app.register_blueprint(portal_bp)
    app.register_blueprint(enfermagem_pages_bp)
    app.register_blueprint(enfermagem_api_bp)
    app.register_blueprint(hotelaria_pages)
    app.register_blueprint(hotelaria_api)

    @app.get("/healthz")
    def healthz():
        """Sinal mínimo de disponibilidade para Docker e Kubernetes."""
        return "ok", 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(404)
    def nao_encontrado(e):
        if _quer_json():
            return jsonify({"erro": "Não encontrado."}), 404
        return render_template("erro.html", codigo=404, mensagem="Página não encontrada."), 404

    @app.errorhandler(409)
    def conflito(e):
        if _quer_json():
            return jsonify({"erro": str(e.description or "Conflito.")}), 409
        return render_template("erro.html", codigo=409, mensagem="Conflito ao processar a solicitação."), 409

    @app.errorhandler(Exception)
    def erro_inesperado(e):
        if isinstance(e, HTTPException):
            return e

        if app.debug:
            raise e

        app.logger.exception("Erro inesperado em %s %s", request.method, request.path)
        if _quer_json():
            return jsonify({"erro": "Erro interno. Tente novamente em instantes."}), 500
        return render_template("erro.html", codigo=500, mensagem="Algo deu errado. Tente novamente em instantes."), 500

    @app.after_request
    def _cabecalhos_seguranca(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resposta.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'",
        )
        resposta.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        return resposta

    def _quer_json():
        return request.path.startswith("/api/") or request.path.startswith("/hotelaria/api/")

    from hotelaria.routes import iniciar_tarefa_background
    iniciar_tarefa_background(app)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"], threaded=True)
