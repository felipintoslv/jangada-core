#!/usr/bin/env python3
"""Preserva pedidos acima do limite de um argumento com provedor sintético."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('baseline', Path(__file__).with_name('baseline.py'))
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class Contexto(unittest.TestCase):
    setUp = baseline.Baseline.setUp
    git = baseline.Baseline.git
    executavel = baseline.Baseline.executavel
    metadados = baseline.Baseline.metadados
    mudar = baseline.Baseline.mudar
    validar = baseline.Baseline.validar
    marca = baseline.Baseline.marca

    def test_pedido_grande_preserva_bytes_e_decisao(self):
        texto = 'conteúdo sintético ' * 12000
        self.mudar('grande.txt', texto)
        self.env['JANGADA_VALIDAR_DIFF_MAX'] = '400000'
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        contexto = json.loads((self.estado / 'revisoes/validacao-teste-r1.contexto.json').read_text())
        self.assertGreater(len(contexto['pedido'].encode()), 131072)
        self.assertIn(texto, contexto['pedido'])
        self.assertEqual(contexto['candidate_sha'], self.git('rev-parse', 'HEAD'))
        self.assertTrue(self.marca().exists())


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
