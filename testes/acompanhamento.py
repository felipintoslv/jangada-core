#!/usr/bin/env python3
"""Confere acompanhamento com banco real, relógio e executores simulados."""

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
from acompanhamento import acompanhar, exclusividade
from estado import Estado
from saude import Saude


class Acompanhamento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.config = self.pasta / 'config'
        self.config.mkdir()
        (self.config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        self.estado = Estado(self.pasta / 'projeto')
        self.global_estado = Estado(self.pasta / 'global')
        self.addCleanup(self.estado.fechar)
        self.addCleanup(self.global_estado.fechar)
        self.saude = Saude(self.global_estado)
        self.agora = 0
        self.eventos = []
        self.ambiente = patch.dict(os.environ, JANGADA_DELEGAR='local')
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

    def importar(self, identificador='T1', **campos):
        self.estado.importar([{'id': identificador, 'pedido': 'Leia', 'papel': 'leitor',
                              'capacidade': 'leitura_documental', 'fontes': ['fonte.md'],
                              'risco': 1, 'qualidade': 'medium', **campos}])

    def aguardar(self, chamadas=0, segundos=0):
        spec, dono = self.estado.reservar()
        self.estado.finalizar(spec['id'], dono, 'WAITING_QUOTA',
                             {'execucao_iniciada': chamadas != 0,
                              'metricas': {'chamadas': chamadas, 'segundos': segundos}})

    def dormir(self, segundos):
        self.agora += segundos

    def executor(self, estado, *args, prazo=None):
        reserva = estado.reservar()
        if reserva is None:
            return []
        spec, dono = reserva
        disponivel = self.saude.listar()[1]['status'] == 'AVAILABLE'
        status = 'REVIEW_REQUIRED' if disponivel else 'WAITING_QUOTA'
        resultado = {'execucao_iniciada': disponivel,
                     'metricas': {'chamadas': int(disponivel), 'segundos': 0}}
        estado.finalizar(spec['id'], dono, status, resultado, 'texto' if disponivel else None)
        return [{'tarefa': spec['id'], 'status': status, **resultado}]

    def rodar(self, **opcoes):
        with patch('acompanhamento.time.monotonic', side_effect=lambda: self.agora), \
                patch('acompanhamento.time.sleep', side_effect=self.dormir), \
                patch('acompanhamento.executar', side_effect=self.executor):
            return acompanhar(self.estado, self.pasta, RAIZ, self.config, self.saude,
                               emitir=self.eventos.append, **opcoes)

    def test_cota_retorna_sem_consumir_limite_na_recusa(self):
        self.importar()
        def atualizar(remoto, prazo=None):
            self.assertFalse(remoto)
            self.saude.observar('local', 'AVAILABLE' if self.agora >= 120 else 'QUOTA_LOW', 'simulado')
        with patch.object(self.saude, 'atualizar', side_effect=atualizar) as sonda:
            fim = self.rodar(limite=1, duracao=180)
        self.assertEqual(fim['motivo'], 'limite_atingido')
        self.assertEqual(fim['execucoes'], 1)
        self.assertEqual(sonda.call_count, 2)
        self.assertEqual(self.estado.listar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(self.estado.listar()[0]['tentativas'], 1)
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 1)

    def test_prazo_e_frequencia_minima_das_sondas(self):
        self.importar()
        self.aguardar()
        with patch.object(self.saude, 'atualizar') as sonda:
            fim = self.rodar(intervalo=1, duracao=65)
        self.assertEqual(fim['motivo'], 'prazo_atingido')
        self.assertEqual(self.agora, 65)
        self.assertEqual(sonda.call_count, 2)
        self.assertEqual(fim['execucoes'], 0)

    def test_sonda_que_esgota_prazo_nao_inicia_execucao_nem_segunda_sonda(self):
        self.importar(permitir_remoto=True, permitir_codex=True)
        self.aguardar()
        (self.config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['agy', 'codex-economico']}))
        def sonda(remoto, prazo=None):
            self.assertTrue(remoto)
            self.assertEqual(prazo, 1)
            self.agora = 1
        with patch.dict(os.environ, JANGADA_DELEGAR='agy'), \
                patch.object(self.saude, 'atualizar', side_effect=sonda), \
                patch.object(self.saude, 'atualizar_codex') as codex, \
                patch('acompanhamento.time.monotonic', side_effect=lambda: self.agora), \
                patch('acompanhamento.executar') as executor:
            fim = acompanhar(self.estado, self.pasta, RAIZ, self.config, self.saude, duracao=1,
                              permitir_remoto=True, permitir_codex=True)
        codex.assert_not_called()
        executor.assert_not_called()
        self.assertEqual(fim['motivo'], 'prazo_atingido')
        self.assertEqual(self.estado.listar()[0]['status'], 'WAITING_QUOTA')

    def test_limite_cumulativo_e_tarefas_restantes(self):
        for i in range(3):
            self.importar(f'T{i}')
        self.saude.observar('local', 'AVAILABLE', 'simulado')
        fim = self.rodar(limite=2)
        self.assertEqual(fim['execucoes'], 2)
        self.assertEqual(fim['estados'], {'REVIEW_REQUIRED': 2, 'QUEUED': 1})

    def test_pendencia_de_revisao_nao_libera_dependencia(self):
        self.importar()
        self.importar('T2', dependencias=['T1'])
        self.saude.observar('local', 'AVAILABLE', 'simulado')
        fim = self.rodar()
        self.assertEqual(fim['motivo'], 'sem_tarefas_executaveis')
        self.assertEqual(fim['estados'], {'REVIEW_REQUIRED': 1, 'QUEUED': 1})

    def test_pausa_e_aprovacao_nao_sao_reexecutadas(self):
        self.importar()
        self.saude.observar('local', 'AVAILABLE', 'simulado')
        self.rodar()
        self.estado.revisar('T1', 'conteúdo conferido', True)
        self.importar('T2')
        self.estado.alterar('T2', 'pausar')
        with patch.object(self.saude, 'atualizar') as sonda:
            fim = self.rodar()
        sonda.assert_not_called()
        self.assertEqual(fim['estados'], {'COMPLETED': 1, 'PAUSED': 1})
        self.assertEqual(fim['execucoes'], 0)

    def test_consumo_desconhecido_ou_esgotado_nao_retoma(self):
        for chamadas, segundos in ((None, 0), (8, 0), (0, 600)):
            with self.subTest(chamadas=chamadas, segundos=segundos):
                identificador = f'T{len(self.estado.listar())}'
                self.importar(identificador)
                self.aguardar(chamadas, segundos)
        with patch.object(self.saude, 'atualizar') as sonda:
            fim = self.rodar()
        sonda.assert_not_called()
        self.assertEqual(fim['execucoes'], 0)
        self.assertEqual(fim['motivo'], 'sem_tarefas_executaveis')

    def test_perfil_local_nao_sonda_nuvem(self):
        (self.config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['agy', 'codex-economico']}))
        self.importar(permitir_remoto=True, permitir_codex=True)
        self.aguardar()
        with patch.object(self.saude, 'atualizar') as agy, patch.object(self.saude, 'atualizar_codex') as codex:
            fim = self.rodar(permitir_remoto=True, permitir_codex=True)
        agy.assert_not_called()
        codex.assert_not_called()
        self.assertEqual(fim['motivo'], 'sem_tarefas_executaveis')

    def test_capacidade_sem_adaptador_nao_sonda(self):
        self.importar(capacidade='coding_complex')
        self.aguardar()
        with patch.object(self.saude, 'atualizar') as sonda:
            self.rodar()
        sonda.assert_not_called()

    def test_trava_rejeita_segundo_monitor_e_libera_apos_interrupcao(self):
        with exclusividade(self.estado):
            with self.assertRaisesRegex(ValueError, 'já existe'):
                self.rodar()
        self.importar()
        self.aguardar()
        with patch('acompanhamento.time.sleep', side_effect=KeyboardInterrupt), \
                patch.object(self.saude, 'atualizar'):
            with self.assertRaises(KeyboardInterrupt):
                acompanhar(self.estado, self.pasta, RAIZ, self.config, self.saude)
        with exclusividade(self.estado):
            self.assertEqual(self.estado.listar()[0]['status'], 'WAITING_QUOTA')

    def test_trava_nao_segue_link(self):
        (self.estado.pasta / 'acompanhamento.lock').symlink_to(self.pasta / 'fora')
        with self.assertRaises(OSError):
            self.rodar()
        self.assertFalse((self.pasta / 'fora').exists())

    def test_argumentos_invalidos(self):
        for opcoes in ({'limite': 0}, {'limite': True}, {'intervalo': 0}, {'duracao': 86401}):
            with self.subTest(opcoes=opcoes), self.assertRaises(ValueError):
                self.rodar(**opcoes)

    def test_cli_sem_tarefas_e_opcoes_incompativeis(self):
        ambiente = {**os.environ, 'JANGADA_ESTADO': str(self.pasta / 'estado'),
                    'JANGADA_CONFIG': str(self.config), 'JANGADA_CORE_PATH': str(RAIZ)}
        comando = [sys.executable, str(RAIZ / 'orquestracao/cli.py'), 'executar',
                   '--projeto', str(self.pasta)]
        recusa = subprocess.run([*comando, '--intervalo', '1'], env=ambiente, capture_output=True, text=True)
        self.assertEqual(recusa.returncode, 2)
        self.assertFalse((self.pasta / 'estado').exists())
        resultado = subprocess.run([*comando, '--acompanhar'], env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        linhas = [json.loads(linha) for linha in resultado.stdout.splitlines()]
        self.assertEqual([linha['evento'] for linha in linhas], ['ciclo', 'fim'])
        self.assertEqual(linhas[-1]['motivo'], 'sem_tarefas_executaveis')


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
