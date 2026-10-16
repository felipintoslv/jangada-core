"""Extrai campos tipados com referências e une partes sem criar fatos."""

import argparse
import json
import pathlib
import re
import sys


TIPOS = {"texto": str, "inteiro": int, "booleano": bool}
JSON_TIPOS = {"texto": "string", "inteiro": "integer", "booleano": "boolean"}


def campos_de(declaracoes):
    campos = {}
    for declaracao in declaracoes:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}:(texto|inteiro|booleano)", declaracao):
            raise ValueError(f"campo inválido: {declaracao}")
        nome, tipo = declaracao.split(":")
        if nome in campos:
            raise ValueError(f"campo repetido: {nome}")
        campos[nome] = tipo
    if not campos:
        raise ValueError("nenhum campo de extração")
    return campos


def esquema(campos):
    return {"type": "object", "properties": {
        nome: {"type": "object", "properties": {
            "valor": {"type": [JSON_TIPOS[tipo], "null"]},
            "referencia": {"type": ["string", "null"]}},
            "required": ["valor", "referencia"], "additionalProperties": False}
        for nome, tipo in campos.items()},
        "required": list(campos), "additionalProperties": False}


def objeto_unico(pares):
    resultado = {}
    for nome, valor in pares:
        if nome in resultado:
            raise ValueError(f"chave repetida: {nome}")
        resultado[nome] = valor
    return resultado


def diagnostico_referencia(nome, referencia, locais):
    if referencia is None:
        estado = "ausente"
    elif not isinstance(referencia, str):
        estado = "tipo inválido"
    else:
        quantidade = len(locais.get(referencia, ()))
        estado = "fora do trecho" if quantidade == 0 else "ambígua" if quantidade > 1 else "válida"
    if isinstance(referencia, str):
        if len(referencia) > 32:
            inicio = json.dumps(referencia[:12], ensure_ascii=True)[1:-1]
            fim = json.dumps(referencia[-20:], ensure_ascii=True)[1:-1]
            exibicao = f'"{inicio}…{fim}"'
        else:
            exibicao = json.dumps(referencia, ensure_ascii=True)
    elif referencia is None:
        exibicao = "null"
    elif isinstance(referencia, (dict, list)):
        exibicao = f"<{type(referencia).__name__}, {len(referencia)} itens>"
    else:
        exibicao = f"<{type(referencia).__name__}>"
    detalhe = f"referência {exibicao} ({estado})"
    sugestao = "; use caminho:linha ou arquivo, p. N" if estado in {"fora do trecho", "tipo inválido"} else ""
    return f"referência fora do trecho ou ambígua: {nome}: {detalhe}{sugestao}"


def referencias(fonte):
    encontradas = {}
    for linha in fonte.splitlines():
        posicao = re.match(r"^(.+?):([0-9]+): ", linha)
        if not posicao:
            continue
        caminho, numero = posicao.groups()
        pagina = re.fullmatch(r"(.+), p\. ([0-9]+)", caminho)
        if pagina:
            caminho, numero = pagina.groups()
            sufixo = f", p. {numero}"
        else:
            sufixo = f":{numero}"
        completa = caminho + sufixo
        encontradas.setdefault(pathlib.Path(caminho).name + sufixo, set()).add(completa)
        encontradas.setdefault(completa, set()).add(completa)
    return encontradas


def exemplos_referencias(fonte, arquivos):
    nomes = {}
    for caminho in arquivos:
        nomes.setdefault(pathlib.Path(caminho).name, set()).add(caminho)
    locais = referencias(fonte)
    exemplos = {}
    for completas in locais.values():
        for completa in sorted(completas):
            caminho = re.sub(r"(, p\. [0-9]+|:[0-9]+)$", "", completa)
            if caminho in exemplos:
                continue
            nome = pathlib.Path(caminho).name
            curta = nome + completa[len(caminho):]
            unica = len(nomes.get(nome, ())) == 1 and len(locais.get(curta, ())) == 1
            exemplos[caminho] = {"rotulo": completa, "referencia": curta if unica else completa}
    return list(exemplos.values())


def conferir(texto, fonte, campos):
    resposta = json.loads(texto, object_pairs_hook=objeto_unico)
    if not isinstance(resposta, dict) or set(resposta) != set(campos):
        raise ValueError("campos omitidos ou inesperados na extração")
    locais = referencias(fonte)
    for nome, tipo in campos.items():
        fato = resposta[nome]
        if not isinstance(fato, dict) or set(fato) != {"valor", "referencia"}:
            raise ValueError(f"estrutura inválida: {nome}")
        valor, referencia = fato["valor"], fato["referencia"]
        if valor is None:
            if referencia is not None:
                raise ValueError(f"ausência com referência: {nome}")
            continue
        if type(valor) is not TIPOS[tipo]:
            raise ValueError(f"tipo inválido: {nome}")
        if isinstance(valor, str) and not valor.strip():
            raise ValueError(f"texto vazio não representa um fato: {nome}")
        if not isinstance(referencia, str) or len(locais.get(referencia, ())) != 1:
            raise ValueError(diagnostico_referencia(nome, referencia, locais))
        fato["referencia"] = next(iter(locais[referencia]))
    return resposta


def consolidar(partes, campos):
    resultado = {nome: {"valor": None, "referencia": None} for nome in campos}
    for parte in partes:
        for nome in campos:
            fato = parte[nome]
            if fato["valor"] is None:
                continue
            anterior = resultado[nome]
            if anterior["valor"] is not None and (
                type(anterior["valor"]) is not type(fato["valor"]) or anterior["valor"] != fato["valor"]
            ):
                raise ValueError(f"fatos conflitantes entre partes: {nome}")
            if anterior["valor"] is None:
                resultado[nome] = fato
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=["esquema", "exemplos", "conferir", "consolidar"])
    parser.add_argument("campos", nargs="+")
    args = parser.parse_args()
    try:
        campos = campos_de(args.campos)
        if args.acao == "esquema":
            resultado = esquema(campos)
        else:
            dados = json.load(sys.stdin, object_pairs_hook=objeto_unico)
            if args.acao == "exemplos":
                resultado = exemplos_referencias(dados["fonte"], dados["arquivos"])
            elif args.acao == "conferir":
                resultado = conferir(dados["resposta"], dados["fonte"], campos)
            else:
                resultado = consolidar(dados, campos)
        print(json.dumps(resultado, ensure_ascii=False))
    except (ValueError, KeyError, TypeError) as erro:
        sys.exit(str(erro))


if __name__ == "__main__":
    main()
