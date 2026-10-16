#!/usr/bin/env python3
"""Confere cotas e a consulta isolada sem autenticação ou serviços reais."""

import base64
import json
import os
import pathlib
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
from cota_codex import consultar, percentual
from estado import Estado
from saude import Saude


def cotas(usado=20, semanal=70):
    return {'rateLimits': {'limitId': 'codex',
                          'primary': {'usedPercent': usado, 'resetsAt': 2000},
                          'secondary': {'usedPercent': semanal, 'resetsAt': 3000}}}


def autenticacao(fim):
    conteudo = base64.urlsafe_b64encode(json.dumps({'exp': fim}).encode()).decode().rstrip('=')
    return {'tokens': {'access_token': 'cabecalho.' + conteudo + '.assinatura',
                       'id_token': 'identidade-falsa', 'refresh_token': 'renovacao-original',
                       'account_id': 'conta-falsa'}}


class Cotas(unittest.TestCase):
    def test_saldo_usa_a_janela_mais_restrita(self):
        self.assertEqual(percentual(cotas(), 1000), (30, 60))
        self.assertEqual(percentual(cotas(100, 0), 1000), (0, 60))

    def test_grupos_separados_nao_inventam_cota_independente(self):
        dados = cotas(0, 0)
        dados['rateLimitsByLimitId'] = {'outro': cotas(0, 0)['rateLimits'],
                                      'codex': cotas(50, 80)['rateLimits']}
        self.assertEqual(percentual(dados, 1000), (20, 60))
        del dados['rateLimitsByLimitId']['codex']
        with self.assertRaises(ValueError):
            percentual(dados, 1000)

    def test_cota_invalida_futura_ausente_ou_renovada_e_recusada(self):
        for valor in (True, '20', [], -1, 101, float('nan'), float('inf')):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                percentual(cotas(valor), 1000)
        for fim in (True, '2000', 999, 1000, 1000.5):
            dados = cotas()
            dados['rateLimits']['primary']['resetsAt'] = fim
            with self.subTest(fim=fim), self.assertRaises(ValueError):
                percentual(dados, 1000)
        for dados in (None, [], {}, {'rateLimits': {'primary': None}},
                      {'rateLimitsByLimitId': []}, {'rateLimits': {'limitId': 'outro'}}):
            with self.subTest(dados=dados), self.assertRaises(ValueError):
                percentual(dados, 1000)

    def test_validade_nao_ultrapassa_renovacao(self):
        self.assertEqual(percentual(cotas(), 1998.4), (30, 1))
        with self.assertRaises(ValueError):
            percentual(cotas(), 1999.4)

    def test_limite_atingido_bloqueia_mesmo_com_saldo(self):
        dados = cotas()
        dados['rateLimits']['rateLimitReachedType'] = 'credits'
        self.assertEqual(percentual(dados, 1000), (0, 60))

    def test_uma_janela_presente_basta_sem_inventar_a_outra(self):
        dados = cotas()
        dados['rateLimits']['secondary'] = None
        self.assertEqual(percentual(dados, 1000), (80, 60))


class Consulta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.casa = self.pasta / 'codex'
        self.casa.mkdir()
        self.auth = self.casa / 'auth.json'
        self.auth.write_text(json.dumps(autenticacao(time.time() + 3600)))
        self.bin = self.pasta / 'bin'
        self.bin.mkdir()
        self.fake = self.bin / 'codex'
        self.ambiente = patch.dict(os.environ, CODEX_HOME=str(self.casa),
                                   PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)
        self.estado = Estado(self.pasta / 'estado')
        self.addCleanup(self.estado.fechar)
        self.saude = Saude(self.estado)

    def programa(self, corpo):
        self.fake.write_text('#!' + sys.executable + '\n' + corpo)
        self.fake.chmod(0o700)

    def resposta(self, dados):
        self.programa('''import json, os, pathlib, sys
assert sys.argv[1] == '--no-daemon'
assert sys.argv[-2:] == ['app-server', '--stdio']
casa = pathlib.Path(os.environ['CODEX_HOME'])
assert casa == pathlib.Path.cwd()
assert casa.name.startswith('.cota-codex-')
assert (casa / 'auth.json').stat().st_mode & 0o777 == 0o600
assert casa.stat().st_mode & 0o777 == 0o700
assert json.loads((casa / 'auth.json').read_text())['tokens']['refresh_token'] == ''
assert 'renovacao-original' not in (casa / 'auth.json').read_text()
assert not (casa / 'config.toml').exists()
assert 'JANGADA_SESSAO' not in os.environ
assert 'SEGREDO_TESTE' not in os.environ
assert os.environ['HOME'] == str(casa)
inicio = json.loads(sys.stdin.readline())
assert inicio['method'] == 'initialize'
print(json.dumps({'id': 1, 'result': {}}), flush=True)
assert json.loads(sys.stdin.readline())['method'] == 'initialized'
pedido = json.loads(sys.stdin.readline())
assert pedido == {'id': 2, 'method': 'account/rateLimits/read', 'params': {}}
print(json.dumps({'method': 'notificacao', 'params': {}}), flush=True)
print(json.dumps({'id': 2, 'method': 'pedido-servidor', 'params': {}}), flush=True)
print(json.dumps({'id': 2, 'result': ''' + repr(dados) + '''}), flush=True)
sys.stdin.read()
''')

    def test_consulta_somente_metadados_e_remove_credenciais_temporarias(self):
        antes = self.auth.read_bytes()
        self.resposta(cotas())
        with patch.dict(os.environ, SEGREDO_TESTE='nao-transmitir'):
            self.assertEqual(consultar(self.estado.pasta), cotas())
        self.assertEqual(self.auth.read_bytes(), antes)
        self.assertEqual(list(self.estado.pasta.glob('.cota-codex-*')), [])

    def test_token_vencido_ou_invalido_nao_inicia_consulta(self):
        for dados in ({}, autenticacao(time.time() - 1), autenticacao(time.time() + 20),
                      {'tokens': {'access_token': 'invalido', 'id_token': 'identidade'}}):
            with self.subTest(dados=dados):
                self.auth.write_text(json.dumps(dados))
                with patch('cota_codex.subprocess.Popen') as iniciar, self.assertRaises(ValueError):
                    consultar(self.estado.pasta)
                iniciar.assert_not_called()

    def test_sigterm_e_sighup_encerram_filho_e_removem_pasta(self):
        prontidao = self.pasta / 'pronto.json'
        self.programa('import json, os, pathlib, time\npathlib.Path(' + repr(str(prontidao))
                      + ').write_text(json.dumps({"pid": os.getpid(), "casa": os.environ["CODEX_HOME"]}))\n'
                      + 'time.sleep(60)\n')
        pedido = 'import sys; sys.dont_write_bytecode = True; sys.path.insert(0, ' \
                 + repr(str(RAIZ / 'orquestracao')) \
                 + '); from cota_codex import consultar; consultar(' + repr(str(self.estado.pasta)) + ')'
        for numero in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(sinal=numero):
                prontidao.unlink(missing_ok=True)
                pai = subprocess.Popen([sys.executable, '-c', pedido], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE)
                try:
                    limite = time.monotonic() + 5
                    while not prontidao.exists() and time.monotonic() < limite:
                        time.sleep(0.01)
                    self.assertTrue(prontidao.exists())
                    dados = json.loads(prontidao.read_text())
                    pai.send_signal(numero)
                    _, erros = pai.communicate(timeout=5)
                    self.assertEqual(pai.returncode, 128 + numero, erros.decode())
                    self.assertFalse(pathlib.Path(dados['casa']).exists())
                    with self.assertRaises(ProcessLookupError):
                        os.kill(dados['pid'], 0)
                finally:
                    if pai.poll() is None:
                        pai.kill()
                    pai.communicate(timeout=5)

    def test_consulta_exige_permissao_e_respeita_pausa(self):
        with patch('saude.consultar') as consultar_cota:
            with self.assertRaises(ValueError):
                self.saude.atualizar_codex()
            self.saude.pausar('codex', True)
            self.saude.atualizar_codex(True)
            consultar_cota.assert_not_called()

    def test_reserva_e_cota_desconhecida_nao_declaram_disponivel(self):
        for usado, esperado in ((70, 'AVAILABLE'), (80, 'QUOTA_LOW'), (100, 'QUOTA_EXHAUSTED')):
            with self.subTest(usado=usado), patch('saude.consultar', return_value=cotas(usado, usado)), \
                    patch('saude.time.time', return_value=1000):
                self.saude.atualizar_codex(True)
                item = next(p for p in self.saude.listar() if p['id'] == 'codex')
                self.assertEqual(item['status'], esperado)
        self.saude.observar('codex', 'AVAILABLE', 'sem cota')
        item = next(p for p in self.saude.listar() if p['id'] == 'codex')
        self.assertEqual(item['status'], 'UNKNOWN')

    def test_reserva_zero_nao_libera_cota_esgotada(self):
        with patch.dict(os.environ, JANGADA_CODEX_COTA_MIN='0', JANGADA_DELEGAR_COTA_MIN='0'):
            for provedor in ('codex', 'agy'):
                self.saude.observar(provedor, 'AVAILABLE', 'cota conferida', cota=0)
                item = next(p for p in self.saude.listar() if p['id'] == provedor)
                self.assertEqual(item['status'], 'QUOTA_EXHAUSTED')

    def test_erros_e_respostas_excessivas_encerram_processo(self):
        for resposta in ('[]', 'invalido', '{"id":1,"error":{"message":"dado externo"}}', 'x' * (1024 * 1024 + 1)):
            with self.subTest(resposta=resposta[:30]):
                self.programa('import sys\nsys.stdin.readline()\nprint(' + repr(resposta) + ', flush=True)\nsys.stdin.read()\n')
                with self.assertRaises(ValueError):
                    consultar(self.estado.pasta)
                self.assertEqual(list(self.estado.pasta.glob('.cota-codex-*')), [])

    def test_autenticacao_simbolica_e_ausente_nao_sao_seguidas(self):
        self.auth.unlink()
        self.auth.symlink_to(self.pasta / 'inexistente')
        with self.assertRaises(OSError):
            consultar(self.estado.pasta)
        self.auth.unlink()
        with self.assertRaises(OSError):
            consultar(self.estado.pasta)

    def test_prazo_e_interrupcao_encerram_o_grupo_e_removem_credenciais(self):
        self.programa('import time\ntime.sleep(60)\n')
        iniciar = subprocess.Popen
        filhos = []

        def capturar(*args, **kwargs):
            processo = iniciar(*args, **kwargs)
            filhos.append(processo)
            return processo

        with patch('cota_codex.subprocess.Popen', side_effect=capturar):
            with patch('cota_codex.time.monotonic', side_effect=[0, 11]), self.assertRaises(TimeoutError):
                consultar(self.estado.pasta)
            with patch('cota_codex.select.select', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                consultar(self.estado.pasta)
        self.assertTrue(all(p.poll() is not None for p in filhos))
        self.assertEqual(list(self.estado.pasta.glob('.cota-codex-*')), [])

    def test_encerramento_prematuro_e_falha_de_inicio_nao_deixam_credenciais(self):
        self.programa('import sys\nsys.exit(1)\n')
        with self.assertRaises(ValueError):
            consultar(self.estado.pasta)
        with patch('cota_codex.subprocess.Popen', side_effect=OSError), self.assertRaises(OSError):
            consultar(self.estado.pasta)
        self.assertEqual(list(self.estado.pasta.glob('.cota-codex-*')), [])

    def test_cli_explicita_e_falha_sem_divulgar_resposta(self):
        self.resposta(cotas())
        ambiente = os.environ.copy()
        ambiente.update(JANGADA_CORE_PATH=str(RAIZ), XDG_STATE_HOME=str(self.pasta / 'state'),
                        XDG_CONFIG_HOME=str(self.pasta / 'config'))
        comando = [str(RAIZ / 'bin/jangada-router'), 'status', '--atualizar-codex']
        negada = subprocess.run(comando, env=ambiente, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(negada.returncode, 0)
        # As datas da resposta falsa já passaram: não declarar que a cota renovou.
        resultado = subprocess.run(comando + ['--permitir-remoto'], env=ambiente,
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        item = next(p for p in json.loads(resultado.stdout)['provedores'] if p['id'] == 'codex')
        self.assertEqual(item['status'], 'UNKNOWN')
        self.assertNotIn('renovacao-original', resultado.stdout + resultado.stderr)


if __name__ == '__main__':
    unittest.main()
