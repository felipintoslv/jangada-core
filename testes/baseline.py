#!/usr/bin/env python3
"""Ensaios locais da baseline com repositórios e provedores sintéticos."""
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class Baseline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.projeto = self.raiz / 'projeto'
        self.projeto.mkdir()
        self.bin = self.raiz / 'bin'
        self.bin.mkdir()
        self.estado = self.raiz / 'estado/jangada'
        (self.estado / 'agentes').mkdir(parents=True)
        (self.estado / 'revisoes').mkdir()
        self.env = dict(os.environ, HOME=str(self.raiz / 'casa'),
                        XDG_STATE_HOME=str(self.raiz / 'estado'),
                        XDG_CONFIG_HOME=str(self.raiz / 'config'),
                        JANGADA_CORE_PATH=str(REPO), JANGADA_SESSAO='teste',
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='teste', GIT_AUTHOR_EMAIL='teste@localhost',
                        GIT_COMMITTER_NAME='teste', GIT_COMMITTER_EMAIL='teste@localhost')
        for chave in ('JANGADA_ISOLADO', 'JANGADA_VALIDAR_TESTANDO',
                      'JANGADA_VALIDAR_PULAR_LOCAL', 'JANGADA_VALIDAR_SEM_GITLEAKS',
                      'JANGADA_VALIDAR_EM_CURSO', 'JANGADA_VALIDAR_REVISOR'):
            self.env.pop(chave, None)
        self.git('init', '-q', '-b', 'main')
        (self.projeto / 'original.txt').write_text('original\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.git('checkout', '-qb', 'agente/teste')
        self.metadados('codex')
        # Provedores falsos não enviam conteúdo para fora da máquina.
        self.executavel('claude', '#!/bin/sh\ncat >/dev/null\nprintf "STATUS: APROVADO\\n"\n')
        self.executavel('gitleaks', '#!/bin/sh\nprintf "[]\\n"\n')
        self.env['PATH'] = str(self.bin) + ':' + os.environ['PATH']

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.projeto), *args],
                                       env=self.env, stderr=subprocess.PIPE, text=True).strip()

    def executavel(self, nome, texto):
        arquivo = self.bin / nome
        arquivo.write_text(texto)
        arquivo.chmod(0o700)

    def metadados(self, autor):
        dados = dict(base='main', agente=autor, revisor='claude', inicio=self.git('rev-parse', 'main'))
        for pasta in ('agentes', 'revisoes'):
            (self.estado / pasta / 'teste.json').write_text(json.dumps(dados))

    def mudar(self, nome='entrega.txt', texto='entrega\n'):
        (self.projeto / nome).write_text(texto)
        self.git('add', '.')
        self.git('commit', '-qm', 'entrega')

    def validar(self, *args):
        return subprocess.run([str(REPO / 'bin/jangada-validar'), '--revisor', 'claude',
                               *args, str(self.projeto)], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def sem_ferramenta(self, nomes):
        pasta = self.raiz / 'ferramentas'
        pasta.mkdir()
        for diretorio in os.get_exec_path(self.env):
            for arquivo in Path(diretorio).glob('*'):
                destino = pasta / arquivo.name
                if arquivo.name not in nomes and arquivo.is_file() and os.access(arquivo, os.X_OK) and not destino.exists():
                    destino.symlink_to(arquivo)
        self.env['PATH'] = str(pasta)

    def marca(self):
        return self.estado / 'revisoes/validacao-teste.aprovado'

    def test_entrega_identificada_e_verificacoes_executadas(self):
        self.mudar()
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        marca = json.loads(self.marca().read_text())
        self.assertTrue(marca['local_verified'] and marca['independent'])
        self.assertEqual(marca['candidate_sha'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(marca['candidate_tree'], self.git('rev-parse', 'HEAD^{tree}'))
        self.assertEqual(marca['base_sha'], self.git('rev-parse', 'main'))
        estados = (self.estado / 'revisoes/validacao-teste-r1.verificacoes.tsv').read_text()
        self.assertIn('conjunto\tPASSED', estados)
        self.assertIn('lintr\tNOT_APPLICABLE', estados)

    def test_verificacao_pulada_nao_aprova(self):
        self.mudar()
        resultado = self.validar('--pular-local')
        self.assertEqual(resultado.returncode, 3)
        self.assertFalse(self.marca().exists())
        self.assertIn('STATUS: REVISAR', resultado.stdout)

    def test_previa_nao_declara_aprovacao_incompleta(self):
        self.mudar()
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        meta = self.estado / 'revisoes/teste.json'
        dados = json.loads(meta.read_text())
        dados.update(raiz=str(self.projeto), ramo='agente/teste')
        meta.write_text(json.dumps(dados))
        marca = json.loads(self.marca().read_text())
        marca['local_verified'] = False
        self.marca().write_text(json.dumps(marca))
        previa = subprocess.run([str(REPO / 'bin/jangada-agentes'), '--previa', 'teste'],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(previa.returncode, 0, previa.stderr)
        self.assertIn('aprovação incompleta ou inválida', previa.stdout)
        self.assertNotIn('aprovação vale', previa.stdout)

    def test_autorrevisao_nao_aprova(self):
        self.metadados('claude')
        self.mudar()
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 3)
        self.assertFalse(self.marca().exists())

    def test_autoria_sem_metadados_protegidos_nao_aprova(self):
        self.mudar()
        (self.estado / 'revisoes/teste.json').unlink()
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 3)
        self.assertFalse(self.marca().exists())
        self.assertIn('independência comprovada', resultado.stdout)

    def test_ferramentas_ausentes_nao_aprovam(self):
        for nome, texto, ferramentas in (
                ('codigo.sh', '#!/bin/bash\necho teste\n', {'shellcheck'}),
                ('codigo.lua', 'print(1)\n', {'luac', 'luac5.4'}),
                ('codigo.R', 'x <- 1\n', {'Rscript'})):
            with self.subTest(nome=nome):
                self.mudar(nome, texto)
                self.sem_ferramenta(ferramentas)
                resultado = self.validar('--forcar')
                self.assertEqual(resultado.returncode, 3, resultado.stderr)
                self.assertIn('UNAVAILABLE', resultado.stdout)
                self.assertFalse(self.marca().exists())
                shutil.rmtree(self.raiz / 'ferramentas')
                self.env['PATH'] = str(self.bin) + ':' + os.environ['PATH']

    def test_marca_com_arvore_invalida_nao_encurta_revisao(self):
        self.mudar()
        cabeca = self.git('rev-parse', 'HEAD')
        self.marca().write_text(json.dumps(dict(cabeca=cabeca, candidate_sha=cabeca,
            candidate_tree='0' * 40, base_sha=self.git('rev-parse', 'main'),
            limpo=True, num=0, local_verified=True, independent=True)))
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertNotEqual(json.loads(self.marca().read_text())['candidate_tree'], '0' * 40)

    def test_rollback_antigo_perde_edicao_concorrente(self):
        # O reset só é executado neste repositório sintético descartável.
        ponta = self.git('rev-parse', 'main')
        self.mudar()
        self.git('checkout', 'main')
        self.git('merge', '--no-ff', '-m', 'merge sintético', 'agente/teste')
        (self.projeto / 'original.txt').write_text('edição concorrente\n')
        self.git('reset', '--hard', ponta)
        self.assertEqual((self.projeto / 'original.txt').read_text(), 'original\n')

    def test_bloqueio_preserva_conflito_e_publicacao_anterior(self):
        self.git('checkout', 'main')
        worktree = self.raiz / 'casa/.local/share/jangada-worktrees/projeto/bloqueada'
        self.git('worktree', 'add', '-qb', 'agente/bloqueada', str(worktree), 'main')
        (worktree / 'original.txt').write_text('candidato\n')
        subprocess.run(['git', '-C', str(worktree), 'commit', '-qam', 'candidato'],
                       env=self.env, check=True, capture_output=True)
        (self.projeto / 'original.txt').write_text('base concorrente\n')
        self.git('commit', '-qam', 'base concorrente')
        conflito = subprocess.run(['git', '-C', str(self.projeto), 'merge', '--no-ff',
                                   'agente/bloqueada'], env=self.env, capture_output=True)
        self.assertNotEqual(conflito.returncode, 0)
        arquivo_estado = self.estado / 'agentes/bloqueada.json'
        arquivo_estado.write_text(json.dumps(dict(raiz=str(self.projeto), worktree=str(worktree),
                                                  ramo='agente/bloqueada', base='main')))
        comando = [str(REPO / 'bin/jangada-agente-fim'), '--integrar', 'bloqueada']
        antes = (self.projeto / 'original.txt').read_bytes()
        ponta = self.git('rev-parse', 'HEAD')
        for _ in range(2):
            resultado = subprocess.run(comando, env=self.env, input='s\n',
                                       text=True, capture_output=True, timeout=15)
            self.assertNotEqual(resultado.returncode, 0)
            self.assertIn('integração automática bloqueada', resultado.stderr)
            self.assertEqual(self.git('rev-parse', 'HEAD'), ponta)
            self.assertEqual((self.projeto / 'original.txt').read_bytes(), antes)
            self.assertTrue((self.projeto / '.git/MERGE_HEAD').exists())
            self.assertTrue(arquivo_estado.exists() and worktree.exists())
        # Simula uma publicação manual anterior. Repetir o comando não limpa
        # uma sessão cuja situação operacional ainda precisa ser conferida.
        (self.projeto / 'original.txt').write_text('resolução manual\n')
        self.git('add', 'original.txt')
        self.git('commit', '-qm', 'resolução sintética')
        ponta = self.git('rev-parse', 'HEAD')
        resultado = subprocess.run(comando, env=self.env, input='s\n',
                                   text=True, capture_output=True, timeout=15)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(self.git('rev-parse', 'HEAD'), ponta)
        self.assertTrue(arquivo_estado.exists() and worktree.exists())

    def test_backup_e_recuperacao_sinteticos(self):
        # A API backup inclui transações confirmadas ainda presentes no WAL.
        banco = self.raiz / 'tarefas.sqlite'
        with sqlite3.connect(banco) as origem:
            origem.execute('PRAGMA journal_mode=WAL')
            origem.execute('CREATE TABLE tarefas (id TEXT, estado TEXT)')
            origem.execute("INSERT INTO tarefas VALUES ('sintetica', 'Em revisão')")
            origem.commit()
            copia = self.raiz / 'backup.sqlite'
            with sqlite3.connect(copia) as destino:
                origem.backup(destino)
        recuperado = self.raiz / 'restaurado/tarefas.sqlite'
        recuperado.parent.mkdir()
        shutil.copy2(copia, recuperado)
        with sqlite3.connect(recuperado) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT * FROM tarefas').fetchall(), [('sintetica', 'Em revisão')])
        self.assertTrue(banco.exists())

    def test_copia_completa_preserva_arquivos_e_metadados(self):
        self.mudar()
        (self.projeto / 'original.txt').write_text('alteração sem commit\n')
        (self.projeto / 'novo.txt').write_text('arquivo novo\n')
        (self.projeto / '.gitignore').write_text('ignorado.txt\n')
        (self.projeto / 'ignorado.txt').write_text('dado local\n')
        (self.estado / 'agentes/teste.json').write_text('{"estado":"interrompido"}\n')
        (self.estado / 'historico.jsonl').write_text('{"evento":"sintetico"}\n')
        copia = self.raiz / 'backup-completo'
        copia.mkdir(mode=0o700)
        for nome, fonte in (('projeto', self.projeto), ('estado', self.estado)):
            subprocess.run(['cp', '-a', str(fonte), str(copia / nome)], check=True)
        restaurado = self.raiz / 'restaurado-completo'
        subprocess.run(['cp', '-a', str(copia), str(restaurado)], check=True)
        for fonte in (self.projeto, self.estado):
            nome = 'projeto' if fonte == self.projeto else 'estado'
            for arquivo in fonte.rglob('*'):
                if arquivo.is_file():
                    self.assertEqual(arquivo.read_bytes(),
                                     (restaurado / nome / arquivo.relative_to(fonte)).read_bytes())
        resultado = subprocess.run(['git', '-C', str(restaurado / 'projeto'), 'fsck', '--full'],
                                   env=self.env, capture_output=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual((self.projeto / 'original.txt').read_text(), 'alteração sem commit\n')

    def test_trava_liberada_apos_interrupcao(self):
        trava = self.raiz / 'trava'
        trava.mkdir()
        comando = ['bash', '-c',
                   'source "$1/bin/jangada-config"; '
                   'segurar() { echo pronta; sleep 30; }; '
                   'jangada_com_trava_dir "$2" segurar', '_', str(REPO), str(trava)]
        processo = subprocess.Popen(comando, env=self.env, stdout=subprocess.PIPE,
                                    text=True, start_new_session=True)
        try:
            self.assertEqual(processo.stdout.readline().strip(), 'pronta')
        finally:
            os.killpg(processo.pid, signal.SIGTERM)
            processo.wait(timeout=5)
            processo.stdout.close()
        resultado = subprocess.run(['bash', '-c', 'source "$1/bin/jangada-config"; '
                                    'jangada_com_trava_dir "$2" true', '_', str(REPO), str(trava)],
                                   env=self.env, capture_output=True, timeout=10)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
