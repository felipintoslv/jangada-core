"""Ambiente fixo dos testes em Python: o resultado não depende do idioma nem da
entrada padrão de quem chama. Caso que precisa de outro idioma ou de entrada
própria passa isso ao subprocesso daquele caso.

Uso, como primeiro comando depois da docstring: import ambiente
O testes/ambiente-fixo.py confere o uso em cada teste.
"""

import locale
import os
import sys

for _nome in [n for n in os.environ if n in ('LANG', 'LANGUAGE') or n.startswith('LC_')]:
    del os.environ[_nome]
os.environ['LC_ALL'] = 'C.UTF-8'
locale.setlocale(locale.LC_ALL, 'C.UTF-8')

# Os subprocessos herdam o descritor 0. Se ele estava fechado, o open já o ocupa.
_nulo = os.open(os.devnull, os.O_RDONLY)
if _nulo != 0:
    os.dup2(_nulo, 0)
    os.close(_nulo)
sys.stdin = open(0, encoding='utf-8', closefd=False)
