#!/usr/bin/env python3
"""Integra fila e executor simulado sem chamar modelos ou serviços externos."""

import hashlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from estado import Estado
from executor import executar, assumir_principal, entregar_principal
from acompanhamento import acompanhar
from saude import Saude

SIMULADO = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
args = sys.argv[1:]
pathlib.Path(os.environ['REGISTRO_TESTE']).write_text(json.dumps({'args': args, 'env': {
    nome: os.environ.get(nome) for nome in ['JANGADA_DELEGAR_TEMPO_TOTAL',
    'JANGADA_DELEGAR_CHAMADAS_MAX', 'JANGADA_DELEGAR', 'JANGADA_DELEGAR_ROTEAMENTO_ID',
    'JANGADA_DELEGAR_IMPEDIMENTOS']}}))
modo = os.environ.get('MODO_TESTE', 'ok')
if modo == 'demorado':
    pathlib.Path(os.environ['REGISTRO_TESTE'] + '.delegado').write_text(str(os.getpid()))
    filho = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
    pathlib.Path(os.environ['REGISTRO_TESTE'] + '.filho').write_text(str(filho.pid))
    time.sleep(10)
if modo == 'paralelo':
    inicio = time.time()
    time.sleep(1)
    with open(os.environ['REGISTRO_TESTE'] + '.tempos', 'a') as tempos:
        tempos.write(json.dumps([inicio, time.time()]) + '\\n')
    modo = 'ok'
if modo == 'quebrado':
    print('saída não estruturada')
    sys.exit(0)
if modo == 'recusa':
    print(json.dumps({'tentativas': [], 'recusa': True, 'chamadas_executor': 0,
                      'motivo_codigo': 'destino_proibido'}))
    sys.exit(4)
if modo == 'saude':
    impedimentos = json.loads(os.environ['JANGADA_DELEGAR_IMPEDIMENTOS'])
    print(json.dumps({'tentativas': [dict(i, codigo_saida=4, chamadas=0) for i in impedimentos],
                      'destino': '', 'recusa': True, 'chamadas_executor': 0, 'motivo_codigo': 'sem_executor'}))
    sys.exit(4)
fontes = args[args.index('--arquivos') + 1:args.index('--')]
saida = pathlib.Path(args[args.index('--arquivo') + 1])
texto = '\\n'.join(f'Regra conferida na fonte indicada: {fonte}:1.' for fonte in fontes)
if modo == 'invalido':
    texto = 'Sem referências.'
if modo == 'mudou':
    pathlib.Path(fontes[0]).write_text('fonte alterada')
if modo in ('ok', 'invalido', 'mudou'):
    saida.write_text(texto, encoding='utf-8')
codigo = 'cota_insuficiente' if modo == 'cota' else ''
print(json.dumps({'destino': 'agy' if modo == 'cota' else 'local', 'modelo': 'qwen3:4b',
    'tentativas': [{'destino': 'local', 'chamadas': 0 if modo == 'cota' else 1,
    'motivo_codigo': codigo}], 'motivo_codigo': codigo, 'relatorio': 'prévia incompleta',
    'artefato': '/arquivo/que/nao/deve/ser/lido'}))
sys.exit(4 if modo == 'cota' else 0)
'''


def processo_vivo(pid):
    try:
        return pathlib.Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] != 'Z'
    except FileNotFoundError:
        return False


class Execucao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.projeto = self.pasta / 'projeto'
        self.projeto.mkdir()
        self.fonte = self.projeto / 'fonte.md'
        self.fonte.write_text('regra de teste', encoding='utf-8')
        self.raiz = self.pasta / 'jangada'
        (self.raiz / 'bin').mkdir(parents=True)
        (self.raiz / 'delegacao').mkdir(parents=True)
        shutil.copyfile(RAIZ / 'delegacao/validar.py', self.raiz / 'delegacao/validar.py')
        simulador = self.raiz / 'bin/jangada-delegar'
        simulador.write_text(SIMULADO, encoding='utf-8')
        simulador.chmod(0o700)
        self.estado = Estado(self.pasta / 'estado')
        self.addCleanup(self.estado.fechar)
        self.registro = self.pasta / 'registro.json'
        self.ambiente = patch.dict(os.environ, REGISTRO_TESTE=str(self.registro), MODO_TESTE='ok')
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

    def tarefa(self, identificador='T1', **campos):
        return {'id': identificador, 'pedido': 'Leia a regra', 'papel': 'leitor',
                'capacidade': 'leitura_documental', 'risco': 1, 'qualidade': 'medium',
                'fontes': [str(self.fonte)],
                'hashes_fontes': {str(self.fonte): hashlib.sha256(self.fonte.read_bytes()).hexdigest()}, **campos}

    def rodar(self, perfil='balanced', limite=1):
        return executar(self.estado, self.projeto, self.raiz, perfil, limite)

    def test_principais_entregam_sem_aprovar_ou_chamar_outro_modelo(self):
        for agente in ('claude', 'codex'):
            with self.subTest(agente=agente):
                self.estado.importar([self.tarefa(agente, risco=3, qualidade='high')])
                reserva = assumir_principal(self.estado, agente, self.projeto, agente)
                relatorio = self.projeto / f'{agente}.md'
                relatorio.write_text(f'Análise da regra documentada em {self.fonte}:1.')
                resultado = entregar_principal(self.estado, agente, reserva['dono'], self.projeto, self.raiz, relatorio)
                self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')
                self.assertIsNone(resultado['metricas']['chamadas'])
                self.assertEqual(resultado['executor'], agente)
                self.assertIsNone(self.estado.consumo(agente)['chamadas'])
                with self.assertRaises(ValueError):
                    entregar_principal(self.estado, agente, reserva['dono'], self.projeto, self.raiz, relatorio)
        self.assertFalse(self.registro.exists())

    def test_principal_recusa_risco_quatro_e_microtarefa(self):
        for risco, qualidade in ((4, 'high'), (1, 'medium')):
            id_tarefa = f'R{risco}'
            self.estado.importar([self.tarefa(id_tarefa, risco=risco, qualidade=qualidade)])
            with self.assertRaises(ValueError):
                assumir_principal(self.estado, id_tarefa, self.projeto, 'codex')
        self.assertTrue(all(t['status'] == 'QUEUED' and t['tentativas'] == 0 for t in self.estado.listar()))

    def test_principal_nao_assume_espera_de_cota_pausa_ou_tarefa_reservada(self):
        self.estado.importar([self.tarefa(risco=3)])
        self.estado.alterar('T1', 'pausar')
        with self.assertRaises(ValueError):
            assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        self.estado.alterar('T1', 'retomar')
        _, dono = self.estado.reservar()
        with self.assertRaises(ValueError):
            assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        self.estado.finalizar('T1', dono, 'WAITING_QUOTA', {'execucao_iniciada': False,
                              'metricas': {'chamadas': 0, 'segundos': 0}})
        with self.assertRaises(ValueError):
            assumir_principal(self.estado, 'T1', self.projeto, 'codex')

    def test_principal_exige_dependencia_aprovada_e_integra(self):
        self.estado.importar([self.tarefa(), self.tarefa('Final', risco=3, dependencias=['T1'])])
        with self.assertRaises(ValueError):
            assumir_principal(self.estado, 'Final', self.projeto, 'claude')
        self.rodar()
        self.estado.revisar('T1', 'conferido', True)
        reserva = assumir_principal(self.estado, 'Final', self.projeto, 'claude')
        dependencia = reserva['dependencias'][0]['arquivo']
        relatorio = self.projeto / 'final.md'
        relatorio.write_text(f'Análise da fonte {self.fonte}:1 e do relatório {dependencia}:1.')
        pathlib.Path(dependencia).write_text('alterado')
        resultado = entregar_principal(self.estado, 'Final', reserva['dono'], self.projeto, self.raiz, relatorio)
        self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
        self.assertIn('adulterado', resultado['motivo'])

    def test_principal_confere_fontes_na_reserva_e_na_entrega(self):
        self.estado.importar([self.tarefa(risco=3)])
        original = self.fonte.read_text()
        self.fonte.write_text('alterada')
        with self.assertRaises(ValueError):
            assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        self.fonte.write_text(original)
        reserva = assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        self.fonte.write_text('alterada')
        relatorio = self.projeto / 'final.md'
        relatorio.write_text(f'Regra descrita em {self.fonte}:1.')
        resultado = entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, relatorio)
        self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
        self.assertIn('alterada', resultado['motivo'])

    def test_principal_recusa_dono_errado_reserva_expirada_e_relatorio_externo(self):
        self.estado.importar([self.tarefa(risco=3)])
        reserva = assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        fora = self.pasta / 'fora.md'
        fora.write_text(f'Regra em {self.fonte}:1.')
        with self.assertRaises(ValueError):
            entregar_principal(self.estado, 'T1', 'outro', self.projeto, self.raiz, fora)
        with self.assertRaises(ValueError):
            entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, fora)
        with patch('executor.time.time', return_value=reserva['prazo'] + 1), self.assertRaises(ValueError):
            entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, fora)
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')

    def test_principal_preserva_relatorio_reprovado_e_exige_requisitos(self):
        self.estado.importar([self.tarefa(risco=3, requisitos=['Conclusão'])])
        reserva = assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        relatorio = self.projeto / 'final.md'
        relatorio.write_text(f'Regra em {self.fonte}:1.')
        resultado = entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, relatorio)
        self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
        self.assertEqual(self.estado.ler_artefato(self.estado.listar()[0]['artefato']), relatorio.read_text())

    def test_principal_respeita_consumo_e_tentativas(self):
        for campo, valor in (('max_tentativas', 1), ('tempo_total', 1), ('max_chamadas', 1)):
            self.estado.importar([self.tarefa(campo, risco=3, **{campo: valor})])
            _, dono = self.estado.reservar()
            self.estado.finalizar(campo, dono, 'WAITING_REVIEWER',
                                 {'metricas': {'chamadas': 1, 'segundos': 1}})
            with self.assertRaises(ValueError):
                assumir_principal(self.estado, campo, self.projeto, 'codex')

    def test_principal_recusa_consumo_desconhecido(self):
        self.estado.importar([self.tarefa(risco=3)])
        self.estado.evento('T1', 'execucao_encerrada', {'resultado': {'metricas': {'chamadas': None, 'segundos': 1}}})
        with self.assertRaises(ValueError):
            assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        self.assertEqual(self.estado.listar()[0]['tentativas'], 0)

    def test_principal_assume_esperas_sem_chamar_modelo_adicional(self):
        self.estado.importar([self.tarefa('P', papel='arquiteto', capacidade='architecture', risco=3),
                             self.tarefa('R', risco=3, qualidade='high')])
        self.assertEqual([r['status'] for r in self.rodar(limite=2)], ['WAITING_PROVIDER', 'WAITING_REVIEWER'])
        for identificador in ('P', 'R'):
            reserva = assumir_principal(self.estado, identificador, self.projeto, 'claude', 'declarado')
            self.assertEqual(reserva['status'], 'RUNNING')
            self.assertEqual(reserva['modelo_declarado'], 'declarado')
        self.assertFalse(self.registro.exists())

    def test_principal_utf8_invalido_mantem_reserva_para_corrigir(self):
        self.estado.importar([self.tarefa(risco=3)])
        reserva = assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        relatorio = self.projeto / 'relatorio.md'
        relatorio.write_bytes(b'\xff')
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, relatorio)
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')
        self.assertEqual(self.estado.db.execute("SELECT COUNT(*) FROM eventos WHERE evento='relatorio_recusado'").fetchone()[0], 1)
        relatorio.write_text(f'Regra descrita em {self.fonte}:1.')
        resultado = entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, relatorio)
        self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')

    def test_principal_prazo_expira_durante_gate_sem_persistir_saida(self):
        self.estado.importar([self.tarefa(risco=3)])
        reserva = assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        relatorio = self.projeto / 'relatorio.md'
        relatorio.write_text(f'Regra em {self.fonte}:1.')
        with patch('executor.time.time', return_value=reserva['prazo'] - 1) as relogio, \
                patch('executor.importlib.util.spec_from_file_location'), \
                patch('executor.importlib.util.module_from_spec') as gate:
            def expirar(*_):
                relogio.return_value = reserva['prazo'] + 1
            gate.return_value.verificar.side_effect = expirar
            with self.assertRaisesRegex(ValueError, 'reserva válida'):
                entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, relatorio)
        item = self.estado.listar()[0]
        self.assertEqual(item['status'], 'RUNNING')
        self.assertIsNone(item['artefato'])
        self.assertTrue(relatorio.is_file())

    def test_principal_recusa_relatorio_simbolico_especial_ou_grande(self):
        self.estado.importar([self.tarefa(risco=3)])
        reserva = assumir_principal(self.estado, 'T1', self.projeto, 'codex')
        arquivo = self.projeto / 'relatorio.md'
        arquivo.symlink_to(self.fonte)
        with self.assertRaises(OSError):
            entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, arquivo)
        arquivo.unlink()
        os.mkfifo(arquivo)
        with self.assertRaises(ValueError):
            entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, arquivo)
        arquivo.unlink()
        arquivo.write_bytes(b'x' * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            entregar_principal(self.estado, 'T1', reserva['dono'], self.projeto, self.raiz, arquivo)
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')

    def test_cli_principal_entrega_e_revisao_liberam_dependente(self):
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), JANGADA_ESTADO=str(self.pasta / 'cli-estado'),
                        XDG_STATE_HOME=str(self.pasta / 'state'), XDG_CONFIG_HOME=str(self.pasta / 'config'))
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(risco=3), self.tarefa('T2', dependencias=['T1'])]))
        def comando(*args):
            return subprocess.run([sys.executable, str(RAIZ / 'orquestracao/cli.py'), *args,
                                   '--projeto', str(self.projeto)], env=ambiente, capture_output=True, text=True, timeout=10)
        self.assertEqual(comando('fila', '--importar', str(plano)).returncode, 0)
        for args in (('assumir', '--executor', 'claude', '--dono', 'indevido'),
                     ('assumir', '--executor', 'claude', '--arquivo', str(plano)),
                     ('entregar', '--dono', 'indevido', '--arquivo', str(plano), '--modelo', 'indevido'),
                     ('entregar', '--dono', 'indevido', '--arquivo', str(plano), '--executor', 'codex')):
            with self.subTest(args=args):
                self.assertEqual(comando('task', 'T1', *args).returncode, 2)
        reserva = comando('task', 'T1', 'assumir', '--executor', 'claude')
        self.assertEqual(reserva.returncode, 0, reserva.stderr)
        relatorio = self.projeto / 'final.md'
        relatorio.write_text(f'Regra na fonte {self.fonte}:1.')
        entrega = comando('task', 'T1', 'entregar', '--dono', json.loads(reserva.stdout)['dono'], '--arquivo', str(relatorio))
        self.assertEqual(entrega.returncode, 0, entrega.stderr)
        self.assertEqual(json.loads(entrega.stdout)['status'], 'REVIEW_REQUIRED')
        self.assertEqual(comando('task', 'T1', 'revisar', '--aprovar', '--parecer', 'conferido').returncode, 0)
        itens = json.loads(comando('fila', '--json').stdout)['tarefas']
        self.assertEqual([t['status'] for t in itens], ['COMPLETED', 'QUEUED'])
        self.assertEqual(comando('task', 'T2', 'pausar', '--dono', 'indevido').returncode, 2)

    def test_preserva_relatorio_completo_sem_aprovar(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        resultados = self.rodar(limite=2)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]['status'], 'REVIEW_REQUIRED')
        item = self.estado.listar()[0]
        texto = self.estado.ler_artefato(item['artefato'])
        self.assertIn(str(self.fonte) + ':1', texto)
        self.assertNotIn('prévia', texto)
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 1)
        self.estado.revisar('T1', 'conferido', True)
        self.assertEqual(self.rodar()[0]['tarefa'], 'T2')
        argumentos = json.loads(self.registro.read_text())['args']
        self.assertTrue(any('/artefatos/' in argumento for argumento in argumentos))

    def test_prioridade_critica_nao_amplia_permissao_remota(self):
        self.estado.importar([self.tarefa('Normal'), self.tarefa('Critica', prioridade='critical',
                                                               permitir_remoto=False)])
        resultado = self.rodar()[0]
        self.assertEqual(resultado['tarefa'], 'Critica')
        argumentos = json.loads(self.registro.read_text())['args']
        self.assertNotIn('--permitir-remoto', argumentos)
        self.assertNotIn('--permitir-codex', argumentos)
        self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')

    def test_cota_nao_gasta_tentativa_e_preserva_espera(self):
        self.estado.importar([self.tarefa(max_tentativas=1)])
        with patch.dict(os.environ, MODO_TESTE='cota'):
            self.assertEqual(self.rodar()[0]['status'], 'WAITING_QUOTA')
        self.assertEqual(self.estado.listar()[0]['tentativas'], 0)
        self.assertEqual(self.rodar(), [])
        self.estado.alterar('T1', 'retomar')
        self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')

    def test_acompanhamento_retoma_com_adaptador_simulado_e_banco_real(self):
        config = self.pasta / 'config'
        config.mkdir()
        (config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        global_estado = Estado(self.pasta / 'global')
        self.addCleanup(global_estado.fechar)
        saude = Saude(global_estado)
        self.estado.importar([self.tarefa(max_tentativas=1)])
        agora, eventos = [0], []

        def dormir(segundos):
            agora[0] += segundos

        def atualizar(remoto, prazo=None):
            self.assertFalse(remoto)
            os.environ['MODO_TESTE'] = 'ok'
            saude.observar('local', 'AVAILABLE', 'simulado')

        with patch.dict(os.environ, MODO_TESTE='cota', JANGADA_DELEGAR='local'), \
                patch('acompanhamento.time.monotonic', side_effect=lambda: agora[0]), \
                patch('acompanhamento.time.sleep', side_effect=dormir), \
                patch.object(saude, 'atualizar', side_effect=atualizar):
            fim = acompanhar(self.estado, self.projeto, self.raiz, config, saude,
                              limite=1, intervalo=1, duracao=10, emitir=eventos.append)
        self.assertEqual(fim['motivo'], 'limite_atingido')
        self.assertEqual([e['resultados'][0]['status'] for e in eventos],
                         ['WAITING_QUOTA', 'REVIEW_REQUIRED'])
        self.assertEqual(self.estado.listar()[0]['tentativas'], 1)
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 1)
        self.assertIn(str(self.fonte) + ':1', self.estado.ler_artefato(self.estado.listar()[0]['artefato']))

    def test_orcamento_compartilhado_entre_repeticoes(self):
        self.estado.importar([self.tarefa(max_chamadas=1)])
        with patch.dict(os.environ, MODO_TESTE='invalido'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.estado.alterar('T1', 'repetir')
        self.registro.unlink()
        self.assertEqual(self.rodar()[0]['status'], 'FAILED')
        self.assertFalse(self.registro.exists())

    def test_consumo_desconhecido_nao_repete(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_TESTE='quebrado'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.estado.alterar('T1', 'repetir')
        self.registro.unlink()
        self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertFalse(self.registro.exists())

    def test_recusa_sem_tentativas_nao_bloqueia_consumo(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_TESTE='recusa'):
            self.assertEqual(self.rodar()[0]['status'], 'WAITING_PROVIDER')
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 0)
        self.assertEqual(self.estado.listar()[0]['tentativas'], 0)
        self.estado.alterar('T1', 'retomar')
        self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')

    def test_interrupcao_nao_inicia_proxima_tarefa(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2')])
        with patch('executor.subprocess.Popen') as fabrica, patch('executor.os.killpg') as matar:
            processo = fabrica.return_value
            processo.pid = 42
            processo.communicate.side_effect = [KeyboardInterrupt(), ('', '')]
            with self.assertRaises(KeyboardInterrupt):
                self.rodar(limite=2)
            matar.assert_called_once()
            fabrica.assert_called_once()
        self.assertEqual([t['status'] for t in self.estado.listar()], ['REVISION_REQUIRED', 'QUEUED'])
        self.assertIsNone(self.estado.consumo('T1')['chamadas'])

    def test_queda_sem_resultado_nao_reinicia_orcamento(self):
        self.estado.importar([self.tarefa()])
        self.estado.reservar()
        self.estado.db.execute('UPDATE tarefas SET prazo=0 WHERE id=?', ('T1',))
        self.assertIsNone(self.estado.reservar())
        self.estado.alterar('T1', 'repetir')
        self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertFalse(self.registro.exists())
        self.assertIsNone(self.estado.consumo('T1')['chamadas'])

    def test_evento_antigo_sem_objeto_resultado_exige_conferencia(self):
        self.estado.importar([self.tarefa()])
        self.estado.evento('T1', 'execucao_encerrada', {'resultado': ['formato antigo']})
        self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertFalse(self.registro.exists())

    def test_dependencia_adulterada_nao_e_enviada(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        self.rodar()
        self.estado.revisar('T1', 'conferido na fonte', True)
        resumo = self.estado.listar()[0]['artefato']
        (self.estado.pasta / 'artefatos' / f'{resumo}.txt').write_text('alterado')
        self.registro.unlink()
        self.assertEqual(self.rodar(), [])
        mapa = {t['id']: t for t in self.estado.listar()}
        self.assertEqual(mapa['T1']['status'], 'REVIEW_REQUIRED')
        self.assertEqual(mapa['T2']['status'], 'QUEUED')
        self.assertEqual(mapa['T2']['tentativas'], 0)
        self.assertFalse(self.registro.exists())

    def test_dependencia_ausente_no_mapa_preserva_estado(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        self.rodar()
        self.estado.revisar('T1', 'conferido na fonte', True)
        self.registro.unlink()
        with patch.object(self.estado, 'listar', side_effect=[[]]):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertFalse(self.registro.exists())

    def test_perfil_ainda_sem_politica_e_recusado(self):
        with self.assertRaises(ValueError):
            self.rodar('economico')

    def test_saude_injetada_vira_espera_sem_consumo(self):
        self.estado.importar([self.tarefa()])
        global_estado = Estado(self.pasta / 'global')
        self.addCleanup(global_estado.fechar)
        saude = Saude(global_estado)
        saude.pausar('local', True)
        saude.observar('agy', 'QUOTA_LOW', 'cota insuficiente', cota=10)
        with patch.dict(os.environ, MODO_TESTE='saude'):
            resultados = executar(self.estado, self.projeto, self.raiz, saude=saude)
        self.assertEqual(resultados[0]['status'], 'WAITING_QUOTA')
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 0)
        impedimentos = json.loads(json.loads(self.registro.read_text())['env']['JANGADA_DELEGAR_IMPEDIMENTOS'])
        self.assertEqual({i['motivo_codigo'] for i in impedimentos}, {'cota_indisponivel', 'provedor_pausado'})
        self.estado.alterar('T1', 'retomar')
        saude.pausar('agy', True)
        with patch.dict(os.environ, MODO_TESTE='saude'):
            resultados = executar(self.estado, self.projeto, self.raiz, saude=saude)
        self.assertEqual(resultados[0]['status'], 'WAITING_PROVIDER')

    def test_timeout_preserva_consumo_desconhecido(self):
        self.estado.importar([self.tarefa(tempo_total=1)])
        with patch.dict(os.environ, MODO_TESTE='demorado'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertIsNone(self.estado.consumo('T1')['chamadas'])
        self.assertGreaterEqual(self.estado.consumo('T1')['segundos'], 1)
        pid = (self.pasta / 'registro.json.filho').read_text()
        processo = pathlib.Path('/proc') / pid / 'stat'
        self.assertTrue(not processo.exists() or processo.read_text().split(') ', 1)[1].startswith('Z'))

    def test_fonte_alterada_antes_e_durante_execucao(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2')])
        with patch.dict(os.environ, MODO_TESTE='mudou'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.registro.unlink()
        self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertFalse(self.registro.exists())

    def test_perfis_nao_ampliam_permissao_da_sessao(self):
        self.estado.importar([self.tarefa(permitir_remoto=True)])
        with patch.dict(os.environ, JANGADA_DELEGAR='local', JANGADA_DELEGAR_ROTEAMENTO_ID='forjado'):
            self.rodar('offline')
        registro = json.loads(self.registro.read_text())
        self.assertEqual(registro['env']['JANGADA_DELEGAR'], 'local')
        self.assertIsNone(registro['env']['JANGADA_DELEGAR_ROTEAMENTO_ID'])
        self.assertNotIn('--permitir-remoto', registro['args'])
        self.assertIn('--destino', registro['args'])
        self.assertIn('local', registro['args'])

    def test_tarefa_principal_aguarda_sem_chamada(self):
        self.estado.importar([self.tarefa(qualidade='high')])
        self.assertEqual(self.rodar()[0]['status'], 'WAITING_REVIEWER')
        self.assertFalse(self.registro.exists())
        self.assertEqual(self.estado.listar()[0]['tentativas'], 0)

    def test_remoto_exige_permissao_na_chamada_e_no_plano(self):
        self.estado.importar([self.tarefa(permitir_remoto=True), self.tarefa('T2'),
                             self.tarefa('T3', permitir_remoto=True)])
        self.rodar('quality')
        self.assertNotIn('--permitir-remoto', json.loads(self.registro.read_text())['args'])
        executar(self.estado, self.projeto, self.raiz, 'quality', permitir_remoto=True)
        self.assertNotIn('--permitir-remoto', json.loads(self.registro.read_text())['args'])
        executar(self.estado, self.projeto, self.raiz, 'quality', permitir_remoto=True)
        self.assertIn('--permitir-remoto', json.loads(self.registro.read_text())['args'])

    def test_codex_exige_duas_permissoes_no_plano_e_na_chamada(self):
        tarefas = [self.tarefa(permitir_remoto=True, permitir_codex=True),
                   self.tarefa('T2', permitir_remoto=True),
                   self.tarefa('T3', permitir_codex=True),
                   self.tarefa('T4', permitir_remoto=True, permitir_codex=True)]
        self.estado.importar(tarefas)
        executar(self.estado, self.projeto, self.raiz, permitir_remoto=True)
        self.assertNotIn('--permitir-codex', json.loads(self.registro.read_text())['args'])
        for esperado in (False, False, True):
            executar(self.estado, self.projeto, self.raiz, permitir_remoto=True, permitir_codex=True)
            self.assertEqual('--permitir-codex' in json.loads(self.registro.read_text())['args'], esperado)

    def test_offline_nao_envia_ao_codex_mesmo_com_permissoes(self):
        self.estado.importar([self.tarefa(permitir_remoto=True, permitir_codex=True)])
        executar(self.estado, self.projeto, self.raiz, 'offline', permitir_remoto=True, permitir_codex=True)
        self.assertNotIn('--permitir-codex', json.loads(self.registro.read_text())['args'])

    def test_cli_executa_plano_sem_interpretar_pedido(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(pedido='$(touch invasao); --opcao')]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'))
        importacao = subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', str(plano)],
                                   cwd=self.projeto, env=ambiente, text=True, capture_output=True, timeout=30)
        self.assertEqual(importacao.returncode, 0, importacao.stderr)
        execucao = subprocess.run([str(RAIZ / 'bin/jangada-executar'), '--perfil', 'offline'],
                                 cwd=self.projeto, env=ambiente, text=True, capture_output=True, timeout=30)
        self.assertEqual(execucao.returncode, 0, execucao.stderr)
        self.assertEqual(json.loads(execucao.stdout)['resultados'][0]['status'], 'REVIEW_REQUIRED')
        self.assertFalse((self.projeto / 'invasao').exists())

    def test_cli_lista_revisao_e_revisa_em_lote(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(), self.tarefa('T2'), self.tarefa('T3')]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'))

        def comando(nome, *argumentos):
            return subprocess.run([str(RAIZ / 'bin' / nome), *argumentos], cwd=self.projeto,
                                  env=ambiente, text=True, capture_output=True, timeout=30)

        self.assertEqual(comando('jangada-fila', '--importar', str(plano)).returncode, 0)
        execucao = comando('jangada-executar', '--perfil', 'offline', '--limite', '2')
        self.assertEqual(execucao.returncode, 0, execucao.stderr)
        pendentes = json.loads(comando('jangada-fila', '--revisao', '--json').stdout)['revisao']
        self.assertEqual([item['id'] for item in pendentes], ['T1', 'T2'])
        for item in pendentes:
            self.assertTrue(pathlib.Path(item['arquivo']).read_text(encoding='utf-8').strip())
        self.assertEqual(len(comando('jangada-fila', '--revisao').stdout.splitlines()), 2)
        recusa = comando('jangada-task', 'T1,T3', 'revisar', '--aprovar', '--parecer', 'conferido')
        self.assertEqual(recusa.returncode, 2)
        self.assertIn('T3', recusa.stderr)
        self.assertEqual(len(json.loads(comando('jangada-fila', '--revisao', '--json').stdout)['revisao']), 2)
        lote = comando('jangada-task', 'T1,T2', 'revisar', '--aprovar', '--parecer', 'conferido')
        self.assertEqual(lote.returncode, 0, lote.stderr)
        self.assertEqual(json.loads(comando('jangada-fila', '--revisao', '--json').stdout)['revisao'], [])

    def test_cli_paralelo_executa_tarefas_distintas_ao_mesmo_tempo(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(f'T{i}', permitir_remoto=True) for i in range(5)]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'), MODO_TESTE='paralelo')

        def comando(nome, *argumentos):
            return subprocess.run([str(RAIZ / 'bin' / nome), *argumentos], cwd=self.projeto,
                                  env=ambiente, text=True, capture_output=True, timeout=30)

        self.assertEqual(comando('jangada-fila', '--importar', str(plano)).returncode, 0)
        for argumentos in (('--paralelo', '2', '--limite', '4'), ('--paralelo', '5', '--limite', '5', '--permitir-remoto'),
                           ('--paralelo', '2', '--permitir-remoto'),
                           ('--paralelo', '2', '--limite', '4', '--permitir-remoto', '--perfil', 'offline'),
                           ('--paralelo', '2', '--limite', '4', '--permitir-remoto', '--acompanhar')):
            with self.subTest(argumentos=argumentos):
                self.assertEqual(comando('jangada-executar', *argumentos).returncode, 2)
        self.assertFalse(pathlib.Path(str(self.registro) + '.tempos').exists())
        execucao = comando('jangada-executar', '--paralelo', '2', '--limite', '3', '--permitir-remoto')
        self.assertEqual(execucao.returncode, 0, execucao.stderr)
        resultados = json.loads(execucao.stdout)['resultados']
        self.assertEqual(sorted(r['tarefa'] for r in resultados), ['T0', 'T1', 'T2'])
        self.assertEqual({r['status'] for r in resultados}, {'REVIEW_REQUIRED'})
        tempos = sorted(json.loads(linha) for linha in
                        pathlib.Path(str(self.registro) + '.tempos').read_text().splitlines())
        self.assertEqual(len(tempos), 3)
        self.assertLess(tempos[1][0], tempos[0][1])
        fila = json.loads(comando('jangada-fila', '--json').stdout)['tarefas']
        self.assertEqual([t['status'] for t in fila], ['REVIEW_REQUIRED'] * 3 + ['QUEUED'] * 2)
        self.assertEqual([t['tentativas'] for t in fila], [1, 1, 1, 0, 0])

    def test_prazo_vencido_nao_reserva_nem_chama_delegado(self):
        self.estado.importar([self.tarefa()])
        resultados = executar(self.estado, self.projeto, self.raiz, prazo=time.monotonic() - 1)
        self.assertEqual(resultados, [])
        self.assertEqual(self.estado.listar()[0]['status'], 'QUEUED')
        self.assertEqual(self.estado.listar()[0]['tentativas'], 0)
        self.assertFalse(self.registro.exists())

    def test_interrupcao_na_preparacao_nao_deixa_reserva_ativa(self):
        self.estado.importar([self.tarefa()])
        with patch('executor.conferir_fontes', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            executar(self.estado, self.projeto, self.raiz)
        self.assertEqual(self.estado.listar()[0]['status'], 'REVISION_REQUIRED')
        self.assertFalse(self.registro.exists())

    def test_acompanhamento_limita_delegado_ativo_e_preserva_proxima_tarefa(self):
        config = self.pasta / 'config-acompanhamento'
        config.mkdir()
        (config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        global_estado = Estado(self.pasta / 'global-acompanhamento')
        self.addCleanup(global_estado.fechar)
        saude = Saude(global_estado)
        self.estado.importar([self.tarefa(), self.tarefa('T2')])
        with patch.dict(os.environ, MODO_TESTE='demorado'):
            inicio = time.monotonic()
            try:
                fim = acompanhar(self.estado, self.projeto, self.raiz, config, saude,
                                  perfil='offline', duracao=1)
            finally:
                marca = pathlib.Path(str(self.registro) + '.delegado')
                if marca.exists():
                    try:
                        os.killpg(int(marca.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        self.assertLess(time.monotonic() - inicio, 4)
        self.assertEqual(fim['motivo'], 'prazo_atingido')
        self.assertEqual(fim['execucoes'], 1)
        tarefas = {t['id']: t for t in self.estado.listar()}
        self.assertEqual(tarefas['T1']['status'], 'REVISION_REQUIRED')
        self.assertIsNone(tarefas['T1']['resultado']['metricas']['chamadas'])
        self.assertEqual(tarefas['T2']['status'], 'QUEUED')
        for sufixo in ('.delegado', '.filho'):
            pid = int(pathlib.Path(str(self.registro) + sufixo).read_text())
            self.assertFalse(processo_vivo(pid))

    def test_cli_sequencial_encerrado_interrompe_delegado_e_descendente(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa()]))
        ambiente = dict(os.environ, JANGADA_CORE_PATH=str(self.raiz),
                        XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'), MODO_TESTE='demorado')
        comum = dict(cwd=self.projeto, env=ambiente, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for sinal in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            with self.subTest(sinal=sinal):
                caso = dict(comum, env=dict(ambiente, XDG_STATE_HOME=str(self.pasta / f'state-{sinal}')))
                importacao = subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', str(plano)],
                                            timeout=30, **caso)
                self.assertEqual(importacao.returncode, 0, importacao.stderr)
                marca = pathlib.Path(str(self.registro) + '.filho')
                marca.unlink(missing_ok=True)
                delegado = None
                processo = subprocess.Popen([str(RAIZ / 'bin/jangada-executar'), '--perfil', 'offline'],
                                            start_new_session=True, **caso)
                try:
                    inicio = time.monotonic()
                    while not marca.exists() and time.monotonic() - inicio < 5:
                        time.sleep(0.02)
                    self.assertTrue(marca.exists(), 'delegado não iniciou')
                    delegado = int(pathlib.Path(str(self.registro) + '.delegado').read_text())
                    descendente = int(marca.read_text())
                    processo.send_signal(sinal)
                    processo.wait(timeout=5)
                    self.assertEqual(processo.returncode, 130)
                    processo.communicate(timeout=5)
                    for pid in (delegado, descendente):
                        self.assertFalse(processo_vivo(pid), f'processo {pid} ainda está executando')
                    fila = subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--json'], timeout=30, **caso)
                    self.assertEqual(fila.returncode, 0, fila.stderr)
                    tarefas = json.loads(fila.stdout)['tarefas']
                    encerradas = [t for t in tarefas if t['status'] == 'REVISION_REQUIRED']
                    self.assertNotIn('RUNNING', {t['status'] for t in tarefas})
                    self.assertTrue(encerradas)
                    self.assertTrue(all(t['resultado']['metricas']['chamadas'] is None for t in encerradas))
                finally:
                    if delegado is not None:
                        try:
                            os.killpg(delegado, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if processo.poll() is None:
                        processo.kill()
                    processo.communicate(timeout=5)

    def test_cli_paralelo_encerrado_interrompe_os_processos_filhos(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(f'T{i}', permitir_remoto=True) for i in range(4)]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'), MODO_TESTE='demorado')
        comum = dict(cwd=self.projeto, env=ambiente, text=True)
        self.assertEqual(subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', str(plano)],
                                        capture_output=True, timeout=30, **comum).returncode, 0)
        for sinal in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(sinal=sinal):
                marca = pathlib.Path(str(self.registro) + '.filho')
                marca.unlink(missing_ok=True)
                inicio = time.monotonic()
                processo = subprocess.Popen([str(RAIZ / 'bin/jangada-executar'), '--paralelo', '2', '--limite', '2',
                                             '--permitir-remoto'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **comum)
                while not marca.exists() and time.monotonic() - inicio < 8:
                    time.sleep(0.05)
                time.sleep(0.3)
                processo.send_signal(sinal)
                processo.communicate(timeout=8)
                self.assertEqual(processo.returncode, 130)
                self.assertLess(time.monotonic() - inicio, 8)
                fila = json.loads(subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--json'], capture_output=True,
                                                 timeout=30, **comum).stdout)['tarefas']
                self.assertNotIn('RUNNING', {t['status'] for t in fila})
        self.assertEqual({t['status'] for t in fila}, {'REVISION_REQUIRED'})

    def test_cli_retomada_repassa_a_amostragem(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(intermediaria=True, amostragem=True)]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'))
        comum = dict(cwd=self.projeto, env=ambiente, text=True, capture_output=True, timeout=30)
        self.assertEqual(subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', str(plano)], **comum).returncode, 0)
        retomada = subprocess.run([str(RAIZ / 'bin/jangada-retomar'), '--executar', '--perfil', 'offline', '--amostrar'],
                                  **comum)
        self.assertEqual(retomada.returncode, 0, retomada.stderr)
        resultado = json.loads(retomada.stdout)['resultados'][0]
        self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')
        self.assertEqual(resultado['amostragem']['taxa'], 1)

    def test_cli_paralelo_informa_falha_de_um_processo(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        (self.raiz / 'orquestracao/executor.py').write_text(
            (RAIZ / 'orquestracao/executor.py').read_text(encoding='utf-8')
            + "\n\n_original = executar\n\n\ndef executar(estado, projeto, raiz, perfil, limite, *resto):\n"
              "    if limite == 1:\n        raise ValueError('falha simulada')\n"
              "    return _original(estado, projeto, raiz, perfil, limite, *resto)\n", encoding='utf-8')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(f'T{i}', permitir_remoto=True) for i in range(3)]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'))
        comum = dict(cwd=self.projeto, env=ambiente, text=True, capture_output=True, timeout=30)
        self.assertEqual(subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', str(plano)], **comum).returncode, 0)
        execucao = subprocess.run([str(RAIZ / 'bin/jangada-executar'), '--paralelo', '2', '--limite', '3',
                                   '--permitir-remoto'], **comum)
        self.assertEqual(execucao.returncode, 2)
        self.assertIn('1 processo(s) paralelo(s) falharam', execucao.stderr)
        self.assertEqual(len(json.loads(execucao.stdout)['resultados']), 2)

    def test_cli_retomada_executa_com_provedor_verificado(self):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        config = self.pasta / 'config-cli/jangada'
        config.mkdir(parents=True)
        (config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa()]), encoding='utf-8')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.pasta / 'state-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'), MODO_TESTE='cota')

        def comando(nome, *argumentos):
            return subprocess.run([str(RAIZ / 'bin' / nome), *argumentos], cwd=self.projeto,
                                  env=ambiente, text=True, capture_output=True, timeout=30)

        self.assertEqual(comando('jangada-fila', '--importar', str(plano)).returncode, 0)
        espera = comando('jangada-executar')
        self.assertEqual(espera.returncode, 0, espera.stderr)
        self.assertEqual(json.loads(espera.stdout)['resultados'][0]['status'], 'WAITING_QUOTA')
        global_estado = Estado(self.pasta / 'state-cli/jangada/agentes/runtime', raiz=self.pasta / 'state-cli/jangada')
        Saude(global_estado).observar('local', 'AVAILABLE', 'serviço simulado presente')
        global_estado.fechar()
        ambiente['MODO_TESTE'] = 'ok'
        resultado = comando('jangada-retomar', '--executar', '--perfil', 'offline')
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        retomada = json.loads(resultado.stdout)
        self.assertEqual(retomada['retomadas'], ['T1'])
        self.assertEqual(retomada['resultados'][0]['status'], 'REVIEW_REQUIRED')


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
