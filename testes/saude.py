#!/usr/bin/env python3
"""Confere disponibilidade, pausa, validade, cota e retomada sem serviços reais."""

import json
import http.client
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from estado import Estado
from saude import Saude, retomar


class Disponibilidade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.global_estado = Estado(self.pasta / 'global')
        self.addCleanup(self.global_estado.fechar)
        self.saude = Saude(self.global_estado)
        self.estado = Estado(self.pasta / 'projeto')
        self.addCleanup(self.estado.fechar)
        self.cache = self.pasta / 'cache/jangada/agy-usage.json'
        self.cache.parent.mkdir(parents=True)
        self.ambiente = patch.dict(os.environ, XDG_CACHE_HOME=str(self.pasta / 'cache'),
                                   JANGADA_DELEGAR='local', JANGADA_LOCAL_MODELO='qwen3:4b')
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

    def test_prazo_global_limita_sonda_local_sem_registrar_falha_do_provedor(self):
        agora = [100]
        self.saude.observar('local', 'AVAILABLE', 'observação anterior')
        def esgotar(url, timeout):
            self.assertEqual(timeout, 1)
            agora[0] = 101
            raise TimeoutError('prazo global')
        with patch('saude.time.monotonic', side_effect=lambda: agora[0]), \
                patch('saude.urllib.request.urlopen', side_effect=esgotar), \
                patch('saude.consultar_uso') as nuvem:
            self.saude.atualizar(True, prazo=101)
        nuvem.assert_not_called()
        local = next(p for p in self.saude.listar() if p['id'] == 'local')
        self.assertEqual(local['status'], 'AVAILABLE')
        self.assertEqual(local['motivo'], 'observação anterior')

    def test_prazo_global_interrompe_sonda_remota_sem_descendente_vivo(self):
        binarios = self.pasta / 'bin'
        binarios.mkdir()
        marca = self.pasta / 'agy.pid'
        programa = binarios / 'agy'
        programa.write_text('#!/usr/bin/env python3\nimport os, pathlib, time\n'
                            f'pathlib.Path({str(marca)!r}).write_text(str(os.getpid()))\n'
                            'time.sleep(30)\n')
        programa.chmod(0o700)
        self.saude.observar('agy', 'AVAILABLE', 'observação anterior', cota=80)
        with patch.dict(os.environ, JANGADA_DELEGAR='agy', PATH=str(binarios) + os.pathsep + os.environ['PATH']), \
                patch('saude.urllib.request.urlopen', side_effect=OSError()):
            inicio = time.monotonic()
            self.saude.atualizar(True, prazo=inicio + 0.3)
        self.assertLess(time.monotonic() - inicio, 2)
        self.assertTrue(marca.exists())
        pid = int(marca.read_text())
        caminho = pathlib.Path(f'/proc/{pid}/stat')
        try:
            situacao = caminho.read_text().split(') ', 1)[1][0]
        except FileNotFoundError:
            situacao = 'Z'
        self.assertEqual(situacao, 'Z')
        agy = next(p for p in self.saude.listar() if p['id'] == 'agy')
        self.assertEqual(agy['status'], 'AVAILABLE')
        self.assertEqual(agy['motivo'], 'observação anterior')

    def test_interrupcao_da_sonda_remota_encerra_grupo_inteiro(self):
        binarios = self.pasta / 'bin-interrupcao'
        binarios.mkdir()
        marca = self.pasta / 'sonda.json'
        programa = binarios / 'agy'
        programa.write_text('#!/usr/bin/env python3\nimport json, os, pathlib, subprocess, sys, time\n'
                            'filho = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])\n'
                            f'pathlib.Path({str(marca)!r}).write_text(json.dumps('
                            '{"pid": os.getpid(), "filho": filho.pid, "grupo": os.getpgrp()}))\n'
                            'time.sleep(30)\n')
        programa.chmod(0o700)
        comunicar = subprocess.Popen.communicate
        interrompido = [False]
        dados = {}
        def interromper(processo, *args, **kwargs):
            if not interrompido[0]:
                interrompido[0] = True
                limite = time.monotonic() + 3
                while time.monotonic() < limite:
                    try:
                        dados.update(json.loads(marca.read_text()))
                        break
                    except (FileNotFoundError, ValueError):
                        time.sleep(0.01)
                self.assertTrue(dados, 'sonda simulada não iniciou')
                raise KeyboardInterrupt
            return comunicar(processo, *args, **kwargs)
        try:
            with patch.dict(os.environ, JANGADA_DELEGAR='agy', PATH=str(binarios) + os.pathsep + os.environ['PATH']), \
                    patch('saude.urllib.request.urlopen', side_effect=OSError()), \
                    patch('saude.subprocess.Popen.communicate', new=interromper), \
                    self.assertRaises(KeyboardInterrupt):
                self.saude.atualizar(True)
            for pid in (dados['pid'], dados['filho']):
                try:
                    situacao = pathlib.Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0]
                except FileNotFoundError:
                    situacao = 'Z'
                self.assertEqual(situacao, 'Z', f'processo {pid} sobreviveu à consulta')
        finally:
            if dados and dados['grupo'] != os.getpgrp():
                try:
                    os.killpg(dados['grupo'], signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_prazo_vencido_nao_consulta_provedores(self):
        with patch('saude.time.monotonic', return_value=100), \
                patch('saude.urllib.request.urlopen') as local, patch('saude.consultar') as codex:
            self.saude.atualizar(True, prazo=99)
            self.saude.atualizar_codex(True, prazo=99)
        local.assert_not_called()
        codex.assert_not_called()

    def dados_cota(self, valor):
        return {'command': {'data': {'groups': [{'buckets': [{'id': 'gemini-5h', 'remaining_fraction': valor}]}]}}}

    def tarefa(self, **campos):
        return {'id': 'T1', 'pedido': 'Leia', 'papel': 'leitor', 'capacidade': 'leitura_documental',
                'risco': 1, 'qualidade': 'medium', 'fontes': ['fonte.md'], **campos}

    def aguardar(self, **campos):
        self.estado.importar([self.tarefa(**campos)])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'WAITING_QUOTA',
                             {'execucao_iniciada': False, 'metricas': {'chamadas': 0, 'segundos': 0}})

    def test_estado_desconhecido_e_observacao_expirada(self):
        self.assertTrue(all(p['status'] == 'UNKNOWN' for p in self.saude.listar()))
        with patch('saude.time.time', return_value=100):
            self.saude.observar('local', 'AVAILABLE', 'conferido', validade=10)
        with patch('saude.time.time', return_value=111):
            self.assertEqual(self.saude.listar()[1]['status'], 'UNKNOWN')

    def test_pausa_persistente_e_ativacao_exige_nova_observacao(self):
        self.saude.pausar('local', True)
        self.saude.observar('local', 'AVAILABLE', 'respondeu')
        outra = Estado(self.pasta / 'global')
        self.addCleanup(outra.fechar)
        saude = Saude(outra)
        self.assertEqual(saude.impedimentos()[0]['motivo_codigo'], 'provedor_pausado')
        saude.pausar('local', False)
        self.assertEqual(saude.listar()[1]['status'], 'UNKNOWN')

    def test_tres_falhas_entram_em_espera_e_nao_presumem_retorno(self):
        with patch('saude.time.time', return_value=100):
            for _ in range(3):
                self.saude.observar('agy', 'UNAVAILABLE', 'não respondeu')
            item = self.saude.listar()[0]
            self.assertEqual(item['status'], 'COOLDOWN')
            self.assertEqual(item['espera_segundos'], 900)
        with patch('saude.time.time', return_value=1001):
            self.assertEqual(self.saude.listar()[0]['status'], 'UNKNOWN')

    def test_ativacao_preserva_espera_vigente(self):
        with patch('saude.time.time', return_value=100):
            for _ in range(3):
                self.saude.observar('agy', 'UNAVAILABLE', 'falhou')
            self.saude.pausar('agy', True)
            self.saude.pausar('agy', False)
            self.assertEqual(self.saude.listar()[0]['status'], 'COOLDOWN')
            self.assertEqual(self.saude.listar()[0]['espera_segundos'], 900)

    def test_http_truncado_vira_falha_de_rede(self):
        with patch('saude.urllib.request.urlopen', side_effect=http.client.IncompleteRead(b'')):
            self.saude.atualizar()
        self.assertEqual(self.saude.listar()[1]['status'], 'NETWORK_ERROR')

    def test_cota_malformada_do_executor_nao_libera_provedor(self):
        for valor in ('50', True, [], float('nan')):
            with self.subTest(valor=valor):
                self.saude.registrar_delegacao({'destino': 'agy', 'cota_depois': valor}, 0)
                self.assertEqual(self.saude.listar()[0]['status'], 'UNKNOWN')
                self.saude.registrar_delegacao({'destino': 'agy', 'motivo_codigo': 'cota_insuficiente',
                                               'cota_antes': valor}, 4)
                self.assertEqual(self.saude.listar()[0]['status'], 'QUOTA_LOW')

    def test_cota_desconhecida_nao_declara_disponivel(self):
        self.saude.observar('agy', 'AVAILABLE', 'serviço respondeu')
        self.assertEqual(self.saude.listar()[0]['status'], 'UNKNOWN')
        for valor in (True, float('nan'), -1, 101):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                self.saude.observar('agy', 'AVAILABLE', 'conferido', cota=valor)

    def test_sonda_usa_cota_fresca_sem_chamar_nuvem(self):
        self.cache.write_text(json.dumps(self.dados_cota(0.5)))
        resposta = MagicMock()
        resposta.__enter__.return_value.read.return_value = b'{"models":[{"name":"qwen3:4b"}]}'
        with patch('saude.urllib.request.urlopen', return_value=resposta), patch('saude.consultar_uso') as nuvem:
            self.saude.atualizar()
            nuvem.assert_not_called()
        self.assertEqual([p['status'] for p in self.saude.listar()], ['AVAILABLE', 'AVAILABLE'])
        self.assertEqual(self.saude.listar()[0]['cota'], 50)

    def test_cota_semanal_zerada_e_grupo_de_terceiros(self):
        gemini = {'buckets': [{'id': 'gemini-weekly', 'remaining_fraction': 0},
                              {'id': 'gemini-5h', 'disabled': True, 'remaining_fraction': 0.99}]}
        terceiros = {'buckets': [{'id': '3p-weekly', 'remaining_fraction': 1}, {'id': '3p-5h', 'remaining_fraction': 0.8}]}
        for grupos, status, cota in (([gemini], 'QUOTA_EXHAUSTED', 0), ([gemini, terceiros], 'AVAILABLE', 80)):
            with self.subTest(status=status):
                self.cache.write_text(json.dumps({'command': {'data': {'groups': grupos}}}))
                with patch('saude.urllib.request.urlopen', side_effect=OSError()), \
                        patch.dict(os.environ, JANGADA_DELEGAR_MODELOS='gemini-3.8-flash-high claude-sonnet-5-5-high'):
                    self.saude.atualizar()
                agy = self.saude.listar()[0]
                self.assertEqual((agy['status'], agy['cota']), (status, cota))

    def test_cota_expirada_futura_ou_invalida_nao_libera_chamada(self):
        for valor, idade in ((0.8, 301), (0.8, -100), (True, 0), (float('nan'), 0)):
            with self.subTest(valor=valor, idade=idade):
                self.cache.write_text(json.dumps(self.dados_cota(valor)))
                agora = __import__('time').time()
                os.utime(self.cache, (agora - idade, agora - idade))
                with patch('saude.urllib.request.urlopen', side_effect=OSError()), patch('saude.consultar_uso') as nuvem:
                    self.saude.atualizar(permitir_remoto=True)
                    nuvem.assert_not_called()
                self.assertEqual(self.saude.listar()[0]['status'], 'UNKNOWN')

    def test_grupo_invalido_nao_impede_modelo_de_outro_grupo(self):
        gemini = {'buckets': [{'id': 'gemini-5h', 'remaining_fraction': 'invalida'}]}
        terceiros = {'buckets': [{'id': '3p-5h', 'remaining_fraction': 0.8}]}
        self.cache.write_text(json.dumps({'command': {'data': {'groups': [gemini, terceiros]}}}))
        with patch('saude.urllib.request.urlopen', side_effect=OSError()), \
                patch.dict(os.environ, JANGADA_DELEGAR_MODELOS='gemini-3.8-flash-high claude-sonnet-5-5-high'):
            self.saude.atualizar()
        agy = self.saude.listar()[0]
        self.assertEqual((agy['status'], agy['cota']), ('AVAILABLE', 80))

    def test_cota_valida_de_grupo_nao_configurado_nao_libera_provedor(self):
        grupos = [{'buckets': [{'id': 'gemini-5h', 'remaining_fraction': 'invalida'}]},
                  {'buckets': [{'id': '3p-5h', 'remaining_fraction': 0.8}]}]
        self.cache.write_text(json.dumps({'command': {'data': {'groups': grupos}}}))
        with patch('saude.urllib.request.urlopen', side_effect=OSError()), \
                patch.dict(os.environ, JANGADA_DELEGAR_MODELOS='gemini-3.8-flash-high'):
            self.saude.atualizar()
        self.assertEqual(self.saude.listar()[0]['status'], 'UNKNOWN')

    def test_retorno_respeita_privacidade_e_perfil(self):
        self.aguardar(permitir_remoto=True)
        self.saude.observar('agy', 'AVAILABLE', 'cota conferida', cota=50)
        self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', True), [])
        with patch.dict(os.environ, JANGADA_DELEGAR='agy'):
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'offline', True), [])
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', False), [])
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', True), ['T1'])

    def test_consulta_de_metadados_exige_permissao_e_nao_le_fontes(self):
        with patch.dict(os.environ, JANGADA_DELEGAR='agy'):
            with patch('saude.urllib.request.urlopen', side_effect=OSError()), patch('saude.consultar_uso') as consultar:
                consultar.return_value.stdout = json.dumps(self.dados_cota(0.6))
                self.saude.atualizar(permitir_remoto=True)
                self.assertEqual(consultar.call_count, 1)
                args, kwargs = consultar.call_args
                self.assertIn('/usage', args[0])
                self.assertIn('--sandbox', args[0])
                self.assertEqual(kwargs['cwd'], pathlib.Path.home())
                self.assertEqual(kwargs['env']['JANGADA_HOOK_DESLIGADO'], '1')
                self.assertNotIn('JANGADA_SESSAO', kwargs['env'])
        self.assertEqual(self.saude.listar()[0]['cota'], 60)

    def test_cota_baixa_impede_retomada(self):
        self.aguardar(permitir_remoto=True)
        self.saude.observar('agy', 'AVAILABLE', 'cota conferida', cota=10)
        self.assertEqual(self.saude.listar()[0]['status'], 'QUOTA_LOW')
        with patch.dict(os.environ, JANGADA_DELEGAR='agy'):
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'quality', True), [])

    def test_estado_compartilhado_entre_projetos_pela_cli(self):
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), XDG_STATE_HOME=str(self.pasta / 'state'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config'))
        pausa = subprocess.run([str(RAIZ / 'bin/jangada-provedor'), 'pausar', 'agy'], cwd=self.pasta,
                               env=ambiente, capture_output=True, text=True, timeout=30)
        self.assertEqual(pausa.returncode, 0, pausa.stderr)
        status = subprocess.run([str(RAIZ / 'bin/jangada-router'), 'status'], cwd=self.estado.pasta,
                                env=ambiente, capture_output=True, text=True, timeout=30)
        self.assertEqual(status.returncode, 0, status.stderr)
        item = json.loads(status.stdout)['provedores'][0]
        self.assertEqual(item['id'], 'agy')
        self.assertEqual(item['pausado'], 1)

    def test_pausa_nao_retoma_tarefa_mesmo_com_servico_ativo(self):
        self.aguardar()
        self.saude.observar('local', 'AVAILABLE', 'conferido')
        self.saude.pausar('local', True)
        self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', False), [])

    def test_fallback_atualiza_saude_de_cada_executor(self):
        registro = {'destino': 'local', 'modelo': 'qwen3:4b', 'tentativas': [
            {'destino': 'agy', 'motivo_codigo': 'cota_insuficiente', 'codigo_saida': 4},
            {'destino': 'local', 'motivo_codigo': '', 'codigo_saida': 0}]}
        self.saude.registrar_delegacao(registro, 0)
        self.assertEqual([p['status'] for p in self.saude.listar()], ['QUOTA_LOW', 'AVAILABLE'])

    def test_codex_compartilha_cota_e_nao_presume_saldo_apos_geracao(self):
        self.saude.registrar_delegacao({'destino': 'codex-economico', 'motivo_codigo': 'cota_insuficiente',
                                       'cota_antes': 10}, 4)
        self.assertEqual(self.saude.impedimentos()[0]['destino'], 'codex-economico')
        self.saude.registrar_delegacao({'destino': 'codex-economico', 'modelo': 'economico'}, 0)
        item = next(p for p in self.saude.listar() if p['id'] == 'codex')
        self.assertEqual(item['status'], 'UNKNOWN')

    def test_retomada_codex_exige_autorizacao_especifica_e_modelo(self):
        self.aguardar(permitir_remoto=True, permitir_codex=True)
        (self.pasta / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['codex-economico']}))
        self.saude.observar('codex', 'AVAILABLE', 'saldo confirmado', cota=50)
        with patch.dict(os.environ, JANGADA_DELEGAR='agy', JANGADA_CODEX_ECONOMICO_MODELO='economico'):
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', True), [])
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'offline', True, True), [])
            with patch.dict(os.environ, JANGADA_CODEX_ECONOMICO_MODELO=''):
                self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', True, True), [])
            self.assertEqual(retomar(self.estado, self.saude, RAIZ, self.pasta, 'balanced', True, True), ['T1'])

    def test_delegacao_recusa_impedidos_sem_chamar_modelo(self):
        fonte = self.pasta / 'fonte.md'
        fonte.write_text('regra')
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), XDG_STATE_HOME=str(self.pasta / 'state'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config'),
                        JANGADA_DELEGAR_IMPEDIMENTOS=json.dumps([
                            {'destino': d, 'motivo_codigo': 'provedor_pausado', 'motivo': 'pausado'}
                            for d in ['local', 'agy']]))
        processo = subprocess.run([str(RAIZ / 'bin/jangada-delegar'), '--capacidade', 'leitura_documental',
                                   '--json', '--arquivos', str(fonte), '--', 'leitor', 'Leia'],
                                  cwd=self.pasta, env=ambiente, capture_output=True, text=True, timeout=30)
        self.assertEqual(processo.returncode, 4, processo.stderr)
        resultado = json.loads(processo.stdout)
        self.assertEqual([t['destino'] for t in resultado['tentativas']], ['agy'])
        self.assertTrue(all(t['chamadas'] == 0 for t in resultado['tentativas']))
        self.assertTrue(all(t['motivo_codigo'] == 'provedor_pausado' for t in resultado['tentativas']))


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
