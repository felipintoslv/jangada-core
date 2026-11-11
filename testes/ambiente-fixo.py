#!/usr/bin/env python3
"""Confere que os testes dão o mesmo resultado em qualquer idioma e entrada
padrão de quem chama: cada teste fixa os dois pelo testes/ambiente.sh ou pelo
testes/ambiente.py, e os casos sensíveis passam com chamador diferente.

Uso: testes/ambiente-fixo.py
"""
import ambiente
import ast
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest

RAIZ = Path(__file__).resolve().parents[1]
TESTES = RAIZ / 'testes'
# Arquivos carregados ou executados pelos testes, que não são testes: não
# podem fixar a própria entrada (o servidor falso lê a do teste que o chama).
APOIO = {'ambiente.sh', 'ambiente.py', 'isolamento.sh', 'isolamento.py', 'falso-codex-hooks.py'}
FONTE_BASH = 'source "$(dirname "$0")/ambiente.sh"'
IDIOMA_DE_FORA = {'LANG': 'pt_BR.UTF-8', 'LANGUAGE': 'pt_BR', 'LC_MESSAGES': 'pt_BR.UTF-8',
                  'LC_ALL': 'pt_BR.UTF-8'}


def executados_pelo_verificar():
    """Arquivos de testes/ que o verificar.sh executa: no começo de um comando,
    direto ou pelo python3, ou num for cujo corpo executa a variável. Os for da
    sintaxe e do shellcheck só leem os arquivos."""
    arquivos = set()
    laco = None
    for linha in (TESTES / 'verificar.sh').read_text(encoding='utf-8').splitlines():
        if linha.lstrip().startswith('#'):
            continue
        cabecalho = re.match(r'\s*for (\w+) in (testes/[\w.*-]+); do', linha)
        if cabecalho:
            laco = cabecalho.groups()
        elif laco and re.search(r'(^|[;)|&]|python3)\s*"\$%s"' % laco[0], linha):
            arquivos.update(RAIZ.glob(laco[1]))
        elif re.match(r'\s*done\b', linha):
            laco = None
        for nome in re.findall(r'(?:^|\|\||&&|;)\s*(?:python3(?:\s+-B)?\s+)?(testes/[\w.-]+)', linha):
            arquivos.add(RAIZ / nome)
    return arquivos


def problema_bash(caminho):
    for linha in caminho.read_text(encoding='utf-8').splitlines():
        if not linha.strip() or linha.startswith('#') or linha.startswith('set -'):
            continue
        return None if linha == FONTE_BASH else f'primeiro comando é {linha!r}, não {FONTE_BASH!r}'
    return 'sem comandos'


def problema_python(caminho):
    corpo = ast.parse(caminho.read_text(encoding='utf-8')).body
    if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
        corpo = corpo[1:]
    if corpo and isinstance(corpo[0], ast.Import) and [n.name for n in corpo[0].names] == ['ambiente'] \
            and corpo[0].names[0].asname is None:
        return None
    return 'o primeiro comando depois da docstring não é import ambiente'


def com_socket(argumentos, **kwargs):
    """Roda com um socket na entrada padrão, como um chamador que não usou </dev/null."""
    a, b = socket.socketpair()
    try:
        return subprocess.run(argumentos, stdin=a, capture_output=True, text=True, cwd=RAIZ, **kwargs)
    finally:
        a.close()
        b.close()


class Ambiente(unittest.TestCase):
    def test_todo_teste_fixa_idioma_e_entrada(self):
        testes = {p for p in TESTES.iterdir() if p.suffix in ('.sh', '.py') and p.name not in APOIO}
        executados = executados_pelo_verificar()
        self.assertGreater(len(executados), 50)
        for caminho in sorted(executados):
            with self.subTest(executado=caminho.name):
                self.assertTrue(caminho.is_file())
                self.assertEqual(caminho.parent, TESTES)
                self.assertNotIn(caminho.name, APOIO)
        for caminho in sorted(testes):
            with self.subTest(teste=caminho.name):
                problema = (problema_bash if caminho.suffix == '.sh' else problema_python)(caminho)
                self.assertIsNone(problema)

    def test_apoio_isola_do_chamador(self):
        bash = ('source testes/ambiente.sh; printf "%s|%s|%s|%s\\n" "$LC_ALL" "${LANG-}" "${LANGUAGE-}" '
                '"${LC_MESSAGES-}"; readlink /proc/self/fd/0')
        python = ('import sys; sys.path.insert(0, "testes"); import ambiente, locale, os, subprocess; '
                  'print("|".join([os.environ["LC_ALL"], os.environ.get("LANG", ""), '
                  'os.environ.get("LANGUAGE", ""), os.environ.get("LC_MESSAGES", "")])); '
                  'print(locale.setlocale(locale.LC_ALL)); print(os.readlink("/proc/self/fd/0")); '
                  'print(sys.stdin.read() == "", flush=True); subprocess.run(["readlink", "/proc/self/fd/0"])')
        ambiente_de_fora = dict(os.environ, **IDIOMA_DE_FORA)
        resultado = com_socket(['bash', '-c', bash], env=ambiente_de_fora)
        self.assertEqual(resultado.stdout.splitlines(), ['C.UTF-8|||', '/dev/null'], resultado.stderr)
        resultado = com_socket([sys.executable, '-c', python], env=ambiente_de_fora)
        self.assertEqual(resultado.stdout.splitlines(),
                         ['C.UTF-8|||', 'C.UTF-8', '/dev/null', 'True', '/dev/null'], resultado.stderr)

    def test_cotas_com_socket_na_entrada(self):
        # O jangada-isolar recusa entrada padrão que seja socket; o teste não herda a do chamador.
        resultado = com_socket([sys.executable, 'testes/cotas.py', '-v',
                                'Cotas.test_agente_isolado_nao_altera_o_cotas_json'], timeout=300)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn('Ran 1 test', resultado.stderr)

    def test_hooks_em_qualquer_idioma_de_quem_chama(self):
        for idioma in ('C', 'pt_BR.UTF-8'):
            with self.subTest(idioma=idioma):
                fora = dict(os.environ, LC_ALL=idioma, LANG=idioma, LC_MESSAGES=idioma)
                resultado = subprocess.run(['bash', 'testes/hooks.sh'], cwd=RAIZ, env=fora,
                                           capture_output=True, text=True, timeout=300)
                self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == '__main__':
    unittest.main()
