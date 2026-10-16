#!/usr/bin/env python3
"""Confere referências às fontes fornecidas, sem aprovar o conteúdo."""

import argparse
import pathlib
import re
import subprocess
import sys


def verificar(texto, arquivos, requisitos=()):
    nomes = [pathlib.Path(arquivo).name for arquivo in arquivos]
    referencias_encontradas = []
    for arquivo in arquivos:
        caminho = pathlib.Path(arquivo)
        mime = subprocess.run(
            ["file", "-b", "--mime-type", str(caminho)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        pdf = caminho.suffix.lower() == ".pdf" or mime == "application/pdf"
        if pdf:
            fonte = subprocess.run(
                ["pdftotext", "-layout", str(caminho), "-"],
                capture_output=True, text=True, check=True,
            ).stdout
            partes = fonte.split("\f")
        else:
            fonte = caminho.read_text()
            partes = fonte.split("\n")
        if partes and partes[-1] == "":
            partes.pop()
        alternativas = [arquivo, str(caminho.resolve())]
        if nomes.count(caminho.name) == 1:
            alternativas.append(caminho.name)
        nome = "(?:" + "|".join(re.escape(a) for a in alternativas) + ")"
        localizador = r",\s*p\.\s*" if pdf else ":"
        localizador += r"(\d+)(?:[-–](\d+))?(?![\w-])"
        padrao = r"(?<![\w/])" + nome + localizador
        referencias = re.findall(padrao, texto)
        referencias_encontradas.append(padrao)
        if not referencias or any(
            not 1 <= int(inicio) <= int(fim or inicio) <= len(partes)
            for inicio, fim in referencias
        ):
            raise ValueError(f"fonte sem referência válida ou posição inexistente: {arquivo}")
    for requisito in requisitos:
        secoes = re.findall(
            r"^## " + re.escape(requisito) + r"[ \t]*\n(.*?)(?=^## |\Z)",
            texto, flags=re.MULTILINE | re.DOTALL,
        )
        if len(secoes) != 1:
            raise ValueError(f"requisito ausente ou repetido: {requisito}")
        explicacao = secoes[0]
        tem_referencia = False
        for padrao in referencias_encontradas:
            tem_referencia |= re.search(padrao, explicacao) is not None
            explicacao = re.sub(padrao, "", explicacao)
        explicacao = explicacao.replace(requisito, "")
        if not tem_referencia or len(re.findall(r"\b[^\W\d_]+\b", explicacao)) < 5:
            raise ValueError(f"requisito sem explicação ou referência: {requisito}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requisito", action="append", default=[])
    parser.add_argument("arquivos", nargs="+")
    args = parser.parse_args()
    try:
        verificar(sys.stdin.read(), args.arquivos, args.requisito)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as erro:
        sys.exit(str(erro))
