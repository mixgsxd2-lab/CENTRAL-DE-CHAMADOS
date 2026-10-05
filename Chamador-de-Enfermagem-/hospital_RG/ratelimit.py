# -*- coding: utf-8 -*-
"""Limitador de tentativas simples, em memória — sem dependência externa.

Usado para conter força bruta nos dois formulários de login (Enfermagem e
Hotelaria). Deliberadamente simples (dict + lock, janela deslizante por
timestamps) porque o sistema roda em um único processo/máquina — não precisa
de Redis nem de qualquer serviço externo para isso.

Não é (nem tenta ser) proteção contra um atacante distribuído com muitos IPs;
é uma barreira razoável contra tentativa manual/script simples de adivinhar a
senha de teste, que é o risco real neste sistema.
"""
import threading
import time

_lock = threading.Lock()
_tentativas = {}  # chave -> [timestamps das tentativas recentes]


def permitido(chave, max_tentativas=8, janela_segundos=300):
    """True se a `chave` (ex.: IP do cliente) ainda pode tentar; também
    registra a tentativa atual. Chamar uma vez por tentativa de login."""
    agora = time.monotonic()
    with _lock:
        marcas = _tentativas.setdefault(chave, [])
        limite_inferior = agora - janela_segundos
        while marcas and marcas[0] < limite_inferior:
            marcas.pop(0)

        if len(marcas) >= max_tentativas:
            return False

        marcas.append(agora)

        # Faxina oportunista para não crescer para sempre em memória — só
        # roda ocasionalmente, não a cada chamada.
        if len(_tentativas) > 500:
            for k in list(_tentativas.keys()):
                if not _tentativas[k] or _tentativas[k][-1] < limite_inferior:
                    _tentativas.pop(k, None)

        return True


def limpar_para_testes():
    """Usado apenas por testes/depuração manual."""
    with _lock:
        _tentativas.clear()
