#!/usr/bin/env python3
"""Ataques e preservação com HOME, SQLite, sessões e Git descartáveis.

Bubblewrap é real. Provedores usados para validar Git são simulados, sem rede.
"""

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'orquestracao'))
sys.path.insert(0, str(REPO))
from estado import Estado
from projetos import cadastrar, chave
from confianca import arquivar, guardar, registrar_inicio
from nucleo.consultas import consultar

spec = importlib.util.spec_from_file_location('fixture_baseline', REPO / 'testes/baseline.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Confianca(unittest.TestCase):
    def setUp(self):
        fixture.Baseline.setUp(self)
        (self.raiz / 'casa').mkdir()
        self.env.update(XDG_DATA_HOME=str(self.raiz / 'dados'),
                        XDG_CACHE_HOME=str(self.raiz / 'cache'),
                        XDG_RUNTIME_DIR=str(self.raiz / 'runtime'),
                        PYTHONDONTWRITEBYTECODE='1')
        for nome in ('DBUS_SESSION_BUS_ADDRESS', 'DISPLAY', 'WAYLAND_DISPLAY',
                     'HYPRLAND_INSTANCE_SIGNATURE', 'TMUX', 'CODEX_HOME'):
            self.env.pop(nome, None)
        for nome in ('pgrep', 'pkill', 'inotifywait', 'nvidia-smi'):
            self.executavel(nome, '#!/bin/sh\nexit 1\n')
        self.executavel('tmux', '#!/bin/sh\ncase "$*" in *has-session*) exit 1;; esac\nexit 0\n')
        self.fonte = self.projeto / 'fonte.txt'
        self.fonte.write_text('2,4,6\n')
        self.pasta = self.estado / 'agentes/projetos' / chave(self.projeto)
        self.fila = Estado(self.pasta, raiz=self.estado)
        self.addCleanup(self.fila.fechar)
        self.fila.importar([self.tarefa()])
        _, self.dono = self.fila.reservar()
        self.fila.finalizar('T1', self.dono, 'REVIEW_REQUIRED',
                           {'delegacao': {'destino': 'codex-principal', 'modelo': 'autor'},
                            'metricas': {'chamadas': 1}}, 'Média = 4')

    git = fixture.Baseline.git
    executavel = fixture.Baseline.executavel
    metadados = fixture.Baseline.metadados
    mudar = fixture.Baseline.mudar
    validar = fixture.Baseline.validar

    def tarefa(self, identificador='T1', **campos):
        return dict(id=identificador, pedido='Média deve ser 4', papel='redator',
                    capacidade='analise', risco=2, qualidade='high', fontes=[str(self.fonte)],
                    hashes_fontes={str(self.fonte): hashlib.sha256(self.fonte.read_bytes()).hexdigest()}, **campos)

    def isolar(self, codigo, **opcoes):
        if shutil.which('bwrap') is None:
            self.skipTest('BLOQUEADO: Bubblewrap ausente')
        ambiente = dict(self.env, JANGADA_ISOLAR_ESCRITA=str(self.pasta) + ':' + self.env.get('JANGADA_ISOLAR_ESCRITA', ''), DB_SINTETICO=str(self.pasta / 'tarefas.sqlite'))
        resultado = subprocess.run([str(REPO / 'bin/jangada-isolar'), '--', sys.executable,
                                    '-c', codigo], env=ambiente, cwd=self.projeto,
                                   capture_output=True, text=True, timeout=25, **opcoes)
        if ('bwrap:' in resultado.stderr and any(m in resultado.stderr for m in (
                'Operation not permitted', 'No permissions', 'Creating new namespace failed'))):
            self.skipTest('BLOQUEADO: ' + resultado.stderr)
        registro = os.environ.get('JANGADA_P0_EVIDENCIAS')
        if registro:
            with (Path(registro) / 'ataques-bubblewrap.jsonl').open('a') as arquivo:
                arquivo.write(json.dumps(dict(caso=self._testMethodName, codigo=resultado.returncode,
                    stdout=resultado.stdout, stderr=resultado.stderr, modo='Bubblewrap real, dados sintéticos')) + '\n')
        return resultado

    def test_B_revisor_claude_realmente_isolado_do_sqlite(self):
        self.env['DB_SINTETICO'] = str(self.pasta / 'tarefas.sqlite')
        self.executavel('claude', """#!/usr/bin/python3
import os,sqlite3,sys
sys.stdin.read()
try:
    db=sqlite3.connect(os.environ['DB_SINTETICO'])
    db.execute("UPDATE tarefas SET status='COMPLETED'");db.commit()
except sqlite3.OperationalError as erro:
    assert 'readonly' in str(erro)
    print('STATUS: APROVADO\\nATAQUE-REVISOR-BLOQUEADO')
else:
    raise SystemExit('FALHOU: revisor escreveu no SQLite')
""")
        self.mudar()
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.registrar_provedor(resultado)
        self.assertIn('ATAQUE-REVISOR-BLOQUEADO', resultado.stdout)
        self.assertEqual(self.fila.db.execute('SELECT status FROM tarefas').fetchone()[0], 'REVIEW_REQUIRED')

    def test_B_executor_delegado_realmente_isolado_do_sqlite(self):
        self.env.update(DB_SINTETICO=str(self.pasta / 'tarefas.sqlite'),
                        JANGADA_DELEGAR_MODELOS='gemini-teste', JANGADA_DELEGAR_COTA_MIN='1')
        configuracao = Path(self.env['HOME']) / '.gemini/antigravity-cli/settings.json'
        configuracao.parent.mkdir(parents=True, exist_ok=True)
        configuracao.write_text(json.dumps({'trustedWorkspaces': [str(self.projeto)]}))
        hooks = Path(self.env['HOME']) / '.gemini/config/hooks.json'
        hooks.parent.mkdir(parents=True, exist_ok=True)
        hooks.write_text((REPO / 'agentes/agy/hooks.json').read_text().replace('@JANGADA_CORE_PATH@', str(REPO)))
        self.executavel('agy', """#!/usr/bin/python3
import os,sqlite3,sys,json
if sys.argv[1]=='agents':
    print('leitor');raise SystemExit()
if '/usage' in sys.argv:
    print(json.dumps({'status':'SUCCESS','command':{'name':'usage','data':{'groups':[{'name':'Gemini Models','buckets':[{'id':'gemini-weekly','remaining_fraction':0.9},{'id':'gemini-5h','remaining_fraction':0.9}]}]}}}));raise SystemExit()
try:
    db=sqlite3.connect(os.environ['DB_SINTETICO'])
    db.execute("UPDATE tarefas SET status='COMPLETED'");db.commit()
except sqlite3.OperationalError as erro:
    assert 'readonly' in str(erro) or 'unable to open database file' in str(erro)
    print(json.dumps({'status':'SUCCESS','response':'Média 4 em fonte.txt:1; ATAQUE-EXECUTOR-BLOQUEADO'}))
else:
    raise SystemExit('FALHOU: executor escreveu no SQLite')
""")
        resultado = subprocess.run([str(REPO / 'bin/jangada-delegar'), 'leitor', 'Calcule média com fontes',
            '--destino', 'agy', '--capacidade', 'analise_documental', '--permitir-remoto', '--json',
            '--arquivos', str(self.fonte)], env=self.env, cwd=self.projeto,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(resultado.returncode, 0, resultado.stderr + resultado.stdout)
        self.registrar_provedor(resultado)
        self.assertIn('ATAQUE-EXECUTOR-BLOQUEADO', resultado.stdout)
        self.assertEqual(self.fila.db.execute('SELECT status FROM tarefas').fetchone()[0], 'REVIEW_REQUIRED')

    def registrar_provedor(self, resultado):
        registro = os.environ.get('JANGADA_P0_EVIDENCIAS')
        if registro:
            with (Path(registro) / 'ataques-bubblewrap.jsonl').open('a') as arquivo:
                arquivo.write(json.dumps(dict(caso=self._testMethodName, codigo=resultado.returncode,
                    stdout=resultado.stdout, stderr=resultado.stderr,
                    modo='Bubblewrap real, provedor simulado sem rede')) + '\n')

    def test_B_revisor_agy_realmente_isolado_do_sqlite(self):
        self.env['DB_SINTETICO'] = str(self.pasta / 'tarefas.sqlite')
        self.executavel('agy', """#!/usr/bin/python3
import os,sqlite3,sys,json
if sys.argv[1]=='agents':
    print('revisor');raise SystemExit()
try:
    db=sqlite3.connect(os.environ['DB_SINTETICO'])
    db.execute("UPDATE tarefas SET status='COMPLETED'");db.commit()
except sqlite3.OperationalError as erro:
    assert 'readonly' in str(erro)
    print(json.dumps({'status':'SUCCESS','response':'STATUS: APROVADO\\nATAQUE-REVISOR-AGY-BLOQUEADO'}))
else:
    raise SystemExit('FALHOU: revisor escreveu no SQLite')
""")
        self.mudar()
        resultado = subprocess.run([str(REPO / 'bin/jangada-validar'), '--revisor', 'agy', str(self.projeto)],
            env=self.env, cwd=self.projeto, capture_output=True, text=True, timeout=30)
        self.registrar_provedor(resultado)
        self.assertEqual(resultado.returncode, 0, resultado.stderr + resultado.stdout)
        self.assertIn('ATAQUE-REVISOR-AGY-BLOQUEADO', resultado.stdout)
        self.assertEqual(self.fila.db.execute('SELECT status FROM tarefas').fetchone()[0], 'REVIEW_REQUIRED')

    def test_J_foto_nao_pode_reexpor_autoridade(self):
        (self.estado / 'fotos').mkdir(parents=True, exist_ok=True)
        self.env['JANGADA_ISOLAR_FOTO'] = str(self.pasta)
        resultado = self.isolar("raise SystemExit('processo não deveria iniciar')")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertNotIn('processo não deveria iniciar', resultado.stderr)
        self.assertIn('AUTORIZACAO_RECUSADA', resultado.stderr)

    def test_J_foto_com_ligacao_inicia_sem_reexpor_revisoes(self):
        foto = self.estado / 'fotos/f1'
        foto.mkdir(parents=True)
        (foto / 'volta').symlink_to('../../revisoes')
        (self.estado / 'revisoes').mkdir(exist_ok=True)
        (self.estado / 'revisoes/segredo').write_text('ATAQUE')
        self.env['JANGADA_ISOLAR_FOTO'] = str(foto)
        resultado = self.isolar(f"import os;assert os.listdir({str(foto / 'volta')!r}) == [];print('INICIOU')")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn('INICIOU', resultado.stdout)
        (self.estado / 'fotos/alias').symlink_to('../revisoes')
        self.env['JANGADA_ISOLAR_FOTO'] = str(self.estado / 'fotos/alias')
        resultado = self.isolar("print('INICIOU')")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertNotIn('INICIOU', resultado.stdout)
        self.assertIn('AUTORIZACAO_RECUSADA', resultado.stderr)

    def test_J_descritor_padrao_para_foto_recusado(self):
        foto = self.estado / 'fotos/f1'
        foto.mkdir(parents=True)
        (foto / 'entrega.diff').write_text('diff')
        with open(foto / 'entrega.diff') as entrada:
            resultado = self.isolar("print('INICIOU')", stdin=entrada)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertNotIn('INICIOU', resultado.stdout)
        self.assertIn('descritor padrão', resultado.stderr)

    def test_A_sqlite_real_somente_leitura_mesmo_com_extra(self):
        resultado = self.isolar("import os,sqlite3; d=sqlite3.connect(os.environ['DB_SINTETICO']); d.execute(\"UPDATE tarefas SET status='COMPLETED'\");d.commit()")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('readonly', resultado.stderr)
        self.assertEqual(self.fila.listar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(self.fila.db.execute("SELECT count(*) FROM eventos WHERE evento='revisada'").fetchone()[0], 0)
        self.assertTrue(list((self.estado / 'revisoes/falhas-isolamento').glob('*.json')))

    def test_A_alias_simbolico_nao_reabre_banco(self):
        alias = self.projeto / 'banco'
        alias.symlink_to(self.pasta / 'tarefas.sqlite')
        resultado = self.isolar("import sqlite3;d=sqlite3.connect('banco');d.execute(\"UPDATE tarefas SET status='COMPLETED'\");d.commit()")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(self.fila.listar()[0]['status'], 'REVIEW_REQUIRED')

    def test_A_configuracao_nao_desliga_fronteira(self):
        self.env['JANGADA_AGENTE_ISOLAR'] = '0'
        resultado = self.isolar("import os,sqlite3;d=sqlite3.connect(os.environ['DB_SINTETICO']);d.execute(\"UPDATE tarefas SET status='COMPLETED'\");d.commit()")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('isolamento obrigatório', resultado.stderr)
        self.assertIn('readonly', resultado.stderr)

    def test_J_codigo_do_controlador_nao_pode_ser_alterado(self):
        instalacao = self.raiz / 'instalacao-sintetica'
        helper = instalacao / 'orquestracao'
        helper.mkdir(parents=True)
        shutil.copyfile(REPO / 'orquestracao/confianca.py', helper / 'confianca.py')
        codigo = instalacao / 'controlador.txt'
        codigo.write_text('original')
        self.env['JANGADA_CORE_PATH'] = str(instalacao)
        self.env['JANGADA_ISOLAR_ESCRITA'] = str(instalacao)
        resultado = self.isolar(f'from pathlib import Path;Path({str(codigo)!r}).write_text("ATAQUE")')
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(codigo.read_text(), 'original')

    def test_A_ligacao_fisica_recusada_antes_de_iniciar(self):
        os.link(self.pasta / 'tarefas.sqlite', self.projeto / 'alias.sqlite')
        resultado = self.isolar('raise SystemExit(0)')
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('ligação adicional', resultado.stderr)

    def test_A_descritor_adicional_nao_e_herdado(self):
        fd = os.open(self.pasta / 'tarefas.sqlite', os.O_RDWR)
        try:
            resultado = self.isolar(f'import os;os.write({fd},b"ATAQUE")', pass_fds=(fd,))
            self.assertNotEqual(resultado.returncode, 0)
            self.assertIn('Bad file descriptor', resultado.stderr)
        finally:
            os.close(fd)

    def test_A_descritor_padrao_para_banco_recusado(self):
        with (self.pasta / 'tarefas.sqlite').open('rb') as banco:
            resultado = self.isolar('raise SystemExit(0)', stdin=banco)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('descritor padrão', resultado.stderr)

    def test_B_interface_recusa_executor_mesmo_sem_variavel(self):
        codigo = f'import os,sys;os.environ.pop("JANGADA_ISOLADO",None);sys.path.insert(0,{str(REPO / "orquestracao")!r});from estado import Estado;Estado({str(self.pasta)!r},raiz={str(self.estado)!r})'
        resultado = self.isolar(codigo)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('AUTORIZACAO_RECUSADA', resultado.stderr)

    def test_B_estado_sqlite_forjado_nao_e_decisao(self):
        self.fila.db.execute("UPDATE tarefas SET status='COMPLETED' WHERE id='T1'")
        self.assertEqual(self.fila.listar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(consultar(self.estado)['tarefas'][0]['status'], 'REVIEW_REQUIRED')

    def test_B_dependencia_nao_libera_por_sqlite_forjado(self):
        self.fila.importar([self.tarefa('T2', dependencias=['T1'])])
        self.fila.db.execute("UPDATE tarefas SET status='COMPLETED' WHERE id='T1'")
        self.assertIsNone(self.fila.reservar())

    def test_B_json_de_supervisao_inventada_nao_aprova(self):
        tarefa = self.tarefa('FORJA')
        tarefa.update(papel='leitor', capacidade='resumo_curto', risco=1, qualidade='medium',
                      intermediaria=True, supervisao_automatica=True, permitir_remoto=True)
        self.fila.importar([tarefa])
        _, dono = self.fila.reservar()
        texto = 'Relatório sintético'
        parecer = dict(task_id='FORJA', relatorio_sha256=hashlib.sha256(texto.encode()).hexdigest(),
                       decisao='APPROVED', observacoes=[], criterios={c: {
                           'resultado': 'PASS', 'justificativa': 'Tudo conferido em fonte por revisor inventado'}
                           for c in ('fidelidade', 'completude', 'extrapolacoes')})
        resultado = dict(verificacao='referencias_e_requisitos_validos',
                         delegacao={'destino': 'local', 'modelo': 'autor'}, metricas={'chamadas': 2},
                         supervisao=dict(executor='agy', habilitada=True, referencias_conferidas=True,
                                         chamadas=1, texto=json.dumps(parecer)))
        with self.assertRaises(ValueError):
            self.fila.finalizar('FORJA', dono, 'COMPLETED', resultado, texto)
        self.assertEqual(next(t for t in self.fila.listar() if t['id'] == 'FORJA')['status'], 'RUNNING')

    def test_C_artefato_alterado_invalida_decisao(self):
        self.fila.revisar('T1', 'Conferido por operador', True)
        self.assertEqual(self.fila.listar()[0]['status'], 'COMPLETED')
        objeto = self.pasta / 'artefatos' / (self.fila.listar()[0]['hash_artefato'] + '.txt')
        objeto.write_text('Média = 6')
        self.assertEqual(self.fila.listar()[0]['status'], 'REVIEW_REQUIRED')

    def test_C_aprovacao_outra_tarefa_nao_pode_ser_reutilizada(self):
        self.fila.revisar('T1', 'Conferido por operador', True)
        self.fila.db.execute('PRAGMA foreign_keys=OFF')
        self.fila.db.execute("UPDATE tarefas SET id='OUTRA' WHERE id='T1'")
        self.assertEqual(self.fila.listar()[0]['status'], 'REVIEW_REQUIRED')

    def test_D_sem_revisao_independente_nao_aprova(self):
        cadastrar(self.fila, self.projeto, {'revisao_minima': {'2': {'independente': True}}})
        with self.assertRaises(ValueError):
            self.fila.revisar('T1', 'opinião de humano', True)
        self.assertEqual(self.fila.listar()[0]['status'], 'REVIEW_REQUIRED')

    def test_E_rotulo_modelo_nao_registra_revisao_inexistente(self):
        for revisor, modelo in [('codex', 'autor'), ('claude', None), ('claude', 'inventado')]:
            with self.subTest(revisor=revisor, modelo=modelo), self.assertRaises(ValueError):
                self.fila.revisar('T1', 'PARECER-FORJADO', True, revisor, modelo)
        self.assertEqual(self.fila.db.execute("SELECT count(*) FROM eventos WHERE evento='revisada'").fetchone()[0], 0)
        self.assertEqual(self.fila.db.execute("SELECT count(*) FROM eventos WHERE evento='autorizacao_recusada'").fetchone()[0], 3)
        self.assertEqual(len(list((self.pasta / 'recusas').glob('*.json'))), 3)

    def test_D_reprovacao_manual_nao_finge_independencia(self):
        cadastrar(self.fila, self.projeto, {'revisao_minima': {'2': {'independente': True}}})
        self.fila.revisar('T1', 'Erro identificado por operador', False)
        self.assertEqual(self.fila.listar()[0]['status'], 'REVISION_REQUIRED')
        self.fila.alterar('T1', 'repetir')
        self.assertIsNotNone(self.fila.reservar())

    def test_H_alias_de_arquivo_recusado_antes_de_criar_pastas(self):
        externo = self.raiz / 'externo-sintetico'
        externo.mkdir()
        alias = self.raiz / 'alias-sintetico'
        alias.symlink_to(externo, target_is_directory=True)
        with self.assertRaises(ValueError):
            guardar(alias / 'historico', {'parecer': 'sintético'})
        self.assertEqual(list(externo.iterdir()), [])

    def test_H_falha_fsync_nao_apaga_documentos(self):
        originais = self.documentos()
        with patch('confianca.os.fsync', side_effect=OSError('falha sintética durante escrita')):
            with self.assertRaises(OSError):
                arquivar(self.estado, 'teste')
        for nome, conteudo in originais.items():
            self.assertEqual((self.estado / nome).read_bytes(), conteudo)
        self.assertFalse(list((self.estado / 'revisoes/arquivo').glob('*.json')))

    def test_F_reprovacoes_e_rodadas_intermediarias_preservadas(self):
        self.documentos()
        self.mudar('outra.txt')
        self.executavel('claude', '#!/bin/sh\ncat >/dev/null\nprintf "STATUS: REVISAR\\nDIVERGENCIA-SINTETICA-INTEGRAL\\n"\n')
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 3, resultado.stderr)
        self.assertEqual(self.encerrar().returncode, 0)
        historico = json.loads(next((self.estado / 'revisoes/arquivo').glob('*.json')).read_text())
        self.assertIn('revisoes/validacao-teste-r1.md', historico['documentos'])
        self.assertIn('revisoes/validacao-teste-r2.md', historico['documentos'])
        self.assertIn('DIVERGENCIA-SINTETICA-INTEGRAL', base64.b64decode(
            historico['documentos']['revisoes/validacao-teste-r2.md']['conteudo_base64']).decode())

    def test_G_prompt_inicial_protegido_mesmo_apos_adulteracao_local(self):
        self.documentos()
        registro = registrar_inicio(self.estado, 'teste')
        prompt = self.estado / 'agentes/prompt-teste.md'
        original = prompt.read_bytes()
        prompt.write_text('PROMPT-ADULTERADO-PELO-EXECUTOR')
        (self.estado / 'agentes/protocolo-teste.md').unlink()
        resultado = self.encerrar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        historico = json.loads(next((self.estado / 'revisoes/arquivo').glob('*.json')).read_text())
        inicio = historico['registros_inicio'][registro.stem]
        self.assertEqual(base64.b64decode(inicio['documentos']['agentes/prompt-teste.md']['conteudo_base64']), original)
        self.assertIn('agentes/protocolo-teste.md', inicio['documentos'])

    def documentos(self):
        self.mudar()
        self.executavel('claude', '#!/bin/sh\ncat >/dev/null\nprintf "STATUS: APROVADO\\nPARECER-INTEGRAL-SINTETICO\\n"\n')
        resultado = self.validar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        for nome in ('prompt-teste.md', 'protocolo-teste.md'):
            (self.estado / 'agentes' / nome).write_text('PROMPT-SINTETICO-INTEGRAL\n')
        return {str(p.relative_to(self.estado)): p.read_bytes() for pasta in ('agentes', 'revisoes')
                for p in (self.estado / pasta).glob('*') if p.is_file() and p.name != 'validar.jsonl'}

    def encerrar(self, *args):
        ambiente = dict(self.env)
        ambiente.pop('JANGADA_SESSAO', None)
        return subprocess.run([str(REPO / 'bin/jangada-agente-fim'), *args, 'teste'], env=ambiente,
                              capture_output=True, text=True, timeout=30)

    def test_FG_encerramento_preserva_integrais_e_contexto(self):
        originais = self.documentos()
        resultado = self.encerrar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        arquivos = list((self.estado / 'revisoes/arquivo').glob('*.json'))
        self.assertEqual(len(arquivos), 1)
        historico = json.loads(arquivos[0].read_text())
        registro = os.environ.get('JANGADA_P0_EVIDENCIAS')
        if registro:
            (Path(registro) / 'arquivo-sintetico.json').write_bytes(arquivos[0].read_bytes())
        for nome, conteudo in originais.items():
            self.assertEqual(base64.b64decode(historico['documentos'][nome]['conteudo_base64']), conteudo)
        marca = json.loads(originais['revisoes/validacao-teste.aprovado'])
        contexto = json.loads(base64.b64decode(historico['documentos']['revisoes/validacao-teste-r1.contexto.json']['conteudo_base64']))
        self.assertEqual(marca['candidate_sha'], contexto['candidate_sha'])
        self.assertTrue(contexto['pedido'])
        self.assertFalse((self.estado / 'revisoes/validacao-teste.aprovado').exists())

    def test_H_falha_publicacao_preserva_originais(self):
        originais = self.documentos()
        (self.estado / 'revisoes/arquivo').write_text('impedimento sintético')
        resultado = self.encerrar()
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('originais mantidas', resultado.stderr)
        for nome, conteudo in originais.items():
            self.assertEqual((self.estado / nome).read_bytes(), conteudo)

    def test_H_contexto_ausente_nao_encerra_com_aprovacao(self):
        self.documentos()
        (self.estado / 'revisoes/validacao-teste-r1.contexto.json').unlink()
        resultado = self.encerrar()
        self.assertNotEqual(resultado.returncode, 0)
        self.assertTrue((self.estado / 'revisoes/validacao-teste-r1.md').exists())
        historico = json.loads(next((self.estado / 'revisoes/arquivo').glob('*.json')).read_text())
        self.assertTrue(historico['pendencias'])

    def test_I_arquivamento_repetido_sem_duplicacao(self):
        self.documentos()
        primeiro = arquivar(self.estado, 'teste')
        segundo = arquivar(self.estado, 'teste')
        self.assertEqual(primeiro, segundo)
        self.assertEqual(len(list(primeiro.parent.glob('*.json'))), 1)
        self.assertEqual(self.encerrar().returncode, 0)
        self.assertNotEqual(self.encerrar().returncode, 0)
        self.assertEqual(len(list(primeiro.parent.glob('*.json'))), 1)

    def test_I_sessao_acima_do_limite_recusa_antes_de_gravar(self):
        originais = self.documentos()
        # Cada documento cabe no limite; em base64, o maior deles já não cabe.
        limite = max(len(conteudo) for conteudo in originais.values())
        with patch('confianca.LIMITE_REGISTRO', limite):
            with self.assertRaisesRegex(ValueError, 'sessão excede'):
                arquivar(self.estado, 'teste')
            with self.assertRaisesRegex(ValueError, 'registro excede'):
                guardar(self.estado / 'revisoes/arquivo', {'conteudo': 'x' * limite})
        self.assertEqual(list((self.estado / 'revisoes/arquivo').glob('*')), [])
        for nome, conteudo in originais.items():
            self.assertEqual((self.estado / nome).read_bytes(), conteudo)

    def test_J_isolamento_nao_altera_outro_projeto(self):
        outra = self.estado / 'agentes/projetos/outro'
        outro = Estado(outra, raiz=self.estado)
        try:
            outro.importar([self.tarefa('OUTRA')])
        finally:
            outro.fechar()
        resultado = self.isolar(f'import sqlite3;d=sqlite3.connect({str(outra / "tarefas.sqlite")!r});d.execute("DELETE FROM tarefas");d.commit()')
        self.assertNotEqual(resultado.returncode, 0)
        outro = Estado(outra, raiz=self.estado)
        try:
            self.assertEqual(len(outro.listar()), 1)
        finally:
            outro.fechar()

    def test_J_evidencia_protegida_nao_persiste_escrita_real(self):
        self.documentos()
        historico = guardar(self.estado / 'revisoes/arquivo', {'prova': 'original'})
        original = historico.read_bytes()
        codigo = f'from pathlib import Path;p=Path({str(historico)!r});p.parent.mkdir(parents=True,exist_ok=True);p.write_text("FORJADO")'
        resultado = self.isolar(codigo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(historico.read_bytes(), original)

    def test_L_integracao_permanece_bloqueada(self):
        self.documentos()
        ponta = self.git('rev-parse', 'HEAD')
        resultado = self.encerrar('--integrar')
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('bloqueada', resultado.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), ponta)
        self.assertTrue((self.estado / 'agentes/teste.json').exists())

    def test_H_ligacoes_em_evidencias_bloqueiam_limpeza(self):
        self.documentos()
        parecer = self.estado / 'revisoes/validacao-teste-r1.md'
        original = parecer.read_bytes()
        os.link(parecer, self.projeto / 'parecer-alias')
        resultado = self.encerrar()
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(parecer.read_bytes(), original)


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main(verbosity=2)
