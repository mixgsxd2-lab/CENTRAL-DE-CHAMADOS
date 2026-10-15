# -*- coding: utf-8 -*-
"""Acesso ao banco de dados — MySQL via PyMySQL (sem ORM).

Uma conexão por requisição (via flask.g), fechada automaticamente ao final
de cada requisição. As tabelas da Enfermagem e da Hotelaria vivem no mesmo
banco por simplicidade operacional, mas continuam sendo dados de sistemas
logicamente independentes — cada um só lê/escreve nas suas próprias tabelas.

As consultas usam `%s` como marcador de parâmetro e as linhas voltam como
dicionários (`row["coluna"]`).
"""
import pymysql
import pymysql.cursors
from flask import current_app, g

# Um comando por item (o PyMySQL executa um comando por vez).
SCHEMA = [
    # -----------------------------------------------------------------
    # Central de Chamados
    # -----------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS enfermagem_chamados (
        id INT AUTO_INCREMENT PRIMARY KEY,
        andar VARCHAR(255) NOT NULL,
        leito VARCHAR(255) NOT NULL,
        categoria VARCHAR(255) NOT NULL,
        subcategoria VARCHAR(255) NOT NULL,
        detalhe TEXT,
        gravidade_base INT NOT NULL DEFAULT 0,
        status VARCHAR(50) NOT NULL DEFAULT 'pendente',
        profissional_responsavel VARCHAR(255),
        criado_em VARCHAR(40) NOT NULL,
        inicio_atendimento VARCHAR(40),
        finalizado_em VARCHAR(40),
        avaliacao INT,
        comentario_avaliacao TEXT,
        INDEX idx_enf_status (status),
        INDEX idx_enf_leito (leito),
        INDEX idx_enf_criado_em (criado_em)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    # Leitos desativados pela tela "Controle de Leitos" (Configurações). Um
    # leito só aparece aqui enquanto estiver INATIVO — por padrão, todo
    # leito cadastrado em `andares.py` está ativo.
    """CREATE TABLE IF NOT EXISTS enfermagem_leitos_inativos (
        andar VARCHAR(255) NOT NULL,
        leito VARCHAR(255) NOT NULL,
        desde VARCHAR(40) NOT NULL,
        PRIMARY KEY (andar, leito)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    # Configurações chave/valor da Enfermagem — token fixo dos QR Codes e
    # horário do último "Expirar todos" (ver enfermagem/acesso.py).
    """CREATE TABLE IF NOT EXISTS enfermagem_config (
        chave VARCHAR(100) PRIMARY KEY,
        valor TEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    # Acesso do paciente pelo QR Code do leito (ver enfermagem/acesso.py).
    # Guarda SÓ horários — nenhum dado do paciente:
    #   ultimo_acesso_em: último escaneamento do QR Code deste leito
    #   expirado_em:      último "Expirar acesso" da Central para o leito
    """CREATE TABLE IF NOT EXISTS enfermagem_acesso_leitos (
        andar VARCHAR(255) NOT NULL,
        leito VARCHAR(255) NOT NULL,
        ultimo_acesso_em VARCHAR(40),
        expirado_em VARCHAR(40),
        PRIMARY KEY (andar, leito)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    # -----------------------------------------------------------------
    # Central de Hotelaria
    # -----------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS hotelaria_chamados (
        id INT AUTO_INCREMENT PRIMARY KEY,
        leito VARCHAR(255) NOT NULL,
        servico VARCHAR(255) NOT NULL,
        descricao TEXT NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pendente',
        origem VARCHAR(50) NOT NULL DEFAULT 'hotelaria',
        criado_em VARCHAR(40) NOT NULL,
        iniciado_em VARCHAR(40),
        finalizado_em VARCHAR(40),
        confirmacao_resolucao VARCHAR(50) NOT NULL DEFAULT 'nao_aplicavel',
        prazo_confirmacao VARCHAR(40),
        andar VARCHAR(255),
        INDEX idx_hotel_status (status),
        INDEX idx_hotel_leito (leito),
        INDEX idx_hotel_criado_em (criado_em)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    """CREATE TABLE IF NOT EXISTS hotelaria_mensagens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        chamado_id INT NOT NULL,
        remetente VARCHAR(50) NOT NULL,
        mensagem TEXT NOT NULL,
        criado_em VARCHAR(40) NOT NULL,
        lida_central TINYINT NOT NULL DEFAULT 0,
        INDEX idx_hotel_msg_chamado (chamado_id),
        CONSTRAINT fk_hotel_msg_chamado FOREIGN KEY (chamado_id)
            REFERENCES hotelaria_chamados (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    """CREATE TABLE IF NOT EXISTS hotelaria_avaliacoes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        chamado_id INT NOT NULL UNIQUE,
        estrelas INT NOT NULL,
        comentario TEXT,
        criado_em VARCHAR(40) NOT NULL,
        CONSTRAINT fk_hotel_aval_chamado FOREIGN KEY (chamado_id)
            REFERENCES hotelaria_chamados (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]


class Conexao:
    """Conexão PyMySQL com o atalho `conexao.execute(sql, params)`, que
    abre o cursor e devolve-o já executado."""

    def __init__(self, config):
        self._conn = pymysql.connect(
            host=config["MYSQL_HOST"],
            port=config["MYSQL_PORT"],
            user=config["MYSQL_USER"],
            password=config["MYSQL_PASSWORD"],
            database=config["MYSQL_DATABASE"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, seq_params):
        cur = self._conn.cursor()
        cur.executemany(sql, seq_params)
        return cur

    def criar_tabelas(self):
        cur = self._conn.cursor()
        for comando in SCHEMA:
            cur.execute(comando)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    if "db" not in g:
        g.db = Conexao(current_app.config)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        db.criar_tabelas()
        if app.config.get("DADOS_DEMO"):
            # Chamados fictícios de demonstração — só quando o banco ainda
            # não tem NENHUM chamado; nunca apaga nada (ver dados_demo.py).
            from dados_demo import popular_se_vazio
            if popular_se_vazio(db):
                app.logger.info("Banco vazio: dados de demonstração inseridos.")
        close_db()
    app.teardown_appcontext(close_db)


def nova_conexao_standalone(app):
    """Conexão avulsa para uso FORA do contexto de requisição (ex.: a
    thread de segundo plano que expira confirmações de hotelaria)."""
    return Conexao(app.config)
