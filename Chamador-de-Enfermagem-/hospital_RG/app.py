# -*- coding: utf-8 -*-
"""Hospital Rio Grande — ponto de entrada da aplicação.

Um único processo Flask hospeda dois sistemas independentes:

  • Chamador de Enfermagem  (blueprints enfermagem_pages / enfermagem_api)
  • Central de Hotelaria     (blueprints hotelaria_pages / hotelaria_api,
                               sistema já existente, preservado)

Cada sistema tem seu próprio conjunto de tabelas e rotas — a única coisa
que compartilham é o processo/porta e, quando o paciente escolhe "OUTROS"
no Chamador de Enfermagem, uma chamada de função interna que cria o
chamado diretamente na Hotelaria (ver hotelaria/services.py). Toda a
persistência é SQLite puro (biblioteca padrão, sem ORM) e a atualização em
tempo real é feita por polling — o mesmo padrão comprovado do projeto
original, sem depender de bibliotecas externas de WebSocket.
"""
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
    # Flask 3.x usa app.json em vez das antigas chaves JSON_AS_ASCII /
    # JSON_SORT_KEYS — mantemos o comportamento pretendido (acentos legíveis
    # nas respostas e ordem das categorias preservada) explicitamente aqui.
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    # `app.json.sort_keys = False` acima só afeta `jsonify(...)`. O filtro
    # `tojson` do Jinja (usado em templates para embutir JSON, ex.:
    # `window.CATEGORIAS = {{ categorias | tojson }}`) tem sua própria
    # política padrão do Jinja2 com `sort_keys: True` — que ignora o
    # `app.json.sort_keys` e reordena os dicts alfabeticamente. Isso
    # bagunçava a ordem das categorias do Chamador de Enfermagem (que
    # precisa ser Urgência, Dor, Soro, Falar com Enfermagem, Outros — a
    # mesma ordem definida em enfermagem/constants.py). Sobrescrevemos essa
    # política para que `tojson` também preserve a ordem de inserção.
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
        # Qualquer erro HTTP "esperado" (400/401/404/409/etc., já levantado
        # via `abort(...)` em algum lugar do código, ou os handlers acima)
        # continua seguindo o fluxo normal do Flask — este handler só entra
        # em ação para exceções realmente inesperadas (bug, falha de I/O).
        if isinstance(e, HTTPException):
            return e

        if app.debug:
            # Modo debug ligado explicitamente (FLASK_DEBUG=1) só para
            # desenvolvimento local: deixa o depurador interativo do
            # Werkzeug assumir normalmente, como antes.
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
    # DEBUG vem de config.py (Config.DEBUG), controlado pela variável de
    # ambiente FLASK_DEBUG — desligado por padrão (ver config.py para o
    # racional de segurança). O servidor embutido do Flask/Werkzeug é
    # adequado para desenvolvimento e para um único hospital em rede local;
    # para exposição além disso, sirva `app` com um servidor WSGI dedicado
    # (ex.: waitress no Windows, gunicorn no Linux) atrás de HTTPS.
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"], threaded=True)
