"""Ajudante dos testes em Python que também rodam dentro do jangada-isolar.

Numa sessão de agente, a marca /tmp/.jangada-sem-autoridade faz o Core recusar
o que exige o controlador de fora. Ali, o caso que falha por essa recusa vira
pulado, com uma linha "pulado no isolamento: MOTIVO". Fora dela nada muda.

A recusa só conta quando sai do próprio comando conferido: o último processo
que o teste rodou terminou com o código da recusa e a escreveu no stdout ou no
stderr, ou o código testado no mesmo processo parou na exigência do controlador
depois de escrever a recusa no stderr. O texto do traceback, que traz as
linhas do teste, não conta. A falha também precisa depender desse processo:
a linha que falhou é a que o rodou, ou cita o resultado dele. Uma asserção
independente depois de uma recusa esperada continua falha.

Uso: import isolamento; isolamento.instalar()
"""

import ast
import contextlib
import functools
import linecache
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SEM_AUTORIDADE = '/tmp/.jangada-sem-autoridade'
RECUSAS = ('AUTORIZACAO_RECUSADA', 'exige controlador fora do isolamento')
# orquestracao/confianca.py e o jangada-validar saem com 1; o orquestracao/cli.py
# (jangada-fila e afins), com 2; o jangada-delegar, com 4.
CODIGOS_DA_RECUSA = (1, 2, 4)
MOTIVO = 'exige o controlador de fora'
TESTES = Path(__file__).resolve().parent
CONFIANCA = TESTES.parent / 'orquestracao' / 'confianca.py'


def sem_autoridade():
    try:
        with open('/proc/self/mountinfo', encoding='utf-8') as arquivo:
            return any(linha.split()[4] == SEM_AUTORIDADE for linha in arquivo)
    except OSError:
        return False


def pular(descricao):
    """Registra o pulo como o testes/isolamento.sh: uma linha e o arquivo da suíte."""
    print(f'pulado no isolamento: {descricao}', flush=True)
    if os.environ.get('JANGADA_TESTES_PULADOS'):
        with open(os.environ['JANGADA_TESTES_PULADOS'], 'a', encoding='utf-8') as arquivo:
            arquivo.write(descricao + '\n')


def _texto(valor):
    if isinstance(valor, bytes):
        return valor.decode('utf-8', 'replace')
    return valor or ''


def tem_recusa(texto):
    return any(recusa in texto for recusa in RECUSAS)


class Comandos:
    """O último processo que o teste rodou e o stderr do código testado."""

    def __init__(self):
        self.ultimo = None
        self.erros = tempfile.TemporaryFile('w+', encoding='utf-8')

    def novo_teste(self):
        self.ultimo = None
        self.erros.seek(0)
        self.erros.truncate()

    def processo(self, codigo, saida, erro, objeto, origem):
        self.ultimo = (codigo, _texto(saida) + _texto(erro), (objeto, saida, erro), origem)

    def stderr_do_teste(self):
        self.erros.flush()
        self.erros.seek(0)
        return self.erros.read()


def _do_teste(quadro):
    arquivo = Path(quadro.f_code.co_filename).resolve()
    return arquivo.parent == TESTES and arquivo.name != 'isolamento.py'


def _chamado_pelo_teste():
    quadro = sys._getframe(2)
    while quadro is not None and quadro.f_code.co_filename == subprocess.__file__:
        quadro = quadro.f_back
    return quadro is not None and _do_teste(quadro)


def _origem():
    """As linhas do teste em execução quando o processo rodou."""
    origem = []
    quadro = sys._getframe(2)
    while quadro is not None:
        if _do_teste(quadro):
            origem.append((quadro, quadro.f_lineno))
        quadro = quadro.f_back
    return origem


@functools.lru_cache(maxsize=None)
def _arvore(arquivo):
    return ast.parse(''.join(linecache.getlines(arquivo)))


def _nomes_da_linha(arquivo, linha):
    """Nomes citados no comando do teste que contém a linha."""
    try:
        arvore = _arvore(arquivo)
    except (SyntaxError, ValueError):
        return set()
    comando = None
    for no in ast.walk(arvore):
        if isinstance(no, ast.stmt) and no.lineno <= linha <= (no.end_lineno or no.lineno):
            if comando is None or no.lineno >= comando.lineno:
                comando = no
    if comando is None:
        return set()
    return {no.id for no in ast.walk(comando) if isinstance(no, ast.Name)}


def _resultado_do_processo(valor, objetos):
    objeto, saida, erro = objetos
    if valor is objeto:
        return True
    if any(valor is texto for texto in (saida, erro) if texto):
        return True
    return isinstance(valor, subprocess.CompletedProcess) and valor.args is objeto.args


def _depende(rastro, objetos, origem):
    """A falha está na linha que rodou o processo ou cita o resultado dele."""
    pontos = {(id(quadro), linha) for quadro, linha in origem}
    while rastro is not None:
        quadro = rastro.tb_frame
        if _do_teste(quadro):
            if (id(quadro), rastro.tb_lineno) in pontos:
                return True
            for nome in _nomes_da_linha(quadro.f_code.co_filename, rastro.tb_lineno):
                if nome in quadro.f_locals and _resultado_do_processo(quadro.f_locals[nome], objetos):
                    return True
        rastro = rastro.tb_next
    return False


def recusado(comandos, erro):
    """A falha vem da recusa do controlador no comando conferido."""
    tipo, valor, rastro = erro
    if comandos.ultimo is not None:
        codigo, saida, objetos, origem = comandos.ultimo
        if codigo in CODIGOS_DA_RECUSA and tem_recusa(saida) and _depende(rastro, objetos, origem):
            return True
    if tipo is not ValueError or rastro is None:
        return False
    while rastro.tb_next is not None:
        rastro = rastro.tb_next
    origem = rastro.tb_frame.f_code
    return (Path(origem.co_filename).resolve() == CONFIANCA and origem.co_name == 'exigir_controlador'
            and tem_recusa(comandos.stderr_do_teste()))


def instalar(motivo=MOTIVO):
    """Troca falha por pulo quando a falha vem da recusa do controlador."""
    if not sem_autoridade():
        return
    comandos = Comandos()
    original_communicate = subprocess.Popen.communicate

    def communicate(self, *args, **kwargs):
        saida, erro = original_communicate(self, *args, **kwargs)
        if _chamado_pelo_teste():
            comandos.processo(self.returncode, saida, erro, self, _origem())
        return saida, erro

    subprocess.Popen.communicate = communicate
    original_run = unittest.TestCase.run

    def run(self, result=None):
        comandos.novo_teste()
        # A recusa que o código testado imprime no sys.stderr fica neste arquivo;
        # o executor do unittest guardou o stderr original e segue nele.
        with contextlib.redirect_stderr(comandos.erros):
            return original_run(self, result)

    unittest.TestCase.run = run
    # O TextTestResult imprime a falha antes de chamar a base: as duas classes
    # são trocadas para o caso recusado sair só como pulado.
    for classe in (unittest.TestResult, unittest.TextTestResult):
        for metodo in ('addFailure', 'addError'):
            _trocar(classe, metodo, motivo, comandos)
        _trocar_sub(classe, motivo, comandos)


def _trocar(classe, metodo, motivo, comandos):
    original = classe.__dict__[metodo]

    def novo(self, teste, erro):
        if recusado(comandos, erro):
            pular(f'{teste.id()} ({motivo})')
            return self.addSkip(teste, 'pulado no isolamento')
        return original(self, teste, erro)

    setattr(classe, metodo, novo)


def _trocar_sub(classe, motivo, comandos):
    original = classe.__dict__.get('addSubTest')
    if original is None:
        return

    def novo(self, teste, sub, erro):
        recusa = erro is not None and recusado(comandos, erro)
        # O subteste seguinte não herda o processo nem o stderr deste.
        comandos.novo_teste()
        if recusa:
            pular(f'{sub.id()} ({motivo})')
            return self.addSkip(teste, 'pulado no isolamento')
        return original(self, teste, sub, erro)

    classe.addSubTest = novo
