#!/usr/bin/env python3
"""Verifica persistência, dependências, reservas e revisão dos artefatos."""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
SPEC = importlib.util.spec_from_file_location('estado', RAIZ / 'orquestracao/estado.py')
MODULO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULO)


def tarefa(identificador='T1', **campos):
    return {'id': identificador, 'pedido': 'Leia a fonte', 'papel': 'leitor',
            'capacidade': 'leitura_documental', 'risco': 1, 'qualidade': 'medium',
            'fontes': ['fonte.md'], **campos}


class Persistencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name) / 'estado'
        self.estado = MODULO.Estado(self.pasta)
        self.addCleanup(lambda: self.estado.fechar())

    def test_consultas_de_eventos_por_tarefa_usam_indice(self):
        consultas = (
            "SELECT dados FROM eventos WHERE tarefa=? AND evento='reservada' ORDER BY seq DESC LIMIT 1",
            'SELECT evento,dados FROM eventos WHERE tarefa=? AND evento IN (?,?)',
        )
        for consulta in consultas:
            plano = ' '.join(linha['detail'] for linha in self.estado.db.execute(
                'EXPLAIN QUERY PLAN ' + consulta, ('T1', 'a', 'b')[:consulta.count('?')]))
            self.assertIn('USING INDEX eventos_tarefa', plano)
            self.assertNotIn('SCAN eventos', plano)

    def test_importacao_idempotente_sem_apagar_execucao(self):
        self.estado.importar([tarefa()])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {'gate': 'PASS'}, 'relatório')
        self.estado.revisar('T1', 'conferido na fonte', True)
        self.estado.importar([tarefa()])
        self.assertEqual(self.estado.listar()[0]['status'], 'COMPLETED')
        self.assertIsNone(self.estado.reservar())
        with self.assertRaises(ValueError):
            self.estado.importar([tarefa(pedido='Pedido alterado')])

    def test_dag_importacao_atomica(self):
        for plano in (
            [tarefa(dependencias=['T2'])],
            [tarefa(dependencias=['T2']), tarefa('T2', dependencias=['T1'])],
            [tarefa(), tarefa()],
        ):
            with self.subTest(plano=plano), self.assertRaises(ValueError):
                self.estado.importar(plano)
            self.assertEqual(self.estado.listar(), [])

    def test_prioridades_ordenam_tarefas_prontas(self):
        self.estado.importar([tarefa('B', prioridade='background'), tarefa('N'),
                             tarefa('L', prioridade='low'), tarefa('H', prioridade='high'),
                             tarefa('C', prioridade='critical')])
        escolhidas = []
        for _ in range(5):
            spec, dono = self.estado.reservar()
            escolhidas.append(spec['id'])
            self.estado.finalizar(spec['id'], dono, 'WAITING_REVIEWER', {})
        self.assertEqual(escolhidas, ['C', 'H', 'N', 'L', 'B'])

    def test_empate_preserva_ordem_antiga_e_identificador(self):
        with patch.object(MODULO.time, 'time', return_value=100):
            self.estado.importar([tarefa('Z'), tarefa('Y')])
        with patch.object(MODULO.time, 'time', return_value=101):
            self.estado.importar([tarefa('B'), tarefa('A')])
        self.assertEqual(self.estado.reservar()[0]['id'], 'Y')
        self.assertEqual(self.estado.reservar()[0]['id'], 'Z')
        self.assertEqual(self.estado.reservar()[0]['id'], 'A')

    def test_dependencia_herda_prioridade_critica_sem_alterar_especificacao(self):
        self.estado.importar([tarefa('Normal'), tarefa('Base', prioridade='background'),
                             tarefa('Final', prioridade='critical', dependencias=['Base'])])
        spec, dono = self.estado.reservar()
        self.assertEqual(spec['id'], 'Base')
        self.assertEqual(spec['prioridade'], 'background')
        evento = self.estado.db.execute("SELECT dados FROM eventos WHERE evento='reservada'").fetchone()
        self.assertEqual(json.loads(evento['dados'])['prioridade_efetiva'], 'critical')
        self.estado.finalizar('Base', dono, 'REVIEW_REQUIRED', {}, 'relatório')
        self.assertEqual(self.estado.reservar()[0]['id'], 'Normal')

    def test_prioridade_transitiva_em_cadeia_longa(self):
        plano = [tarefa('Normal')]
        for indice in range(1100):
            plano.append(tarefa(f'P{indice}', prioridade='background',
                               dependencias=[f'P{indice - 1}'] if indice else []))
        plano.append(tarefa('Final', prioridade='critical', dependencias=['P1099']))
        self.estado.importar(plano)
        self.assertEqual(self.estado.reservar()[0]['id'], 'P0')

    def test_antecipa_base_mesmo_com_outra_dependencia_em_revisao(self):
        self.estado.importar([tarefa('Revisao')])
        _, dono = self.estado.reservar()
        self.estado.finalizar('Revisao', dono, 'REVIEW_REQUIRED', {}, 'relatório')
        self.estado.importar([tarefa('Normal'), tarefa('Base', prioridade='background'),
                             tarefa('Final', prioridade='critical', dependencias=['Base', 'Revisao'])])
        self.assertEqual(self.estado.reservar()[0]['id'], 'Base')
        self.assertEqual(next(t for t in self.estado.listar() if t['id'] == 'Final')['status'], 'QUEUED')

    def test_descendente_pausado_nao_promove_dependencia(self):
        self.estado.importar([tarefa('Normal'), tarefa('Base', prioridade='background'),
                             tarefa('Final', prioridade='critical', dependencias=['Base'])])
        self.estado.alterar('Final', 'pausar')
        self.assertEqual(self.estado.reservar()[0]['id'], 'Normal')

    def test_descendente_bloqueado_nao_promove_outro_antecessor(self):
        self.estado.importar([tarefa('Normal'), tarefa('Base', prioridade='background'),
                             tarefa('Cancelada'), tarefa('Final', prioridade='critical',
                                                        dependencias=['Base', 'Cancelada'])])
        self.estado.alterar('Cancelada', 'cancelar')
        self.assertEqual(self.estado.reservar()[0]['id'], 'Normal')
        self.assertEqual(next(t for t in self.estado.listar() if t['id'] == 'Final')['status'], 'BLOCKED')

    def test_reinicio_preserva_prioridade_sem_interromper_reserva(self):
        self.estado.importar([tarefa('Normal')])
        self.estado.reservar()
        self.estado.importar([tarefa('Critica', prioridade='critical')])
        outro = MODULO.Estado(self.pasta)
        self.addCleanup(outro.fechar)
        self.assertEqual(outro.reservar()[0]['id'], 'Critica')
        self.assertTrue(all(t['status'] == 'RUNNING' for t in outro.listar()))

    def test_dependencia_exige_revisao(self):
        self.estado.importar([tarefa(), tarefa('T2', dependencias=['T1'])])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {'gate': 'PASS'}, 'relatório')
        self.assertIsNone(self.estado.reservar())
        self.estado.revisar('T1', 'fiel à fonte', True)
        self.assertEqual(self.estado.reservar()[0]['id'], 'T2')

    def test_artefato_adulterado_nao_aprova(self):
        self.estado.importar([tarefa()])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {}, 'relatório')
        resumo = self.estado.listar()[0]
        (self.pasta / 'artefatos' / f'{resumo["artefato"]}.txt').write_text('alterado')
        with self.assertRaises(ValueError):
            self.estado.revisar('T1', 'aprovado', True)
        self.assertEqual(self.estado.listar()[0]['status'], 'REVIEW_REQUIRED')

    def test_reserva_expirada_exige_conferencia(self):
        self.estado.importar([tarefa()])
        with patch.object(MODULO.time, 'time', return_value=100):
            _, dono = self.estado.reservar(10)
        with patch.object(MODULO.time, 'time', return_value=111):
            self.assertIsNone(self.estado.reservar())
            with self.assertRaises(ValueError):
                self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {}, 'relatório')
        self.assertEqual(self.estado.listar()[0]['status'], 'REVISION_REQUIRED')

    def test_reserva_de_outro_executor_nao_finaliza(self):
        self.estado.importar([tarefa()])
        self.estado.reservar()
        with self.assertRaises(ValueError):
            self.estado.finalizar('T1', 'outro', 'REVIEW_REQUIRED', {}, 'relatório')
        with self.assertRaises(ValueError):
            self.estado.finalizar('T1', 'outro', 'COMPLETED', {}, 'relatório')

    def test_reinicio_preserva_resultado_e_dependencia(self):
        self.estado.importar([tarefa(), tarefa('T2', dependencias=['T1'])])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'WAITING_QUOTA', {'motivo': 'cota esgotada'})
        outra = MODULO.Estado(self.pasta)
        self.addCleanup(outra.fechar)
        self.assertEqual(outra.listar()[0]['status'], 'WAITING_QUOTA')
        self.assertIsNone(outra.reservar())
        outra.alterar('T1', 'retomar')
        self.assertEqual(outra.reservar()[0]['id'], 'T1')

    def test_limite_de_tentativas(self):
        self.estado.importar([tarefa(max_tentativas=1)])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVISION_REQUIRED', {'motivo': 'falha'})
        self.estado.alterar('T1', 'repetir')
        self.assertIsNone(self.estado.reservar())
        self.assertEqual(self.estado.listar()[0]['status'], 'FAILED')

    def test_cancelamento_e_pausa(self):
        self.estado.importar([tarefa(), tarefa('T2')])
        self.estado.alterar('T1', 'pausar')
        self.estado.alterar('T2', 'cancelar')
        self.assertIsNone(self.estado.reservar())
        self.estado.alterar('T1', 'retomar')
        self.assertEqual(self.estado.reservar()[0]['id'], 'T1')
        with self.assertRaises(ValueError):
            self.estado.alterar('T2', 'retomar')

    def test_dois_executores_nao_reservam_a_mesma_tarefa(self):
        self.estado.importar([tarefa()])
        resultados = []
        barreira = threading.Barrier(2)

        def reservar():
            outro = MODULO.Estado(self.pasta)
            try:
                barreira.wait()
                resultados.append(outro.reservar())
            finally:
                outro.fechar()

        threads = [threading.Thread(target=reservar) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(resultados), 2)
        self.assertEqual(sum(resultado is not None for resultado in resultados), 1)

    def test_entrada_invalida_nao_cria_tarefas(self):
        for alteracao in ({'risco': True}, {'fontes': []}, {'qualidade': 'unknown'},
                          {'max_tentativas': 0}, {'dependencias': ['T1']},
                          {'permitir_remoto': 'true'}, {'permitir_codex': 'true'}, {'requisitos': ['-opcao']},
                          {'prioridade': 'urgente'}, {'prioridade': True}, {'prioridade': []}):
            with self.subTest(alteracao=alteracao), self.assertRaises(ValueError):
                self.estado.importar([tarefa(**alteracao)])
        self.assertEqual(self.estado.listar(), [])

    def test_estado_por_link_simbolico_recusado(self):
        link = pathlib.Path(self.tmp.name) / 'link'
        link.symlink_to(self.pasta, target_is_directory=True)
        with self.assertRaises(ValueError):
            MODULO.Estado(link)
        with self.assertRaises(ValueError):
            MODULO.Estado(link / 'subpasta', raiz=self.tmp.name)

    def test_raiz_configurada_por_link_e_permissoes(self):
        link = pathlib.Path(self.tmp.name) / 'raiz'
        link.symlink_to(self.pasta, target_is_directory=True)
        outro = MODULO.Estado(link / 'projeto', raiz=link)
        self.addCleanup(outro.fechar)
        self.assertEqual(outro.pasta, self.pasta / 'projeto')
        self.assertEqual(outro.pasta.stat().st_mode & 0o777, 0o700)
        self.assertEqual((outro.pasta / 'tarefas.sqlite').stat().st_mode & 0o777, 0o600)

    def test_revisao_em_lote_e_atomica(self):
        self.estado.importar([tarefa('T1'), tarefa('T2'), tarefa('T3')])
        for _ in range(2):
            item, dono = self.estado.reservar()
            self.estado.finalizar(item['id'], dono, 'REVIEW_REQUIRED', {}, 'relatório')
        for ids in (['T1', 'T3'], ['T1', 'T1'], ['T1', 'ausente'], []):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.estado.revisar_lote(ids, 'conferido', True)
        situacao = {item['id']: item['status'] for item in self.estado.listar()}
        self.assertEqual(situacao, {'T1': 'REVIEW_REQUIRED', 'T2': 'REVIEW_REQUIRED', 'T3': 'QUEUED'})
        self.estado.revisar_lote(['T1', 'T2'], 'conferido', True)
        self.assertEqual([item['status'] for item in self.estado.listar()], ['COMPLETED', 'COMPLETED', 'QUEUED'])

    def test_revisao_exige_artefato_e_nao_permite_pausa(self):
        self.estado.importar([tarefa()])
        _, dono = self.estado.reservar()
        for artefato in (None, '', '   '):
            with self.subTest(artefato=artefato), self.assertRaises(ValueError):
                self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {}, artefato)
        for status in ('PAUSED', 'CANCELLED'):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.estado.finalizar('T1', dono, status, {})
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {}, 'ação com acentuação')
        with self.assertRaises(ValueError):
            self.estado.alterar('T1', 'pausar')
        self.estado.revisar('T1', 'referência incompleta', False)
        with self.assertRaises(ValueError):
            self.estado.alterar('T1', 'pausar')
        self.estado.alterar('T1', 'repetir')
        item = self.estado.listar()[0]
        self.assertIsNone(item['artefato'])
        self.assertIsNone(item['resultado'])
        self.assertEqual(self.estado.reservar()[0]['id'], 'T1')

    def test_escrita_interrompida_nao_deixa_artefato_final(self):
        self.estado.importar([tarefa()])
        _, dono = self.estado.reservar()
        with patch.object(MODULO.os, 'replace', side_effect=OSError('interrompido')):
            with self.assertRaises(OSError):
                self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {}, 'relatório')
        self.assertEqual(list((self.pasta / 'artefatos').iterdir()), [])
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {}, 'relatório')
        self.assertEqual(self.estado.ler_artefato(self.estado.listar()[0]['artefato']), 'relatório')

    def test_dependencia_impedida_propaga_motivo(self):
        for status in ('FAILED', 'CANCELLED'):
            with self.subTest(status=status):
                estado = MODULO.Estado(pathlib.Path(self.tmp.name) / status)
                self.addCleanup(estado.fechar)
                estado.importar([tarefa(), tarefa('T2', dependencias=['T1']),
                                 tarefa('T3', dependencias=['T2'])])
                if status == 'FAILED':
                    _, dono = estado.reservar()
                    estado.finalizar('T1', dono, 'FAILED', {'motivo': 'erro'})
                else:
                    estado.alterar('T1', 'cancelar')
                self.assertIsNone(estado.reservar())
                itens = estado.listar()
                self.assertEqual([t['status'] for t in itens], [status, 'BLOCKED', 'BLOCKED'])
                self.assertIn('T1', itens[1]['motivo'])
                self.assertIn('T2', itens[2]['motivo'])

    def test_identificador_de_artefato_nao_e_caminho(self):
        with self.assertRaises(ValueError):
            self.estado.ler_artefato('../../segredo')
        externo = pathlib.Path(self.tmp.name) / 'externo'
        externo.mkdir()
        (self.pasta / 'artefatos').symlink_to(externo, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.estado.ler_artefato('0' * 64)

    def test_comandos_importam_sem_executar_dados(self):
        projeto = pathlib.Path(self.tmp.name) / 'projeto'
        projeto.mkdir()
        (projeto / 'fonte.md').write_text('conteúdo de teste')
        (projeto / 'plano.json').write_text(json.dumps([tarefa(comando='touch invasao'),
                                                     tarefa('T2', prioridade='critical')]))
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), XDG_STATE_HOME=str(pathlib.Path(self.tmp.name) / 'state'),
                        XDG_CONFIG_HOME=str(pathlib.Path(self.tmp.name) / 'config'))

        def executar(comando, *args):
            return subprocess.run([str(RAIZ / 'bin' / comando), *args], cwd=projeto,
                                  env=ambiente, capture_output=True, text=True, timeout=30)

        resultado = executar('jangada-fila', '--importar', 'plano.json', '--json')
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        fila = json.loads(resultado.stdout)
        self.assertEqual(fila['tarefas'][0]['status'], 'QUEUED')
        listagem = executar('jangada-fila')
        self.assertEqual(listagem.returncode, 0, listagem.stderr)
        linhas = {linha.split('\t')[0]: linha.split('\t') for linha in listagem.stdout.splitlines()}
        self.assertEqual(linhas['T1'][-1], 'normal')
        self.assertEqual(linhas['T2'][-1], 'critical')
        self.assertFalse((projeto / 'invasao').exists())
        self.assertEqual(executar('jangada-task', 'T1', 'pausar').returncode, 0)
        self.assertEqual(json.loads(executar('jangada-fila', '--json').stdout)['tarefas'][0]['status'], 'PAUSED')
        self.assertEqual(executar('jangada-task', 'T1', 'retomar').returncode, 0)
        self.assertEqual(executar('jangada-task', 'T1', 'revisar', '--aprovar').returncode, 2)

    def test_cli_recusa_fontes_fora_do_projeto(self):
        projeto = pathlib.Path(self.tmp.name) / 'projeto'
        projeto.mkdir()
        segredo = pathlib.Path(self.tmp.name) / 'segredo.txt'
        segredo.write_text('não enviar')
        (projeto / 'plano.json').write_text(json.dumps([tarefa(fontes=['../segredo.txt'])]))
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), XDG_STATE_HOME=str(pathlib.Path(self.tmp.name) / 'state'),
                        XDG_CONFIG_HOME=str(pathlib.Path(self.tmp.name) / 'config'))
        resultado = subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', 'plano.json'],
                                   cwd=projeto, env=ambiente, capture_output=True, text=True, timeout=30)
        self.assertEqual(resultado.returncode, 2)
        self.assertIn('fora do projeto', resultado.stderr)

    def test_cli_raiz_git_e_fonte_alterada(self):
        projeto = pathlib.Path(self.tmp.name) / 'repositorio'
        projeto.mkdir()
        subpasta = projeto / 'subpasta'
        subpasta.mkdir()
        subprocess.run(['git', 'init', '-q', str(projeto)], check=True, capture_output=True)
        fonte = projeto / 'fonte.md'
        fonte.write_text('conteúdo inicial', encoding='utf-8')
        plano = projeto / 'plano.json'
        plano.write_text(json.dumps([tarefa()]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), XDG_STATE_HOME=str(pathlib.Path(self.tmp.name) / 'state'),
                        XDG_CONFIG_HOME=str(pathlib.Path(self.tmp.name) / 'config'))

        def consultar(pasta, *args):
            return subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--json', *args], cwd=pasta,
                                  env=ambiente, capture_output=True, text=True, timeout=30)

        resultado = consultar(projeto, '--importar', str(plano))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(json.loads(resultado.stdout), json.loads(consultar(subpasta).stdout))
        fonte.write_text('conteúdo alterado', encoding='utf-8')
        resultado = consultar(subpasta, '--importar', str(plano))
        self.assertEqual(resultado.returncode, 2)
        self.assertIn('use outro identificador', resultado.stderr)
        self.assertEqual(json.loads(consultar(projeto).stdout)['tarefas'][0]['tentativas'], 0)


if __name__ == '__main__':
    unittest.main()
