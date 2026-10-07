# -*- coding: utf-8 -*-
"""Representação em memória de um chamado de Enfermagem.

Não é um ORM — é apenas um wrapper leve em volta de uma linha do SQLite
(sqlite3.Row), convertendo os campos de data/hora de texto para `datetime`
uma única vez. Feito assim (em vez de usar `sqlite3.Row` diretamente em
todo o código) para que o motor de prioridade e os serializadores leiam
`chamado.categoria`, `chamado.criado_em` etc. com atributos normais, sem
espalhar `row["..."]` e `parse_dt(...)` por toda parte.
"""
from timeutils import parse_dt, agora

COLUNAS = (
    "id", "andar", "leito", "categoria", "subcategoria", "detalhe",
    "gravidade_base", "status", "profissional_responsavel",
    "criado_em", "inicio_atendimento", "finalizado_em",
    "avaliacao", "comentario_avaliacao",
)


class ChamadoEnfermagem:
    __slots__ = COLUNAS

    def __init__(self, row):
        self.id = row["id"]
        self.andar = row["andar"]
        self.leito = row["leito"]
        self.categoria = row["categoria"]
        self.subcategoria = row["subcategoria"]
        self.detalhe = row["detalhe"]
        self.gravidade_base = row["gravidade_base"]
        self.status = row["status"]
        self.profissional_responsavel = row["profissional_responsavel"]
        self.criado_em = parse_dt(row["criado_em"])
        self.inicio_atendimento = parse_dt(row["inicio_atendimento"])
        self.finalizado_em = parse_dt(row["finalizado_em"])
        self.avaliacao = row["avaliacao"]
        self.comentario_avaliacao = row["comentario_avaliacao"]

    def tempo_atendimento_min(self):
        if self.inicio_atendimento and self.finalizado_em:
            return round((self.finalizado_em - self.inicio_atendimento).total_seconds() / 60, 1)
        return None

    def segundos_ate_poder_finalizar(self):
        """Segundos que ainda faltam para cumprir o tempo mínimo de
        atendimento (0 se já pode finalizar)."""
        from enfermagem.priority import TEMPO_MINIMO_ATENDIMENTO_SEG
        if self.status != "em_atendimento" or not self.inicio_atendimento:
            return 0
        decorrido = (agora() - self.inicio_atendimento).total_seconds()
        return max(0, int(TEMPO_MINIMO_ATENDIMENTO_SEG - decorrido + 0.999))

    def tempo_total_min(self):
        fim = self.finalizado_em or agora()
        if self.criado_em:
            return round((fim - self.criado_em).total_seconds() / 60, 1)
        return None
