#!/usr/bin/env python3
"""Confere totais, incerteza e histórico de revisão sem serviços externos."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from estado import Estado
from metricas_projeto import ler_precos, resumir


class Indicadores(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.estado = Estado(self.pasta / 'estado')
        self.addCleanup(self.estado.fechar)

    def importar(self, identificador='T1', **campos):
        self.estado.importar([{'id': identificador, 'papel': 'leitor', 'capacidade': 'leitura_documental',
            'pedido': 'Leia', 'risco': 1, 'qualidade': 'medium', 'fontes': ['fonte.md'], **campos}])

    def finalizar(self, chamadas=1, segundos=3, status='REVIEW_REQUIRED', registro=None):
        tarefa, dono = self.estado.reservar()
        resultado = {'execucao_iniciada': chamadas != 0,
                     'metricas': {'chamadas': chamadas, 'segundos': segundos},
                     'delegacao': registro if registro is not None else {'destino': 'local', 'modelo': 'qwen'}}
        self.estado.finalizar(tarefa['id'], dono, status, resultado,
                             'relatório' if status == 'REVIEW_REQUIRED' else None)
        return tarefa['id']

    def test_fila_vazia_tem_totais_zero_e_custo_desconhecido(self):
        resultado = resumir(self.estado)
        self.assertEqual(resultado['chamadas'], 0)
        self.assertEqual(resultado['tarefas'], 0)
        self.assertIsNone(resultado['custo_estimado'])
        self.assertEqual(resultado['desempenho'], [])

    def test_totais_nao_duplicam_apos_revisao_ou_nova_consulta(self):
        self.importar()
        self.finalizar()
        self.estado.revisar('T1', 'conferido', True)
        eventos = self.estado.db.execute('SELECT count(*) FROM eventos').fetchone()[0]
        resultado = resumir(self.estado)
        self.assertEqual(resultado, resumir(self.estado))
        self.assertEqual(resultado['chamadas'], 1)
        self.assertEqual(resultado['segundos'], 3)
        self.assertEqual(resultado['revisoes_aprovadas'], 1)
        self.assertEqual(resultado['estados'], {'COMPLETED': 1})
        self.assertEqual(eventos, self.estado.db.execute('SELECT count(*) FROM eventos').fetchone()[0])
        self.assertFalse(self.estado.db.in_transaction)

    def test_recusa_nao_e_processamento(self):
        self.importar()
        self.finalizar(chamadas=0, status='WAITING_QUOTA')
        resultado = resumir(self.estado)
        self.assertEqual(resultado['processamentos_confirmados'], 0)
        self.assertEqual(resultado['recusas_sem_chamadas'], 1)
        self.assertEqual(resultado['tokens_entrada'], 0)

    def test_consumo_desconhecido_preserva_parcela_conhecida(self):
        self.importar()
        self.finalizar()
        self.importar('T2')
        self.finalizar(chamadas=None, status='REVISION_REQUIRED')
        resultado = resumir(self.estado)
        self.assertIsNone(resultado['chamadas'])
        self.assertEqual(resultado['chamadas_confirmadas'], 1)
        self.assertEqual(resultado['chamadas_desconhecidas'], 1)
        self.assertIsNone(resultado['tokens_entrada'])

    def test_reserva_expirada_nao_parece_consumo_zero(self):
        self.importar()
        with patch('estado.time.time', return_value=100):
            self.estado.reservar(1)
        with patch('estado.time.time', return_value=102):
            self.estado.reservar()
        resultado = resumir(self.estado)
        self.assertEqual(resultado['reservas_expiradas'], 1)
        self.assertIsNone(resultado['chamadas'])
        self.assertIsNone(resultado['segundos'])
        self.assertIsNone(resultado['tokens_saida'])
        grupo = resultado['por_executor'][0]
        self.assertEqual(grupo['executor'], 'nao_informado')
        self.assertEqual(grupo['reservas_expiradas'], 1)
        self.assertEqual(grupo['duracoes_do_fluxo_desconhecidas'], 1)

    def test_reserva_em_aberto_nao_parece_consumo_zero(self):
        self.importar()
        self.estado.reservar()
        resultado = resumir(self.estado)
        self.assertEqual(resultado['reservas_em_aberto'], 1)
        self.assertEqual(resultado['processamentos_confirmados'], 0)
        self.assertIsNone(resultado['chamadas'])
        self.assertIsNone(resultado['tokens_entrada'])
        self.assertIsNone(resultado['segundos'])
        self.assertEqual(resultado['por_executor'][0]['reservas_em_aberto'], 1)

    def test_duracao_omitida_nao_e_zero_e_bloqueia_repeticao(self):
        self.importar()
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVISION_REQUIRED', {'metricas': {'chamadas': 1}})
        resultado = resumir(self.estado)
        self.assertIsNone(resultado['segundos'])
        self.assertEqual(resultado['chamadas'], 1)
        self.assertEqual(resultado['duracoes_desconhecidas'], 1)
        self.assertEqual(resultado['por_executor'][0]['duracoes_do_fluxo_desconhecidas'], 1)
        self.assertIsNone(self.estado.consumo('T1')['chamadas'])
        self.assertEqual(resultado['processamentos_confirmados'], 1)

    def test_tokens_sem_chamadas_sao_zero_e_chamada_sem_medicao_e_desconhecida(self):
        self.importar()
        self.finalizar(chamadas=0, status='WAITING_QUOTA')
        resultado = resumir(self.estado)
        self.assertEqual(resultado['tokens_entrada'], 0)
        self.assertEqual(resultado['tokens_saida'], 0)
        self.importar('T2')
        self.finalizar(chamadas=1)
        resultado = resumir(self.estado)
        self.assertIsNone(resultado['tokens_entrada'])
        self.assertIsNone(resultado['tokens_saida'])

    def test_repeticao_preserva_consumo_e_revisoes(self):
        self.importar()
        self.finalizar()
        self.estado.revisar('T1', 'corrigir', False)
        self.estado.alterar('T1', 'repetir')
        self.finalizar()
        self.estado.revisar('T1', 'conferido', True)
        resultado = resumir(self.estado)
        self.assertEqual(resultado['chamadas'], 2)
        self.assertEqual(resultado['repeticoes_solicitadas'], 1)
        self.assertEqual(resultado['desempenho'][0]['revisoes_na_janela'], 2)
        self.assertEqual(resultado['desempenho'][0]['taxa_reprovacao'], 0.5)

    def test_tokens_codex_conhecidos_e_mudanca_entre_candidatos(self):
        self.importar()
        registro = {'destino': 'codex-economico', 'modelo': 'modelo-teste',
            'tokens_codex_entrada': 10, 'tokens_codex_saida': 4,
            'tentativas': [{'destino': 'agy', 'chamadas': 0}, {'destino': 'codex-economico', 'chamadas': 1}]}
        self.finalizar(registro=registro)
        resultado = resumir(self.estado)
        self.assertEqual(resultado['tokens_entrada'], 10)
        self.assertEqual(resultado['tokens_saida'], 4)
        self.assertEqual(resultado['mudancas_entre_candidatos'], 1)
        self.assertEqual(resultado['por_executor'][0]['executor'], 'codex-economico')

    PRECOS = {'moeda': 'USD', 'precos': {'codex-economico': {
        'modelo-teste': {'entrada_por_milhao': 2, 'saida_por_milhao': 10.5}}}}

    def codex(self, identificador, modelo='modelo-teste', chamadas=1, **campos):
        self.importar(identificador)
        self.finalizar(chamadas=chamadas, registro={'destino': 'codex-economico', 'modelo': modelo,
                                                    'tokens_codex_entrada': 100000, 'tokens_codex_saida': 20000, **campos})

    def test_custo_usa_preco_declarado_e_tokens_completos(self):
        self.codex('T1')
        self.codex('T2')
        self.importar('T3')
        self.finalizar(chamadas=0, status='WAITING_QUOTA')
        resultado = resumir(self.estado, self.PRECOS)
        self.assertEqual(resultado['custo_estimado'], 0.82)
        self.assertEqual(resultado['custo_estimado_confirmado'], 0.82)
        self.assertEqual(resultado['execucoes_sem_custo'], 0)
        self.assertEqual(resultado['moeda'], 'USD')
        grupo = next(g for g in resultado['por_executor'] if g['executor'] == 'codex-economico')
        self.assertEqual(grupo['custo_estimado_confirmado'], 0.82)
        sem_tabela = resumir(self.estado)
        self.assertIsNone(sem_tabela['custo_estimado'])
        self.assertIsNone(sem_tabela['moeda'])
        self.assertEqual(sem_tabela['execucoes_sem_custo'], 2)

    def test_custo_desconhecido_sem_preco_tokens_ou_reserva_concluida(self):
        self.codex('T1')
        casos = (lambda: self.codex('S1', modelo='sem-preco'), lambda: self.codex('S2', chamadas=2),
                 lambda: self.codex('S3', tokens_codex_saida=None),
                 lambda: (self.importar('S4'), self.finalizar()),
                 lambda: (self.importar('S5'), self.estado.reservar()))
        for sem_custo, caso in enumerate(casos, 1):
            with self.subTest(caso=sem_custo):
                caso()
                resultado = resumir(self.estado, self.PRECOS)
                self.assertIsNone(resultado['custo_estimado'])
                self.assertEqual(resultado['custo_estimado_confirmado'], 0.41)
                self.assertEqual(resultado['execucoes_sem_custo'], sem_custo)
        self.assertEqual(sum(g['execucoes_sem_custo'] for g in resultado['por_executor']), 5)

    def test_tabela_de_precos_ausente_ou_invalida(self):
        arquivo = self.pasta / 'precos.json'
        self.assertIsNone(ler_precos(arquivo))
        arquivo.write_text(json.dumps(self.PRECOS))
        self.assertEqual(ler_precos(arquivo), self.PRECOS)
        preco = {'entrada_por_milhao': 1, 'saida_por_milhao': 1}
        for invalido in ([], {'moeda': 'USD'}, {'moeda': '', 'precos': {}}, {'moeda': 'USD', 'precos': {'x': preco}},
                         {'moeda': 'USD', 'precos': {'x': {'m': {**preco, 'saida_por_milhao': -1}}}},
                         {'moeda': 'USD', 'precos': {'x': {'m': {**preco, 'entrada_por_milhao': True}}}},
                         {'moeda': 'USD', 'precos': {'x': {'m': {'entrada_por_milhao': 1}}}},
                         {'moeda': 'USD', 'precos': {'x': {'m': {**preco, 'cache': 1}}}}):
            with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                arquivo.write_text(json.dumps(invalido))
                ler_precos(arquivo)

    def test_tokens_parciais_nao_viram_total_da_cadeia(self):
        self.importar()
        self.finalizar(chamadas=2, registro={'destino': 'codex-economico', 'modelo': 'teste',
            'tokens_codex_entrada': 10, 'tokens_codex_saida': 4})
        resultado = resumir(self.estado)
        self.assertEqual(resultado['tokens_entrada_confirmados'], 10)
        self.assertIsNone(resultado['tokens_entrada'])
        self.assertEqual(resultado['por_executor'][0]['chamadas_do_fluxo_confirmadas'], 2)

    def test_cadeia_interrompida_preserva_chamadas_parciais(self):
        self.importar()
        self.finalizar(chamadas=None, status='REVISION_REQUIRED', registro={
            'destino': 'agy', 'tentativas': [{'destino': 'local', 'chamadas': 2},
                                           {'destino': 'agy', 'chamadas': None}]})
        resultado = resumir(self.estado)
        self.assertIsNone(resultado['chamadas'])
        self.assertEqual(resultado['chamadas_confirmadas'], 2)

    def test_recomendacao_intermediaria_e_limite_estrito(self):
        for i in range(20):
            self.importar(f'T{i}')
            self.finalizar()
            self.estado.revisar(f'T{i}', 'parecer', i != 0)
        self.assertEqual(resumir(self.estado)['desempenho'][0]['amostragem_sugerida'], 0.1)
        self.importar('F1')
        self.finalizar()
        self.estado.revisar('F1', 'corrigir', False)
        self.assertEqual(resumir(self.estado)['desempenho'][0]['amostragem_sugerida'], 0.5)

    def test_erro_de_leitura_encerra_transacao(self):
        self.importar()
        self.estado.db.execute("UPDATE eventos SET dados='nao-json'")
        with self.assertRaises(ValueError):
            resumir(self.estado)
        self.assertFalse(self.estado.db.in_transaction)

    def test_janela_e_limiares_com_amostra_minima(self):
        for i in range(70):
            self.importar(f'T{i}')
            self.finalizar()
            self.estado.revisar(f'T{i}', 'parecer', i >= 20)
        grupo = resumir(self.estado)['desempenho'][0]
        self.assertEqual(grupo['revisoes_na_janela'], 50)
        self.assertEqual(grupo['taxa_reprovacao'], 0)
        self.assertEqual(grupo['amostragem_sugerida'], 0.1)
        for i in range(8):
            self.importar(f'F{i}')
            self.finalizar()
            self.estado.revisar(f'F{i}', 'corrigir', False)
        grupo = resumir(self.estado)['desempenho'][0]
        self.assertEqual(grupo['amostragem_sugerida'], 1)
        self.assertEqual(grupo['reprovadas'], 8)

    def test_risco_moderado_e_historico_insuficiente_mantem_amostra_total(self):
        for i in range(20):
            self.importar(f'T{i}', risco=2)
            self.finalizar()
            self.estado.revisar(f'T{i}', 'conferido', True)
        grupo = resumir(self.estado)['desempenho'][0]
        self.assertEqual(grupo['amostragem_sugerida'], 1)
        self.importar('R1')
        self.finalizar()
        self.estado.revisar('R1', 'conferido', True)
        self.assertTrue(all(g['amostragem_sugerida'] == 1 for g in resumir(self.estado)['desempenho']))

    def test_cli_consulta_metricas_e_rejeita_importacao_simultanea(self):
        ambiente = {**os.environ, 'JANGADA_ESTADO': str(self.pasta / 'cli-estado'),
                    'JANGADA_CORE_PATH': str(RAIZ)}
        comando = [sys.executable, str(RAIZ / 'orquestracao/cli.py'), 'fila', '--projeto', str(self.pasta)]
        consulta = subprocess.run([*comando, '--metricas'], env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(consulta.returncode, 0, consulta.stderr)
        self.assertEqual(json.loads(consulta.stdout)['metricas']['tarefas'], 0)
        config = self.pasta / 'config'
        config.mkdir()
        (config / 'precos.json').write_text(json.dumps(self.PRECOS))
        ambiente['JANGADA_CONFIG'] = str(config)
        consulta = subprocess.run([*comando, '--metricas'], env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(consulta.stdout)['metricas']['custo_estimado'], 0)
        (config / 'precos.json').write_text('{"moeda": "USD"}')
        consulta = subprocess.run([*comando, '--metricas'], env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(consulta.returncode, 2)
        self.assertIn('precos.json', consulta.stderr)
        recusa = subprocess.run([*comando, '--metricas', '--importar', 'ausente.json'],
                                env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(recusa.returncode, 2)


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
