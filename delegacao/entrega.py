"""Resumo de uma entrega: campo subagentes do validar.jsonl.

Só monta o resumo, com a biblioteca padrão. Quem chama lê os registros de
subagentes e de delegações e os passa prontos.
"""

import datetime as dt
import math
import os


def instante(texto):
    """Segundos desde a época para um ISO 8601 (com Z ou fuso) ou None."""
    if not texto:
        return None
    try:
        t = dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.astimezone()
    return t.timestamp()


def numero_valido(v):
    try:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
    except OverflowError:
        return False


def uso_local(d, campo):
    """Chamadas individuais prevalecem sobre agregado legado, sem duplicar."""
    chamadas = d.get("chamadas_local")
    if isinstance(chamadas, list):
        chave = "tokens_entrada" if campo == "tokens_local_entrada" else "tokens_saida"
        valores = [c[chave] for c in chamadas if numero_valido(c.get(chave))]
        return sum(valores) if valores else None
    v = d.get(campo)
    return v if numero_valido(v) else None


def resumo_local(dels):
    locais = [d for d in dels if d.get("destino") == "local"]
    def medida(campo):
        valores = [uso_local(d, campo) for d in locais]
        conhecidos = [v for v in valores if v is not None]
        return sum(conhecidos) if conhecidos else None, len(conhecidos)
    entrada, n_entrada = medida("tokens_local_entrada")
    saida, n_saida = medida("tokens_local_saida")
    return {"n": len(locais), "atendidas": sum(not d.get("recusa") for d in locais),
            "recusas": sum(bool(d.get("recusa")) for d in locais),
            "tokens_entrada": entrada, "tokens_saida": saida,
            "medidas_entrada": n_entrada, "medidas_saida": n_saida,
            "ferramentas_disponiveis": False}


def mesma_pasta(a, b):
    if not a or not b:
        return False
    return os.path.realpath(a) == os.path.realpath(b)


def resumo_entrega(pasta, subagentes, delegacoes, principal, desde=None, ate=None):
    """Resumo dos subagentes e delegações de uma entrega (campo subagentes
    do validar.jsonl): tudo o que rodou na pasta entre desde e ate.
    subagentes já vêm só da pasta; delegacoes vêm de todas as pastas;
    principal é o par (tokens novos, cache lido) da conversa principal."""
    ini = instante(desde) if desde else None
    fim = instante(ate) if ate else None

    def dentro(t):
        t = instante(t)
        return t is not None and (ini is None or t >= ini) and (fim is None or t <= fim)

    subs = [s for s in subagentes if dentro(s["inicio"])]
    dels = [d for d in delegacoes if mesma_pasta(d.get("pasta"), pasta) and dentro(d.get("data"))]
    atendidas = [d for d in dels if not d.get("recusa")]
    c = [s for s in subs if s["origem"] == "claude"]
    a = [s for s in subs if s["origem"] == "agy"]
    papeis = {}
    for x in subs:
        if x["papel"]:
            papeis[x["papel"]] = papeis.get(x["papel"], 0) + 1
    for d in atendidas:
        papeis[d.get("papel")] = papeis.get(d.get("papel"), 0) + 1

    def soma(itens, chave):
        v = [i.get(chave) for i in itens if isinstance(i.get(chave), (int, float))]
        return sum(v) if v else 0

    delegadas_agy = sum(d.get("destino") == "agy" for d in atendidas)
    agy_n = len(a) + delegadas_agy
    principal, cache_lido = principal
    return {
        "n": len(subs) + len(atendidas),
        "claude": {"n": len(c), "tokens": soma(c, "tokens"), "principal": principal,
                   "principal_cache_lido": cache_lido},
        "delegadas_agy": delegadas_agy,
        "codex_economico": {"n": sum(d.get("destino") == "codex-economico" for d in atendidas)},
        "agy": {"n": agy_n, "passos": soma(a, "passos") + soma(atendidas, "passos")},
        "local": resumo_local(dels),
        "papeis": papeis,
        "retorno_tokens": soma(c, "retorno_tokens") + soma(atendidas, "tokens_retorno"),
        "edicoes": soma(subs, "edicoes"),
        "autorrevisao": sum(bool(s["autorrevisao"]) for s in subs),
        "recusas": len(dels) - len(atendidas),
    }
