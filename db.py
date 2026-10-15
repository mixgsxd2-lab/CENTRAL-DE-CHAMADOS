# -*- coding: utf-8 -*-

import pymysql
import pymysql.cursors
from flask import current_app, g

SCHEMA = """
-- ---------------------------------------------------------------------
-- Central de Chamados
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enfermagem_chamados (
    id INT AUTO_INCREMENT PRIMARY KEY,
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
    comentario_avaliacao TEXT,
    INDEX idx_enf_status (status),
    INDEX idx_enf_leito (leito),
    INDEX idx_enf_criado_em (criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS enfermagem_leitos_inativos (
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    desde VARCHAR(50) NOT NULL,
    PRIMARY KEY (andar, leito)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS enfermagem_config (
    chave VARCHAR(191) PRIMARY KEY,
    valor TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS enfermagem_acesso_leitos (
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    ultimo_acesso_em VARCHAR(50),
    expirado_em VARCHAR(50),
    PRIMARY KEY (andar, leito)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Central de Hotelaria
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotelaria_chamados (
    id INT AUTO_INCREMENT PRIMARY KEY,
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
    andar VARCHAR(100),
    INDEX idx_hotel_status (status),
    INDEX idx_hotel_leito (leito),
    INDEX idx_hotel_criado_em (criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hotelaria_mensagens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chamado_id INT NOT NULL,
    remetente VARCHAR(100) NOT NULL,
    mensagem TEXT NOT NULL,
    criado_em VARCHAR(50) NOT NULL,
    lida_central INT NOT NULL DEFAULT 0,
    INDEX idx_hotel_msg_chamado (chamado_id),
    CONSTRAINT fk_hotel_msg_chamado FOREIGN KEY (chamado_id) REFERENCES hotelaria_chamados (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hotelaria_avaliacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chamado_id INT NOT NULL UNIQUE,
    estrelas INT NOT NULL,
    comentario TEXT,
    criado_em VARCHAR(50) NOT NULL,
    CONSTRAINT fk_hotel_av_chamado FOREIGN KEY (chamado_id) REFERENCES hotelaria_chamados (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=current_app.config.get("MYSQL_HOST", "localhost"),
            user=current_app.config.get("MYSQL_USER", "root"),
            password=current_app.config.get("MYSQL_PASSWORD", "Hrg@12345"),
            database=current_app.config.get("MYSQL_DATABASE", "Central_Chamados"),
            port=current_app.config.get("MYSQL_PORT", 3306),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
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
            cursor.execute(f"SHOW COLUMNS FROM {tabela}")
            existentes = {row["Field"] for row in cursor.fetchall()}
            for nome_coluna, tipo_coluna in colunas:
                if nome_coluna not in existentes:
                    cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {tipo_coluna}")
    db.commit()


def init_db(app):
    with app.app_context():
        db = get_db()
        with db.cursor() as cursor:
            for statement in SCHEMA.split(";"):
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)
        db.commit()
        _aplicar_migracoes(db)
        if app.config.get("DADOS_DEMO"):
            from dados_demo import popular_se_vazio
            if popular_se_vazio(db):
                app.logger.info("Banco vazio: dados de demonstração inseridos.")
        close_db()
    app.teardown_appcontext(close_db)


def nova_conexao_standalone(app):
    """Conexão avulsa para uso FORA do contexto de requisição (ex.: a
    thread de segundo plano que expira confirmações de hotelaria)[cite: 1]."""
    return pymysql.connect(
        host=app.config.get("MYSQL_HOST", "localhost"),
        user=app.config.get("MYSQL_USER", "root"),
        password=app.config.get("MYSQL_PASSWORD", "Hrg@12345"),
        database=app.config.get("MYSQL_DATABASE", "Central_Chamados"),
        port=app.config.get("MYSQL_PORT", 3306),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )