#!/usr/bin/env python3
"""Confere cotas.json: formato, honestidade das medições e gravação só no estado.

Nenhum teste chama agy, Codex ou Claude de verdade: os executáveis são falsos.
Uso: testes/cotas.py [--gravar-base PASTA]  (PASTA: extração de `git archive 5ef1536`)
"""

import base64
import itertools
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
sys.path.insert(0, str(RAIZ))
import cotas
from confianca import isolado

BASE = '5ef1536'
CONTRATOS = RAIZ / 'testes/contratos'
STATUS_BASE = CONTRATOS / ('router-status-%s.json' % BASE)
DOCTOR_BASE = CONTRATOS / ('doctor-%s.json' % BASE)
FERRAMENTAS = ('bash python3 sqlite3 bwrap tmux git jq claude codex agy ollama curl xdg-dbus-proxy gdbus '
               'Rscript shellcheck ssh-keygen notify-send inotifywait timeout flock').split()
AGY_USO = {'command': {'data': {'groups': [
    {'buckets': [
        {'id': 'gemini-weekly', 'window': 'weekly', 'remaining_fraction': 0.875, 'reset_time': '2026-10-30T23:23:36Z', 'disabled': None},
        {'id': 'gemini-5h', 'window': '5h', 'remaining_fraction': 0.9275, 'reset_time': '2026-10-25T00:51:24Z', 'disabled': None}]},
    {'buckets': [
        {'id': '3p-weekly', 'window': 'weekly', 'remaining_fraction': 0.905, 'reset_time': '2026-10-30T20:10:04Z', 'disabled': None},
        {'id': '3p-5h', 'window': '5h', 'remaining_fraction': 1, 'reset_time': '2026-10-25T03:23:24Z', 'disabled': None}]},
    {'buckets': [
        {'id': 'gemini-argon-wtu-weekly', 'window': 'weekly', 'remaining_fraction': 0.333, 'reset_time': None, 'disabled': None}]}]}}}


def executavel(pasta, nome, corpo='exit 0'):
    caminho = pathlib.Path(pasta) / nome
    caminho.write_text('#!/bin/sh\n' + corpo + '\n')
    caminho.chmod(0o755)
    return caminho


class Casa:
    """HOME, XDG e PATH temporários, com agy e codex falsos."""

    def __init__(self, raiz=RAIZ, confia=True, onde=None):
        self.tmp = tempfile.TemporaryDirectory(prefix='jangada-cotas-', dir=onde)
        base = pathlib.Path(self.tmp.name)
        self.raiz = raiz
        self.casa, self.bin = base / 'casa', base / 'bin'
        self.casa.mkdir(), self.bin.mkdir()
        self.estado = self.casa / '.local/state/jangada'
        self.cache = self.casa / '.cache/jangada'
        self.marca = base / 'marca'
        for nome in FERRAMENTAS:
            executavel(self.bin, nome)
        for nome in ('bash', 'python3', 'git', 'jq', 'sqlite3'):
            (self.bin / nome).unlink()
            (self.bin / nome).symlink_to(shutil.which(nome))
        self.agy_corpo = 'echo agy >> %s; exit 1' % (base / 'marca-agy')
        self.codex_corpo = 'echo codex >> %s; exit 1' % self.marca
        executavel(self.bin, 'agy', self.agy_corpo)
        executavel(self.bin, 'codex', self.codex_corpo)
        if confia:
            self.confiar(RAIZ)

    def confiar(self, pasta, conta=None):
        destino = self.casa / '.gemini/antigravity-cli' if conta is None else conta
        destino.mkdir(parents=True, exist_ok=True)
        (destino / 'settings.json').write_text(json.dumps({'trustedWorkspaces': [str(pasta)]}))

    def cache_agy(self, dados=None, nome='agy-usage.json', idade=0):
        self.cache.mkdir(parents=True, exist_ok=True)
        arquivo = self.cache / nome
        arquivo.write_text(dados if isinstance(dados, str) else json.dumps(AGY_USO if dados is None else dados))
        os.utime(arquivo, (time.time() - idade, time.time() - idade))
        return arquivo

    def env(self, **extra):
        ambiente = {'PATH': str(self.bin) + ':/usr/bin:/bin', 'HOME': str(self.casa), 'LANG': 'C.UTF-8',
                    'XDG_STATE_HOME': str(self.casa / '.local/state'), 'XDG_CACHE_HOME': str(self.casa / '.cache'),
                    'XDG_CONFIG_HOME': str(self.casa / '.config'), 'XDG_DATA_HOME': str(self.casa / '.local/share'),
                    'TMPDIR': self.tmp.name, 'JANGADA_OLLAMA_URL': 'http://127.0.0.1:9',
                    'JANGADA_CORE_PATH': str(self.raiz), 'JANGADA_ESTADO': str(self.estado),
                    'JANGADA_CONFIG': str(self.casa / '.config/jangada')}
        ambiente.update(extra)
        return ambiente

    def router(self, *args, **extra):
        return subprocess.run([str(RAIZ / 'bin/jangada-router'), *args], cwd=RAIZ, env=self.env(**extra),
                              capture_output=True, text=True, timeout=120)

    def arquivos(self):
        return sorted(str(p.relative_to(self.tmp.name)) for p in pathlib.Path(self.tmp.name).rglob('*')
                      if p.is_file() and not p.is_relative_to(self.bin))

    def limpar(self):
        self.tmp.cleanup()


def numeros_zerados(texto):
    return re.sub(r'("(?:atualizado|valido_ate|gerado_em)": )[0-9.]+', r'\g<1>0', texto)


def saida_status(raiz, casa, *args):
    """Saída de `router status` com o executor tratado como controlador, como no uso normal."""
    programa = ("import os, runpy, sys; raiz = sys.argv[1]; sys.path[:0] = [raiz + '/orquestracao', raiz];"
                " import confianca; confianca.isolado = lambda: False;"
                " sys.argv = ['cli.py', 'router', 'status'] + sys.argv[2:];"
                " runpy.run_path(raiz + '/orquestracao/cli.py', run_name='__main__')")
    resposta = subprocess.run([sys.executable, '-B', '-c', programa, str(raiz), *args], cwd=raiz,
                              env=casa.env(JANGADA_CORE_PATH=str(raiz)), capture_output=True, text=True, timeout=120)
    return json.loads(numeros_zerados(resposta.stdout)), resposta.returncode


def saida_doctor(raiz, casa):
    resposta = subprocess.run([sys.executable, '-B', str(raiz / 'orquestracao/doctor.py'), '--json'], cwd=raiz,
                              env=casa.env(JANGADA_CORE_PATH=str(raiz)), capture_output=True, text=True, timeout=120)
    texto = numeros_zerados(resposta.stdout).replace(str(raiz), '<RAIZ>')
    texto = re.sub(r'("gerado_em": )"[^"]*"', r'\g<1>"<DATA>"', texto)
    texto = re.sub(r'UID \d+', 'UID <UID>', texto)
    saida = json.loads(texto)
    # Depende de a cópia ser um repositório git ou um arquivo extraído, e do commit.
    for verificacao in saida.get('verificacoes', []):
        if verificacao.get('id') == 'versao.origem':
            verificacao['detalhe'] = verificacao['estado'] = '<DEPENDE DA CÓPIA>'
    return saida, resposta.returncode


def gerar_base(raiz):
    casa = Casa(raiz, confia=False)
    try:
        casa.cache_agy()
        resultado = {}
        for nome, args in (('novo', ()), ('atualizado', ('--atualizar',))):
            saida, codigo = saida_status(raiz, casa, *args)
            resultado[nome] = {'codigo': codigo, 'saida': saida}
        casa.cache_agy()
        doctor, codigo = saida_doctor(raiz, casa)
        return resultado, {'codigo': codigo, 'saida': doctor}
    finally:
        casa.limpar()



def autenticacao_falsa(casa):
    exp = int(time.time()) + 3600
    conteudo = base64.urlsafe_b64encode(json.dumps({'exp': exp}).encode()).decode().rstrip('=')
    pasta = casa.casa / '.codex'
    pasta.mkdir(exist_ok=True)
    (pasta / 'auth.json').write_text(json.dumps({'tokens': {
        'access_token': 'cabecalho.' + conteudo + '.assinatura', 'id_token': 'identidade-falsa',
        'refresh_token': 'renovacao-falsa', 'account_id': 'conta-falsa'}}))


def cota_da_base(modelo, arquivo):
    """Executa cota_do_grupo como estava em 5ef1536, sem cópia no teste."""
    fonte = subprocess.run(['git', 'show', BASE + ':bin/jangada-delegar'], cwd=RAIZ, capture_output=True, text=True)
    if fonte.returncode != 0:
        raise unittest.SkipTest('BLOQUEADO: commit %s ausente do repositório' % BASE)
    inicio = fonte.stdout.index('grupo_do_modelo() {')
    fim = fonte.stdout.index('\n}\n', fonte.stdout.index('cota_do_grupo() {')) + 3
    resposta = subprocess.run(['bash', '-c', fonte.stdout[inicio:fim] + '\ncota_do_grupo "$1" "$2"', 'x', modelo, str(arquivo)],
                              capture_output=True, text=True, check=True)
    return resposta.stdout.strip()


def lido(casa):
    return json.loads((casa.estado / 'cotas.json').read_text())


def grupos(documento, provedor='agy', conta='principal'):
    entrada = next(e for e in documento['provedores'] if e['provedor'] == provedor and e['conta'] == conta)
    return {g['grupo']: g for g in entrada['grupos']}


class Cotas(unittest.TestCase):
    def casa(self, **opcoes):
        casa = Casa(**opcoes)
        self.addCleanup(casa.limpar)
        return casa

    def test_leitura_local_grava_so_cotas_json_no_estado(self):
        casa = self.casa()
        casa.cache_agy()
        antes = casa.arquivos()
        resposta = casa.router('cotas')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        novos = sorted(set(casa.arquivos()) - set(antes))
        self.assertEqual(novos, ['casa/.local/state/jangada/cotas.json'])
        self.assertEqual(set(antes) - set(casa.arquivos()), set())
        arquivo = casa.estado / 'cotas.json'
        self.assertEqual(arquivo.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(resposta.stdout), lido(casa))
        self.assertFalse((casa.tmp.name and pathlib.Path(casa.tmp.name) / 'marca-agy').exists())
        documento = lido(casa)
        self.assertEqual(documento['versao'], 1)
        self.assertEqual([(e['provedor'], e['conta']) for e in documento['provedores']],
                         [('agy', 'principal'), ('codex', None), ('claude', None)])
        self.assertEqual(grupos(documento)['gemini']['percentual'], 87.5)
        claude = documento['provedores'][2]
        self.assertEqual((claude['grupos'], claude['motivo']), ([], 'nao_medido_por_este_provedor'))

    def test_validador_recusa_numero_sem_origem_ou_data_e_validade_vencida(self):
        agora = time.time()
        bom = {'grupo': 'gemini', 'percentual': 50.0, 'janelas': [], 'origem': 'agy -p /usage',
               'medido_em': cotas.iso(agora - 60), 'valido_ate': cotas.iso(agora + 60), 'motivo': None}
        documento = lambda grupo: {'versao': 1, 'gerado': cotas.iso(agora),
                                   'provedores': [{'provedor': 'agy', 'conta': 'principal', 'grupos': [grupo], 'motivo': None}]}
        cotas.validar(documento(bom), agora)
        for campo, valor in (('origem', None), ('origem', ''), ('medido_em', None), ('valido_ate', None),
                             ('valido_ate', cotas.iso(agora - 1)), ('percentual', 101),
                             ('percentual', float('nan')), ('percentual', True), ('grupo', 'Gemini 1')):
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                cotas.validar(documento(dict(bom, **{campo: valor})), agora)
        for nulo in (dict(bom, percentual=None, motivo=None), dict(bom, percentual=None, motivo='outro')):
            with self.assertRaises(ValueError):
                cotas.validar(documento(nulo), agora)

    def test_nada_vira_numero_sem_medicao(self):
        casa = self.casa()
        casa.cache_agy(idade=3600)
        documento = lido_apos(casa)
        self.assertEqual({g['motivo'] for g in grupos(documento).values()}, {'cache_vencido'})
        casa.cache_agy(idade=-3600)
        self.assertEqual({g['motivo'] for g in grupos(lido_apos(casa)).values()}, {'cache_vencido'})
        (casa.cache / 'agy-usage.json').unlink()
        self.assertEqual({g['motivo'] for g in grupos(lido_apos(casa)).values()}, {'sem_cache'})
        (casa.cache / 'agy-usage.json').write_text('{ não é json')
        self.assertEqual({g['motivo'] for g in grupos(lido_apos(casa)).values()}, {'consulta_falhou'})
        for documento in (lido_apos(casa),):
            for grupo in grupos(documento).values():
                self.assertIsNone(grupo['percentual'])
                self.assertEqual(grupo['janelas'], [])

    def test_agy_que_falha_da_nulo_com_motivo(self):
        casa = self.casa()
        casa.cache_agy(idade=3600)
        resposta = casa.router('cotas', '--atualizar', '--permitir-remoto')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        self.assertTrue((casa.casa.parent / 'marca-agy').exists())
        for grupo in grupos(lido(casa)).values():
            self.assertEqual((grupo['percentual'], grupo['motivo']), (None, 'consulta_falhou'))

    def test_agy_que_responde_vira_medicao_com_data_de_agora(self):
        casa = self.casa()
        executavel(casa.bin, 'agy', "cat <<'FIM'\n%s\nFIM" % json.dumps(AGY_USO))
        resposta = casa.router('cotas', '--atualizar', '--permitir-remoto')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        gemini = grupos(lido(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['origem']), (87.5, 'agy -p /usage'))
        self.assertFalse(casa.cache.exists(), 'a consulta não escreve no cache do agy')

    def test_atualizar_sem_permitir_remoto_nao_consulta(self):
        casa = self.casa()
        autenticacao_falsa(casa)
        resposta = casa.router('cotas', '--atualizar')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        self.assertFalse(casa.marca.exists(), 'codex foi chamado sem --permitir-remoto')
        self.assertFalse((casa.casa.parent / 'marca-agy').exists(), 'agy foi chamado sem --permitir-remoto')
        self.assertEqual(grupos(lido(casa), 'codex', None)['codex']['motivo'], 'sem_cache')

    def test_com_permitir_remoto_o_teste_enxerga_a_chamada_ao_codex(self):
        casa = self.casa()
        autenticacao_falsa(casa)
        resposta = casa.router('cotas', '--atualizar', '--permitir-remoto')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        self.assertTrue(casa.marca.exists())
        self.assertEqual(grupos(lido(casa), 'codex', None)['codex']['motivo'], 'consulta_falhou')

    def test_codex_com_resposta_valida_traz_janelas_e_renovacao(self):
        casa = self.casa()
        autenticacao_falsa(casa)
        agora = int(time.time())
        resposta = {'id': 2, 'result': {'rateLimits': {'limitId': 'codex',
                                                       'primary': {'usedPercent': 20, 'resetsAt': agora + 600},
                                                       'secondary': {'usedPercent': 70.5, 'resetsAt': agora + 86400}}}}
        casa.codex_resposta = json.dumps(resposta)
        executavel(casa.bin, 'codex', "read l; echo '{\"id\":1,\"result\":{}}'; read l; read l\n"
                   "echo '%s'; sleep 1" % casa.codex_resposta)
        saida = casa.router('cotas', '--atualizar', '--permitir-remoto')
        self.assertEqual(saida.returncode, 0, saida.stderr)
        codex = grupos(lido(casa), 'codex', None)['codex']
        self.assertEqual(codex['percentual'], 29.5)
        self.assertEqual([j['id'] for j in codex['janelas']], ['codex-primary', 'codex-secondary'])
        self.assertEqual(codex['origem'], cotas.ORIGEM_CODEX)
        cotas.validar(lido(casa), time.time())

    def test_numero_que_venceu_durante_as_consultas_vira_nulo(self):
        medido = cotas.grupo_medido('gemini', 50.0, [], cotas.ORIGEM_AGY, cotas.iso(1000), cotas.iso(1060))
        entrada = {'provedor': 'agy', 'conta': 'principal', 'grupos': [medido], 'motivo': None}
        with tempfile.TemporaryDirectory() as pasta, \
                patch.object(cotas, 'entradas_agy', return_value=[entrada]), \
                patch.object(cotas.time, 'time', side_effect=[1000, 1061]):
            documento = cotas.montar(pathlib.Path(pasta), RAIZ)
        grupo = documento['provedores'][0]['grupos'][0]
        self.assertEqual((grupo['percentual'], grupo['motivo']), (None, 'cache_vencido'))
        self.assertEqual(grupo['valido_ate'], cotas.iso(1060))

    def test_validade_no_ultimo_segundo_nao_derruba_o_comando(self):
        medido = cotas.grupo_medido('gemini', 50.0, [], cotas.ORIGEM_AGY, cotas.iso(940), cotas.iso(1000.9))
        documento = {'versao': 1, 'gerado': cotas.iso(1000.5),
                     'provedores': [{'provedor': 'agy', 'conta': None, 'grupos': [medido], 'motivo': None}]}
        cotas.vencer(documento, 1000.5)
        cotas.validar(documento, 1000.5)
        self.assertEqual(documento['provedores'][0]['grupos'][0]['motivo'], 'cache_vencido')

    def test_validade_com_fracao_final_de_segundo_sai_vencida_com_ultimo(self):
        # valido_ate sai truncado: 1000.9 vira 1000 e já não passa de agora=1000.5.
        grupo = cotas.grupo_medido('gemini', 50.0, [], cotas.ORIGEM_AGY, cotas.iso(940), cotas.iso(1000))
        documento = {'versao': 1, 'gerado': cotas.iso(1000.5),
                     'provedores': [{'provedor': 'agy', 'conta': None, 'grupos': [grupo], 'motivo': None}]}
        candidatas = {}
        cotas.lembrar(candidatas, ('agy', None, 'gemini'), 50.0, 940, 1000.9, cotas.ORIGEM_AGY, [], cotas.RANK_CACHE, 1000.5)
        cotas.vencer(documento, 1000.5)
        cotas.resolver(documento, candidatas, 1000.5)
        cotas.validar(documento, 1000.5)
        publicado = documento['provedores'][0]['grupos'][0]
        self.assertEqual((publicado['percentual'], publicado['motivo']), (None, 'cache_vencido'))
        self.assertEqual(publicado['ultimo'], {'percentual': 50.0, 'medido_em': cotas.iso(940)})

    def publicar_tres_candidatas(self, ordem):
        chave, agora = ('codex', None, 'codex'), 1010.5
        candidatas = {}
        for percentual, valido, origem, rank in ordem:
            cotas.lembrar(candidatas, chave, percentual, 1000.2, valido, origem, [], rank, agora)
        grupo = cotas.grupo_medido('codex', 50.0, [], cotas.ORIGEM_CODEX, cotas.iso(1000.2), cotas.iso(1300))
        documento = {'versao': 1, 'gerado': cotas.iso(agora),
                     'provedores': [{'provedor': 'codex', 'conta': None, 'grupos': [grupo], 'motivo': None}]}
        cotas.resolver(documento, candidatas, agora)
        cotas.validar(documento, agora)
        return documento

    TRES_CANDIDATAS = [  # (percentual, valido, origem, rank), todas no mesmo segundo
        (30.0, None, None, cotas.RANK_ANTERIOR),  # anterior com só `ultimo`
        (40.0, 1001, cotas.ORIGEM_CODEX_ESTADO, cotas.RANK_CACHE),  # banco vencido
        (50.0, 1300, cotas.ORIGEM_CODEX, cotas.RANK_ATUALIZADO)]  # atualização válida

    def test_anterior_so_com_ultimo_banco_vencido_e_atualizacao_valida_publicam_vencido(self):
        publicado = self.publicar_tres_candidatas(self.TRES_CANDIDATAS)['provedores'][0]['grupos'][0]
        self.assertEqual((publicado['percentual'], publicado['motivo']), (None, 'cache_vencido'))
        self.assertEqual(publicado['ultimo'], {'percentual': 50.0, 'medido_em': cotas.iso(1000.2)})

    def test_tres_candidatas_no_mesmo_segundo_dao_o_mesmo_documento_em_qualquer_ordem(self):
        documentos = [self.publicar_tres_candidatas(ordem) for ordem in itertools.permutations(self.TRES_CANDIDATAS)]
        self.assertEqual(len(documentos), 6)
        for documento in documentos:
            self.assertEqual(documento, documentos[0])

    def test_validade_do_cache_zero_vira_nulo_na_atualizacao(self):
        casa = self.casa()
        executavel(casa.bin, 'agy', "cat <<'FIM'\n%s\nFIM" % json.dumps(AGY_USO))
        saida = casa.router('cotas', '--atualizar', '--permitir-remoto', JANGADA_DELEGAR_CACHE='0')
        self.assertEqual(saida.returncode, 0, saida.stderr)
        gemini = grupos(lido(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'cache_vencido'))

    def test_codex_do_estado_so_vale_dentro_da_validade(self):
        casa = self.casa()
        banco = casa.estado / 'agentes/runtime/tarefas.sqlite'
        banco.parent.mkdir(parents=True)
        db = sqlite3.connect(banco)
        db.execute('CREATE TABLE provedores(id TEXT PRIMARY KEY, status TEXT, motivo TEXT, atualizado REAL, '
                   'valido_ate REAL, cota REAL, modelo TEXT, falhas INTEGER, pausado INTEGER)')
        agora = time.time()
        db.execute("INSERT INTO provedores VALUES('codex','AVAILABLE','x',?,?,?,NULL,0,0)", (agora - 10, agora + 50, 41.5))
        db.commit()
        codex = grupos(lido_apos(casa), 'codex', None)['codex']
        self.assertEqual((codex['percentual'], codex['origem']), (41.5, cotas.ORIGEM_CODEX_ESTADO))
        db.execute('UPDATE provedores SET valido_ate=?', (agora - 1,))
        db.commit()
        # O cotas.json anterior ainda guarda a validade longa; na mesma medição vale a menor.
        codex = grupos(lido_apos(casa), 'codex', None)['codex']
        self.assertEqual((codex['percentual'], codex['motivo']), (None, 'cache_vencido'))
        db.close()

    def test_instantes_extremos_nao_derrubam_o_comando(self):
        ruins = ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-12:00', '2026-10-25T00:51:24', '1e20', '']
        gigantes = [10 ** 20, -10 ** 20, 10 ** 400, 253402300800, float('inf'), float('nan')]
        for valor in gigantes + [1e20, -1e20, 1e308]:
            self.assertIsNone(cotas.iso(valor), valor)
            self.assertIsNone(cotas.iso(valor), valor)
        for texto in ruins + gigantes:
            self.assertIsNone(cotas.renovacao(texto), texto)
        self.assertEqual(cotas.renovacao('9999-12-31T23:59:59+00:00'), '9999-12-31T23:59:59+00:00')
        for valor in ruins[:4] + [1e20, -1e20, 10 ** 20, 10 ** 400]:
            with self.subTest(entrada='reset_time', valor=valor):
                uso = json.loads(json.dumps(AGY_USO))
                uso['command']['data']['groups'][0]['buckets'][0]['reset_time'] = valor
                casa = self.casa()
                casa.cache_agy(uso)
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas')
        for valor in [10 ** 20, -10 ** 20, 10 ** 400, 253402300800, 1e20, -1e20]:
            with self.subTest(entrada='resetsAt', valor=valor):
                casa = self.casa()
                autenticacao_falsa(casa)
                resposta = {'id': 2, 'result': {'rateLimits': {'limitId': 'codex',
                                                               'primary': {'usedPercent': 20, 'resetsAt': valor}}}}
                executavel(casa.bin, 'codex', "read l; echo '{\"id\":1,\"result\":{}}'; read l; read l\n"
                           "echo '%s'; sleep 1" % json.dumps(resposta))
                self.assertNulo(casa, 'codex', 'consulta_falhou', 'cotas', '--atualizar', '--permitir-remoto')
        for valor in [1e20, -1e20, 1e308, 253402300800.0, -124271193600.0]:
            with self.subTest(entrada='sqlite', valor=valor):
                casa = self.casa()
                banco = casa.estado / 'agentes/runtime/tarefas.sqlite'
                banco.parent.mkdir(parents=True)
                db = sqlite3.connect(banco)
                db.execute('CREATE TABLE provedores(id TEXT PRIMARY KEY, status TEXT, motivo TEXT, atualizado REAL, '
                           'valido_ate REAL, cota REAL, modelo TEXT, falhas INTEGER, pausado INTEGER)')
                db.execute("INSERT INTO provedores VALUES('codex','AVAILABLE','x',?,?,41.5,NULL,0,0)", (valor, valor))
                db.commit()
                db.close()
                self.assertNulo(casa, 'codex', 'consulta_falhou', 'cotas')
        for mtime in (253402300800, 4102444800, -62135596800, 1):
            with self.subTest(entrada='mtime', valor=mtime):
                casa = self.casa()
                arquivo = casa.cache_agy()
                try:
                    os.utime(arquivo, (mtime, mtime))
                except (OverflowError, OSError, ValueError):
                    continue
                self.assertNulo(casa, 'gemini', 'cache_vencido', 'cotas')

    def test_numeros_extremos_de_toda_entrada_viram_nulo_sem_derrubar_o_comando(self):
        # Texto JSON cru: 1e309, NaN e Infinity só existem assim, e o inteiro de 401 dígitos também.
        fracoes = ['1' + '0' * 400, '1e309', '-1', '2', 'true', 'NaN', 'Infinity', '-Infinity', '"0.5"']
        modelo = json.dumps(AGY_USO)
        for fracao in fracoes:
            texto = modelo.replace('"remaining_fraction": 0.875', '"remaining_fraction": ' + fracao, 1)
            self.assertNotEqual(texto, modelo)
            with self.subTest(entrada='cache do agy', valor=fracao[:12]):
                casa = self.casa()
                casa.cache_agy(texto)
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas')
                self.assertEqual(grupos(lido(casa))['3p']['percentual'], 90.5)
            with self.subTest(entrada='resposta do agy', valor=fracao[:12]):
                casa = self.casa()
                executavel(casa.bin, 'agy', "cat <<'FIM'\n%s\nFIM" % texto)
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas', '--atualizar', '--permitir-remoto')
                self.assertEqual(grupos(lido(casa))['3p']['percentual'], 90.5)
        agora = time.time()
        valores = ['-1', '101', '9e999', '-9e999', "'abc'", "x'00'", '1' + '0' * 400, "'" + '1' * 401 + "'", 'NULL']
        casos = [(coluna, valor) for coluna in ('cota', 'atualizado', 'valido_ate') for valor in valores]
        casos += [('atualizado', '9223372036854775807'), ('valido_ate', '9223372036854775807')]
        for coluna, valor in casos:
            if coluna == 'cota' and valor in ('1' + '0' * 400, "'" + '1' * 401 + "'"):
                continue
            if coluna != 'cota' and valor in ('-1', '101'):
                continue
            with self.subTest(entrada='sqlite', coluna=coluna, valor=valor[:12]):
                casa = self.casa()
                banco = casa.estado / 'agentes/runtime/tarefas.sqlite'
                banco.parent.mkdir(parents=True)
                db = sqlite3.connect(banco)
                db.execute('CREATE TABLE provedores(id TEXT PRIMARY KEY, status TEXT, motivo TEXT, atualizado REAL, '
                           'valido_ate REAL, cota REAL, modelo TEXT, falhas INTEGER, pausado INTEGER)')
                campos = {'atualizado': str(agora - 10), 'valido_ate': str(agora + 50), 'cota': '41.5'}
                campos[coluna] = valor
                db.execute("INSERT INTO provedores VALUES('codex','AVAILABLE','x',%(atualizado)s,%(valido_ate)s,%(cota)s,NULL,0,0)"
                           % campos)
                db.commit()
                db.close()
                alvo = self.assertNulo(casa, 'codex', None, 'cotas')
                if valor != 'NULL':
                    self.assertEqual(alvo['motivo'], 'consulta_falhou')

    def test_renova_em_sai_em_utc_com_tz_local_diferente(self):
        self.assertTrue(pathlib.Path('/usr/share/zoneinfo/America/Sao_Paulo').exists(), 'BLOQUEADO: tzdata ausente')
        casa = self.casa()
        casa.cache_agy()
        saida = casa.router('cotas', TZ='America/Sao_Paulo')
        self.assertEqual(saida.returncode, 0, saida.stderr)
        janelas = grupos(lido(casa))['gemini']['janelas']
        self.assertEqual([j['renova_em'] for j in janelas], ['2026-10-30T23:23:36+00:00', '2026-10-25T00:51:24+00:00'])
        self.assertTrue(lido(casa)['gerado'].endswith('+00:00'))
        casa = self.casa()
        autenticacao_falsa(casa)
        agora = int(time.time())
        resposta = {'id': 2, 'result': {'rateLimits': {'limitId': 'codex',
                                                       'primary': {'usedPercent': 20, 'resetsAt': agora + 600},
                                                       'secondary': {'usedPercent': 70.5, 'resetsAt': agora + 86400}}}}
        executavel(casa.bin, 'codex', "read l; echo '{\"id\":1,\"result\":{}}'; read l; read l\n"
                   "echo '%s'; sleep 1" % json.dumps(resposta))
        saida = casa.router('cotas', '--atualizar', '--permitir-remoto', TZ='America/Sao_Paulo')
        self.assertEqual(saida.returncode, 0, saida.stderr)
        janelas = grupos(lido(casa), 'codex', None)['codex']['janelas']
        self.assertEqual(len(janelas), 2)
        for janela in janelas:
            self.assertTrue(janela['renova_em'].endswith('+00:00'), janela)
        self.assertEqual(cotas.instante(janelas[0]['renova_em']), agora + 600)

    def test_ambiente_e_arquivos_de_fora_do_alcance_nao_derrubam_o_comando(self):
        gigante = '1' * 401
        for valor in (gigante, '9' * 5000, '525601', '-5', 'abc', '1e3', '', ' 7 '):
            with self.subTest(entrada='JANGADA_DELEGAR_CACHE no cache', valor=valor[:12]):
                casa = self.casa()
                casa.cache_agy()
                saida = casa.router('cotas', JANGADA_DELEGAR_CACHE=valor)
                self.assertEqual(saida.returncode, 0, saida.stderr)
                documento = lido(casa)
                cotas.validar(documento, time.time())
                self.assertEqual(documento['provedores'][-1]['provedor'], 'claude')
                if valor in (gigante, '9' * 5000, '525601', 'abc', '1e3', ''):
                    gemini = grupos(documento)['gemini']
                    self.assertEqual(gemini['percentual'], 87.5)
                    self.assertEqual(cotas.instante(gemini['valido_ate']) - cotas.instante(gemini['medido_em']), 300)
            with self.subTest(entrada='JANGADA_DELEGAR_CACHE na resposta', valor=valor[:12]):
                casa = self.casa()
                executavel(casa.bin, 'agy', "cat <<'FIM'\n%s\nFIM" % json.dumps(AGY_USO))
                saida = casa.router('cotas', '--atualizar', '--permitir-remoto', JANGADA_DELEGAR_CACHE=valor)
                self.assertEqual(saida.returncode, 0, saida.stderr)
                cotas.validar(lido(casa), time.time())
                self.assertEqual(lido(casa)['provedores'][-1]['provedor'], 'claude')
        for valor in ('', 'a' * 100000, 'gemini-é\tx   claude-', 'gemini-4-argon- claude- gpt- ??'):
            with self.subTest(entrada='JANGADA_DELEGAR_MODELOS', valor=valor[:12]):
                casa = self.casa()
                casa.cache_agy()
                saida = casa.router('cotas', JANGADA_DELEGAR_MODELOS=valor)
                self.assertEqual(saida.returncode, 0, saida.stderr)
                cotas.validar(lido(casa), time.time())
        for nome in ('arquivo', 'x' * 5000):
            with self.subTest(entrada='XDG_CACHE_HOME', valor=nome[:12]):
                casa = self.casa()
                (casa.casa / '.cache').mkdir()
                alvo = casa.casa / nome
                if nome == 'arquivo':
                    alvo.write_text('x')
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas', XDG_CACHE_HOME=str(alvo))

        def profundo(abre, fecha):
            return abre * 100000 + fecha * 100000

        corpos = {'aninhado': profundo('[', ']'), 'sobre o limite': ' ' * (1024 * 1024 + 1) + '{}', 'utf-8 inválido': '\377'}
        for nome, corpo in corpos.items():
            with self.subTest(entrada='cache do agy', corpo=nome):
                casa = self.casa()
                casa.cache.mkdir(parents=True)
                (casa.cache / 'agy-usage.json').write_bytes(corpo.encode('latin-1' if nome == 'utf-8 inválido' else 'utf-8'))
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas')
        for nome, comando in (('aninhado', "head -c 100000 /dev/zero | tr '\\0' '['; head -c 100000 /dev/zero | tr '\\0' ']'"),
                              ('sobre o limite', "head -c 1100000 /dev/zero | tr '\\0' ' '"),
                              ('utf-8 inválido', "printf '\\377'")):
            with self.subTest(entrada='resposta do agy', corpo=nome):
                casa = self.casa()
                executavel(casa.bin, 'agy', comando)
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas', '--atualizar', '--permitir-remoto')
        for nome in ('diretório', 'link', 'fifo'):
            with self.subTest(entrada='cache do agy', tipo=nome):
                casa = self.casa()
                casa.cache.mkdir(parents=True)
                alvo = casa.cache / 'agy-usage.json'
                if nome == 'diretório':
                    alvo.mkdir()
                elif nome == 'link':
                    alvo.symlink_to(casa.cache_agy(nome='outro.json'))
                else:
                    os.mkfifo(alvo)
                self.assertNulo(casa, 'gemini', 'consulta_falhou', 'cotas')
        with self.subTest(entrada='auth.json do Codex aninhado'):
            casa = self.casa()
            autenticacao_falsa(casa)
            (casa.casa / '.codex/auth.json').write_text(profundo('[', ']'))
            self.assertNulo(casa, 'codex', 'consulta_falhou', 'cotas', '--atualizar', '--permitir-remoto')
        with self.subTest(entrada='resposta do Codex aninhada'):
            casa = self.casa()
            autenticacao_falsa(casa)
            executavel(casa.bin, 'codex', "read l; echo '{\"id\":1,\"result\":{}}'; read l; read l\n"
                       "a=$(head -c 100000 /dev/zero | tr '\\0' '['); b=$(head -c 100000 /dev/zero | tr '\\0' ']')\n"
                       "echo \"{\\\"id\\\":2,\\\"result\\\":$a$b}\"; sleep 1")
            self.assertNulo(casa, 'codex', 'consulta_falhou', 'cotas', '--atualizar', '--permitir-remoto')
        for nome in ('lixo', 'grande'):
            with self.subTest(entrada='SQLite', corpo=nome):
                casa = self.casa()
                banco = casa.estado / 'agentes/runtime/tarefas.sqlite'
                banco.parent.mkdir(parents=True)
                if nome == 'lixo':
                    banco.write_bytes(b'isto nao e um banco' * 100)
                else:
                    with banco.open('wb') as arquivo:
                        arquivo.truncate(cotas.LIMITE_BANCO + 1)
                self.assertNulo(casa, 'codex', 'consulta_falhou', 'cotas')

    def test_data_com_fuso_local_de_segundos_nao_derruba_o_comando(self):
        # Antes de 1914 o America/Sao_Paulo tem deslocamento -03:06:28; todo instante sai em UTC.
        casa = self.casa()
        banco = casa.estado / 'agentes/runtime/tarefas.sqlite'
        banco.parent.mkdir(parents=True)
        db = sqlite3.connect(banco)
        db.execute('CREATE TABLE provedores(id TEXT PRIMARY KEY, status TEXT, motivo TEXT, atualizado REAL, '
                   'valido_ate REAL, cota REAL, modelo TEXT, falhas INTEGER, pausado INTEGER)')
        db.execute("INSERT INTO provedores VALUES('codex','AVAILABLE','x',-2208988800,?,41.5,NULL,0,0)", (time.time() + 600,))
        db.commit()
        db.close()
        uso = json.loads(json.dumps(AGY_USO))
        uso['command']['data']['groups'][0]['buckets'][0]['reset_time'] = '1899-12-31T20:53:32-03:06:28'
        casa.cache_agy(uso)
        saida = casa.router('cotas', TZ='America/Sao_Paulo')
        self.assertEqual(saida.returncode, 0, saida.stderr)
        documento = lido(casa)
        cotas.validar(documento, time.time())
        self.assertEqual(json.loads(saida.stdout), documento)
        self.assertEqual(documento['provedores'][-1]['provedor'], 'claude')
        codex = grupos(documento, 'codex', None)['codex']
        self.assertEqual((codex['percentual'], codex['medido_em']), (41.5, '1900-01-01T00:00:00+00:00'))
        self.assertEqual(grupos(documento)['gemini']['janelas'][0]['renova_em'], '1900-01-01T00:00:00+00:00')
        datas = [documento['gerado']] + [grupo[campo] for entrada in documento['provedores'] for grupo in entrada['grupos']
                                          for campo in ('medido_em', 'valido_ate') if grupo[campo]]
        for data in datas:
            self.assertTrue(data.endswith('+00:00'), data)

    def assertNulo(self, casa, grupo, motivo, *args, **ambiente):
        saida = casa.router(*args, **ambiente)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        documento = lido(casa)
        cotas.validar(documento, time.time())
        self.assertEqual(json.loads(saida.stdout), documento)
        provedor = 'codex' if grupo == 'codex' else 'agy'
        alvo = grupos(documento, provedor, None if provedor == 'codex' else 'principal')[grupo]
        self.assertIsNone(alvo['percentual'])
        if motivo:
            self.assertEqual(alvo['motivo'], motivo)
        self.assertEqual(documento['provedores'][-1]['provedor'], 'claude')
        return alvo

    def test_conta_sem_confianca_nao_le_nem_consulta(self):
        casa = self.casa(confia=False)
        casa.cache_agy()
        resposta = casa.router('cotas', '--atualizar', '--permitir-remoto')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        self.assertFalse((casa.casa.parent / 'marca-agy').exists())
        for grupo in grupos(lido(casa)).values():
            self.assertEqual((grupo['percentual'], grupo['motivo']), (None, 'conta_sem_confianca'))

    def test_varias_contas_cada_uma_com_seu_cache_e_sua_confianca(self):
        casa = self.casa(confia=False)
        area = casa.estado / 'contas'
        area.mkdir(parents=True)
        pastas = {nome: area / nome for nome in ('a', 'b')}
        (area / 'agy.json').write_text(json.dumps([
            {'nome': nome, 'pasta': str(pasta), 'argon': nome == 'a'} for nome, pasta in pastas.items()]))
        casa.confiar(RAIZ, pastas['a'])
        casa.cache_agy(nome='agy-usage-a.json')
        casa.cache_agy(nome='agy-usage-b.json')
        resposta = casa.router('cotas', JANGADA_DELEGAR_MODELOS='gemini-3.8-flash-high gemini-4-argon-x')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        documento = lido(casa)
        self.assertEqual([(e['provedor'], e['conta']) for e in documento['provedores']],
                         [('agy', 'a'), ('agy', 'b'), ('codex', None), ('claude', None)])
        self.assertEqual(set(grupos(documento, 'agy', 'a')), {'gemini', 'gemini-argon-wtu', '3p'})
        self.assertEqual(grupos(documento, 'agy', 'a')['gemini-argon-wtu']['percentual'], 33.3)
        self.assertEqual({g['motivo'] for g in grupos(documento, 'agy', 'b').values()}, {'conta_sem_confianca'})
        self.assertNotIn('gemini-argon-wtu', grupos(documento, 'agy', 'b'))

    def test_catalogo_invalido_nao_inventa_conta(self):
        casa = self.casa()
        (casa.estado / 'contas').mkdir(parents=True)
        (casa.estado / 'contas/agy.json').write_text('{ruim')
        resposta = casa.router('cotas')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        agy = lido(casa)['provedores'][0]
        self.assertEqual((agy['conta'], agy['grupos'], agy['motivo']), (None, [], 'consulta_falhou'))

    def test_percentuais_iguais_aos_do_cota_do_grupo_da_base(self):
        def balde(identificador, fracao, **extra):
            return dict({'id': identificador, 'remaining_fraction': fracao, 'reset_time': None, 'disabled': None}, **extra)

        variantes = [
            AGY_USO,
            {'command': {'data': {'groups': [{'buckets': [balde('gemini-weekly', 0.12345), balde('gemini-5h', 0.5)]},
                                              {'buckets': [balde('3p-weekly', 0.005), balde('3p-5h', 0.0049)]}]}}},
            {'command': {'data': {'groups': [{'buckets': [balde('gemini-weekly', 0.4), balde('gemini-5h', 0.1, disabled=True)]},
                                              {'buckets': [balde('3p-weekly', 0), balde('3p-5h', 1)]}]}}},
            {'command': {'data': {'groups': [{'buckets': [balde('gemini-weekly', 1.5), balde('gemini-5h', 0.5)]},
                                              {'buckets': [balde('3p-weekly', '0.5'), balde('3p-5h', 0.5)]}]}}},
            {'command': {'data': {'groups': [{'buckets': [balde('gemini-5h', 0.7)]}, {'buckets': [balde('3p-weekly', None)]}]}}},
            {'command': {'data': {'groups': [{'buckets': [balde('gemini-weekly', 0.1, disabled=True)]}]}}},
            {'command': {'data': {'groups': []}}},
            {'command': {}},
            {},
        ]
        modelos = {'gemini-3.8-flash-high': 'gemini', 'claude-sonnet-5-5-high': '3p', 'gemini-4-argon-x': 'gemini-argon-wtu'}
        with tempfile.TemporaryDirectory() as pasta:
            for indice, dados in enumerate(variantes):
                arquivo = pathlib.Path(pasta) / ('v%d.json' % indice)
                arquivo.write_text(json.dumps(dados))
                novos = {g['grupo']: g['percentual'] for g in cotas.grupos_agy(dados, list(modelos.values()), 'o', 'm', 'v')}
                for modelo, grupo in modelos.items():
                    esperado = cota_da_base(modelo, arquivo)
                    with self.subTest(variante=indice, modelo=modelo):
                        self.assertEqual(novos[grupo], float(esperado) if esperado else None)

    def test_sem_catalogo_o_percentual_do_json_e_o_da_base(self):
        casa = self.casa()
        arquivo = casa.cache_agy()
        resposta = casa.router('cotas', JANGADA_DELEGAR_MODELOS='gemini-3.8-flash-high claude-sonnet-5-5-high gemini-4-argon-x')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        documento = lido(casa)
        self.assertEqual([e['conta'] for e in documento['provedores'] if e['provedor'] == 'agy'], ['principal'])
        for modelo, grupo in (('gemini-3.8-flash-high', 'gemini'), ('claude-sonnet-5-5-high', '3p'),
                              ('gemini-4-argon-x', 'gemini-argon-wtu')):
            self.assertEqual(grupos(documento)[grupo]['percentual'], float(cota_da_base(modelo, arquivo)))

    def test_status_preserva_base_e_doctor_corrige_aviso_do_agy(self):
        status, doctor = gerar_base(RAIZ)
        self.assertEqual(status, json.loads(STATUS_BASE.read_text()))
        esperado = json.loads(DOCTOR_BASE.read_text())
        # Preserva a referência histórica. A única mudança intencional é o
        # reconhecimento de coordenador no registro válido do agy.
        agy = next(v for v in esperado['saida']['verificacoes'] if v['id'] == 'registro.agy')
        self.assertEqual(agy['estado'], 'aviso')
        agy.update(estado='ok', detalhe='Registro válido, com precedência da configuração do usuário; arquivo não executado.')
        esperado['saida']['resumo']['aviso'] -= 1
        esperado['saida']['resumo']['ok'] += 1
        self.assertEqual(doctor, esperado)

    def test_gravacao_interrompida_nao_deixa_json_truncado(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = pathlib.Path(pasta) / 'cotas.json'
            documento = {'versao': 1, 'dados': 'x' * 100000}
            for falha in (OSError('disco cheio'), KeyboardInterrupt()):
                with self.subTest(falha=type(falha).__name__):
                    with patch('cotas.os.replace', side_effect=falha), self.assertRaises(type(falha)):
                        cotas.gravar(destino, documento)
                    self.assertFalse(destino.exists())
                    self.assertEqual(os.listdir(pasta), [])
            cotas.gravar(destino, {'versao': 1, 'dados': 'antigo'})
            with patch('cotas.os.replace', side_effect=OSError('x')), self.assertRaises(OSError):
                cotas.gravar(destino, documento)
            self.assertEqual(json.loads(destino.read_text())['dados'], 'antigo')
            self.assertEqual(os.listdir(pasta), ['cotas.json'])

    @unittest.skipUnless(shutil.which('bwrap'), 'BLOQUEADO: Bubblewrap ausente')
    def test_agente_isolado_nao_altera_o_cotas_json(self):
        # O jangada-isolar recusa abrir isolamento dentro de outro e monta /tmp vazio: com ele a casa do
        # teste fica em /var/tmp; sem ele vale o bwrap puro, com o mesmo ponto de partida (tudo somente leitura).
        com_isolar = not isolado() and os.access('/var/tmp', os.W_OK)
        casa = Casa(onde='/var/tmp' if com_isolar else None)
        self.addCleanup(casa.limpar)
        (casa.bin / 'bwrap').unlink()
        (casa.bin / 'bwrap').symlink_to(shutil.which('bwrap'))
        casa.cache_agy()
        self.assertEqual(casa.router('cotas').returncode, 0)
        arquivo = casa.estado / 'cotas.json'
        antes = arquivo.read_bytes()
        os.utime(arquivo, (1, 1))
        roteador = str(RAIZ / 'bin/jangada-router')
        isolamento = ([str(RAIZ / 'bin/jangada-isolar'), '--'] if com_isolar
                      else [shutil.which('bwrap'), '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--'])
        resposta = subprocess.run(isolamento + [roteador, 'cotas'], cwd=RAIZ, env=casa.env(),
                                  capture_output=True, text=True, timeout=120)
        if 'bwrap:' in resposta.stderr and any(m in resposta.stderr for m in (
                'Operation not permitted', 'No permissions', 'Creating new namespace failed')):
            self.skipTest('BLOQUEADO: ' + resposta.stderr)
        self.assertEqual(arquivo.read_bytes(), antes)
        self.assertEqual(arquivo.stat().st_mtime, 1)
        self.assertEqual([p.name for p in casa.estado.glob('.cotas-*')], [])
        self.assertEqual(resposta.returncode, 1, resposta.stderr)
        self.assertIn('cotas.json não gravado', resposta.stderr)
        self.assertEqual(json.loads(resposta.stdout)['versao'], 1)

    def anterior(self, casa, grupos_agy=(), grupos_codex=(), texto=None):
        """Grava um cotas.json anterior; cada grupo é um dict de grupo_medido ou grupo_nulo."""
        casa.estado.mkdir(parents=True, exist_ok=True)
        documento = {'versao': 1, 'gerado': cotas.iso(time.time()), 'provedores': [
            {'provedor': 'agy', 'conta': 'principal', 'grupos': list(grupos_agy), 'motivo': None},
            {'provedor': 'codex', 'conta': None, 'grupos': list(grupos_codex), 'motivo': None}]}
        (casa.estado / 'cotas.json').write_text(texto if texto is not None else json.dumps(documento))

    def medida(self, grupo, percentual, idade, validade=60):
        medido = time.time() - idade
        return cotas.grupo_medido(grupo, percentual, [], cotas.ORIGEM_AGY, cotas.iso(medido), cotas.iso(medido + validade))

    def banco_codex(self, casa, atualizado, valido_ate, cota=41.5):
        banco = casa.estado / 'agentes/runtime/tarefas.sqlite'
        banco.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(banco)
        db.execute('CREATE TABLE provedores(id TEXT PRIMARY KEY, status TEXT, motivo TEXT, atualizado REAL, '
                   'valido_ate REAL, cota REAL, modelo TEXT, falhas INTEGER, pausado INTEGER)')
        db.execute("INSERT INTO provedores VALUES('codex','AVAILABLE','x',?,?,?,NULL,0,0)", (atualizado, valido_ate, cota))
        db.commit()
        db.close()

    def test_cache_vencido_do_agy_traz_o_ultimo_com_numero_e_data_do_cache(self):
        casa = self.casa()
        arquivo = casa.cache_agy(idade=3600)
        documento = lido_apos(casa)
        for nome, esperado in (('gemini', 87.5), ('3p', 90.5)):
            grupo = grupos(documento)[nome]
            self.assertEqual((grupo['percentual'], grupo['motivo']), (None, 'cache_vencido'))
            self.assertEqual(grupo['ultimo'], {'percentual': esperado, 'medido_em': cotas.iso(arquivo.stat().st_mtime)})
        cotas.validar(documento, time.time())

    def test_cotas_json_anterior_mais_novo_que_o_cache_vence(self):
        casa = self.casa()
        casa.cache_agy(idade=3600)
        anterior = self.medida('gemini', 12.5, 600)
        self.anterior(casa, [anterior])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual(gemini['ultimo'], {'percentual': 12.5, 'medido_em': anterior['medido_em']})
        self.assertEqual(grupos(lido(casa))['3p']['ultimo']['percentual'], 90.5)

    def test_cache_mais_novo_que_o_cotas_json_anterior_vence(self):
        casa = self.casa()
        casa.cache_agy(idade=3600)
        self.anterior(casa, [self.medida('gemini', 12.5, 7200)])
        self.assertEqual(grupos(lido_apos(casa))['gemini']['ultimo']['percentual'], 87.5)

    def test_ultimo_do_cotas_json_anterior_sobrevive_a_leituras_seguintes(self):
        casa = self.casa()
        anterior = cotas.grupo_nulo('gemini', 'cache_vencido', cotas.ORIGEM_AGY)
        anterior['ultimo'] = {'percentual': 95.12, 'medido_em': cotas.iso(time.time() - 900)}
        self.anterior(casa, [anterior])
        for _ in range(2):
            gemini = grupos(lido_apos(casa))['gemini']
            self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'sem_cache'))
            self.assertEqual(gemini['ultimo'], anterior['ultimo'])

    def vencer_anterior(self, casa, grupo='gemini'):
        arquivo = casa.estado / 'cotas.json'
        documento = json.loads(arquivo.read_text())
        for entrada in documento['provedores']:
            for item in entrada['grupos']:
                if item['grupo'] == grupo and item['percentual'] is not None:
                    item['valido_ate'] = cotas.iso(time.time() - 1)
        arquivo.write_text(json.dumps(documento))

    def test_medida_da_atualizacao_sobrevive_ao_cache_antigo_ate_vencer_e_depois_vira_ultimo(self):
        casa = self.casa()
        executavel(casa.bin, 'agy', "cat <<'FIM'\n%s\nFIM" % json.dumps(AGY_USO))
        self.assertEqual(casa.router('cotas', '--atualizar', '--permitir-remoto').returncode, 0)
        t1 = grupos(lido(casa))['gemini']
        self.assertEqual(t1['percentual'], 87.5)
        antigo = json.loads(json.dumps(AGY_USO))
        antigo['command']['data']['groups'][0]['buckets'][0]['remaining_fraction'] = 0.5
        antigo['command']['data']['groups'][0]['buckets'][1]['remaining_fraction'] = 0.5
        casa.cache_agy(antigo, idade=60)
        executavel(casa.bin, 'agy', 'exit 1')
        # Cache T0 ainda válido e mais velho: vale a medida T1, com a validade dela.
        publicado = grupos(lido_apos(casa))['gemini']
        self.assertEqual(publicado, t1)
        self.assertNotIn('ultimo', publicado)
        self.assertEqual(grupos(lido(casa))['3p']['percentual'], 90.5)
        # T1 venceu e o cache T0 também: T1 só entra como `ultimo`.
        self.vencer_anterior(casa)
        casa.cache_agy(antigo, idade=3600)
        vencido = grupos(lido_apos(casa))['gemini']
        self.assertEqual((vencido['percentual'], vencido['motivo']), (None, 'cache_vencido'))
        self.assertEqual(vencido['ultimo'], {'percentual': 87.5, 'medido_em': t1['medido_em']})

    def test_medida_do_anterior_mais_velha_que_o_cache_nao_vence(self):
        casa = self.casa()
        casa.cache_agy(idade=30)
        self.anterior(casa, [self.medida('gemini', 12.5, 100, validade=900)])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['origem']), (87.5, 'agy -p /usage'))
        self.assertNotIn('ultimo', gemini)

    def test_validade_do_anterior_nunca_passa_da_validade_do_cache(self):
        casa = self.casa()
        anterior = self.medida('gemini', 12.5, 60, validade=10 ** 8)
        self.anterior(casa, [anterior])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual(gemini['percentual'], 12.5)
        self.assertEqual(gemini['medido_em'], anterior['medido_em'])
        self.assertEqual(gemini['valido_ate'], cotas.iso(cotas.instante(anterior['medido_em']) + cotas.CACHE_PADRAO * 60))
        # Com a validade do cache em 1 minuto, a mesma medida já venceu e só resta o `ultimo`.
        self.anterior(casa, [anterior])
        resposta = casa.router('cotas', JANGADA_DELEGAR_CACHE='1')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        gemini = grupos(lido(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'sem_cache'))
        self.assertEqual(gemini['ultimo'], {'percentual': 12.5, 'medido_em': anterior['medido_em']})

    def test_cache_vencido_local_e_anterior_vencido_mais_novo_publicam_a_medida_do_anterior(self):
        casa = self.casa()
        casa.cache_agy(idade=3600)
        t1 = self.medida('gemini', 70, 600, validade=60)
        self.anterior(casa, [t1])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'cache_vencido'))
        self.assertEqual((gemini['origem'], gemini['medido_em'], gemini['valido_ate']),
                         (cotas.ORIGEM_AGY, t1['medido_em'], t1['valido_ate']))
        self.assertEqual(gemini['ultimo'], {'percentual': 70, 'medido_em': t1['medido_em']})

    def test_medida_mais_nova_ja_vencida_nao_cede_lugar_a_cache_antigo_ainda_valido(self):
        casa = self.casa()
        casa.cache_agy(idade=200)
        # T1 foi gravada com JANGADA_DELEGAR_CACHE=1 (60 s) e venceu; T0 ainda vale pelos 5 minutos de hoje.
        t1 = self.medida('gemini', 70, 120, validade=60)
        self.anterior(casa, [t1])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'cache_vencido'))
        self.assertEqual(gemini['ultimo'], {'percentual': 70, 'medido_em': t1['medido_em']})
        # O 3p não tem medida mais nova: segue o cache T0, que ainda vale.
        self.assertEqual(grupos(lido(casa))['3p']['percentual'], 90.5)
        # E a regravação não perde T1.
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual(gemini['ultimo'], {'percentual': 70, 'medido_em': t1['medido_em']})

    def test_atualizacao_vence_o_cache_mesmo_no_mesmo_segundo(self):
        casa = self.casa()
        antigo = json.loads(json.dumps(AGY_USO))
        for balde in antigo['command']['data']['groups'][0]['buckets']:
            balde['remaining_fraction'] = 0.5
        casa.cache_agy(antigo)
        executavel(casa.bin, 'agy', "cat <<'FIM'\n%s\nFIM" % json.dumps(AGY_USO))
        self.assertEqual(casa.router('cotas', '--atualizar', '--permitir-remoto').returncode, 0)
        self.assertEqual(grupos(lido(casa))['gemini']['percentual'], 87.5)

    def test_medidas_diferentes_no_mesmo_segundo_conservam_a_do_anterior(self):
        casa = self.casa()
        segundo = int(time.time()) - 60
        arquivo = casa.cache_agy()
        os.utime(arquivo, (segundo + 0.2, segundo + 0.2))
        anterior = cotas.grupo_medido('gemini', 12.5, [], cotas.ORIGEM_AGY, cotas.iso(segundo), cotas.iso(segundo + 240))
        self.anterior(casa, [anterior])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['medido_em']), (12.5, anterior['medido_em']))

    def test_medida_do_anterior_com_validade_vencida_so_entra_como_ultimo(self):
        casa = self.casa()
        casa.cache_agy(idade=3600)
        anterior = self.medida('gemini', 12.5, 100, validade=50)
        self.anterior(casa, [anterior])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'cache_vencido'))
        self.assertEqual(gemini['ultimo'], {'percentual': 12.5, 'medido_em': anterior['medido_em']})

    def test_medida_valida_do_anterior_nao_atravessa_conta_sem_confianca(self):
        casa = self.casa(confia=False)
        self.anterior(casa, [self.medida('gemini', 12.5, 60, validade=900)])
        gemini = grupos(lido_apos(casa))['gemini']
        self.assertEqual((gemini['percentual'], gemini['motivo']), (None, 'conta_sem_confianca'))
        self.assertNotIn('ultimo', gemini)

    def test_codex_vencido_traz_o_ultimo(self):
        casa = self.casa()
        agora = time.time()
        self.banco_codex(casa, agora - 600, agora - 300)
        codex = grupos(lido_apos(casa), 'codex', None)['codex']
        self.assertEqual((codex['percentual'], codex['motivo']), (None, 'cache_vencido'))
        self.assertEqual(codex['ultimo'], {'percentual': 41.5, 'medido_em': cotas.iso(agora - 600)})

    def test_medida_valida_nao_traz_ultimo(self):
        casa = self.casa()
        casa.cache_agy()
        agora = time.time()
        self.banco_codex(casa, agora - 10, agora + 50)
        self.anterior(casa, [self.medida('gemini', 12.5, 600)])
        documento = lido_apos(casa)
        self.assertEqual(grupos(documento)['gemini']['percentual'], 87.5)
        self.assertEqual(grupos(documento, 'codex', None)['codex']['percentual'], 41.5)
        for provedor in documento['provedores']:
            for grupo in provedor['grupos']:
                self.assertNotIn('ultimo', grupo)

    def test_conta_sem_confianca_continua_sem_numero_nenhum(self):
        casa = self.casa(confia=False)
        casa.cache_agy(idade=3600)
        self.anterior(casa, [self.medida('gemini', 12.5, 600), self.medida('3p', 50, 600)])
        for grupo in grupos(lido_apos(casa)).values():
            self.assertEqual((grupo['percentual'], grupo['motivo']), (None, 'conta_sem_confianca'))
            self.assertNotIn('ultimo', grupo)

    def test_cotas_json_anterior_invalido_e_ignorado(self):
        casa = self.casa()
        valido = lambda **extra: dict(self.medida('gemini', 40, 60, validade=900), **extra)
        gigante = json.dumps({'versao': 1, 'provedores': [], 'folga': 'x' * cotas.LIMITE_LEITURA})
        textos = {'corrompido': '{ruim', 'vazio': '', 'gigante': gigante, 'lista': '[1, 2]',
                  'sem_lista': json.dumps({'provedores': {'agy': 1}}), 'NaN': '{"provedores": [{"provedor": "agy", "conta": "principal", '
                  '"grupos": [{"grupo": "gemini", "percentual": NaN, "medido_em": "%s"}]}]}' % cotas.iso(time.time() - 60)}
        for rotulo, grupo in (('acima_de_100', valido(percentual=100.5)), ('abaixo_de_0', valido(percentual=-1)),
                              ('booleano', valido(percentual=True)), ('texto', valido(percentual='40')),
                              ('data_sem_fuso', valido(medido_em='2026-10-25T00:51:24')),
                              ('data_ruim', valido(medido_em='ontem')), ('grupo_ruim', valido(grupo='Gemini 1')),
                              ('ultimo_fora_de_0_a_100', dict(cotas.grupo_nulo('gemini', 'sem_cache'),
                                                              ultimo={'percentual': 101, 'medido_em': cotas.iso(time.time() - 60)}))):
            textos[rotulo] = None
            self.anterior(casa, [grupo])
            textos[rotulo] = (casa.estado / 'cotas.json').read_text()
        for rotulo, texto in textos.items():
            with self.subTest(rotulo=rotulo):
                self.anterior(casa, texto=texto)
                documento = lido_apos(casa)
                for grupo in grupos(documento).values():
                    self.assertNotIn('ultimo', grupo)
                    self.assertIsNone(grupo['percentual'])
                cotas.validar(documento, time.time())
        with self.subTest(rotulo='link'):
            self.anterior(casa, [self.medida('gemini', 40, 60, validade=900)])
            real = casa.estado / 'real.json'
            (casa.estado / 'cotas.json').rename(real)
            (casa.estado / 'cotas.json').symlink_to(real)
            self.assertEqual(casa.router('cotas').returncode, 0)
            for grupo in grupos(lido(casa)).values():
                self.assertNotIn('ultimo', grupo)
                self.assertIsNone(grupo['percentual'])

    def test_data_futura_e_ignorada(self):
        casa = self.casa()
        casa.cache_agy(idade=-3600)
        self.anterior(casa, [self.medida('gemini', 40, -3600)], [self.medida('codex', 30, -3600)])
        documento = lido_apos(casa)
        for grupo in list(grupos(documento).values()) + list(grupos(documento, 'codex', None).values()):
            self.assertNotIn('ultimo', grupo)
            self.assertIsNone(grupo['percentual'])
        casa.cache_agy(idade=3600)
        self.assertEqual(grupos(lido_apos(casa))['gemini']['ultimo']['percentual'], 87.5)
        agora = time.time()
        self.banco_codex(casa, agora + 3600, agora + 7200)
        self.assertNotIn('ultimo', grupos(lido_apos(casa), 'codex', None)['codex'])

    def validar_com_ultimo_em(self, medido_em):
        agora = time.time()
        nulo = cotas.grupo_nulo('gemini', 'cache_vencido', cotas.ORIGEM_AGY)
        nulo['ultimo'] = {'percentual': 50.0, 'medido_em': medido_em(agora)}
        cotas.validar({'versao': 1, 'gerado': cotas.iso(agora), 'provedores': [
            {'provedor': 'agy', 'conta': 'principal', 'grupos': [nulo], 'motivo': None}]}, agora)

    def test_validador_recusa_ultimo_com_data_impossivel(self):
        with self.assertRaises(ValueError):
            self.validar_com_ultimo_em(lambda agora: '2026-02-30T00:00:00+00:00')

    def test_validador_recusa_ultimo_com_data_futura(self):
        with self.assertRaises(ValueError):
            self.validar_com_ultimo_em(lambda agora: cotas.iso(agora + 3600))

    def test_validador_recusa_ultimo_mal_formado(self):
        agora = time.time()
        ultimo = {'percentual': 50.0, 'medido_em': cotas.iso(agora - 60)}
        nulo = cotas.grupo_nulo('gemini', 'cache_vencido', cotas.ORIGEM_AGY)
        documento = lambda grupo: {'versao': 1, 'gerado': cotas.iso(agora),
                                   'provedores': [{'provedor': 'agy', 'conta': 'principal', 'grupos': [grupo], 'motivo': None}]}
        cotas.validar(documento(dict(nulo, ultimo=ultimo)), agora)
        medido = self.medida('gemini', 50.0, 60)
        sem_confianca = cotas.grupo_nulo('gemini', 'conta_sem_confianca')
        for rotulo, grupo in (('com_numero', dict(medido, ultimo=ultimo)), ('sem_confianca', dict(sem_confianca, ultimo=ultimo)),
                              ('percentual_101', dict(nulo, ultimo=dict(ultimo, percentual=101))),
                              ('sem_data', dict(nulo, ultimo={'percentual': 50.0})),
                              ('data_ruim', dict(nulo, ultimo=dict(ultimo, medido_em='ontem'))),
                              ('nao_objeto', dict(nulo, ultimo=50)), ('campo_extra', dict(nulo, ultimo=dict(ultimo, origem='x')))):
            with self.subTest(rotulo), self.assertRaises(ValueError):
                cotas.validar(documento(grupo), agora)

def lido_apos(casa):
    resposta = casa.router('cotas')
    assert resposta.returncode == 0, resposta.stderr
    return lido(casa)


if __name__ == '__main__' and '--gravar-base' in sys.argv:
    status, doctor = gerar_base(pathlib.Path(sys.argv[sys.argv.index('--gravar-base') + 1]).resolve())
    STATUS_BASE.write_text(json.dumps(status, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    DOCTOR_BASE.write_text(json.dumps(doctor, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    sys.exit(0)


if __name__ == '__main__':
    unittest.main()
