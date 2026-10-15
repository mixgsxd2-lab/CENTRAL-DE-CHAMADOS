# -*- coding: utf-8 -*-
"""Acesso ao banco de dados — MySQL via PyMySQL (sem ORM).

Uma conexão por requisição (via flask.g), fechada automaticamente ao final
de cada requisição. As duas "tabelas de chamados" (Enfermagem e Hotelaria)
vivem no mesmo banco por simplicidade operacional, mas continuam sendo
dados de sistemas logicamente independentes — cada um só lê/escreve nas
suas próprias tabelas.

Este módulo expõe, em cima do driver PyMySQL, a mesma API "estilo sqlite3"
que o resto do código já usava (`conexao.execute(sql, params)` com `?`
como marcador de posição, linhas acessíveis por `row["coluna"]` — e também
por índice, `row[0]`, igual a `sqlite3.Row`) para que `enfermagem/`,
`hotelaria/` e `dados_demo.py` não precisassem reescrever cada consulta.
"""
import pymysql
import pymysql.cursors
from flask import current_app, g

# ---------------------------------------------------------------------------
# Esquema (dialeto MySQL/InnoDB).
#
# Colunas TEXT que entram em chave primária, UNIQUE ou índice foram trocadas
# por VARCHAR: o MySQL não indexa uma coluna TEXT/BLOB sem um tamanho de
# prefixo explícito. As demais (campos livres como `detalhe`, `comentario`)
# continuam TEXT.
# ---------------------------------------------------------------------------
SCHEMA = """
-- ---------------------------------------------------------------------
-- Central de Chamados
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enfermagem_chamados (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Leitos desativados pela tela "Controle de Leitos" (Configurações). Um
-- leito só aparece aqui enquanto estiver INATIVO — por padrão, todo leito
-- cadastrado em `andares.py` está ativo, então a ausência de linha já
-- significa "ativo" (evita ter que semear milhares de linhas "ativo=1").
CREATE TABLE IF NOT EXISTS enfermagem_leitos_inativos (
    andar VARCHAR(255) NOT NULL,
    leito VARCHAR(255) NOT NULL,
    desde VARCHAR(40) NOT NULL,
    PRIMARY KEY (andar, leito)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Configurações simples de chave/valor da Enfermagem — hoje guarda o token
-- fixo dos QR Codes e o horário do último "Expirar todos" (ver
-- enfermagem/acesso.py), mas fica
-- genérica para não precisar de uma tabela nova a cada configuração futura.
CREATE TABLE IF NOT EXISTS enfermagem_config (
    chave VARCHAR(100) PRIMARY KEY,
    valor TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Acesso do paciente pelo QR Code do leito (ver enfermagem/acesso.py).
-- Uma linha por leito, criada na primeira vez que algo acontece com ele.
-- Guarda SÓ horários — nenhum dado do paciente (nome, aparelho, etc.):
--   ultimo_acesso_em: última vez que o QR Code deste leito foi escaneado
--                     (só para a Central mostrar "liberado hoje às HH:MM");
--   expirado_em:      último "Expirar acesso" da Central para este leito —
--                     toda liberação ANTERIOR a esse horário deixa de valer.
CREATE TABLE IF NOT EXISTS enfermagem_acesso_leitos (
    andar VARCHAR(255) NOT NULL,
    leito VARCHAR(255) NOT NULL,
    ultimo_acesso_em VARCHAR(40),
    expirado_em VARCHAR(40),
    PRIMARY KEY (andar, leito)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- Central de Hotelaria
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotelaria_chamados (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hotelaria_mensagens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chamado_id INT NOT NULL,
    remetente VARCHAR(50) NOT NULL,
    mensagem TEXT NOT NULL,
    criado_em VARCHAR(40) NOT NULL,
    lida_central TINYINT NOT NULL DEFAULT 0,
    INDEX idx_hotel_msg_chamado (chamado_id),
    CONSTRAINT fk_hotel_msg_chamado FOREIGN KEY (chamado_id)
        REFERENCES hotelaria_chamados (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hotelaria_avaliacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chamado_id INT NOT NULL UNIQUE,
    estrelas INT NOT NULL,
    comentario TEXT,
    criado_em VARCHAR(40) NOT NULL,
    CONSTRAINT fk_hotel_aval_chamado FOREIGN KEY (chamado_id)
        REFERENCES hotelaria_chamados (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


class Row(dict):
    """Compatível com `sqlite3.Row`: aceita tanto `row["coluna"]` quanto
    `row[0]` (posição da coluna, na ordem devolvida pelo cursor) — o
    restante do código (enfermagem/, hotelaria/, dados_demo.py) depende
    das duas formas."""

    def __getitem__(self, chave):
        if isinstance(chave, int):
            return list(self.values())[chave]
        return dict.__getitem__(self, chave)


class _RowDictCursor(pymysql.cursors.DictCursor):
    dict_type = Row


def _traduzir_sql(sql):
    """Os módulos do app escrevem as consultas com `?` (estilo sqlite3);
    o PyMySQL usa `%s`. Nenhuma das consultas deste projeto tem um `?`
    literal dentro de uma string SQL — é seguro trocar diretamente."""
    return sql.replace("?", "%s")


class Conexao:
    """Fininho wrapper em volta de `pymysql.connect(...)` que imita a
    conveniência do `sqlite3.Connection` (`conexao.execute(...)` sem
    precisar abrir um cursor manualmente)."""

    def __init__(self, **kwargs):
        self._conn = pymysql.connect(cursorclass=_RowDictCursor, **kwargs)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(_traduzir_sql(sql), params)
        return cur

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(_traduzir_sql(sql), seq_of_params)
        return cur

    def executescript(self, script):
        """Equivalente ao `sqlite3.Connection.executescript`: roda vários
        comandos separados por `;` (usado só para criar o SCHEMA). Linhas de
        comentário (`-- ...`) são descartadas antes de dividir por `;` —
        um comentário em português pode conter pontuação com `;` sem que
        isso signifique o fim de um comando SQL."""
        sem_comentarios = "\n".join(
            linha for linha in script.splitlines() if not linha.strip().startswith("--")
        )
        cur = self._conn.cursor()
        for comando in sem_comentarios.split(";"):
            comando = comando.strip()
            if comando:
                cur.execute(comando)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()


def _config_mysql(app_config):
    return dict(
        host=app_config["MYSQL_HOST"],
        port=app_config["MYSQL_PORT"],
        user=app_config["MYSQL_USER"],
        password=app_config["MYSQL_PASSWORD"],
        database=app_config["MYSQL_DATABASE"],
        charset="utf8mb4",
        autocommit=False,
    )


def get_db():
    if "db" not in g:
        g.db = Conexao(**_config_mysql(current_app.config))
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
    "hotelaria_chamados": [("andar", "VARCHAR(255)")],
}


def _aplicar_migracoes(db):
    for tabela, colunas in _MIGRACOES_COLUNAS.items():
        existentes = {
            row["COLUMN_NAME"]
            for row in db.execute(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = ?",
                (tabela,),
            )
        }
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
    return Conexao(**_config_mysql(app.config))
