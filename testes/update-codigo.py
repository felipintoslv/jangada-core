#!/usr/bin/env python3
"""Guardas do jangada-update em clones descartáveis, sem comandos reais do sistema."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class Atualizacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='update-codigo-')
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.origem = self.raiz / 'origem'
        self.instalado = self.raiz / 'instalado'
        self.bin = self.raiz / 'bin'
        self.bin.mkdir()
        (self.raiz / 'temporario').mkdir()
        self.registro = self.raiz / 'sistema-chamado'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('JANGADA_')}
        self.env.update(XDG_CONFIG_HOME=str(self.raiz / 'config'),
                        XDG_STATE_HOME=str(self.raiz / 'estado'),
                        JANGADA_CORE_PATH=str(self.instalado),
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='teste', GIT_AUTHOR_EMAIL='teste@localhost',
                        GIT_COMMITTER_NAME='teste', GIT_COMMITTER_EMAIL='teste@localhost',
                        PATH=str(self.bin) + ':/usr/bin:/bin')
        self.origem.mkdir()
        (self.origem / 'bin').mkdir()
        for nome in ('jangada-config', 'jangada-update', 'jangada-versao'):
            shutil.copy2(REPO / 'bin' / nome, self.origem / 'bin' / nome)
        self.migrou = self.raiz / 'migrou'
        self.falso(self.origem / 'bin' / 'jangada-migrar', f'#!/bin/sh\ntouch "{self.migrou}"\n')
        # O sistema só entra pelo jangada-sistema-update, ausente do PATH aqui.
        for nome in ('sudo', 'pacman', 'checkupdates', 'paru', 'yay'):
            self.falso(self.bin / nome, self.proibido())
        self.falso(self.bin / 'tmux', '#!/bin/sh\nprintf "%s" "${TESTE_SESSAO:-}"\n')
        self.falso(self.bin / 'ps', '#!/bin/sh\n[ -z "${TESTE_PS_REAL:-}" ] || exec /usr/bin/ps "$@"\n'
                   'printf "%s" "${TESTE_PROCESSO:-}"\n')
        for pasta in ('nucleo',):
            (self.origem / pasta).mkdir()
            self.falso(self.origem / pasta / 'servico.py', '#!/bin/sh\nsleep 30\n')
        self.falso(self.origem / 'bin' / 'jangada-servico', '#!/bin/sh\nsleep 30\n')
        self.git(self.origem, 'init', '-q', '-b', 'main')
        self.git(self.origem, 'add', '.')
        self.git(self.origem, 'commit', '-qm', 'base')
        self.git(self.raiz, 'clone', '-q', str(self.origem), str(self.instalado))
        self.antes = self.git(self.instalado, 'rev-parse', 'HEAD')
        (self.origem / 'novidade.txt').write_text('código novo\n')
        self.git(self.origem, 'add', '.')
        self.git(self.origem, 'commit', '-qm', 'novidade')
        self.novo = self.git(self.origem, 'rev-parse', 'HEAD')

    def falso(self, caminho, texto):
        caminho.write_text(texto)
        caminho.chmod(0o700)

    def proibido(self):
        return f'#!/bin/sh\ntouch "{self.registro}"\nexit 99\n'

    def git(self, pasta, *args):
        return subprocess.check_output(['git', '-C', str(pasta), *args],
                                       env=self.env, stderr=subprocess.PIPE, text=True).strip()

    def atualizar(self, resposta='s\n', marcador=False, programa=None):
        if shutil.which('bwrap') is None:
            self.skipTest('Bubblewrap ausente: conferência do controlador bloqueada')
        comando = ['bwrap', '--die-with-parent', '--unshare-net', '--unshare-pid',
                   '--ro-bind', '/', '/', '--bind', str(self.raiz / 'temporario'), '/tmp',
                   '--bind', str(self.raiz), str(self.raiz), '--proc', '/proc', '--dev', '/dev']
        if marcador:
            comando += ['--ro-bind', '/dev/null', '/tmp/.jangada-sem-autoridade']
        comando += ['--', *(programa or [str(REPO / 'bin/jangada-update'), '--so-core'])]
        return subprocess.run(comando, input=resposta, env=self.env,
                              capture_output=True, text=True, timeout=20)

    def atualizar_instalada(self, comando=None):
        """Roda o jangada-update da instalação falsa com o ps real do isolamento.

        Os caminhos ficam no arquivo do lançador, não na linha de comando do
        bwrap, que também aparece no ps.
        """
        self.env['TESTE_PS_REAL'] = '1'
        lancador = self.raiz / 'lancador'
        fundo = f'{comando} &\n' if comando else ''
        lancador.write_text(f'{fundo}exec "{self.instalado}/bin/jangada-update" --so-core\n')
        return self.atualizar(programa=['sh', str(lancador)])

    def conferir_recusa(self, resultado):
        self.assertNotEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.git(self.instalado, 'rev-parse', 'HEAD'), self.antes)
        self.assertFalse(self.registro.exists())
        self.assertFalse(self.migrou.exists())

    def test_avanco_confirmado_roda_so_as_migracoes_do_core(self):
        resultado = self.atualizar()
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.git(self.instalado, 'rev-parse', 'HEAD'), self.novo)
        self.assertFalse(self.registro.exists())
        self.assertTrue(self.migrou.exists())

    def test_recusa_sem_confirmacao(self):
        self.conferir_recusa(self.atualizar(''))

    def test_recusa_instalacao_suja(self):
        (self.instalado / 'pendente.txt').write_text('trabalho preservado\n')
        self.conferir_recusa(self.atualizar())
        self.assertEqual((self.instalado / 'pendente.txt').read_text(), 'trabalho preservado\n')

    def test_recusa_sessao_ativa(self):
        self.env['TESTE_SESSAO'] = 'agente-em-andamento'
        self.conferir_recusa(self.atualizar())

    def test_sessao_ativa_pula_o_codigo_e_segue_para_o_sistema(self):
        self.env['TESTE_SESSAO'] = 'agente-em-andamento'
        sistema = self.raiz / 'sistema-ok'
        self.falso(self.bin / 'jangada-sistema-update', f'#!/bin/sh\ntouch "{sistema}"\n')
        resultado = self.atualizar(programa=[str(REPO / 'bin/jangada-update')])
        self.assertNotEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn('há sessões de agentes abertas', resultado.stderr)
        self.assertEqual(self.git(self.instalado, 'rev-parse', 'HEAD'), self.antes)
        self.assertFalse(self.migrou.exists())
        self.assertTrue(sistema.exists())

    def test_recusa_processo_da_instalacao(self):
        self.env['TESTE_PROCESSO'] = f'99 python3 {self.instalado}/nucleo/servico.py\n'
        self.conferir_recusa(self.atualizar())

    def test_recusa_comando_da_instalacao_em_execucao(self):
        resultado = self.atualizar_instalada(f'sh "{self.instalado}/bin/jangada-servico"')
        self.conferir_recusa(resultado)
        self.assertIn('há processos usando a instalação', resultado.stderr)

    def test_conferencia_de_processos_ignora_a_propria_atualizacao(self):
        resultado = self.atualizar_instalada()
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.git(self.instalado, 'rev-parse', 'HEAD'), self.novo)

    def test_recusa_isolamento_por_variavel(self):
        self.env['JANGADA_ISOLADO'] = '1'
        self.conferir_recusa(self.atualizar())

    def test_recusa_marca_sem_variavel(self):
        self.conferir_recusa(self.atualizar(marcador=True))

    def test_recusa_simulacao_sem_mudar_referencias(self):
        self.env['JANGADA_SIMULAR'] = '1'
        self.conferir_recusa(self.atualizar())
        self.assertEqual(self.git(self.instalado, 'rev-parse', 'origin/main'), self.antes)

    def test_recusa_commit_sem_assinatura(self):
        config = self.raiz / 'config/jangada'
        config.mkdir(parents=True)
        (config / 'allowed_signers').write_text('')
        self.conferir_recusa(self.atualizar())

    def test_avanco_assinado(self):
        chave = self.raiz / 'chave-teste'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(chave)], check=True)
        self.git(self.origem, '-c', 'gpg.format=ssh', '-c', 'user.signingkey=' + str(chave),
                 'commit', '--amend', '-q', '-S', '--no-edit')
        self.novo = self.git(self.origem, 'rev-parse', 'HEAD')
        config = self.raiz / 'config/jangada'
        config.mkdir(parents=True)
        (config / 'allowed_signers').write_text('teste@localhost namespaces="git" ' + chave.with_suffix('.pub').read_text())
        resultado = self.atualizar()
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.git(self.instalado, 'rev-parse', 'HEAD'), self.novo)
        self.assertFalse(self.registro.exists())


if __name__ == '__main__':
    unittest.main()
