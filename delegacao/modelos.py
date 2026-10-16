"""Seleção fechada de modelos por tarefa; metadados nunca são comandos."""

import json
import sys


AUTORES = {"codex": {"gpt-6-luna": "medium", "gpt-6.1-sol": "high"},
           "claude": {"sonnet": "high", "opus": "high"}}
REVISORES = {"codex": ("gpt-6.1-sol", "high"), "claude": ("opus", "high")}


def selecionar(autor, revisor, modelo="", esforco="", rev_modelo="", rev_esforco=""):
    if not any((modelo, esforco)):
        return {}
    if autor not in AUTORES or revisor not in REVISORES or autor == revisor:
        raise ValueError("seleção por tarefa exige autor e revisor de provedores diferentes")
    if modelo not in AUTORES[autor]:
        raise ValueError("modelo do autor incompatível: " + modelo)
    esperado = AUTORES[autor][modelo]
    if esforco and esforco != esperado:
        raise ValueError("esforço incompatível com o modelo do autor")
    forte, nivel = REVISORES[revisor]
    if rev_modelo and rev_modelo != forte or rev_esforco and rev_esforco != nivel:
        raise ValueError("o piloto exige o revisor independente forte")
    return {"autor": {"provedor": autor, "modelo": modelo, "esforco": esperado},
            "revisor": {"provedor": revisor, "modelo": forte, "esforco": nivel}}


def conferir(valor, autor, revisor):
    if not isinstance(valor, dict) or set(valor) != {"autor", "revisor"}:
        raise ValueError("seleção registrada inválida")
    for papel in valor.values():
        if not isinstance(papel, dict) or set(papel) != {"provedor", "modelo", "esforco"}:
            raise ValueError("campos da seleção inválidos")
        if not all(isinstance(v, str) for v in papel.values()):
            raise ValueError("tipos da seleção inválidos")
    a, r = valor["autor"], valor["revisor"]
    validado = selecionar(autor, revisor, a["modelo"], a["esforco"], r["modelo"], r["esforco"])
    if valor != validado:
        raise ValueError("seleção registrada diverge dos provedores")
    return validado


if __name__ == "__main__":
    try:
        if sys.argv[1] == "conferir":
            resultado = conferir(json.load(sys.stdin), *sys.argv[2:])
        else:
            resultado = selecionar(*sys.argv[1:])
        print(json.dumps(resultado, ensure_ascii=False))
    except (ValueError, KeyError, TypeError) as erro:
        sys.exit("modelos da tarefa: " + str(erro))
