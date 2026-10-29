#!/usr/bin/env python3
"""Falhas reais de processos com estado e clientes descartáveis, sem rede."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_executor', RAIZ / 'testes/executor.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
from estado import Estado
from processos import Processo
from projetos import cadastrar


class Recuperacao(unittest.TestCase):
    setUp = fixture.Execucao.setUp
    tarefa = fixture.Execucao.tarefa

    def reservar_em_processo(self, *, finalizar=False, principal=False):
        self.estado.importar([self.tarefa(**({'risco': 3, 'qualidade': 'high'} if principal else {}))])
        reserva = "e.reservar_principal('T1','codex',monitorar=True)" if principal else 'e.reservar()'
        finalizar_codigo = ("e.finalizar('T1',dono,'REVIEW_REQUIRED',"
                           "{'metricas':{'chamadas':1,'segundos':1}},'relatório confirmado'); ") if finalizar else ''
        codigo = ('import sys,time; sys.path.insert(0,sys.argv[1]); from estado import Estado; '
                  f'e=Estado(sys.argv[2]); spec,dono,*resto={reserva}; {finalizar_codigo}'
                  'print("reservada",flush=True); time.sleep(60)')
        processo = subprocess.Popen([sys.executable, '-B', '-c', codigo,
                                     str(RAIZ / 'orquestracao'), str(self.estado.pasta)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: self.encerrar(processo))
        self.assertEqual(processo.stdout.readline().strip(), 'reservada')
        return processo

    @staticmethod
    def encerrar(processo):
        if processo.poll() is None:
            processo.kill()
        processo.communicate(timeout=5)

    def test_sigkill_reabre_reserva_sem_esperar_prazo_e_sem_inventar_consumo(self):
        processo = self.reservar_em_processo()
        processo.kill()
        processo.wait(timeout=5)
        for _ in range(2):
            estado = Estado(self.estado.pasta)
            try:
                item = estado.listar()[0]
                self.assertEqual(item['status'], 'REVISION_REQUIRED')
                self.assertEqual(item['tentativas'], 1)
                self.assertIsNone(estado.consumo('T1')['chamadas'])
                self.assertEqual(estado.db.execute(
                    "SELECT count(*) FROM eventos WHERE evento='reserva_expirada'").fetchone()[0], 1)
                execucao = estado.db.execute('SELECT * FROM execucoes').fetchone()
                self.assertEqual(execucao['status'], 'REVISION_REQUIRED')
                self.assertIsNone(execucao['chamadas'])
                self.assertIsNotNone(execucao['fim'])
                self.assertIsNone(estado.reservar())
            finally:
                estado.fechar()

    def test_outro_controlador_vivo_conserva_reserva(self):
        self.reservar_em_processo()
        estado = Estado(self.estado.pasta)
        try:
            self.assertEqual(estado.listar()[0]['status'], 'RUNNING')
            self.assertEqual(estado.db.execute(
                "SELECT count(*) FROM eventos WHERE evento='reserva_expirada'").fetchone()[0], 0)
        finally:
            estado.fechar()

    def test_principal_automatico_monitorado_e_recuperado_apos_sigkill(self):
        processo = self.reservar_em_processo(principal=True)
        processo.kill()
        processo.wait(timeout=5)
        estado = Estado(self.estado.pasta)
        try:
            self.assertEqual(estado.listar()[0]['status'], 'REVISION_REQUIRED')
            self.assertIsNone(estado.consumo('T1')['chamadas'])
        finally:
            estado.fechar()

    def test_sigkill_apos_confirmacao_preserva_artefato_e_consumo_sem_aprovar(self):
        processo = self.reservar_em_processo(finalizar=True)
        processo.kill()
        processo.wait(timeout=5)
        estado = Estado(self.estado.pasta)
        try:
            item = estado.listar()[0]
            self.assertEqual(item['status'], 'REVIEW_REQUIRED')
            self.assertEqual(estado.ler_artefato(item['artefato']), 'relatório confirmado')
            self.assertEqual(estado.consumo('T1'), {'chamadas': 1, 'segundos': 1})
            self.assertEqual(estado.db.execute(
                "SELECT count(*) FROM eventos WHERE evento='reserva_expirada'").fetchone()[0], 0)
            self.assertEqual(list((estado.pasta / 'reservas').iterdir()), [])
        finally:
            estado.fechar()

    def test_recusa_da_proxima_reserva_nao_desfaz_recuperacao(self):
        processo = self.reservar_em_processo()
        processo.kill()
        processo.wait(timeout=5)
        self.estado.importar([self.tarefa('T2')])
        def recusar(_):
            raise ValueError('recusa simulada')
        with self.assertRaisesRegex(ValueError, 'recusa simulada'):
            self.estado.reservar(validar=recusar)
        self.assertEqual([t['status'] for t in self.estado.listar()], ['REVISION_REQUIRED', 'QUEUED'])
        self.assertIsNone(self.estado.consumo('T1')['chamadas'])

    def test_reabertura_recupera_legado_expirado_sem_executar_tarefa(self):
        self.estado.importar([self.tarefa()])
        self.estado.reservar()
        self.estado.db.execute("UPDATE tarefas SET prazo=0 WHERE id='T1'")
        estado = Estado(self.estado.pasta)
        try:
            self.assertEqual(estado.listar()[0]['status'], 'REVISION_REQUIRED')
            self.assertIsNone(estado.consumo('T1')['chamadas'])
        finally:
            estado.fechar()

    def test_recuperacao_falha_de_forma_atomica_e_pode_ser_repetida(self):
        processo = self.reservar_em_processo()
        processo.kill()
        processo.wait(timeout=5)
        with patch.object(Estado, 'evento', side_effect=OSError('falha de escrita simulada')):
            with self.assertRaises(OSError):
                Estado(self.estado.pasta)
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')
        estado = Estado(self.estado.pasta)
        try:
            self.assertEqual(estado.listar()[0]['status'], 'REVISION_REQUIRED')
            self.assertEqual(estado.db.execute(
                "SELECT count(*) FROM eventos WHERE evento='reserva_expirada'").fetchone()[0], 1)
            with self.assertRaisesRegex(ValueError, 'consumo desconhecido'):
                cadastrar(estado, self.projeto, {'orcamento': {'chamadas': 10}})
        finally:
            estado.fechar()

    def test_sigkill_durante_transacao_descarta_apenas_escrita_nao_confirmada(self):
        self.estado.importar([self.tarefa()])
        codigo = '''import sys,time
sys.path.insert(0,sys.argv[1])
from estado import Estado
e=Estado(sys.argv[2])
with e.transacao():
    e.db.execute("UPDATE tarefas SET status='CANCELLED'")
    e.evento('T1','cancelar',{})
    print('transacao',flush=True)
    time.sleep(60)
'''
        processo = subprocess.Popen([sys.executable, '-B', '-c', codigo,
                                     str(RAIZ / 'orquestracao'), str(self.estado.pasta)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: self.encerrar(processo))
        self.assertEqual(processo.stdout.readline().strip(), 'transacao')
        processo.kill()
        processo.wait(timeout=5)
        estado = Estado(self.estado.pasta)
        try:
            self.assertEqual(estado.listar()[0]['status'], 'QUEUED')
            self.assertEqual(estado.db.execute('SELECT count(*) FROM eventos').fetchone()[0], 1)
            self.assertEqual(estado.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            estado.fechar()

    def test_reserva_interativa_nao_depende_da_vida_do_comando_assumir(self):
        self.estado.importar([self.tarefa(risco=3, qualidade='high')])
        _, dono, _ = self.estado.reservar_principal('T1', 'codex')
        estado = Estado(self.estado.pasta)
        try:
            self.assertEqual(estado.listar()[0]['status'], 'RUNNING')
            self.assertEqual(estado.listar()[0]['dono'], dono)
        finally:
            estado.fechar()

    def test_vigia_preserva_codigo_e_saida_e_remove_filho_apos_saida_normal(self):
        codigo = '''import subprocess,sys
p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
print(p.pid,flush=True)
raise SystemExit(7)
'''
        processo = Processo([sys.executable, '-c', codigo], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
        saida, erro = processo.communicate(timeout=5)
        self.assertEqual(processo.returncode, 7, erro)
        self.assertFalse(fixture.processo_vivo(int(saida)))

    def test_vigia_nao_executa_cliente_se_controlador_ja_fechou_pipe(self):
        leitura, escrita = os.pipe()
        os.close(escrita)
        marcador = self.pasta / 'nao-deve-existir'
        try:
            resultado = subprocess.run([sys.executable, '-B', str(RAIZ / 'orquestracao/processos.py'),
                                       str(leitura), sys.executable, '-c',
                                       'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marcador)],
                                      pass_fds=(leitura,), capture_output=True, timeout=5)
        finally:
            os.close(leitura)
        self.assertEqual(resultado.returncode, 137, resultado.stderr)
        self.assertFalse(marcador.exists())

    def test_vigia_nao_importa_codigo_do_projeto_por_pythonpath(self):
        marcador = self.pasta / 'importacao-indevida'
        (self.projeto / 'ctypes.py').write_text(
            f'import pathlib; pathlib.Path({str(marcador)!r}).touch(); raise RuntimeError("injeção")')
        processo = Processo(['/bin/true'], cwd=self.projeto,
                            env=dict(os.environ, PYTHONPATH=str(self.projeto)),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, erro = processo.communicate(timeout=5)
        self.assertEqual(processo.returncode, 0, erro)
        self.assertFalse(marcador.exists())

    def test_trava_adulterada_nao_e_seguida_nem_libera_consumo(self):
        processo = self.reservar_em_processo()
        processo.kill()
        processo.wait(timeout=5)
        dono = self.estado.listar()[0]['dono']
        trava = self.estado.pasta / 'reservas' / dono
        trava.unlink()
        externo = self.pasta / 'externo'
        externo.write_text('preservado')
        trava.symlink_to(externo)
        with self.assertRaises(OSError):
            Estado(self.estado.pasta)
        self.assertEqual(externo.read_text(), 'preservado')
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')

    def test_sigkill_do_controlador_encerra_delegado_e_filho_em_outra_sessao(self):
        self.conferir_sigkill(1)

    def test_sigkill_do_controlador_paralelo_encerra_todos_os_descendentes(self):
        self.conferir_sigkill(2)

    def conferir_sigkill(self, quantidade):
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        simulador = self.raiz / 'bin/jangada-delegar'
        simulador.write_text('''#!/usr/bin/env python3
import json,os,subprocess,sys,time
filho=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
with open(os.environ['REGISTRO_TESTE']+'.pids','a') as arquivo:
    arquivo.write(json.dumps([os.getpid(),filho.pid])+'\\n')
time.sleep(60)
''')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        plano = self.projeto / 'plano.json'
        plano.write_text(json.dumps([self.tarefa(f'T{i}', permitir_remoto=True) for i in range(quantidade)]))
        ambiente = dict(os.environ, JANGADA_CORE_PATH=str(self.raiz),
                        XDG_STATE_HOME=str(self.pasta / 'estado-cli'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config-cli'), MODO_TESTE='demorado')
        opcoes = dict(cwd=self.projeto, env=ambiente, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        resposta = subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--importar', str(plano)], timeout=10, **opcoes)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        vizinho = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: self.encerrar(vizinho))
        argumentos = ['--perfil', 'offline'] if quantidade == 1 else ['--paralelo', '2', '--limite', '2', '--permitir-remoto']
        processo = subprocess.Popen([str(RAIZ / 'bin/jangada-executar'), *argumentos], **opcoes)
        pids = []
        try:
            marca = Path(str(self.registro) + '.pids')
            limite = time.monotonic() + 5
            registros = []
            while time.monotonic() < limite:
                if marca.exists():
                    registros = [json.loads(linha) for linha in marca.read_text().splitlines()]
                    if len(registros) == quantidade:
                        break
                time.sleep(0.02)
            pids = [pid for registro in registros for pid in registro]
            self.assertEqual(len(registros), quantidade, 'clientes simulados não iniciaram')
            processo.kill()
            processo.wait(timeout=5)
            limite = time.monotonic() + 3
            while any(fixture.processo_vivo(pid) for pid in pids) and time.monotonic() < limite:
                time.sleep(0.02)
            self.assertFalse(any(fixture.processo_vivo(pid) for pid in pids), 'descendentes órfãos continuam vivos')
            self.assertIsNone(vizinho.poll(), 'processo de outro trabalho foi encerrado')
            resposta = subprocess.run([str(RAIZ / 'bin/jangada-fila'), '--json'], timeout=10, **opcoes)
            self.assertEqual(resposta.returncode, 0, resposta.stderr)
            self.assertEqual([t['status'] for t in json.loads(resposta.stdout)['tarefas']],
                             ['REVISION_REQUIRED'] * quantidade)
        finally:
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.encerrar(processo)


if __name__ == '__main__':
    unittest.main()
