"""Ajudante dos testes em Python que também rodam dentro do jangada-isolar.

Numa sessão de agente, a marca /tmp/.jangada-sem-autoridade faz o Core recusar
o que exige o controlador de fora. Ali, o caso que falha por essa recusa vira
pulado, com uma linha "pulado no isolamento: MOTIVO". Fora dela nada muda.

Uso: import isolamento; isolamento.instalar()
"""

import contextlib
import os
import sys
import tempfile
import traceback
import unittest

SEM_AUTORIDADE = '/tmp/.jangada-sem-autoridade'
RECUSAS = ('AUTORIZACAO_RECUSADA', 'exige controlador fora do isolamento')
MOTIVO = 'exige o controlador de fora'


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


def recusado(erro):
    texto = ''.join(traceback.format_exception(*erro))
    return any(recusa in texto for recusa in RECUSAS)


def instalar(motivo=MOTIVO, sempre=()):
    """Troca falha por pulo quando a falha vem da recusa do controlador.

    sempre: nomes de casos que dependem do controlador sem que a recusa
    apareça na falha (o caso só vê o código de saída do comando).
    """
    if not sem_autoridade():
        return
    original_run = unittest.TestCase.run
    # A recusa que o código testado imprime no sys.stderr fica neste arquivo;
    # o executor do unittest guardou o stderr original e segue nele.
    erros = tempfile.TemporaryFile('w+', encoding='utf-8')

    def run(self, result=None):
        nome = self._testMethodName
        if nome in sempre:
            pular(f'{type(self).__name__}.{nome} ({motivo})')
            setattr(self, nome, unittest.skip('pulado no isolamento')(getattr(self, nome)))
        with contextlib.redirect_stderr(erros):
            return original_run(self, result)

    unittest.TestCase.run = run
    # O TextTestResult imprime a falha antes de chamar a base: as duas classes
    # são trocadas para o caso recusado sair só como pulado.
    for classe in (unittest.TestResult, unittest.TextTestResult):
        for metodo in ('addFailure', 'addError'):
            _trocar(classe, metodo, motivo)
        _trocar_sub(classe, motivo)


def _trocar(classe, metodo, motivo):
    original = classe.__dict__[metodo]

    def novo(self, teste, erro):
        if recusado(erro):
            pular(f'{teste.id()} ({motivo})')
            return self.addSkip(teste, 'pulado no isolamento')
        return original(self, teste, erro)

    setattr(classe, metodo, novo)


def _trocar_sub(classe, motivo):
    original = classe.__dict__.get('addSubTest')
    if original is None:
        return

    def novo(self, teste, sub, erro):
        if erro is not None and recusado(erro):
            pular(f'{sub.id()} ({motivo})')
            return self.addSkip(teste, 'pulado no isolamento')
        return original(self, teste, sub, erro)

    classe.addSubTest = novo
