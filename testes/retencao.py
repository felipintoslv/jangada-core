"""Testa jangada-agentes --limpar-antigos com estado fabricado em pasta temporária.

O estado real nunca é lido nem alterado. A remoção roda pelo módulo
nucleo/retencao.py no próprio processo, para valer também dentro do
isolamento; o caminho completo do comando, com terminal e confirmação
digitada, exige o controlador de fora e vira pulado ali.
"""

import ambiente
import contextlib
import fcntl
import hashlib
import io
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import isolamento

RAIZ = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(RAIZ / 'nucleo'))
import retencao  # noqa: E402

BASE = RAIZ / 'testes/contratos/agentes-77038af.txt'
DIA = 86400


def retrato(pasta):
    """Cada entrada, sem seguir link: tipo, conteúdo ou destino."""
    itens = []
    for caminho in sorted(Path(pasta).rglob('*')):
        relativo = str(caminho.relative_to(pasta))
        if caminho.is_symlink():
            itens.append((relativo, 'link', os.readlink(caminho)))
        elif caminho.is_dir():
            itens.append((relativo, 'pasta', ''))
        else:
            itens.append((relativo, 'arquivo', hashlib.sha256(caminho.read_bytes()).hexdigest()))
    return itens


def dados(pasta):
    """O retrato sem o registro da limpeza e sem as travas, que ficam depois dela."""
    return [item for item in retrato(pasta)
            if item[0] != 'limpezas.jsonl' and not item[0].startswith(('revisoes/travas', 'provedores/.travas'))]


def iso(quando):
    return quando.isoformat(timespec='seconds')


# Com vivas.falha, responde como o tmux 3.x quando o socket não pode ser lido.
FALSO_TMUX = ('[ ! -e "$0.falha" ] || { echo "error connecting to /tmp/s (Permission denied)" >&2; exit 1; }; '
              '[ ! -e "$0" ] || cat "$0"')


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.estado = self.tmp / 'state/jangada'
        self.estado.mkdir(parents=True)
        self.fora = self.tmp / 'fora'
        (self.fora / 'pasta').mkdir(parents=True)
        (self.fora / 'alvo.txt').write_text('fora do estado\n')
        (self.fora / 'pasta/dentro.txt').write_text('fora do estado\n')
        self.vivas = self.tmp / 'vivas'
        self.agora = datetime.now().astimezone()
        bin_falso = self.tmp / 'bin'
        bin_falso.mkdir()
        tmux = bin_falso / 'tmux'
        tmux.write_text('#!/bin/sh\nfor a; do [ "$a" = list-sessions ] && { cat "$FALSO_VIVAS" 2>/dev/null; '
                        'exit 0; }; done\nexit 1\n')
        tmux.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith('JANGADA_') and k not in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME')}
        self.env.update(HOME=str(self.tmp / 'casa'), XDG_STATE_HOME=str(self.tmp / 'state'),
                        XDG_CONFIG_HOME=str(self.tmp / 'config'), JANGADA_CORE_PATH=str(RAIZ),
                        FALSO_VIVAS=str(self.vivas), PATH=f'{bin_falso}:{os.environ["PATH"]}')

    def tearDown(self):
        self._tmp.cleanup()

    def gravar(self, relativo, texto='dados\n'):
        caminho = self.estado / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto)
        return caminho

    def arquivar(self, sessao, **campos):
        documento = dict(dict(versao=1, sessao=sessao, pendencias=[]), **campos)
        bruto = json.dumps(documento).encode()
        self.gravar(f'revisoes/arquivo/{hashlib.sha256(bruto).hexdigest()}.json', bruto.decode())

    def consumir(self, sessao, dias):
        with open(self.estado / 'consumo-tarefas.jsonl', 'a') as arquivo:
            arquivo.write(json.dumps(dict(sessao=sessao, inicio=iso(self.agora - timedelta(days=dias + 1)),
                                          fim=iso(self.agora - timedelta(days=dias)))) + '\n')

    def dados(self, sessao):
        """Os dados que o encerramento deixa em cada área."""
        for relativo in (f'codex/{sessao}/sessions/a.jsonl', f'codex/revisao-codex-{sessao}/b.jsonl',
                         f'provedores/claude/{sessao}/projetos/c.jsonl', f'revisoes/inicios/{sessao}/d.json',
                         f'agentes/validacao-{sessao}-r1.md.log', f'agentes/validacao-{sessao}-r2.contexto.json',
                         f'agentes/fim-{sessao}.log', f'revisoes/validacao-{sessao}-r1.md.tmp'):
            self.gravar(relativo)

    def encerrada(self, sessao, dias=40, arquivo=True, consumo=True):
        self.dados(sessao)
        if arquivo:
            self.arquivar(sessao)
        if consumo:
            self.consumir(sessao, dias)

    def envelhecer(self, dias=60):
        marca = time.time() - dias * DIA
        for caminho in [*self.estado.rglob('*'), self.estado]:
            os.utime(caminho, (marca, marca), follow_symlinks=False)

    def abrir(self, dias=30, provedores=('claude',)):
        estado = retencao.Estado(str(self.estado), list(provedores), dias,
                                 ['sh', '-c', FALSO_TMUX, str(self.vivas)])
        self.addCleanup(estado.fechar)
        return estado

    def aplicar(self, dias=30, provedores=('claude',), antes=None):
        estado = self.abrir(dias, provedores)
        unidades = retencao.medir_todas(estado)
        grupos = retencao.agrupar(unidades)
        if antes:
            antes()
        if not grupos:
            return unidades, ''
        registro = retencao.abrir_registro(estado)
        erro = io.StringIO()
        try:
            retencao.aplicar(estado, grupos, registro, erro)
        finally:
            os.close(registro)
        return unidades, erro.getvalue()

    def existe(self, relativo):
        return os.path.lexists(self.estado / relativo)

    def comando(self, *argumentos, entrada=subprocess.DEVNULL, **env):
        return subprocess.run(['bash', str(RAIZ / 'bin/jangada-agentes'), *argumentos], stdin=entrada,
                              capture_output=True, text=True, env=dict(self.env, **env), timeout=60)

    def registros(self):
        caminho = self.estado / 'limpezas.jsonl'
        if not caminho.exists():
            return []
        return [json.loads(linha) for linha in caminho.read_text().splitlines()]


class Listagem(Base):
    def test_lista_sem_alterar_nada(self):
        self.encerrada('antiga')
        self.encerrada('recente', dias=10)
        self.dados('sem-prova')
        self.envelhecer()
        antes = retrato(self.tmp)
        p = self.comando('--limpar-antigos')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(retrato(self.tmp), antes)
        self.assertIn('SESSÃO', p.stdout)
        self.assertIn('ENCERRADA EM', p.stdout)
        self.assertIn('antiga', p.stdout)
        self.assertIn((self.agora - timedelta(days=40)).strftime('%d/%m/%Y'), p.stdout)
        self.assertIn('Total: 7 itens de 1 sessão', p.stdout)
        self.assertIn('sem prova de encerramento: 8 itens', p.stdout)
        self.assertIn('encerrada há menos de 30 dias: 8 itens', p.stdout)
        self.assertIn('Nada foi apagado.', p.stdout)
        self.assertNotIn('recente  ', p.stdout.split('Mantidos')[0])

    def test_dias_muda_o_prazo(self):
        self.encerrada('recente', dias=10)
        self.envelhecer()
        p = self.comando('--limpar-antigos', '--dias', '5')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('recente', p.stdout.split('Mantidos')[0])
        self.assertIn('--limpar-antigos --dias 5 --aplicar', p.stdout)

    def test_um_dia_no_singular(self):
        p = self.comando('--limpar-antigos', '--dias', '1')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('encerrada há mais de 1 dia com prova', p.stdout)
        self.encerrada('antiga')
        self.encerrada('recente', dias=0)
        self.envelhecer()
        p = self.comando('--limpar-antigos', '--dias', '1')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('encerradas há mais de 1 dia, com prova', p.stdout)
        self.assertIn('encerrada há menos de 1 dia: 8 itens', p.stdout)
        self.assertNotIn(' 1 dias', p.stdout)

    def test_argumentos_invalidos(self):
        for argumentos in (('--dias', '0'), ('--dias', 'x'), ('--dias',), ('--outra',), ('--dias', '36501')):
            p = self.comando('--limpar-antigos', *argumentos)
            self.assertEqual(p.returncode, 2, argumentos)
            self.assertIn('uso: jangada-agentes --limpar-antigos', p.stderr)

    def test_estado_ausente_nao_cria_nada(self):
        self.estado.rmdir()
        p = self.comando('--limpar-antigos')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.estado.exists())

    def test_simular_faz_aplicar_so_listar(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = retrato(self.tmp)
        p = self.comando('--limpar-antigos', '--aplicar', JANGADA_SIMULAR='1')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('JANGADA_SIMULAR=1', p.stdout)
        self.assertEqual(retrato(self.tmp), antes)


class Recusas(Base):
    def test_aplicar_recusa_no_isolamento(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = retrato(self.tmp)
        p = self.comando('--limpar-antigos', '--aplicar', JANGADA_ISOLADO='1')
        self.assertEqual(p.returncode, 1)
        self.assertIn('AUTORIZACAO_RECUSADA', p.stderr)
        self.assertEqual(retrato(self.tmp), antes)

    def test_marca_do_isolamento(self):
        montagens = self.tmp / 'mountinfo'
        montagens.write_text('22 1 0:21 / / rw - ext4 /dev/x rw\n')
        ambiente_antes = os.environ.pop('JANGADA_ISOLADO', None)
        try:
            self.assertFalse(retencao.isolado(str(montagens)))
            with open(montagens, 'a') as arquivo:
                arquivo.write(f'40 22 0:5 / {retencao.MARCA} ro - tmpfs tmpfs ro\n')
            self.assertTrue(retencao.isolado(str(montagens)))
            self.assertTrue(retencao.isolado(str(self.tmp / 'ausente')))
        finally:
            if ambiente_antes is not None:
                os.environ['JANGADA_ISOLADO'] = ambiente_antes

    def test_aplicar_recusa_sem_terminal(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = retrato(self.tmp)
        p = self.comando('--limpar-antigos', '--aplicar')
        self.assertEqual(retrato(self.tmp), antes)
        self.assertEqual(p.returncode, 1)
        self.assertIn('--aplicar exige terminal', p.stderr)

    def test_confirmacao_digitada_pelo_terminal(self):
        self.encerrada('antiga')
        self.encerrada('outra')
        self.envelhecer()
        arquivo = sorted((self.estado / 'revisoes/arquivo').iterdir())
        conteudo = [a.read_bytes() for a in arquivo]
        p, saida = self.no_terminal('nao\n')
        self.assertEqual(p.returncode, 0, saida)
        self.assertIn('digite apagar', saida)
        self.assertTrue(self.existe('codex/antiga'))
        self.assertFalse(self.existe('limpezas.jsonl'))
        p, saida = self.no_terminal('apagar\n')
        self.assertEqual(p.returncode, 0, saida)
        self.assertFalse(self.existe('codex/antiga'))
        self.assertFalse(self.existe('codex/outra'))
        self.assertEqual([a.read_bytes() for a in arquivo], conteudo)
        self.assertEqual(len(self.registros()), 14)

    def no_terminal(self, resposta):
        """Roda o comando com stdin num pseudoterminal e devolve (processo, saída)."""
        mestre, escravo = pty.openpty()
        try:
            processo = subprocess.Popen(['bash', str(RAIZ / 'bin/jangada-agentes'), '--limpar-antigos', '--aplicar'],
                                        stdin=escravo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, env=self.env)
            os.close(escravo)
            escravo = None
            os.write(mestre, resposta.encode())
            saida, erro = processo.communicate(timeout=60)
            while select.select([mestre], [], [], 0)[0]:
                try:
                    os.read(mestre, 4096)
                except OSError:
                    break
        finally:
            os.close(mestre)
            if escravo is not None:
                os.close(escravo)
        return processo, saida + erro


class Remocao(Base):
    def test_encerrada_antiga_sai_e_arquivo_fica(self):
        self.encerrada('antiga')
        self.envelhecer()
        arquivo = retrato(self.estado / 'revisoes/arquivo')
        consumo = (self.estado / 'consumo-tarefas.jsonl').read_bytes()
        _, erro = self.aplicar()
        self.assertEqual(erro, '')
        for relativo in ('codex/antiga', 'codex/revisao-codex-antiga', 'provedores/claude/antiga',
                         'revisoes/inicios/antiga', 'agentes/validacao-antiga-r1.md.log',
                         'agentes/validacao-antiga-r2.contexto.json', 'agentes/fim-antiga.log',
                         'revisoes/validacao-antiga-r1.md.tmp'):
            self.assertFalse(self.existe(relativo), relativo)
        self.assertEqual(retrato(self.estado / 'revisoes/arquivo'), arquivo)
        self.assertEqual((self.estado / 'consumo-tarefas.jsonl').read_bytes(), consumo)
        self.assertTrue(self.existe('codex') and self.existe('provedores/claude'))
        linhas = self.registros()
        self.assertEqual(len(linhas), 7)
        self.assertEqual({l['sessao'] for l in linhas}, {'antiga'})
        self.assertEqual({l['tipo'] for l in linhas},
                         {'codex', 'codex do revisor', 'provedor claude', 'inicios', 'rodadas em agentes',
                          'registro do fim', 'rodadas em revisoes'})
        rodadas = [l for l in linhas if l['tipo'] == 'rodadas em agentes'][0]
        self.assertEqual(sorted(rodadas['caminhos']),
                         ['agentes/validacao-antiga-r1.md.log', 'agentes/validacao-antiga-r2.contexto.json'])
        for linha in linhas:
            self.assertEqual(set(linha), {'sessao', 'tipo', 'caminhos', 'bytes', 'encerrada', 'quando', 'resultado'})
            self.assertEqual(linha['resultado'], 'removido')
            self.assertIsInstance(linha['bytes'], int)
            self.assertIsNotNone(retencao.data(linha['encerrada']))
            self.assertIsNotNone(retencao.data(linha['quando']))
        self.assertEqual(os.stat(self.estado / 'limpezas.jsonl').st_mode & 0o777, 0o600)

    def test_mantidas(self):
        for sessao in ('viva', 'aberta', 'em-revisao', 'alterada'):
            self.encerrada(sessao)
        self.encerrada('recente', dias=10)
        self.encerrada('sem-arquivo', arquivo=False)
        self.encerrada('sem-consumo', consumo=False)
        self.encerrada('com-pendencia', arquivo=False)
        self.arquivar('com-pendencia', pendencias=['x'])
        self.gravar('agentes/aberta.json', '{"estado":"concluido"}')
        self.gravar('revisoes/em-revisao.json', '{}')
        self.envelhecer()
        self.vivas.write_text('viva\n')
        self.gravar('provedores/claude/alterada/novo.jsonl')
        antes = dados(self.estado)
        unidades, _ = self.aplicar()
        self.assertEqual(dados(self.estado), antes)
        self.assertEqual(self.registros(), [])
        motivos = {(u['partes'], u['nome']): u['motivo'] for u in unidades}
        self.assertEqual(motivos[(('codex',), 'viva')], 'aberta')
        self.assertEqual(motivos[(('codex',), 'aberta')], 'aberta')
        self.assertEqual(motivos[(('codex',), 'em-revisao')], 'aberta')
        self.assertEqual(motivos[(('codex',), 'recente')], 'recente')
        self.assertEqual(motivos[(('codex',), 'sem-arquivo')], 'sem_prova')
        self.assertEqual(motivos[(('codex',), 'sem-consumo')], 'sem_prova')
        self.assertEqual(motivos[(('codex',), 'com-pendencia')], 'sem_prova')
        self.assertEqual(motivos[(('provedores', 'claude'), 'alterada')], 'alterada')
        self.assertEqual(motivos[(('codex',), 'alterada')], 'alterada')

    def test_registro_gravavel_pelo_agente_nao_prova(self):
        self.dados('forjada')
        self.gravar('validar.jsonl', json.dumps(dict(rotulo='forjada', resultado='APROVADO',
                                                      data=iso(self.agora - timedelta(days=90)))) + '\n')
        self.gravar('eventos-agentes.jsonl', json.dumps(dict(sessao='forjada', estado='concluido',
                                                              data=iso(self.agora - timedelta(days=90)))) + '\n')
        self.gravar('agentes/forjada-arquivo.json', json.dumps(dict(versao=1, sessao='forjada', pendencias=[])))
        # Arquivo com nome que não confere com o conteúdo não prova nada.
        self.gravar('revisoes/arquivo/' + '0' * 64 + '.json', json.dumps(dict(versao=1, sessao='forjada')))
        self.consumir('forjada', 90)
        self.envelhecer()
        antes = dados(self.estado)
        unidades, _ = self.aplicar()
        self.assertEqual(dados(self.estado), antes)
        self.assertTrue(all(u['motivo'] == 'sem_prova' for u in unidades if u.get('sessao') == 'forjada'))

    def test_prefixo_nao_leva_outra_sessao(self):
        self.encerrada('tarefa')
        self.encerrada('tarefa-2', dias=10)
        self.gravar('agentes/validacao-tarefa-2-r1.md')
        self.envelhecer()
        self.aplicar()
        self.assertFalse(self.existe('codex/tarefa'))
        self.assertFalse(self.existe('agentes/validacao-tarefa-r1.md.log'))
        for relativo in ('codex/tarefa-2', 'codex/revisao-codex-tarefa-2', 'provedores/claude/tarefa-2',
                         'revisoes/inicios/tarefa-2', 'agentes/validacao-tarefa-2-r1.md.log',
                         'agentes/validacao-tarefa-2-r1.md', 'agentes/fim-tarefa-2.log',
                         'revisoes/validacao-tarefa-2-r1.md.tmp'):
            self.assertTrue(self.existe(relativo), relativo)

    def test_dono_do_codex_do_revisor(self):
        # revisao-codex-X é de X; o nome inteiro sem rastro de sessão não pesa.
        self.encerrada('antiga')
        self.encerrada('revisao-codex-antiga', dias=10, arquivo=False)
        self.envelhecer()
        self.aplicar()
        self.assertTrue(self.existe('codex/revisao-codex-antiga'))

    def test_nomes_hostis_e_links(self):
        self.encerrada('antiga')
        self.encerrada('ligada')
        # No consumo, nome hostil recusa tudo (test_consumo_com_linha_invalida_nao_prova_nada).
        for nome in ('..', '.', 'a/b', 'a\nb', '../fora'):
            self.arquivar(nome)
        (self.estado / 'codex/a\nb').mkdir()
        os.symlink(self.fora / 'alvo.txt', self.estado / 'codex/antiga/saida')
        os.symlink(self.fora / 'pasta', self.estado / 'codex/antiga/pasta')
        os.symlink(self.fora, self.estado / 'provedores/claude/antiga/fora')
        (self.estado / 'agentes/fim-ligada.log').unlink()
        os.symlink(self.fora / 'pasta', self.estado / 'agentes/fim-ligada.log')
        os.symlink(self.fora / 'alvo.txt', self.estado / 'agentes/validacao-ligada-r3.md')
        shutil.rmtree(self.estado / 'codex/ligada')
        os.symlink(self.fora / 'pasta', self.estado / 'codex/ligada')
        self.envelhecer()
        fora = retrato(self.fora)
        unidades, _ = self.aplicar()
        self.assertEqual(retrato(self.fora), fora)
        self.assertFalse(self.existe('codex/antiga'))
        self.assertFalse(self.existe('provedores/claude/antiga'))
        self.assertTrue(self.existe('codex/a\nb'))
        self.assertTrue(self.existe('codex/ligada'))
        self.assertTrue(os.path.islink(self.estado / 'codex/ligada'))
        self.assertTrue(self.existe('agentes/fim-ligada.log'))
        self.assertTrue(self.existe('agentes/validacao-ligada-r3.md'))
        # Entrada de ligada que não se mede mantém os outros dados da sessão.
        self.assertTrue(self.existe('provedores/claude/ligada'))
        self.assertEqual({u['motivo'] for u in unidades if u.get('sessao') == 'ligada'}, {'incerta'})
        recusadas = {(u['partes'], u['nome']) for u in unidades if u['motivo'] == 'recusada'}
        self.assertIn((('codex',), 'a\nb'), recusadas)
        self.assertIn((('codex',), 'ligada'), recusadas)
        self.assertIn((('agentes',), 'fim-ligada.log'), recusadas)

    def test_area_ligada_fica_fora(self):
        self.encerrada('antiga')
        shutil.rmtree(self.estado / 'provedores/claude')
        (self.fora / 'antiga').mkdir()
        (self.fora / 'antiga/x').write_text('x')
        os.symlink(self.fora, self.estado / 'provedores/claude')
        self.envelhecer()
        fora = retrato(self.fora)
        estado = self.abrir()
        unidades = list(estado.unidades())
        self.assertTrue(any('provedores/claude/' in a for a in estado.avisos))
        self.assertFalse(any(u['partes'] == ('provedores', 'claude') for u in unidades))
        self.aplicar()
        self.assertEqual(retrato(self.fora), fora)

    def test_reconfere_antes_de_apagar(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = dados(self.estado)
        _, erro = self.aplicar(antes=lambda: self.vivas.write_text('antiga\n'))
        self.assertEqual(dados(self.estado), antes)
        self.assertIn('mantido na reconferência', erro)
        self.vivas.unlink()
        for arquivo in (self.estado / 'revisoes/arquivo').iterdir():
            _, erro = self.aplicar(antes=lambda: arquivo.write_text('{}'))
        self.assertIn('sem prova', erro)
        self.assertTrue(self.existe('codex/antiga'))

    def test_trava_ocupada_mantem(self):
        self.encerrada('antiga')
        self.envelhecer()
        travas = self.estado / 'revisoes/travas/antiga'
        travas.mkdir(parents=True)
        fd = os.open(travas, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        espera, retencao.ESPERA_TRAVA = retencao.ESPERA_TRAVA, 0.2
        try:
            _, erro = self.aplicar()
        finally:
            retencao.ESPERA_TRAVA = espera
            os.close(fd)
        self.assertIn('em uso', erro)
        self.assertTrue(self.existe('codex/antiga'))
        self.assertEqual(self.registros(), [])

    def test_consulta_ao_tmux_que_falha_nao_libera(self):
        def vivas(*comando):
            return retencao.Estado.sessoes_vivas(type('E', (), {'tmux': list(comando)})())
        sem_servidor = ('no server running on /tmp/tmux-1000/jangada',
                        'error connecting to /tmp/tmux-1000/jangada (No such file or directory)')
        for mensagem in sem_servidor:
            self.assertEqual(vivas('sh', '-c', f'echo "{mensagem}" >&2; exit 1'), set(), mensagem)
        for script in ('echo "error connecting to /tmp/s (Permission denied)" >&2; exit 1',
                       'echo "lost server" >&2; exit 1',
                       'echo "no server running on /tmp/s" >&2; exit 2',
                       'echo "no server running on /tmp/s" >&2; echo sobra >&2; exit 1',
                       'echo antiga; echo "no server running on /tmp/s" >&2; exit 1',
                       'exit 1'):
            with self.assertRaises(retencao.Recusa, msg=script):
                vivas('sh', '-c', script)
        for comando in ((), (str(self.tmp / 'sem-tmux'),)):
            with self.assertRaises(retencao.Recusa, msg=comando):
                vivas(*comando)

    @unittest.skipUnless(shutil.which('tmux'), 'tmux ausente')
    def test_tmux_real_sem_servidor_e_sem_permissao(self):
        socket = self.tmp / 's'
        self.assertEqual(retencao.Estado.sessoes_vivas(type('E', (), {'tmux': ['tmux', '-S', str(socket)]})()),
                         set())
        fechada = self.tmp / 'fechada'
        fechada.mkdir(mode=0o000)
        try:
            if os.access(fechada, os.R_OK | os.X_OK):
                self.skipTest('permissão não se aplica a este usuário')
            with self.assertRaises(retencao.Recusa):
                retencao.Estado.sessoes_vivas(type('E', (), {'tmux': ['tmux', '-S', str(fechada / 's')]})())
        finally:
            fechada.chmod(0o700)

    def test_tmux_que_falha_mantem_os_dados(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = dados(self.estado)
        Path(str(self.vivas) + '.falha').touch()
        with self.assertRaises(retencao.Recusa):
            self.abrir()
        falso = self.tmp / 'bin/tmux'
        falso.write_text('#!/bin/sh\necho "error connecting to /tmp/s (Permission denied)" >&2\nexit 1\n')
        p = self.comando('--limpar-antigos')
        self.assertEqual(p.returncode, 1)
        self.assertIn('não foi possível listar as sessões do tmux', p.stderr)
        self.assertEqual(dados(self.estado), antes)
        Path(str(self.vivas) + '.falha').unlink()
        _, erro = self.aplicar(antes=lambda: Path(str(self.vivas) + '.falha').touch())
        self.assertIn('não foi possível listar as sessões do tmux', erro)
        self.assertEqual(dados(self.estado), antes)
        self.assertEqual(self.registros(), [])

    def mudar_entre_remocoes(self, mudanca):
        """Muda o estado logo depois da primeira remoção das rodadas em agentes."""
        self.encerrada('antiga')
        self.envelhecer()
        original, feitas = retencao.apagar, []

        def apagar(estado, partes, nome):
            original(estado, partes, nome)
            feitas.append(nome)
            if nome == 'validacao-antiga-r1.md.log':
                mudanca()
        retencao.apagar = apagar
        try:
            _, erro = self.aplicar()
        finally:
            retencao.apagar = original
        self.assertFalse(self.existe('agentes/validacao-antiga-r1.md.log'))
        self.assertTrue(self.existe('agentes/validacao-antiga-r2.contexto.json'), erro)
        self.assertNotIn('validacao-antiga-r2.contexto.json', feitas)
        self.assertIn('agentes/validacao-antiga-r2.contexto.json mantido', erro)
        linhas = [r for r in self.registros() if r['tipo'] == 'rodadas em agentes']
        self.assertEqual([r['caminhos'] for r in linhas], [['agentes/validacao-antiga-r1.md.log']])
        return erro

    def test_sessao_reaberta_entre_duas_remocoes(self):
        erro = self.mudar_entre_remocoes(lambda: self.gravar('agentes/antiga.json', '{}'))
        self.assertIn('sessão viva ou aberta', erro)
        self.assertTrue(self.existe('revisoes/validacao-antiga-r1.md.tmp'))

    def test_sessao_viva_entre_duas_remocoes(self):
        self.assertIn('sessão viva ou aberta', self.mudar_entre_remocoes(lambda: self.vivas.write_text('antiga\n')))

    def test_alvo_alterado_entre_duas_remocoes(self):
        alvo = self.estado / 'agentes/validacao-antiga-r2.contexto.json'
        self.assertIn('alterada depois do encerramento', self.mudar_entre_remocoes(lambda: os.utime(alvo)))

    def test_tmux_falha_entre_duas_remocoes(self):
        erro = self.mudar_entre_remocoes(lambda: Path(str(self.vivas) + '.falha').touch())
        self.assertIn('não foi possível listar as sessões do tmux', erro)

    def aplicar_pelo_main(self, resposta='nao'):
        """O main com --aplicar, como se fosse fora do isolamento e num terminal."""
        saida, erro = io.StringIO(), io.StringIO()
        isolado, isatty, entrada = retencao.isolado, os.isatty, sys.stdin
        retencao.isolado, os.isatty, sys.stdin = (lambda *_: False), (lambda _: True), io.StringIO(resposta + '\n')
        try:
            with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
                codigo = retencao.main([str(self.estado), 'claude', '--aplicar', '--',
                                        'sh', '-c', FALSO_TMUX, str(self.vivas)])
        finally:
            retencao.isolado, os.isatty, sys.stdin = isolado, isatty, entrada
        return codigo, saida.getvalue(), erro.getvalue()

    def test_consumo_com_linha_invalida_nao_prova_nada(self):
        recente = json.dumps(dict(sessao='antiga', fim=iso(self.agora)))
        for linha in ('{"sessao":"\\u0061ntiga","fim":"2026-',
                      recente[:len(recente) // 2],
                      '[1]', '{"fim":"%s"}' % iso(self.agora), json.dumps(dict(sessao='../x', fim=iso(self.agora))),
                      json.dumps(dict(sessao='outra', fim='ontem')), '{"sessao":"outra","fim":"\udcff"}'):
            with self.subTest(linha=linha):
                shutil.rmtree(self.estado)
                self.estado.mkdir()
                self.encerrada('antiga')
                self.encerrada('terceira')
                with open(self.estado / 'consumo-tarefas.jsonl', 'ab') as arquivo:
                    arquivo.write(linha.encode('utf-8', 'surrogateescape') + b'\n\n')
                self.envelhecer()
                antes = dados(self.estado)
                estado = self.abrir()
                self.assertTrue(estado.impedimentos)
                self.assertTrue(any('consumo-tarefas.jsonl' in a for a in estado.avisos))
                unidades, _ = self.aplicar()
                self.assertEqual(dados(self.estado), antes)
                self.assertTrue(all(u['motivo'] == 'sem_prova' for u in unidades if 'sessao' in u))
                codigo, saida, erro = self.aplicar_pelo_main()
                self.assertEqual(codigo, 1, saida + erro)
                self.assertIn('nada foi apagado: consumo-tarefas.jsonl', erro)
                self.assertNotIn('digite apagar', saida)
                self.assertEqual(dados(self.estado), antes)

    def test_consumo_valido_com_linha_em_branco_prova(self):
        self.encerrada('antiga')
        with open(self.estado / 'consumo-tarefas.jsonl', 'a') as arquivo:
            arquivo.write('\n  \n')
        self.envelhecer()
        self.assertFalse(self.abrir().impedimentos)
        self.aplicar()
        self.assertFalse(self.existe('codex/antiga'))

    def test_alteracao_em_outra_area_depois_da_listagem(self):
        self.encerrada('antiga')
        self.envelhecer()
        alvo = self.estado / 'provedores/claude/antiga/projetos/c.jsonl'
        antes = dados(self.estado)
        _, erro = self.aplicar(antes=lambda: os.utime(alvo))
        self.assertEqual(sorted(i[0] for i in dados(self.estado)), sorted(i[0] for i in antes))
        self.assertIn('codex/antiga mantido na reconferência: alterada depois do encerramento', erro)
        self.assertEqual(self.registros(), [])

    def test_alteracao_em_outra_area_entre_duas_remocoes(self):
        alvo = self.estado / 'revisoes/validacao-antiga-r1.md.tmp'
        erro = self.mudar_entre_remocoes(lambda: os.utime(alvo))
        self.assertIn('alterada depois do encerramento', erro)
        self.assertTrue(self.existe('revisoes/validacao-antiga-r1.md.tmp'))

    def test_dado_que_nao_se_mede_mantem_a_sessao(self):
        self.encerrada('antiga')
        shutil.rmtree(self.estado / 'provedores/claude/antiga')
        os.symlink(self.fora, self.estado / 'provedores/claude/antiga')
        self.envelhecer()
        antes = dados(self.estado)
        unidades, _ = self.aplicar()
        self.assertEqual(dados(self.estado), antes)
        self.assertTrue(all(u['motivo'] in ('incerta', 'recusada') for u in unidades if 'antiga' in u.get('donos', ())))

    def test_provedor_fora_da_lista_e_conferido(self):
        self.encerrada('antiga')
        self.gravar('provedores/agy-velha/antiga/e.json')
        self.envelhecer()
        os.utime(self.estado / 'provedores/agy-velha/antiga/e.json')
        antes = dados(self.estado)
        unidades, _ = self.aplicar()
        self.assertEqual(dados(self.estado), antes)
        self.assertTrue(all(u['motivo'] == 'alterada' for u in unidades if u.get('sessao') == 'antiga'))
        self.envelhecer()
        unidades, _ = self.aplicar()
        self.assertFalse(self.existe('codex/antiga'))
        self.assertTrue(self.existe('provedores/agy-velha/antiga/e.json'))
        self.assertIn('fora_da_lista', {u['motivo'] for u in unidades})

    def test_registro_travado_nada_apaga(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = dados(self.estado)
        caminho = self.estado / 'limpezas.jsonl'
        caminho.touch(mode=0o600)
        fd = os.open(caminho, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        espera, retencao.ESPERA_TRAVA = retencao.ESPERA_TRAVA, 0.2
        try:
            _, erro = self.aplicar()
        finally:
            retencao.ESPERA_TRAVA = espera
            os.close(fd)
        self.assertIn('limpezas.jsonl em uso', erro)
        self.assertEqual(dados(self.estado), antes)
        self.assertEqual(caminho.read_text(), '')

    def test_arquivo_ilegivel_faz_dono_desconhecido_pesar(self):
        self.encerrada('antiga')
        self.gravar('revisoes/arquivo/' + '0' * 64 + '.json', '{}')
        self.envelhecer()
        self.aplicar()
        self.assertTrue(self.existe('codex/revisao-codex-antiga'))
        self.assertFalse(self.existe('codex/antiga'))

    def montado(self, relativos):
        """montagens() com as pastas do estado acrescentadas, como se viessem do mountinfo."""
        original = retencao.montagens
        retencao.montagens = lambda: original() + [str(self.estado / r) for r in relativos]
        pilha = contextlib.ExitStack()
        pilha.callback(setattr, retencao, 'montagens', original)
        return pilha

    def test_area_ou_pasta_acima_montada_impede_tudo(self):
        for montada, partes in (('codex', ('codex',)), ('provedores', ('provedores', 'claude')),
                                ('provedores/claude', ('provedores', 'claude')),
                                ('revisoes', ('revisoes', 'inicios')), ('agentes', ('agentes',))):
            with self.subTest(montada=montada):
                shutil.rmtree(self.estado)
                self.estado.mkdir()
                self.encerrada('antiga')
                self.envelhecer()
                antes = dados(self.estado)
                with self.montado([montada]):
                    estado = self.abrir()
                    unidades = list(estado.unidades())
                    self.assertTrue(any(i.startswith('/'.join(partes)) for i in estado.impedimentos),
                                    estado.impedimentos)
                    self.assertFalse(any(u['partes'] == partes for u in unidades))
                    codigo, _, erro = self.aplicar_pelo_main(resposta='apagar')
                    self.assertEqual(codigo, 1)
                    self.assertIn('nada foi apagado', erro)
                    _, erro = self.aplicar()
                    self.assertIn('mantido na reconferência', erro)
                    nome = os.listdir(self.estado.joinpath(*partes))[0]
                    with self.assertRaises(retencao.Recusa):
                        retencao.apagar(estado, partes, nome)
                self.assertEqual(dados(self.estado), antes)
                self.assertFalse(self.existe('limpezas.jsonl') and self.registros())

    def test_area_em_outro_dispositivo_impede_tudo(self):
        self.encerrada('antiga')
        self.envelhecer()
        antes = dados(self.estado)
        estado = self.abrir()
        original = os.stat

        def outro(caminho, *args, **kwargs):
            info = original(caminho, *args, **kwargs)
            if caminho == 'codex' and kwargs.get('dir_fd') == estado.fd:
                return os.stat_result((*info[:2], info.st_dev + 1, *info[3:10]))
            return info
        os.stat = outro
        try:
            list(estado.unidades())
            self.assertTrue(any(i.startswith('codex/') for i in estado.impedimentos), estado.impedimentos)
            with self.assertRaises(retencao.Recusa):
                retencao.apagar(estado, ('codex',), 'antiga')
        finally:
            os.stat = original
        self.assertEqual(dados(self.estado), antes)

    def test_montagem_entre_duas_remocoes(self):
        pilha = contextlib.ExitStack()
        try:
            self.mudar_entre_remocoes(lambda: pilha.enter_context(self.montado(['agentes'])))
        finally:
            pilha.close()

    def escrita_no_registro(self, falsa):
        """Troca os.write só para o descritor de limpezas.jsonl."""
        original = os.write

        def escrever(fd, dados):
            if os.readlink(f'/proc/self/fd/{fd}') == str(self.estado / 'limpezas.jsonl'):
                return falsa(original, fd, dados)
            return original(fd, dados)
        os.write = escrever
        pilha = contextlib.ExitStack()
        pilha.callback(setattr, os, 'write', original)
        return pilha

    def test_escrita_parcial_do_registro_completa_a_linha(self):
        self.encerrada('antiga')
        self.encerrada('outra')
        self.envelhecer()
        chamadas = []

        def parcial(original, fd, dados):
            chamadas.append(len(dados))
            return original(fd, dados[:7])
        with self.escrita_no_registro(parcial):
            codigo, saida, erro = self.aplicar_pelo_main(resposta='apagar')
        self.assertEqual(codigo, 0, erro)
        self.assertGreater(len(chamadas), 14)
        registros = self.registros()
        self.assertEqual(len(registros), 14)
        self.assertEqual({r['sessao'] for r in registros}, {'antiga', 'outra'})
        caminhos = [c for r in registros for c in r['caminhos']]
        self.assertEqual(len(caminhos), 16)
        self.assertIn('codex/antiga', caminhos)
        self.assertIn('agentes/validacao-outra-r2.contexto.json', caminhos)
        self.assertFalse(self.existe('codex/antiga'))
        self.assertTrue((self.estado / 'limpezas.jsonl').read_bytes().endswith(b'}\n'))

    def test_falha_do_registro_e_falha_explicita(self):
        for nome, falsa in (('zero', lambda original, fd, dados: 0),
                            ('parcial e zero', lambda original, fd, dados:
                             original(fd, dados[:7]) if dados.startswith(b'{') else 0),
                            ('erro', lambda original, fd, dados: (_ for _ in ()).throw(OSError(28, 'sem espaço')))):
            with self.subTest(falha=nome):
                shutil.rmtree(self.estado)
                self.estado.mkdir()
                self.encerrada('antiga')
                self.encerrada('outra')
                self.envelhecer()
                with self.escrita_no_registro(falsa):
                    codigo, saida, erro = self.aplicar_pelo_main(resposta='apagar')
                self.assertEqual(codigo, 1, erro)
                self.assertIn('erro: antiga (codex): apagado sem registro completo em limpezas.jsonl', erro)
                self.assertIn('codex/antiga', erro.split('sem registro completo')[1])
                self.assertIn('os grupos seguintes ficam mantidos', erro)
                self.assertIn('Apagados: 0 itens', saida)
                self.assertFalse(self.existe('codex/antiga'))
                self.assertTrue(self.existe('codex/outra'))
                self.assertTrue(self.existe('codex/revisao-codex-antiga'))

    def test_ponto_de_montagem_recusado(self):
        self.encerrada('antiga')
        pasta = str(self.estado / 'codex')
        self.assertTrue(retencao.cruza_montagem(pasta + '/antiga', [pasta + '/antiga']))
        self.assertTrue(retencao.cruza_montagem(pasta + '/antiga', [pasta + '/antiga/sessions']))
        self.assertFalse(retencao.cruza_montagem(pasta + '/antiga', [pasta + '/antiga-2', '/']))
        fd = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(retencao.Recusa):
                retencao.medir(fd, pasta, 'antiga', True, [pasta + '/antiga/sessions'])
            self.assertGreater(retencao.medir(fd, pasta, 'antiga', True, ['/'])[0], -1)
        finally:
            os.close(fd)

    def test_provedor_agy_e_trava(self):
        self.encerrada('antiga')
        self.gravar('provedores/agy-conta/antiga/e.json')
        self.gravar('provedores/agy-outra/antiga/e.json')
        self.envelhecer()
        self.aplicar(provedores=('claude', 'agy-conta'))
        self.assertFalse(self.existe('provedores/agy-conta/antiga'))
        self.assertTrue(self.existe('provedores/agy-outra/antiga'))
        self.assertTrue((self.estado / 'provedores/.travas/agy-conta/antiga').is_file())


class IgualABase(Base):
    """Sem a opção nova, --limpar-orfaos e --lista saem como na base 77038af."""

    def fabricar(self):
        futuro = '2099-01-01T00:00:00-03:00'
        self.gravar('agentes/viva.json', json.dumps(dict(estado='ativo', dir=str(self.tmp / 'wt'),
                                                         atualizado=futuro, ramo='agente/viva', tarefa='uma')))
        self.gravar('agentes/feita.json', json.dumps(dict(estado='concluido', dir=str(self.tmp / 'wt2'),
                                                          atualizado=futuro, ramo='agente/feita', tarefa='duas')))
        self.gravar('agentes/orfa.json', json.dumps(dict(estado='concluido', dir=str(self.tmp / 'wt3'),
                                                         atualizado='2020-01-01T00:00:00-03:00')))
        self.gravar('agentes/revisao-viva-r1.json', '{}')
        self.gravar('agentes/validacao-viva-r1.contexto.json', '{}')
        self.encerrada('antiga')
        self.vivas.write_text('viva\n')
        self.envelhecer()

    def saida(self):
        partes = []
        for argumento in ('--lista', '--limpar-orfaos', '--lista'):
            p = self.comando(argumento)
            partes.append(f'== {argumento} {p.returncode}\n{p.stdout}{p.stderr}')
        partes.append('== agentes\n' + ''.join(f'{n}\n' for n in sorted(os.listdir(self.estado / 'agentes'))))
        return ''.join(partes).replace(str(self.tmp), '${TMP}')

    def test_limpar_orfaos_e_lista_iguais_a_base(self):
        self.fabricar()
        self.assertEqual(self.saida(), BASE.read_text())


if __name__ == '__main__':
    isolamento.instalar()
    unittest.main(verbosity=1)
