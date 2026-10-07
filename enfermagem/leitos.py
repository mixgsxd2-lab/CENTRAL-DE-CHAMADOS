# -*- coding: utf-8 -*-
"""Controle de Leitos (Configurações) — ativar/desativar leitos sem tocar
na lista fixa de `andares.py`. Um leito inativo some da tela do paciente
(não pode ser escolhido para abrir um chamado novo), mas continua existindo
normalmente para o histórico de chamados já registrados nele.

Só os leitos INATIVOS ficam gravados no banco (`enfermagem_leitos_inativos`)
— por padrão, todo leito de `andares.py` está ativo."""
from andares import ANDARES, andar_label
from db import get_db
from timeutils import agora, para_texto


def _inativos(db):
    return {(row["andar"], row["leito"]) for row in db.execute(
        "SELECT andar, leito FROM enfermagem_leitos_inativos"
    )}


def listar_leitos():
    """Todos os leitos cadastrados, agrupados por andar, com o status atual
    — usado pela tela Controle de Leitos."""
    db = get_db()
    inativos = _inativos(db)
    return [
        {
            "andar": andar,
            "andar_label": andar_label(andar),
            "leitos": [
                {"leito": leito, "ativo": (andar, leito) not in inativos}
                for leito in leitos
            ],
        }
        for andar, leitos in ANDARES.items()
    ]


def andares_ativos():
    """Mesmo formato de `andares.py::ANDARES` ({andar: [leitos]}), mas só
    com os leitos ativos — para a tela do paciente."""
    db = get_db()
    inativos = _inativos(db)
    if not inativos:
        return ANDARES
    return {
        andar: [leito for leito in leitos if (andar, leito) not in inativos]
        for andar, leitos in ANDARES.items()
    }


def leito_ativo(andar, leito):
    """Usado na criação de chamados: um leito desativado não pode abrir um
    chamado novo, mesmo que a tela do paciente esteja em cache antigo."""
    db = get_db()
    return (andar, leito) not in _inativos(db)


def definir_status_leito(andar, leito, ativo):
    """Retorna False se o andar/leito não existir em `andares.py`."""
    if andar not in ANDARES or leito not in ANDARES[andar]:
        return False
    db = get_db()
    if ativo:
        db.execute("DELETE FROM enfermagem_leitos_inativos WHERE andar = ? AND leito = ?", (andar, leito))
    else:
        db.execute(
            "INSERT OR IGNORE INTO enfermagem_leitos_inativos (andar, leito, desde) VALUES (?, ?, ?)",
            (andar, leito, para_texto(agora())),
        )
    db.commit()
    return True
