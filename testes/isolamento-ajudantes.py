#!/usr/bin/env python3
"""Testa o testes/isolamento.py: só pula o caso cujo próprio comando saiu com
o código da recusa e a escreveu na saída, ou cujo código parou na exigência
do controlador. Roda igual dentro e fora do isolamento: a suíte interna
simula a marca."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES))
sys.path.insert(0, str(TESTES.parent / 'orquestracao'))

import isolamento  # noqa: E402

RECUSA = 'AUTORIZACAO_RECUSADA: executor isolado não possui autoridade'


def sair(codigo, saida='', erro=''):
    programa = 'import sys; sys.stdout.write(sys.argv[1]); sys.stderr.write(sys.argv[2]); sys.exit(int(sys.argv[3]))'
    return subprocess.run([sys.executable, '-c', programa, saida, erro, str(codigo)],
                          capture_output=True, text=True, check=False)


class Interna(unittest.TestCase):
    """Rodada só pelo processo filho, com a marca do isolamento simulada."""

    def test_literal_na_assercao(self):
        self.assertIn('AUTORIZACAO_RECUSADA', 'nada recusado')

    def test_fonte_com_recusa_e_outra_falha(self):
        fonte = Path(os.environ['PASTA']) / 'fonte.py'
        fonte.write_text(f'print({RECUSA!r})\n', encoding='utf-8')
        self.assertEqual(sair(1, erro='SyntaxError').returncode, 0)

    def test_sem_recusa(self):
        self.assertEqual(sair(1, erro='comando não encontrado').returncode, 0)

    def test_recusa_no_stderr(self):
        self.assertEqual(sair(1, erro=RECUSA).returncode, 0)

    def test_recusa_no_stdout_codigo_2(self):
        self.assertEqual(sair(2, saida=RECUSA).returncode, 0)

    def test_recusa_codigo_3(self):
        self.assertEqual(sair(3, erro=RECUSA).returncode, 0)

    def test_recusa_codigo_0(self):
        sair(0, erro=RECUSA)
        self.fail('o comando saiu com 0')

    def test_recusa_do_comando_anterior(self):
        sair(1, erro=RECUSA)
        self.assertEqual(sair(1, erro='outro erro').returncode, 0)

    def test_sem_comando_depois_de_recusa(self):
        # Roda logo depois do test_recusa_no_stdout_codigo_2: o registro é por caso.
        self.fail('sem comando neste caso')

    def test_exigir_controlador(self):
        import confianca
        os.environ['JANGADA_ISOLADO'] = '1'
        try:
            confianca.exigir_controlador()
        finally:
            del os.environ['JANGADA_ISOLADO']

    def test_value_error_do_teste(self):
        print(RECUSA, file=sys.stderr)
        raise ValueError('operação exige controlador fora do isolamento')

    def test_subteste(self):
        with self.subTest('recusado'):
            self.assertEqual(sair(1, erro=RECUSA).returncode, 0)
        with self.subTest('sem recusa'):
            self.assertEqual(sair(1, erro='outro erro').returncode, 0)


def rodar_interna():
    isolamento.sem_autoridade = lambda: True
    isolamento.instalar()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Interna)
    with open(os.devnull, 'w', encoding='utf-8') as nulo:
        resultado = unittest.TextTestRunner(stream=nulo).run(suite)
    nome = lambda teste: teste.id().split('.', 2)[-1]  # noqa: E731
    print(json.dumps({
        'falhas': sorted(nome(t) for t, _ in resultado.failures + resultado.errors),
        'pulados': sorted(nome(t) for t, _ in resultado.skipped),
    }))


class Ajudante(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        pasta = tempfile.TemporaryDirectory()
        cls.addClassCleanup(pasta.cleanup)
        ambiente = {k: v for k, v in os.environ.items()
                    if k not in ('JANGADA_TESTES_PULADOS', 'JANGADA_ISOLADO')}
        ambiente['PASTA'] = pasta.name
        processo = subprocess.run([sys.executable, __file__, '--interna'], capture_output=True,
                                  text=True, env=ambiente, check=False)
        cls.linhas = processo.stdout.splitlines()
        cls.resultado = json.loads(cls.linhas[-1])

    def pulou(self, nome):
        return any(nome in t for t in self.resultado['pulados'])

    def falhou(self, nome):
        return any(nome in t for t in self.resultado['falhas'])

    def test_continua_falha(self):
        for nome in ('test_literal_na_assercao', 'test_fonte_com_recusa_e_outra_falha', 'test_sem_recusa',
                     'test_recusa_codigo_3', 'test_recusa_codigo_0', 'test_recusa_do_comando_anterior',
                     'test_sem_comando_depois_de_recusa', 'test_value_error_do_teste'):
            with self.subTest(nome):
                self.assertTrue(self.falhou(nome))
                self.assertFalse(self.pulou(nome))

    def test_pula(self):
        for nome in ('test_recusa_no_stderr', 'test_recusa_no_stdout_codigo_2', 'test_exigir_controlador'):
            with self.subTest(nome):
                self.assertTrue(self.pulou(nome))
                self.assertFalse(self.falhou(nome))

    def test_subteste(self):
        self.assertTrue(self.pulou('test_subteste'))
        self.assertIn('Interna.test_subteste [recusado]', '\n'.join(self.linhas))
        self.assertTrue(self.falhou('test_subteste [sem recusa]'))

    def test_linha_do_pulo(self):
        self.assertIn('pulado no isolamento: ', '\n'.join(self.linhas))

    def test_fora_do_isolamento_nada_muda(self):
        original = unittest.TestCase.run
        isolamento.sem_autoridade = lambda: False
        isolamento.instalar()
        self.assertIs(unittest.TestCase.run, original)


if __name__ == '__main__':
    if sys.argv[1:] == ['--interna']:
        rodar_interna()
    else:
        unittest.main(defaultTest='Ajudante')
