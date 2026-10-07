# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_bool(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "hospital-rio-grande-chave-dev")

    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "hospital_rio_grande.db")
    )

    # (Configuração de JSON — acentos legíveis e ordem das categorias
    # preservada — é feita em app.py via `app.json`, API do Flask 3.x.)
    TIMEZONE = "America/Fortaleza"

    # Modo debug do Flask: OFF por padrão (item de segurança — com debug=True
    # qualquer erro inesperado mostra a stack trace completa, com trechos de
    # código-fonte, para quem estiver navegando). Para depurar localmente,
    # rode com a variável de ambiente FLASK_DEBUG=1.
    DEBUG = _env_bool("FLASK_DEBUG", False)

    # Cookie de sessão: HttpOnly (não acessível via JS — já é o padrão do
    # Flask, explicitado aqui) e SameSite=Lax (o cookie não é enviado em
    # requisições de origem cruzada iniciadas por navegação simples/POST de
    # formulário de outro site — mitiga CSRF sem precisar de token extra,
    # já que toda mutação de estado deste sistema é feita via fetch/JSON, não
    # formulário cross-site). SECURE fica desligado por padrão para não
    # quebrar acesso via HTTP simples na rede interna do hospital; ligue com
    # SESSION_COOKIE_SECURE=1 quando o sistema estiver atrás de HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)

    # Limite de tamanho do corpo da requisição (256 KB) — nenhum endpoint
    # deste sistema precisa de payloads maiores que isso; barato de aplicar e
    # mitiga envio abusivo de corpos gigantes.
    MAX_CONTENT_LENGTH = 256 * 1024

    # Dados fictícios de demonstração (Enfermagem + Hotelaria): inseridos
    # automaticamente na inicialização SOMENTE se o banco não tiver nenhum
    # chamado — ver dados_demo.py. Nunca apagam nada. Desligado por padrão (DADOS_DEMO=1 liga). Para um banco real,
    # sem dados de teste, rode com DADOS_DEMO=0.
    DADOS_DEMO = _env_bool("DADOS_DEMO", False)

    # Credenciais de teste da Central de Hotelaria (herdadas do sistema já
    # existente — ver hotelaria/routes.py).
    HOTELARIA_USUARIO_TESTE = os.environ.get("HOTELARIA_USUARIO", "admin")
    HOTELARIA_SENHA_TESTE = os.environ.get("HOTELARIA_SENHA", "12345")

    # Credenciais de teste da área administrativa do Chamador de Enfermagem
    # (ver enfermagem/auth.py e enfermagem/routes.py).
    ENFERMAGEM_USUARIO_TESTE = os.environ.get("ENFERMAGEM_USUARIO", "enfermagem")
    ENFERMAGEM_SENHA_TESTE = os.environ.get("ENFERMAGEM_SENHA", "12345")
