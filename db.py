# -*- coding: utf-8 -*-
"""Acesso ao banco de dados — SQLite puro (sem ORM), biblioteca padrão.

Uma conexão por requisição (via flask.g), fechada automaticamente ao final
de cada requisição. As duas "tabelas de chamados" (Enfermagem e Hotelaria)
vivem no mesmo arquivo .db por simplicidade operacional, mas continuam
sendo dados de sistemas logicamente independentes — cada um só lê/escreve
nas suas próprias tabelas.

`PRAGMA journal_mode=WAL` é ligado para permitir leituras e escritas
simultâneas de vários pacientes e vários administradores sem que um
bloqueie o outro (múltiplos dispositivos ao mesmo tempo — item 11 da
especificação).
"""
import sqlite3

from flask import current_app, g

SCHEMA = """
-- ---------------------------------------------------------------------
-- Chamador de Enfermagem
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enfermagem_chamados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    andar TEXT NOT NULL,
    leito TEXT NOT NULL,
    categoria TEXT NOT NULL,
    subcategoria TEXT NOT NULL,
    detalhe TEXT,
    gravidade_base INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pendente',
    profissional_responsavel TEXT,
    criado_em TEXT NOT NULL,
    inicio_atendimento TEXT,
    finalizado_em TEXT,
    avaliacao INTEGER,
    comentario_avaliacao TEXT
);
CREATE INDEX IF NOT EXISTS idx_enf_status ON enfermagem_chamados (status);
CREATE INDEX IF NOT EXISTS idx_enf_leito ON enfermagem_chamados (leito);
CREATE INDEX IF NOT EXISTS idx_enf_criado_em ON enfermagem_chamados (criado_em);

-- Leitos desativados pela tela "Controle de Leitos" (Configurações). Um
-- leito só aparece aqui enquanto estiver INATIVO — por padrão, todo leito
-- cadastrado em `andares.py` está ativo, então a ausência de linha já
-- significa "ativo" (evita ter que semear milhares de linhas "ativo=1").
CREATE TABLE IF NOT EXISTS enfermagem_leitos_inativos (
    andar TEXT NOT NULL,
    leito TEXT NOT NULL,
    desde TEXT NOT NULL,
    PRIMARY KEY (andar, leito)
);

-- Configurações simples de chave/valor da Enfermagem — hoje guarda o token
-- fixo dos QR Codes e o horário do último "Expirar todos" (ver
-- enfermagem/acesso.py), mas fica
-- genérica para não precisar de uma tabela nova a cada configuração futura.
CREATE TABLE IF NOT EXISTS enfermagem_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Acesso do paciente pelo QR Code do leito (ver enfermagem/acesso.py).
-- Uma linha por leito, criada na primeira vez que algo acontece com ele.
-- Guarda SÓ horários — nenhum dado do paciente (nome, aparelho, etc.):
--   ultimo_acesso_em: última vez que o QR Code deste leito foi escaneado
--                     (só para a Central mostrar "liberado hoje às HH:MM");
--   expirado_em:      último "Expirar acesso" da Central para este leito —
--                     toda liberação ANTERIOR a esse horário deixa de valer.
CREATE TABLE IF NOT EXISTS enfermagem_acesso_leitos (
    andar TEXT NOT NULL,
    leito TEXT NOT NULL,
    ultimo_acesso_em TEXT,
    expirado_em TEXT,
    PRIMARY KEY (andar, leito)
);

-- ---------------------------------------------------------------------
-- Central de Hotelaria
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotelaria_chamados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leito TEXT NOT NULL,
    servico TEXT NOT NULL,
    descricao TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    origem TEXT NOT NULL DEFAULT 'hotelaria',
    criado_em TEXT NOT NULL,
    iniciado_em TEXT,
    finalizado_em TEXT,
    confirmacao_resolucao TEXT NOT NULL DEFAULT 'nao_aplicavel',
    prazo_confirmacao TEXT,
    andar TEXT
);
CREATE INDEX IF NOT EXISTS idx_hotel_status ON hotelaria_chamados (status);
CREATE INDEX IF NOT EXISTS idx_hotel_leito ON hotelaria_chamados (leito);
CREATE INDEX IF NOT EXISTS idx_hotel_criado_em ON hotelaria_chamados (criado_em);

CREATE TABLE IF NOT EXISTS hotelaria_mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chamado_id INTEGER NOT NULL REFERENCES hotelaria_chamados (id),
    remetente TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    lida_central INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_hotel_msg_chamado ON hotelaria_mensagens (chamado_id);

CREATE TABLE IF NOT EXISTS hotelaria_avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chamado_id INTEGER NOT NULL UNIQUE REFERENCES hotelaria_chamados (id),
    estrelas INTEGER NOT NULL,
    comentario TEXT,
    criado_em TEXT NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA busy_timeout = 8000")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Migrações leves e idempotentes: colunas adicionadas a tabelas que já
# existiam antes desta remasterização (bancos já em produção não podem
# perder dados só porque uma coluna nova foi criada em `SCHEMA` acima — o
# `CREATE TABLE IF NOT EXISTS` não altera uma tabela já existente).
_MIGRACOES_COLUNAS = {
    "hotelaria_chamados": [("andar", "TEXT")],
}


def _aplicar_migracoes(db):
    for tabela, colunas in _MIGRACOES_COLUNAS.items():
        existentes = {row["name"] for row in db.execute(f"PRAGMA table_info({tabela})")}
        for nome_coluna, tipo_coluna in colunas:
            if nome_coluna not in existentes:
                db.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {tipo_coluna}")
    db.commit()


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
        _aplicar_migracoes(db)
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
    conn = sqlite3.connect(app.config["DATABASE_PATH"], timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn
