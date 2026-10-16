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

    PGHOST = os.environ.get("PGHOST", "localhost")
    PGPORT = int(os.environ.get("PGPORT", "5432"))
    PGUSER = os.environ.get("PGUSER", "postgres")
    PGPASSWORD = os.environ.get("PGPASSWORD", "Hrg@12345")
    PGDATABASE = os.environ.get("PGDATABASE", "Central_Chamados")

    TIMEZONE = "America/Fortaleza"

    DEBUG = _env_bool("FLASK_DEBUG", False)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)

    MAX_CONTENT_LENGTH = 256 * 1024

    DADOS_DEMO = _env_bool("DADOS_DEMO", False)

    HOTELARIA_USUARIO_TESTE = os.environ.get("HOTELARIA_USUARIO", "admin")
    HOTELARIA_SENHA_TESTE = os.environ.get("HOTELARIA_SENHA", "12345")

    ENFERMAGEM_USUARIO_TESTE = os.environ.get("ENFERMAGEM_USUARIO", "enfermagem")
    ENFERMAGEM_SENHA_TESTE = os.environ.get("ENFERMAGEM_SENHA", "12345")
