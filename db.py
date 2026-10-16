# -*- coding: utf-8 -*-

import os
import psycopg2
import psycopg2.extras
from flask import current_app, g

os.environ["PGCLIENTENCODING"] = "utf-8"
os.environ["LC_MESSAGES"] = "C"

SCHEMA = """
-- ---------------------------------------------------------------------
-- Central de Chamados (PostgreSQL)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enfermagem_chamados (
    id SERIAL PRIMARY KEY,
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    categoria VARCHAR(100) NOT NULL,
    subcategoria VARCHAR(100) NOT NULL,
    detalhe TEXT,
    gravidade_base INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'pendente',
    profissional_responsavel VARCHAR(255),
    criado_em VARCHAR(50) NOT NULL,
    inicio_atendimento VARCHAR(50),
    finalizado_em VARCHAR(50),
    avaliacao INT,
    comentario_avaliacao TEXT
);
CREATE INDEX IF NOT EXISTS idx_enf_status ON enfermagem_chamados (status);
CREATE INDEX IF NOT EXISTS idx_enf_leito ON enfermagem_chamados (leito);
CREATE INDEX IF NOT EXISTS idx_enf_criado_em ON enfermagem_chamados (criado_em);

CREATE TABLE IF NOT EXISTS enfermagem_leitos_inativos (
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    desde VARCHAR(50) NOT NULL,
    PRIMARY KEY (andar, leito)
);

CREATE TABLE IF NOT EXISTS enfermagem_config (
    chave VARCHAR(191) PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enfermagem_acesso_leitos (
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    ultimo_acesso_em VARCHAR(50),
    expirado_em VARCHAR(50),
    PRIMARY KEY (andar, leito)
);

-- ---------------------------------------------------------------------
-- Central de Hotelaria
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotelaria_chamados (
    id SERIAL PRIMARY KEY,
    leito VARCHAR(100) NOT NULL,
    servico VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pendente',
    origem VARCHAR(50) NOT NULL DEFAULT 'hotelaria',
    criado_em VARCHAR(50) NOT NULL,
    iniciado_em VARCHAR(50),
    finalizado_em VARCHAR(50),
    confirmacao_resolucao VARCHAR(50) NOT NULL DEFAULT 'nao_aplicavel',
    prazo_confirmacao VARCHAR(50),
    andar VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_hotel_status ON hotelaria_chamados (status);
CREATE INDEX IF NOT EXISTS idx_hotel_leito ON hotelaria_chamados (leito);
CREATE INDEX IF NOT EXISTS idx_hotel_criado_em ON hotelaria_chamados (criado_em);

CREATE TABLE IF NOT EXISTS hotelaria_mensagens (
    id SERIAL PRIMARY KEY,
    chamado_id INT NOT NULL REFERENCES hotelaria_chamados (id) ON DELETE CASCADE,
    remetente VARCHAR(100) NOT NULL,
    mensagem TEXT NOT NULL,
    criado_em VARCHAR(50) NOT NULL,
    lida_central INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_hotel_msg_chamado ON hotelaria_mensagens (chamado_id);

CREATE TABLE IF NOT EXISTS hotelaria_avaliacoes (
    id SERIAL PRIMARY KEY,
    chamado_id INT NOT NULL UNIQUE REFERENCES hotelaria_chamados (id) ON DELETE CASCADE,
    estrelas INT NOT NULL,
    comentario TEXT,
    criado_em VARCHAR(50) NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(
            host=current_app.config.get("PGHOST", "localhost"),
            user=current_app.config.get("PGUSER", "postgres"),
            password=current_app.config.get("PGPASSWORD", "Hrg@12345"),
            dbname=current_app.config.get("PGDATABASE", "Central_Chamados"),
            port=current_app.config.get("PGPORT", 5432),
            client_encoding="utf8",
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


_MIGRACOES_COLUNAS = {
    "hotelaria_chamados": [("andar", "VARCHAR(100)")],
}


def _aplicar_migracoes(db):
    with db.cursor() as cursor:
        for tabela, colunas in _MIGRACOES_COLUNAS.items():
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (tabela,),
            )
            existentes = {row["column_name"] for row in cursor.fetchall()}
            for nome_coluna, tipo_coluna in colunas:
                if nome_coluna not in existentes:
                    cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {tipo_coluna}")
    db.commit()


def init_db(app):
    with app.app_context():
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(SCHEMA)
        db.commit()
        _aplicar_migracoes(db)
        if app.config.get("DADOS_DEMO"):
            from dados_demo import popular_se_vazio
            if popular_se_vazio(db):
                app.logger.info("Banco vazio: dados de demonstração inseridos.")
        close_db()
    app.teardown_appcontext(close_db)


def nova_conexao_standalone(app):
    """Conexão avulsa para uso FORA do contexto de requisição."""
    return psycopg2.connect(
        host=app.config.get("PGHOST", "localhost"),
        user=app.config.get("PGUSER", "postgres"),
        password=app.config.get("PGPASSWORD", "Hrg@12345"),
        dbname=app.config.get("PGDATABASE", "Central_Chamados"),
        port=app.config.get("PGPORT", 5432),
        client_encoding="utf8",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )