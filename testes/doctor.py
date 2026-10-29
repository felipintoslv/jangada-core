"""Diagnóstico em árvores falsas, sem clientes reais nem alterações nas fontes."""

import base64
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('doctor', RAIZ / 'orquestracao/doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def gravar(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados), encoding='utf-8')


def retrato(pasta, ignorar_datas=()):
    itens = {}
    for p in [pasta, *sorted(pasta.rglob('*'))]:
        info = p.lstat()
        conteudo = (os.readlink(p) if p.is_symlink() else
                    hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
        data = None if p in ignorar_datas else info.st_mtime_ns
        itens[str(p.relative_to(pasta))] = (info.st_mode, info.st_uid, info.st_gid, data, conteudo)
    return itens


class Diagnostico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.core = self.base / 'instalado'
        self.core.mkdir()
        self.env = {'HOME': str(self.home), 'PATH': os.environ['PATH'],
                    'XDG_CONFIG_HOME': str(self.home / 'config'), 'XDG_STATE_HOME': str(self.home / 'state'),
                    'XDG_CACHE_HOME': str(self.home / 'cache'), 'JANGADA_CORE_PATH': str(self.core),
                    'JANGADA_OLLAMA_URL': 'https://nao-consultar.invalid'}
        self.ambiente = patch.dict(os.environ, self.env, clear=True)
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)
        self.d = doctor.Doctor()
        for nome in ('provedores', 'migrations', 'bin'):
            (self.core / nome).mkdir()
        (self.core / 'bin/jangada-isolar').write_text('#!/bin/bash\nexit 90\n')
        (self.core / 'bin/jangada-isolar').chmod(0o755)
        for p in (RAIZ / 'provedores').glob('*.conf'):
            shutil.copy2(p, self.core / 'provedores' / p.name)

    def item(self, dados, ident):
        return next(i for i in dados['verificacoes'] if i['id'] == ident)

    def test_ausencias_resumo_json_e_entrada(self):
        vazia = self.base / 'programas'
        vazia.mkdir()
        for nome in ('bash', 'python3', 'dirname'):
            (vazia / nome).symlink_to(shutil.which(nome))
        ambiente = dict(os.environ, PATH=str(vazia))
        antes = retrato(self.home)
        p = subprocess.run([str(RAIZ / 'bin/jangada'), 'doctor', '--json'],
                           env=ambiente, capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 1, p.stderr)
        dados = json.loads(p.stdout)
        self.assertEqual(dados['versao'], 1)
        self.assertEqual(self.item(dados, 'programa.bwrap')['estado'], 'falha')
        self.assertEqual(self.item(dados, 'programa.claude')['estado'], 'aviso')
        self.assertEqual(self.item(dados, 'pastas.estado')['estado'], 'aviso')
        self.assertEqual(self.item(dados, 'local.modelo')['estado'], 'nao_verificavel')
        self.assertEqual(dados['codigo_saida'], p.returncode)
        self.assertEqual(sum(dados['resumo'].values()), len(dados['verificacoes']))
        self.assertEqual(antes, retrato(self.home))
        for opcao in ('--ajuda', '--help', '-h'):
            p = subprocess.run([str(RAIZ / 'bin/jangada-doctor'), opcao], env=ambiente, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0)
            self.assertIn('--json', p.stdout)
        p = subprocess.run([str(RAIZ / 'bin/jangada-doctor'), '--inexistente'], env=ambiente, capture_output=True)
        self.assertEqual(p.returncode, 2)

    def test_arvore_integra_sem_escritas_ou_clientes(self):
        programas = self.base / 'programas'
        programas.mkdir()
        for nome in ('bash', 'python3', 'dirname'):
            (programas / nome).symlink_to(shutil.which(nome))
        for nome in ('claude', 'codex', 'agy', 'ollama', 'jangada-router', 'jangada-migrar', 'jangada-isolar'):
            p = programas / nome
            p.write_text('#!/bin/bash\nexit 91\n')
            p.chmod(0o755)
        bwrap = programas / 'bwrap'
        bwrap.write_text('#!/bin/bash\n[[ "$*" == "--unshare-user --unshare-pid --unshare-net --ro-bind / / --die-with-parent --new-session -- /usr/bin/true" ]]\n')
        bwrap.chmod(0o755)
        for nome in ('agentes/runtime', 'revisoes', 'coordenadores', 'codex', 'fotos', 'integracoes', 'migracoes'):
            (self.d.estado / nome).mkdir(parents=True, exist_ok=True, mode=0o700)
        for nome in ('claude', 'agy'):
            caminho = self.home / ('.claude/settings.json' if nome == 'claude' else '.gemini/config/hooks.json')
            modelo = (RAIZ / 'agentes' / nome / 'hooks.json').read_text().replace('@JANGADA_CORE_PATH@', str(self.core))
            gravar(caminho, json.loads(modelo))
        self.credenciais()
        self.cota()
        (self.core / 'migrations/202610180000-teste.sh').write_text('exit 91\n')
        (self.d.estado / 'migracoes/202610180000-teste.sh').touch()
        gravar(self.d.config / 'jangada.conf', {'nao_executar': 'SEGREDO_SENTINELA'})
        (self.d.config / 'jangada.conf').write_text('JANGADA_OLLAMA_URL=https://nao-consultar.invalid\n$(touch PROIBIDO)\n')
        os.environ['PATH'] = str(programas)
        antes = retrato(self.base)
        p = subprocess.run([str(RAIZ / 'bin/jangada-doctor'), '--json'], capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 1)
        dados = json.loads(p.stdout)
        for ident in ('hooks.claude', 'hooks.agy', 'autenticacao.claude', 'autenticacao.codex', 'cota.agy', 'isolamento.userns', 'migracoes.pendentes'):
            self.assertEqual(self.item(dados, ident)['estado'], 'ok', ident)
        self.assertNotIn('SEGREDO_SENTINELA', p.stdout + p.stderr)
        self.assertEqual(antes, retrato(self.base))
        self.assertFalse((RAIZ / 'PROIBIDO').exists())

    def credenciais(self, prazo=None):
        fim = prazo if prazo is not None else time.time() + 600
        gravar(self.home / '.claude/.credentials.json', {'claudeAiOauth': {
            'accessToken': 'SEGREDO_SENTINELA', 'expiresAt': fim * 1000}})
        payload = base64.urlsafe_b64encode(json.dumps({'exp': fim}).encode()).decode().rstrip('=')
        gravar(self.d.codex / 'auth.json', {'tokens': {'access_token': 'SEGREDO_SENTINELA.' + payload + '.s',
                                                     'id_token': 'SEGREDO_SENTINELA'}})

    def cota(self):
        gravar(self.d.cache / 'agy-usage.json', {'command': {'data': {'groups': [{'buckets': [
            {'id': 'gemini-5h', 'remaining_fraction': .8}, {'id': 'gemini-week', 'remaining_fraction': .7},
            {'id': '3p-5h', 'remaining_fraction': .5}, {'id': '3p-week', 'remaining_fraction': .1, 'disabled': True}]}]}}})

    def test_cota_agy_parcial_e_grupos_independentes(self):
        caminho = self.d.cache / 'agy-usage.json'

        def consultar(baldes):
            gravar(caminho, {'command': {'data': {'groups': [{'buckets': baldes}]}}})
            self.d.conferir('cota.agy', self.d.cota_agy)
            return self.d.itens[-1]

        gemini = {'id': 'gemini-5h', 'remaining_fraction': .8}
        parcial = consultar([gemini])
        self.assertEqual(parcial['estado'], 'aviso')
        self.assertIn('gemini: 80.00%', parcial['detalhe'])
        self.assertIn('ausentes: 3p', parcial['detalhe'])
        parcial = consultar([{'id': '3p-5h', 'remaining_fraction': .5}])
        self.assertEqual(parcial['estado'], 'aviso')
        self.assertIn('3p: 50.00%', parcial['detalhe'])
        self.assertIn('ausentes: gemini', parcial['detalhe'])
        self.d.valores['JANGADA_DELEGAR_MODELOS'] = 'gemini-modelo'
        for fracao in (None, 'SEGREDO_SENTINELA', True, float('nan'), -1, 2):
            item = consultar([gemini, {'id': '3p-5h', 'remaining_fraction': fracao}])
            self.assertEqual(item['estado'], 'ok')
        self.d.valores['JANGADA_DELEGAR_MODELOS'] = 'gemini-modelo claude-modelo'
        item = consultar([gemini, {'id': '3p-5h', 'remaining_fraction': 'SEGREDO_SENTINELA'}])
        self.assertEqual(item['estado'], 'aviso')
        self.assertIn('inválidos: 3p', item['detalhe'])
        self.assertNotIn('SEGREDO_SENTINELA', item['detalhe'])
        item = consultar([gemini, {'id': '3p-5h', 'remaining_fraction': .01}])
        self.assertEqual(item['estado'], 'aviso')
        self.assertIn('3p: 1.00%', item['detalhe'])
        self.assertIn('abaixo da reserva: 3p', item['detalhe'])
        for fracao in (0, .19):
            item = consultar([gemini, {'id': '3p-5h', 'remaining_fraction': fracao}])
            self.assertEqual(item['estado'], 'aviso')
            self.assertIn('abaixo da reserva: 3p', item['detalhe'])
            self.assertIn('gemini: 80.00%', item['detalhe'])
        item = consultar([gemini, {'id': '3p-5h', 'remaining_fraction': .2}])
        self.assertEqual(item['estado'], 'ok')
        item = consultar([gemini, {'id': 'gemini-weekly', 'remaining_fraction': .1},
                          {'id': '3p-5h', 'remaining_fraction': .01}])
        self.assertEqual(item['estado'], 'aviso')
        self.assertIn('gemini: 10.00%', item['detalhe'])
        for baldes in ([], [{'id': 'gemini-5h', 'remaining_fraction': None}],
                       [dict(gemini, disabled=True)], [{'id': 'gemini', 'remaining_fraction': .8}]):
            self.assertEqual(consultar(baldes)['estado'], 'aviso')

    def test_credenciais_invalidas_expiradas_sem_vazamento(self):
        self.credenciais(1)
        for provedor in ('claude', 'codex'):
            self.assertEqual(self.d.autenticacao(provedor)[0], 'aviso')
        for dados in ([], {'tokens': []}, {'tokens': {'access_token': 'x.?.x', 'id_token': 's'}}):
            gravar(self.d.codex / 'auth.json', dados)
            self.d.conferir('autenticacao.codex', lambda: self.d.autenticacao('codex'))
            self.assertEqual(self.d.itens[-1]['estado'], 'nao_verificavel')
        self.assertNotIn('SEGREDO_SENTINELA', json.dumps(self.d.itens))

    def test_cotas_expiradas_invalidas_e_banco_sem_auxiliares(self):
        self.cota()
        cache = self.d.cache / 'agy-usage.json'
        os.utime(cache, (1, 1))
        self.assertEqual(self.d.cota_agy()[0], 'nao_verificavel')
        for dados in ({'command': {'data': {'groups': None}}}, {'command': []}, {'command': {'data': {'groups': [None]}}}):
            gravar(cache, dados)
            self.d.conferir('cota.agy', self.d.cota_agy)
            self.assertEqual(self.d.itens[-1]['estado'], 'nao_verificavel')
        banco = self.d.estado / 'agentes/runtime/tarefas.sqlite'
        banco.parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(banco)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE provedores(id, cota, atualizado, valido_ate)')
            db.execute('INSERT INTO provedores VALUES(?,?,?,?)', ('codex', 80, time.time()-5, time.time()+60))
        antes = retrato(self.home)
        self.assertFalse(Path(str(banco) + '-wal').exists())
        self.assertEqual(self.d.cota_codex()[0], 'ok')
        self.assertEqual(antes, retrato(self.home))
        Path(str(banco) + '-wal').touch()
        self.assertEqual(self.d.cota_codex()[0], 'nao_verificavel')
        Path(str(banco) + '-wal').unlink()
        with contextlib.closing(sqlite3.connect(banco)) as db, db:
            db.execute('UPDATE provedores SET valido_ate=0')
        self.assertEqual(self.d.cota_codex()[0], 'nao_verificavel')

    def test_hooks_e_pastas(self):
        gravar(self.home / '.claude/settings.json', {'hooks': {}})
        self.assertEqual(self.d.hooks('claude')[0], 'aviso')
        self.assertEqual(self.d.hooks('codex')[0], 'nao_verificavel')
        confianca = self.d.codex / 'jangada-hooks-confianca.json'
        gravar(confianca, {'sessao': {'trusted_hash': 'sha256:teste', 'enabled': False}})
        self.assertEqual(self.d.hooks('codex')[0], 'aviso')
        gravar(confianca, {'sessao': {'trusted_hash': 'sha256:teste'}})
        self.assertEqual(self.d.hooks('codex')[0], 'nao_verificavel')
        self.assertIn('1 entradas', self.d.hooks('codex')[1])
        gravar(confianca, {'sessao': []})
        self.d.conferir('hooks.codex', lambda: self.d.hooks('codex'))
        self.assertEqual(self.d.itens[-1]['estado'], 'nao_verificavel')
        pasta = self.d.estado / 'revisoes'
        pasta.mkdir(parents=True, mode=0o700)
        self.assertEqual(self.d.pasta('revisoes')[0], 'ok')
        pasta.chmod(0o777)
        self.assertEqual(self.d.pasta('revisoes')[0], 'aviso')
        pasta.rmdir()
        pasta.symlink_to(self.home, target_is_directory=True)
        self.assertEqual(self.d.pasta('revisoes')[0], 'falha')
        with patch('os.getuid', return_value=os.getuid()+1):
            self.assertEqual(self.d.pasta('')[0], 'falha')
        fifo = self.home / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            doctor.ler(fifo)

    def test_hooks_codex_deduplicados_e_contextos_separados(self):
        sessao = self.d.estado / 'codex/s1/jangada-hooks-confianca.json'
        atual = self.d.codex / 'jangada-hooks-confianca.json'
        coordenador = self.d.estado / 'coordenadores/codex-hooks-confianca.json'
        gravar(sessao, {'s': {'trusted_hash': 'sha256:teste'}})
        atual.parent.mkdir(parents=True)
        os.link(sessao, atual)
        os.environ['JANGADA_SESSAO'] = 's1'
        antes = retrato(self.home)
        estado, detalhe = self.d.hooks('codex')
        self.assertEqual(estado, 'nao_verificavel')
        self.assertIn('sessão atual: 1 entradas', detalhe)
        self.assertNotIn('2 entradas', detalhe)
        self.assertEqual(antes, retrato(self.home))
        gravar(coordenador, {'c': {'trusted_hash': 'sha256:teste', 'enabled': False}})
        estado, detalhe = self.d.hooks('codex')
        self.assertEqual(estado, 'aviso')
        self.assertIn('sessão atual: 1 entradas, 0 desabilitadas', detalhe)
        self.assertIn('coordenadores: 1 entradas, 1 desabilitadas', detalhe)
        self.assertNotIn('2 entradas', detalhe)
        atual.unlink()
        gravar(atual, {'g': {'trusted_hash': 'sha256:teste'}})
        self.assertIn('pasta Codex: 1 entradas', self.d.hooks('codex')[1])

    def test_ollama_sem_geracao_redirect_ou_endereco_remoto(self):
        class Resposta:
            status = 200
            def read(self, _limite):
                return b'{"models":[{"name":"qwen3:4b"}]}'
        with patch.object(doctor.http.client, 'HTTPConnection') as http:
            http.return_value.getresponse.return_value = Resposta()
            self.d.valores['JANGADA_OLLAMA_URL'] = 'http://localhost:11434'
            self.assertEqual(self.d.local()[0], 'ok')
            http.return_value.request.assert_called_once_with('GET', '/api/tags')
            http.return_value.close.assert_called_once()
            self.d.valores['JANGADA_LOCAL_MODELO'] = 'ausente'
            self.assertEqual(self.d.local()[0], 'aviso')
            for status in (302, 500):
                Resposta.status = status
                self.d.conferir('local.modelo', self.d.local)
                self.assertEqual(self.d.itens[-1]['estado'], 'nao_verificavel')
            http.reset_mock()
            for url in ('https://remoto.invalid', 'http://segredo:senha@localhost', 'http://localhost@remoto.invalid'):
                self.d.valores['JANGADA_OLLAMA_URL'] = url
                self.assertEqual(self.d.local()[0], 'nao_verificavel')
            http.assert_not_called()

    def test_tempo_userns_falha_parcial_e_saida_zero(self):
        with patch.object(doctor.shutil, 'which', return_value='/bwrap'), patch.object(doctor, 'executar', side_effect=subprocess.TimeoutExpired('bwrap', 3)):
            self.d.conferir('isolamento.userns', self.d.userns)
        self.assertEqual(self.d.itens[-1]['estado'], 'nao_verificavel')
        with patch.object(doctor, 'executar', side_effect=ValueError('SEGREDO_SENTINELA')):
            self.assertEqual(self.d.userns()[0], 'falha')
        with patch.object(doctor.shutil, 'which', return_value='/programa'), patch.object(doctor, 'executar', return_value=''):
            dados = self.d.relatorio()
        self.assertEqual(dados['codigo_saida'], 0)
        self.assertIn('Resumo:', doctor.texto(dados))
        self.assertNotIn('SEGREDO_SENTINELA', doctor.texto(dados))
        self.assertIn('pastas.migracoes', [i['id'] for i in dados['verificacoes']])

    def test_registro_agy_instalado_aceita_funcao_coordenador(self):
        self.d.registro()
        agy = self.item({'verificacoes': self.d.itens}, 'registro.agy')
        self.assertEqual(agy['estado'], 'ok', agy['detalhe'])

    def test_registro_tem_mesmas_funcoes_que_catalogo_do_core(self):
        extra = self.d.config / 'provedores/extra.conf'
        extra.parent.mkdir(parents=True)
        for tipo, funcoes in [('cli', 'coordenador'), ('cli', 'principal coordenador revisor delegacao'),
                              ('ollama', 'delegacao'), ('ollama', 'coordenador'),
                              ('ollama', 'principal'), ('cli', 'coordenador desconhecido'),
                              ('cli', '')]:
            with self.subTest(tipo=tipo, funcoes=funcoes):
                extra.write_text(f'TIPO={tipo}\nFUNCOES={funcoes}\n')
                self.d.itens.clear()
                self.d.registro()
                resultado = subprocess.run([str(RAIZ / 'bin/jangada-config'), '--provedores-json'],
                                           capture_output=True, text=True, timeout=10)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)
                aceito = any(p['id'] == 'extra' for p in json.loads(resultado.stdout))
                item = self.item({'verificacoes': self.d.itens}, 'registro.extra')
                self.assertEqual(item['estado'] == 'ok', aceito)

    def test_migracoes_e_registro_adicional(self):
        (self.core / 'migrations/202610180000-teste.sh').write_text('exit 99\n')
        self.assertEqual(self.d.migracoes()[0], 'aviso')
        extra = self.d.config / 'provedores/extra.conf'
        extra.parent.mkdir(parents=True)
        extra.write_text('TIPO=cli\nFUNCOES=revisor\nCOMANDO=$(touch PROIBIDO)\n')
        self.d.registro()
        self.assertEqual(self.item({'verificacoes': self.d.itens}, 'registro.extra')['estado'], 'ok')
        extra.write_text('TIPO=ollama\nFUNCOES=principal\n')
        self.d.itens.clear()
        self.d.registro()
        self.assertEqual(self.item({'verificacoes': self.d.itens}, 'registro.extra')['estado'], 'aviso')

    @unittest.skipUnless(shutil.which('git') and shutil.which('ssh-keygen'), 'Git e ssh-keygen necessários para o caso assinado')
    def test_versao_assinada_pendencias_e_configuracao_hostil(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.core), *args], stderr=subprocess.DEVNULL, text=True).strip()

        chave = self.base / 'assinante'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(chave)], check=True)
        git('init', '-q', '-b', 'main')
        for k, v in (('user.name', 'Teste'), ('user.email', 'teste@example.invalid'),
                     ('user.signingkey', str(chave)), ('gpg.format', 'ssh'), ('commit.gpgsign', 'true')):
            git('config', k, v)
        git('commit', '-q', '--allow-empty', '-m', 'feat(teste): primeira versão')
        primeiro = git('rev-parse', 'HEAD')
        git('update-ref', 'refs/remotes/origin/main', primeiro)
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').write_text('teste@example.invalid ' + chave.with_suffix('.pub').read_text())
        antes = retrato(self.base)
        self.assertEqual(self.d.versao()[0], 'nao_verificavel')
        self.assertIn('Pasta de estado ausente', self.d.versao()[1])
        self.assertEqual(antes, retrato(self.base))
        self.assertFalse(self.d.estado.exists())
        self.d.estado.mkdir(parents=True, mode=0o700)
        gravar(self.d.estado / 'registro.json', {'manter': 'SEGREDO_SENTINELA'})
        antes = retrato(self.base, ignorar_datas=(self.d.estado,))
        self.assertEqual(self.d.versao()[0], 'ok')
        self.assertEqual(antes, retrato(self.base, ignorar_datas=(self.d.estado,)))
        self.assertFalse(list(self.d.estado.glob('.git_vtag_tmp*')))
        verificador = shutil.which('ssh-keygen')
        programas = self.base / 'programas'
        programas.mkdir()
        (programas / 'git').symlink_to(shutil.which('git'))
        herdado = self.base / 'temporario-proibido'
        with patch.dict(os.environ, PATH=str(programas), TMPDIR=str(herdado)), patch.object(doctor, 'executar', wraps=doctor.executar) as executar:
            estado, detalhe = self.d.versao()
            self.assertEqual(estado, 'nao_verificavel')
            self.assertIn('ssh-keygen ausente', detalhe)
            self.assertFalse(any('--format=%G?' in c.args[0] for c in executar.call_args_list))
            conferir = programas / 'ssh-keygen'
            conferir.write_text(f'''#!{sys.executable}
import os
from pathlib import Path
import sys
import time
assinatura = Path(sys.argv[sys.argv.index('-s') + 1])
if assinatura.parent != Path({str(self.d.estado)!r}) or not assinatura.is_file():
    raise SystemExit(91)
if os.environ['TMPDIR'] != {str(self.d.estado)!r}:
    raise SystemExit(92)
if os.environ.get('DOCTOR_TESTE_ESPERAR'):
    time.sleep(10)
os.execv({verificador!r}, [{verificador!r}, *sys.argv[1:]])
''')
            conferir.chmod(0o755)
            self.assertEqual(self.d.versao()[0], 'ok')
            conferencias = [c.args[0] for c in executar.call_args_list if '--format=%G?' in c.args[0]]
            self.assertTrue(conferencias)
            self.assertTrue(all('gpg.ssh.program=' + str(programas / 'ssh-keygen') in c for c in conferencias))
            self.assertEqual(os.environ['TMPDIR'], str(herdado))
            self.assertFalse(herdado.exists())
            self.assertFalse(list(self.d.estado.glob('.git_vtag_tmp*')))
        original = doctor.executar

        def prazo_curto(args, **kwargs):
            if '--format=%G?' in args:
                kwargs['prazo'] = .15
            return original(args, **kwargs)

        antes = retrato(self.base, ignorar_datas=(self.d.estado,))
        with patch.dict(os.environ, PATH=str(programas), DOCTOR_TESTE_ESPERAR='1'), \
                patch.object(doctor, 'executar', side_effect=prazo_curto):
            self.d.conferir('versao.origem', self.d.versao)
            self.assertEqual(self.d.itens[-1]['estado'], 'nao_verificavel')
        self.assertFalse(list(self.d.estado.glob('.git_vtag_tmp*')))
        self.assertEqual(antes, retrato(self.base, ignorar_datas=(self.d.estado,)))
        git('commit', '-q', '--allow-empty', '-m', 'feat(teste): segunda versão')
        segundo = git('rev-parse', 'HEAD')
        git('update-ref', 'refs/remotes/origin/main', segundo)
        git('update-ref', 'refs/heads/main', primeiro)
        self.assertIn('1 commits pendentes', self.d.versao()[1])
        git('-c', 'commit.gpgsign=false', 'commit', '-q', '--allow-empty', '-m', 'feat(teste): sem assinatura')
        git('commit', '-q', '--allow-empty', '-m', 'feat(teste): ponta assinada')
        git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
        git('update-ref', 'refs/heads/main', primeiro)
        antes = retrato(self.base, ignorar_datas=(self.d.estado,))
        self.assertEqual(self.d.versao()[0], 'aviso')
        self.assertIn('1 commits sem assinatura válida por allowed_signers', self.d.versao()[1])
        self.assertIn('jangada-update recusaria', self.d.versao()[1])
        self.assertNotIn('feat(teste)', self.d.versao()[1])
        self.assertFalse(list(self.d.estado.glob('.git_vtag_tmp*')))
        self.assertEqual(antes, retrato(self.base, ignorar_datas=(self.d.estado,)))
        outra = self.base / 'outra-chave'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(outra)], check=True)
        git('-c', 'user.signingkey=' + str(outra), 'commit', '-q', '--allow-empty', '-m', 'SEGREDO_SENTINELA')
        git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
        git('update-ref', 'refs/heads/main', primeiro)
        antes = retrato(self.base, ignorar_datas=(self.d.estado,))
        estado, detalhe = self.d.versao()
        self.assertEqual(estado, 'aviso')
        self.assertIn('1 commits sem assinatura válida por allowed_signers', detalhe)
        self.assertIn('jangada-update recusaria', detalhe)
        self.assertNotIn('SEGREDO_SENTINELA', detalhe)
        self.assertFalse(list(self.d.estado.glob('.git_vtag_tmp*')))
        self.assertEqual(antes, retrato(self.base, ignorar_datas=(self.d.estado,)))
        git('update-ref', 'refs/remotes/origin/main', segundo)
        hostil = self.base / 'hostil'
        marca = self.base / 'PROIBIDO'
        hostil.write_text('#!/bin/bash\ntouch "' + str(marca) + '"\nexit 99\n')
        hostil.chmod(0o755)
        git('config', 'core.fsmonitor', str(hostil))
        git('config', 'gpg.ssh.program', str(hostil))
        antes = retrato(self.base, ignorar_datas=(self.d.estado,))
        self.assertIn('1 commits pendentes', self.d.versao()[1])
        self.assertEqual(antes, retrato(self.base, ignorar_datas=(self.d.estado,)))
        self.assertFalse(marca.exists())

    def test_versao_sem_verificador_nao_avalia_assinatura(self):
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').touch()
        with patch.object(self.d, 'git', side_effect=['a' * 40, 'a' * 40, 'v1.2.3']) as git, \
                patch.object(doctor.shutil, 'which', return_value=None):
            estado, detalhe = self.d.versao()
        self.assertEqual(estado, 'nao_verificavel')
        self.assertIn('ssh-keygen ausente', detalhe)
        self.assertFalse(any('--format=%G?' in c.args for c in git.call_args_list))

    def test_versao_recusa_pasta_temporaria_ausente_ou_insegura(self):
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').touch()

        def conferir(motivo):
            antes = retrato(self.home)
            with patch.object(self.d, 'git', side_effect=['a' * 40, 'a' * 40, 'v1.2.3']) as git, \
                    patch.object(doctor.shutil, 'which', return_value='/ssh-keygen'):
                estado, detalhe = self.d.versao()
            self.assertEqual(estado, 'nao_verificavel')
            self.assertIn(motivo, detalhe)
            self.assertFalse(any('--format=%G?' in c.args for c in git.call_args_list))
            self.assertEqual(antes, retrato(self.home))

        conferir('ausente')
        self.d.estado.parent.mkdir(parents=True)
        self.d.estado.write_text('manter')
        conferir('insegura')
        self.d.estado.unlink()
        self.d.estado.mkdir(mode=0o700)
        for modo in (0o777, 0o720, 0o702):
            self.d.estado.chmod(modo)
            conferir('insegura')
        for modo in (0o500, 0o600):
            self.d.estado.chmod(modo)
            conferir('sem acesso')
        self.d.estado.chmod(0o700)
        self.d.estado.parent.chmod(0o777)
        conferir('ancestral inseguro')
        self.d.estado.parent.chmod(0o755)
        with patch('os.getuid', return_value=os.getuid() + 1):
            conferir('insegura')
        with patch.object(doctor.os, 'access', return_value=False):
            conferir('sem acesso')
        self.d.estado.rmdir()
        self.d.estado.symlink_to(self.home, target_is_directory=True)
        conferir('link simbólico')

    def test_falha_no_temporario_nao_acusa_assinatura_invalida(self):
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').touch()
        self.d.estado.mkdir(parents=True, mode=0o700)
        original = doctor.executar
        for codigo in (0, 128):
            for erro in ('error: could not create temporary file: SEGREDO_SENTINELA',
                         'error: failed writing detached signature to SEGREDO_SENTINELA',
                         'fatal: SEGREDO_SENTINELA'):
                if codigo == 0 and erro.startswith('fatal:'):
                    continue
                with self.subTest(codigo=codigo, erro=erro):
                    respostas = iter(['a' * 40, 'a' * 40, 'v1.2.3', ''])

                    def executar(args, **kwargs):
                        if '--format=%G?' in args:
                            programa = 'import sys; sys.stdout.write("N\\n"); sys.stderr.write(sys.argv[1]); sys.exit(int(sys.argv[2]))'
                            return original([sys.executable, '-c', programa, erro, str(codigo)], **kwargs)
                        return next(respostas)

                    with patch.object(doctor, 'executar', side_effect=executar), \
                            patch.object(doctor.shutil, 'which', return_value='/ssh-keygen'):
                        estado, detalhe = self.d.versao()
                    self.assertEqual(estado, 'nao_verificavel')
                    self.assertNotIn('SEGREDO_SENTINELA', detalhe)
                    self.assertNotIn('error:', detalhe)
                    self.assertNotIn('sem assinatura válida', detalhe)
                    if erro.startswith('error:'):
                        self.assertIn('cópia temporária na pasta de estado', detalhe)

    def test_assinaturas_mistas_indeterminadas_e_saida_invalida(self):
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').touch()
        self.d.estado.mkdir(parents=True, mode=0o700)
        resultados = [('G\nG\n', 'aviso'), ('N\nG\n', 'aviso'), ('G\nN\n', 'aviso'),
                      ('G\nU\n', 'aviso'), ('B\nX\n', 'aviso'), ('Y\nR\n', 'aviso'),
                      ('G\nE\n', 'nao_verificavel'), ('E\nN\n', 'nao_verificavel'),
                      ('N\nE\n', 'nao_verificavel'), ('', 'nao_verificavel'),
                      ('G\n', 'nao_verificavel'), ('G\nG\nG\n', 'nao_verificavel'),
                      ('G\n?\n', 'nao_verificavel'), ('G\nG', 'nao_verificavel'),
                      ('G\nG\nSEGREDO_SENTINELA', 'nao_verificavel'),
                      ('G\nN\n\n', 'nao_verificavel'), ('G\n N\n', 'nao_verificavel'),
                      ('G\r\nN\r\n', 'nao_verificavel')]
        for saida, esperado in resultados:
            sha_a, sha_b, sha_c = 'a' * 40, 'b' * 40, 'c' * 40
            with patch.object(doctor, 'executar', side_effect=[sha_a, sha_b, 'v1.2.3', sha_b + '\n' + sha_c, (saida, b''), '']) as executar, \
                    patch.object(doctor.shutil, 'which', return_value='/ssh-keygen'):
                estado, detalhe = self.d.versao()
            self.assertEqual(estado, esperado, repr(saida))
            if esperado == 'aviso':
                recusados = sum(s != 'G' for s in saida.splitlines())
                if recusados:
                    self.assertIn(str(recusados) + ' commits sem assinatura válida', detalhe)
                else:
                    self.assertIn('2 commits pendentes', detalhe)
            self.assertNotIn('SEGREDO_SENTINELA', detalhe)
            consulta = next(c for c in executar.call_args_list if '--format=%G?' in c.args[0])
            self.assertEqual(consulta.kwargs['ambiente']['TMPDIR'], str(self.d.estado))
            self.assertIn('gpg.ssh.program=/ssh-keygen', consulta.args[0])

    def test_erro_de_ancestralidade_nao_afirma_divergencia(self):
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').touch()
        self.d.estado.mkdir(parents=True, mode=0o700)
        for codigo, esperado in ((1, 'aviso'), (128, 'nao_verificavel')):
            sha_a, sha_b = 'a' * 40, 'b' * 40
            with patch.object(self.d, 'git', side_effect=[sha_a, sha_b, 'v1.2.3', sha_b, ('G\n', b''), doctor.ConsultaRecusada(b'SEGREDO_SENTINELA', codigo)]), \
                    patch.object(doctor.shutil, 'which', return_value='/ssh-keygen'):
                estado, detalhe = self.d.versao()
            self.assertEqual(estado, esperado)
            self.assertNotIn('SEGREDO_SENTINELA', detalhe)
            if codigo != 1:
                self.assertNotIn('diverge', detalhe)

    def test_lista_invalida_nao_omite_referencia_assinada(self):
        self.d.config.mkdir(parents=True)
        (self.d.config / 'allowed_signers').touch()
        self.d.estado.mkdir(parents=True, mode=0o700)
        sha_a, sha_b, sha_c = 'a' * 40, 'b' * 40, 'c' * 40
        for lista in (sha_c, sha_b + '\n' + sha_b, sha_b + '\n' + sha_a, 'SEGREDO_SENTINELA'):
            with patch.object(self.d, 'git', side_effect=[sha_a, sha_b, 'v1.2.3', lista]) as git, \
                    patch.object(doctor.shutil, 'which', return_value='/ssh-keygen'):
                estado, detalhe = self.d.versao()
            self.assertEqual(estado, 'nao_verificavel')
            self.assertNotIn('SEGREDO_SENTINELA', detalhe)
            self.assertFalse(any('--format=%G?' in c.args for c in git.call_args_list))

    def test_processo_prazo_real_e_dados_invalidos_continuam(self):
        inicio = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            doctor.executar([sys.executable, '-c', 'import time; time.sleep(10)'], prazo=.05)
        self.assertLess(time.monotonic() - inicio, 2)
        self.cota()
        gravar(self.d.codex / 'auth.json', {'tokens': {'access_token': 'x.!.x', 'id_token': 'SEGREDO_SENTINELA'}})
        gravar(self.home / '.claude/settings.json', [])
        gravar(self.d.cache / 'agy-usage.json', {'command': {'data': {'groups': [None]}}})
        with patch.object(doctor.shutil, 'which', return_value='/programa'), patch.object(doctor, 'executar', return_value=''):
            dados = self.d.relatorio()
        for ident in ('cota.agy', 'autenticacao.codex', 'hooks.claude'):
            self.assertEqual(self.item(dados, ident)['estado'], 'nao_verificavel')
        self.assertIn('pastas.migracoes', [i['id'] for i in dados['verificacoes']])
        self.assertNotIn('SEGREDO_SENTINELA', json.dumps(dados))


if __name__ == '__main__':
    unittest.main()
