# -*- coding: utf-8 -*-
"""Copia os dados do arquivo SQLite antigo (hospital_rio_grande.db) para o
MySQL configurado em `config.py` / variáveis de ambiente.

NÃO apaga nada no SQLite. Cria as tabelas no MySQL (se não existirem) e só
insere — pode ser rodado de novo com segurança contra um banco MySQL vazio;
rodar duas vezes contra um banco MySQL que já tem dados duplica as linhas
(sem UNIQUE/PK conflitante na maioria das tabelas, exceto id/chaves
compostas, que o AUTO_INCREMENT do MySQL vai simplesmente recriar com
IDs novos — por isso o normal é rodar isto uma única vez, numa migração).

Uso:
    python migrar_sqlite_para_mysql.py [caminho/para/hospital_rio_grande.db]

Sem argumento, usa o caminho padrão do projeto
(BASE_DIR/hospital_rio_grande.db, o mesmo nome que o SQLite usava).
"""
import os
import sqlite3
import sys

from config import BASE_DIR, Config
from db import SCHEMA, Conexao, _config_mysql

# Ordem importa: tabelas com FOREIGN KEY depois das tabelas que referenciam.
TABELAS = [
    "enfermagem_chamados",
    "enfermagem_leitos_inativos",
    "enfermagem_config",
    "enfermagem_acesso_leitos",
    "hotelaria_chamados",
    "hotelaria_mensagens",
    "hotelaria_avaliacoes",
]


def migrar(caminho_sqlite):
    if not os.path.exists(caminho_sqlite):
        print(f"Arquivo não encontrado: {caminho_sqlite}")
        sys.exit(1)

    origem = sqlite3.connect(caminho_sqlite)
    origem.row_factory = sqlite3.Row

    destino = Conexao(**_config_mysql(vars(Config)))
    destino.executescript(SCHEMA)
    destino.commit()

    cur = destino.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")

    total_geral = 0
    for tabela in TABELAS:
        linhas = origem.execute(f"SELECT * FROM {tabela}").fetchall()
        if not linhas:
            print(f"{tabela}: 0 linhas (nada a copiar)")
            continue
        colunas = linhas[0].keys()
        marcadores = ", ".join(["%s"] * len(colunas))
        sql = (
            f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({marcadores})"
        )
        valores = [tuple(linha[c] for c in colunas) for linha in linhas]
        cur.executemany(sql, valores)
        print(f"{tabela}: {len(valores)} linhas copiadas")
        total_geral += len(valores)

    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    destino.commit()
    destino.close()
    origem.close()
    print(f"Concluído: {total_geral} linhas copiadas no total.")


if __name__ == "__main__":
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "hospital_rio_grande.db")
    migrar(caminho)
