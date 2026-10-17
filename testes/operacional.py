#!/usr/bin/env python3
"""Contratos operacionais com estado temporário, sem chamar provedores."""

import hashlib
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from estado import Estado
from projetos import cadastrar, chave, ler_projeto, reassociar
from executor import contexto_principal, executar_uma
from nucleo.consultas import consultar, catalogos
from nucleo.acoes import executar as acao
from nucleo.roteamento import decidir
from saude import Saude


class Operacional(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.projeto = self.raiz / 'projeto'
        self.projeto.mkdir()
        self.fonte = self.projeto / 'fonte.md'
        self.fonte.write_text('Fonte original\n')
        self.estado_raiz = self.raiz / 'estado'
        self.pasta = self.estado_raiz / 'agentes/projetos' / chave(self.projeto)
        self.estado = Estado(self.pasta, raiz=self.estado_raiz)
        self.addCleanup(lambda: self.estado.fechar() if self.estado else None)
        self.config = self.raiz / 'config'
        self.config.mkdir()

    def tarefa(self, identificador='T1', **campos):
        return {**dict(id=identificador, pedido='Leia a fonte', papel='leitor', capacidade='leitura_documental',
                    risco=1, qualidade='medium', fontes=[str(self.fonte)],
                    hashes_fontes={str(self.fonte): hashlib.sha256(self.fonte.read_bytes()).hexdigest()}), **campos}

    def entregar(self, **campos):
        self.estado.importar([self.tarefa(**campos)])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED',
                             {'delegacao': {'destino': 'codex-principal', 'modelo': 'autor'},
                              'metricas': {'chamadas': 1}}, 'relatório')
        return self.estado.listar()[0]

    def fechar(self):
        self.estado.fechar()
        self.estado = None

    def test_atividade_importacao_atomica_e_idempotente(self):
        atividade = self.estado.criar_atividade('Auditoria', 'Conferir fontes', ['Fidelidade'])
        self.estado.importar([self.tarefa(atividade=atividade, criterios_aceite=['Fidelidade'])])
        self.estado.importar([self.tarefa(atividade=atividade, criterios_aceite=['Fidelidade'])])
        with self.assertRaises(ValueError):
            self.estado.importar([self.tarefa('T2'), self.tarefa('T3', atividade='atv-' + '0' * 12)])
        self.assertEqual([t['id'] for t in self.estado.listar()], ['T1'])

    def test_execucoes_distintas_apos_recusa_e_expiracao(self):
        self.estado.importar([self.tarefa()])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'WAITING_PROVIDER',
                             {'execucao_iniciada': False, 'metricas': {'chamadas': 0}})
        self.estado.alterar('T1', 'retomar')
        self.estado.reservar()
        self.estado.db.execute("UPDATE tarefas SET prazo=0 WHERE id='T1'")
        self.estado.reservar()
        linhas = list(self.estado.db.execute('SELECT * FROM execucoes ORDER BY inicio'))
        self.assertEqual(len(linhas), 2)
        self.assertNotEqual(linhas[0]['id'], linhas[1]['id'])
        self.assertEqual(linhas[1]['status'], 'REVISION_REQUIRED')
        self.assertIsNone(linhas[1]['chamadas'])
        self.assertIsNone(linhas[0]['segundos'])
        eventos = [json.loads(r[0]) for r in self.estado.db.execute(
            "SELECT dados FROM eventos WHERE evento IN ('reservada','execucao_encerrada','reserva_expirada')")]
        self.assertTrue(all('execucao' in e for e in eventos))

    def test_finalizacao_sem_dono_nao_altera_execucao(self):
        self.estado.importar([self.tarefa()])
        self.estado.reservar()
        with self.assertRaises(ValueError):
            self.estado.finalizar('T1', 'errado', 'REVIEW_REQUIRED', {}, 'texto')
        self.assertIsNone(self.estado.db.execute('SELECT fim FROM execucoes').fetchone()[0])

    def test_sessao_vinculada_nao_recebe_finalizacao_da_fila(self):
        self.estado.importar([self.tarefa()])
        self.estado.db.execute("INSERT INTO execucoes(id,sessao,tarefa,funcao,inicio,status) VALUES('sessao-exe','sessao','T1','execucao',0,'RUNNING')")
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {'metricas': {'chamadas': 1}}, 'texto')
        linhas = {r['id']: dict(r) for r in self.estado.db.execute('SELECT * FROM execucoes')}
        self.assertEqual(linhas['sessao-exe']['status'], 'RUNNING')
        self.assertIsNone(linhas['sessao-exe']['fim'])
        fila = next(r for r in linhas.values() if r['dono'] == dono)
        self.assertEqual(fila['status'], 'REVIEW_REQUIRED')
        self.assertEqual(fila['chamadas'], 1)

    def test_cadastro_recusa_orcamento_com_consumo_desconhecido(self):
        cadastrar(self.estado, self.projeto)
        self.entregar()
        self.estado.db.execute("UPDATE eventos SET dados='{}' WHERE evento='execucao_encerrada'")
        with self.assertRaisesRegex(ValueError, 'consumo.*desconhecido'):
            cadastrar(self.estado, self.projeto, {'orcamento': {'chamadas': 3}})
        self.assertEqual(ler_projeto(self.pasta)['politica'], {})

    def test_politica_de_revisao_exige_identidade_e_nao_inventa_independencia(self):
        cadastrar(self.estado, self.projeto, {'revisao_minima': {'1': {'independente': True}}})
        self.entregar()
        with patch.dict(os.environ, {'JANGADA_ISOLADO': ''}):
            with self.assertRaisesRegex(ValueError, 'identificados'):
                self.estado.revisar('T1', 'parecer', True)
            cadastrar(self.estado, self.projeto, {})
            self.estado.revisar('T1', 'parecer', True)
        registro = json.loads(self.estado.db.execute("SELECT dados FROM eventos WHERE evento='revisada'").fetchone()[0])
        self.assertIsNone(registro['independente'])

    def test_cli_sessao_confere_aborta_e_encerra_sem_concluir_tarefa(self):
        self.estado.importar([self.tarefa()])
        ambiente = dict(os.environ, JANGADA_ESTADO=str(self.estado_raiz), JANGADA_CORE_PATH=str(RAIZ),
                        JANGADA_CONFIG=str(self.config), JANGADA_ISOLADO='')
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), '--projeto', str(self.projeto)]
        ambiente['PYTHONPATH'] = str(RAIZ)

        def chamar(*args):
            resposta = subprocess.run([*comando, *args], env=ambiente, capture_output=True, text=True)
            self.assertEqual(resposta.returncode, 0, resposta.stderr)
            return json.loads(resposta.stdout)

        chamar('sessao-conferir', 'sessao', '--executor', 'codex', '--tarefa-id', 'T1')
        primeira = chamar('sessao-iniciar', 'sessao', '--executor', 'codex', '--tarefa-id', 'T1')['execucao']
        chamar('sessao-abortar', 'sessao', '--execucao', primeira)
        segunda = chamar('sessao-iniciar', 'sessao', '--executor', 'codex', '--tarefa-id', 'T1')['execucao']
        chamar('sessao-encerrar', 'sessao', '--integrada')
        linhas = {r['id']: r['status'] for r in self.estado.db.execute('SELECT id,status FROM execucoes')}
        self.assertEqual(linhas, {primeira: 'CANCELLED', segunda: 'COMPLETED'})
        self.assertEqual(self.estado.listar()[0]['status'], 'QUEUED')

    def test_sessao_orfa_encerra_por_nome_e_orcamento_recupera_apos_janela(self):
        cadastrar(self.estado, self.projeto)
        self.estado.importar([self.tarefa()])
        ambiente = dict(os.environ, JANGADA_ESTADO=str(self.estado_raiz), JANGADA_CORE_PATH=str(RAIZ),
                        JANGADA_CONFIG=str(self.config), PYTHONPATH=str(RAIZ), JANGADA_ISOLADO='')
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), '--projeto', str(self.projeto)]
        resposta = subprocess.run([*comando, 'sessao-iniciar', 'orfã', '--executor', 'codex'],
                                  env=ambiente, capture_output=True, text=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        orcamento = {'chamadas': 3, 'periodo_segundos': 60}
        with self.assertRaisesRegex(ValueError, 'sessao-encerrar'):
            cadastrar(self.estado, self.projeto, {'orcamento': orcamento})
        with self.assertRaisesRegex(ValueError, 'sessao-encerrar'):
            self.estado.chamadas_usadas(orcamento)
        resposta = subprocess.run([*comando, 'sessao-encerrar', 'orfã'],
                                  env=ambiente, capture_output=True, text=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        execucao = self.estado.db.execute("SELECT status,fim,chamadas FROM execucoes WHERE sessao='orfã'").fetchone()
        self.assertEqual(execucao['status'], 'CANCELLED')
        self.assertIsNotNone(execucao['fim'])
        self.assertIsNone(execucao['chamadas'])
        self.assertEqual(self.estado.listar()[0]['status'], 'QUEUED')
        with self.assertRaisesRegex(ValueError, 'aguarde o fim da janela'):
            cadastrar(self.estado, self.projeto, {'orcamento': orcamento})
        self.assertEqual(ler_projeto(self.pasta)['politica'], {})
        with patch('estado.time.time', return_value=time.time() + 61):
            cadastrar(self.estado, self.projeto, {'orcamento': orcamento})
            self.assertEqual(self.estado.limite_projeto(self.tarefa()), 3)
            self.assertIsNotNone(self.estado.reservar())

    def test_conferencia_previa_nao_cria_estado_e_recusa_vinculo_ausente(self):
        raiz = self.raiz / 'sem-estado'
        ambiente = dict(os.environ, JANGADA_ESTADO=str(raiz), JANGADA_CORE_PATH=str(RAIZ),
                        JANGADA_CONFIG=str(self.config), PYTHONPATH=str(RAIZ))
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), '--projeto', str(self.projeto),
                   'sessao-conferir', 'nova', '--executor', 'codex']
        resposta = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        self.assertEqual(json.loads(resposta.stdout), {'permitida': True})
        resposta = subprocess.run([*comando, '--tarefa-id', 'T1'], env=ambiente, capture_output=True, text=True)
        self.assertNotEqual(resposta.returncode, 0)
        self.assertIn('tarefa inexistente', resposta.stderr)
        self.assertFalse(raiz.exists())

    def test_corrupcao_alheia_nao_impede_conferencia_e_roteamento(self):
        (self.config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        cadastrar(self.estado, self.projeto)
        self.estado.importar([self.tarefa()])
        outra = self.raiz / 'outro-projeto'
        outra.mkdir()
        pasta = self.estado_raiz / 'agentes/projetos' / chave(outra)
        pasta.mkdir()
        (pasta / 'projeto.json').write_text('{inválido')
        (self.estado_raiz / 'agentes/alheia.json').write_text('{inválido')
        (self.estado_raiz / 'agentes/sem-raiz.json').write_text(json.dumps({'sessao': 'sem-raiz'}))
        antes = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.estado_raiz.rglob('*') if p.is_file()}
        consulta = consultar(self.estado_raiz, self.projeto)
        self.assertFalse(consulta['erros'])
        self.assertEqual([t['id'] for t in consulta['tarefas']], ['T1'])
        global_ = consultar(self.estado_raiz)
        self.assertEqual(len(global_['erros']), 3)
        ambiente = dict(os.environ, JANGADA_ESTADO=str(self.estado_raiz), JANGADA_CORE_PATH=str(RAIZ),
                        JANGADA_CONFIG=str(self.config), PYTHONPATH=str(RAIZ))
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), '--projeto', str(self.projeto),
                   'sessao-conferir', 'nova', '--executor', 'codex', '--tarefa-id', 'T1']
        resposta = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        with patch.dict(os.environ, {'JANGADA_DELEGAR': 'local'}):
            rota = decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'manual', 'local')
        self.assertEqual(rota['executor'], 'local')
        self.assertEqual(antes, {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                                 for p in self.estado_raiz.rglob('*') if p.is_file()})
        sessao = self.estado_raiz / 'agentes/propria.json'
        sessao.write_text(json.dumps(dict(sessao='propria', raiz=str(self.projeto), estado=[])))
        consulta = consultar(self.estado_raiz, self.projeto)
        self.assertEqual(len(consulta['erros']), 1)
        self.assertIn('propria.json', consulta['erros'][0])
        resposta = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
        self.assertNotEqual(resposta.returncode, 0)
        self.assertIn('propria.json', resposta.stderr)
        sessao.unlink()
        (self.pasta / 'projeto.json').write_text('{inválido')
        resposta = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
        self.assertNotEqual(resposta.returncode, 0)
        with self.assertRaises(ValueError):
            decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'manual', 'local')

    def test_conferencia_previa_preserva_banco_legado_e_recusa_politica_sem_gravar(self):
        self.estado.importar([self.tarefa()])
        ambiente = dict(os.environ, JANGADA_ESTADO=str(self.estado_raiz), JANGADA_CORE_PATH=str(RAIZ),
                        JANGADA_CONFIG=str(self.config), PYTHONPATH=str(RAIZ))
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), '--projeto', str(self.projeto),
                   'sessao-conferir', 'nova', '--executor', 'codex', '--tarefa-id', 'T1']
        for politica in (None, {'dados': 'local'}, {'orcamento': {'chamadas': 3}}):
            if politica is not None:
                cadastrar(self.estado, self.projeto, politica)
            antes = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.estado_raiz.rglob('*') if p.is_file()}
            resposta = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
            self.assertEqual(resposta.returncode == 0, politica is None, resposta.stderr)
            self.assertEqual(antes, {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                                     for p in self.estado_raiz.rglob('*') if p.is_file()})

    def test_consulta_sem_catalogos_nao_depende_dos_executaveis(self):
        ambiente = dict(os.environ, JANGADA_ESTADO=str(self.estado_raiz), JANGADA_CORE_PATH=str(self.raiz),
                        JANGADA_CONFIG=str(self.config), PYTHONPATH=str(RAIZ))
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), 'consultar', '--todos', '--sem-catalogos']
        resposta = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        dados = json.loads(resposta.stdout)
        self.assertFalse(dados['erros'])
        self.assertNotIn('perfis', dados)
        self.assertNotIn('provedores', dados)

    def test_reserva_principal_deterministica_nao_confunde_zero_com_esgotamento(self):
        cadastrar(self.estado, self.projeto, {'orcamento': {'chamadas': 1}})
        self.estado.importar([self.tarefa(papel='verificador', capacidade='validacao_json', risco=0, qualidade='high')])
        spec, _, _ = self.estado.reservar_principal('T1', 'codex')
        self.assertEqual(spec['capacidade'], 'validacao_json')
        self.assertEqual(self.estado.db.execute('SELECT limite_chamadas FROM execucoes').fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, 'não aguarda supervisão'):
            self.estado.reservar_supervisao('T1')

    def test_revisao_recusa_isolamento_e_alias_do_autor(self):
        self.entregar()
        with patch.dict(os.environ, {'JANGADA_ISOLADO': '1'}), self.assertRaises(ValueError):
            self.estado.revisar('T1', 'conferido', True)
        with patch.dict(os.environ, {'JANGADA_ISOLADO': ''}):
            with self.assertRaises(ValueError):
                self.estado.revisar('T1', 'conferido', True, 'codex', 'outro')
            with self.assertRaisesRegex(ValueError, 'execução verificável'):
                self.estado.revisar('T1', 'conferido', True, 'claude', 'revisor')
            self.estado.revisar('T1', 'conferido', True)
        evento = json.loads(self.estado.db.execute("SELECT dados FROM eventos WHERE evento='revisada'").fetchone()[0])
        self.assertEqual(evento['artefato_sha256'], hashlib.sha256('relatório'.encode()).hexdigest())
        self.assertIsNone(evento['independente'])

    def test_parecer_exige_criterios_hash_e_tarefa(self):
        tarefa = self.entregar(criterios_aceite=['Fidelidade'])
        documento = dict(tarefa='T1', artefato_sha256=tarefa['hash_artefato'],
                         criterios=[dict(criterio='Fidelidade', resultado='APROVADO', justificativa='Fonte conferida')])
        with patch.dict(os.environ, {'JANGADA_ISOLADO': ''}):
            for campo, valor in (('tarefa', 'outra'), ('artefato_sha256', '0' * 64), ('criterios', [])):
                with self.assertRaises(ValueError):
                    self.estado.revisar('T1', json.dumps({**documento, campo: valor}), True)
            self.estado.revisar('T1', json.dumps(documento), True)
        self.assertEqual(self.estado.listar()[0]['status'], 'COMPLETED')

    def test_politica_bloqueia_reserva_principal_e_preserva_importacao(self):
        cadastrar(self.estado, self.projeto, {'dados': 'local'})
        self.estado.importar([self.tarefa(qualidade='high')])
        with self.assertRaises(ValueError):
            self.estado.reservar_principal('T1', 'codex', 'modelo')
        self.assertEqual(self.estado.listar()[0]['status'], 'QUEUED')
        self.assertEqual(len(self.estado.impedimentos_politica()), 2)

    def test_orcamento_reservado_entre_conexoes(self):
        cadastrar(self.estado, self.projeto, {'orcamento': {'chamadas': 3}})
        self.estado.importar([self.tarefa(), self.tarefa('T2')])
        _, dono = self.estado.reservar()
        outro = Estado(self.pasta, raiz=self.estado_raiz)
        try:
            self.assertIsNone(outro.reservar())
        finally:
            outro.fechar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {'metricas': {'chamadas': 2}}, 'texto')
        self.estado.reservar()
        limites = [r[0] for r in self.estado.db.execute('SELECT limite_chamadas FROM execucoes ORDER BY inicio')]
        self.assertEqual(limites, [3, 1])

    def test_execucao_direta_nao_contorna_politica_de_dados(self):
        cadastrar(self.estado, self.projeto, {'dados': 'local'})
        self.estado.importar([self.tarefa(permitir_remoto=True)])
        binarios = self.raiz / 'bin'
        binarios.mkdir()
        marcador = self.raiz / 'agy-chamado'
        falso = binarios / 'agy'
        falso.write_text('#!/bin/sh\ntouch "' + str(marcador) + '"\nexit 1\n')
        falso.chmod(0o755)
        with patch.dict(os.environ, dict(PATH=str(binarios) + ':' + os.environ['PATH'],
                JANGADA_CORE_PATH=str(RAIZ), JANGADA_DELEGAR='agy', XDG_CONFIG_HOME=str(self.config),
                XDG_STATE_HOME=str(self.raiz / 'temporario'), XDG_CACHE_HOME=str(self.raiz / 'cache'))):
            resultado = executar_uma(self.estado, self.projeto, RAIZ, 'quality', True, None)
        self.assertEqual(resultado['status'], 'WAITING_PROVIDER')
        self.assertEqual(resultado['metricas']['chamadas'], 0)
        self.assertFalse(marcador.exists())

    def test_orcamento_desconhecido_e_custo_nao_autorizam(self):
        cadastrar(self.estado, self.projeto, {'orcamento': {'chamadas': 3}})
        self.entregar()
        self.estado.db.execute("UPDATE eventos SET dados='{}' WHERE evento='execucao_encerrada'")
        self.estado.importar([self.tarefa('T2')])
        self.assertIsNone(self.estado.reservar())
        self.assertEqual(self.estado.listar()[1]['status'], 'WAITING_QUOTA')
        cadastrar(self.estado, self.projeto, {'orcamento': {'custo_estimado': 10}})
        self.estado.alterar('T2', 'retomar')
        self.assertIsNone(self.estado.reservar())
        self.assertIn('teto de custo', self.estado.listar()[1]['motivo'])

    def test_orcamento_com_reserva_expirada_preserva_estado_e_tarefa_deterministica(self):
        politica = {'orcamento': {'chamadas': 3, 'periodo_segundos': 60}}
        cadastrar(self.estado, self.projeto, politica)
        self.estado.importar([self.tarefa()])
        self.estado.reservar()
        self.estado.db.execute("UPDATE tarefas SET prazo=0 WHERE id='T1'")
        self.estado.importar([self.tarefa('T2'), self.tarefa('T3', papel='verificador',
                             capacidade='validacao_json', risco=0)])
        spec, dono = self.estado.reservar()
        self.assertEqual(spec['id'], 'T3')
        linhas = {t['id']: t for t in self.estado.listar()}
        self.assertEqual(linhas['T1']['status'], 'REVISION_REQUIRED')
        self.assertEqual(linhas['T2']['status'], 'WAITING_QUOTA')
        self.assertIn('aguarde o fim da janela', linhas['T2']['motivo'])
        vencida = self.estado.db.execute("SELECT * FROM execucoes WHERE tarefa='T1'").fetchone()
        self.assertEqual(vencida['status'], 'REVISION_REQUIRED')
        self.assertIsNone(vencida['chamadas'])
        self.assertEqual(self.estado.db.execute("SELECT COUNT(*) FROM eventos WHERE evento='reserva_expirada'").fetchone()[0], 1)
        self.assertIsNone(self.estado.reservar())
        self.estado.finalizar('T3', dono, 'REVIEW_REQUIRED',
                             {'metricas': {'chamadas': 0, 'segundos': 0}}, 'conferência pendente')
        with self.assertRaisesRegex(ValueError, 'reserva expirada'):
            cadastrar(self.estado, self.projeto, politica)
        self.estado.db.execute('UPDATE eventos SET data=data-61')
        cadastrar(self.estado, self.projeto, politica)
        self.estado.alterar('T2', 'retomar')
        self.assertEqual(self.estado.reservar()[0]['id'], 'T2')

    def test_reassociacao_preserva_spec_e_verifica_fontes_atuais(self):
        cadastrar(self.estado, self.projeto)
        self.estado.importar([self.tarefa()])
        original = self.estado.listar()[0]['especificacao']
        self.fechar()
        novo = self.raiz / 'renomeado'
        self.projeto.rename(novo)
        dados = reassociar(self.estado_raiz, self.projeto, novo)
        self.assertEqual(dados['id'], chave(self.projeto))
        self.estado = Estado(self.estado_raiz / 'agentes/projetos' / chave(novo), raiz=self.estado_raiz)
        atual, _ = contexto_principal(self.estado, 'T1', novo)
        self.assertEqual(atual['fontes'], [str(novo / 'fonte.md')])
        self.assertEqual(self.estado.listar()[0]['especificacao'], original)
        (novo / 'fonte.md').write_text('adulterado')
        with self.assertRaises(ValueError):
            contexto_principal(self.estado, 'T1', novo)

    def test_reassociacao_recusa_projeto_em_uso(self):
        novo = self.raiz / 'novo'
        novo.mkdir()
        with self.assertRaises(ValueError):
            reassociar(self.estado_raiz, self.projeto, novo)
        self.assertTrue(self.pasta.exists())

    def test_deterministico_apos_reassociacao_reconfere_spec_imutavel(self):
        self.fonte.write_text('{"dado": 1}')
        cadastrar(self.estado, self.projeto, {'dados': 'local', 'orcamento': {'chamadas': 1}})
        self.estado.importar([self.tarefa(papel='verificador', capacidade='validacao_json', risco=0)])
        self.fechar()
        novo = self.raiz / 'renomeado'
        self.projeto.rename(novo)
        reassociar(self.estado_raiz, self.projeto, novo)
        self.estado = Estado(self.estado_raiz / 'agentes/projetos' / chave(novo), raiz=self.estado_raiz)
        resultado = executar_uma(self.estado, novo, RAIZ, 'offline', False, None)
        self.assertEqual(resultado['status'], 'COMPLETED')
        self.assertEqual(resultado['metricas']['chamadas'], 0)

    def test_consulta_com_wal_ativo_nao_escreve_na_origem(self):
        cadastrar(self.estado, self.projeto)
        self.estado.db.execute('PRAGMA wal_autocheckpoint=0')
        self.estado.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.estado.importar([self.tarefa()])
        with contextlib.closing(sqlite3.connect((self.pasta / 'tarefas.sqlite').as_uri() + '?immutable=1', uri=True)) as disco:
            self.assertEqual(disco.execute('SELECT COUNT(*) FROM tarefas').fetchone()[0], 0)
        self.estado.db.execute('BEGIN IMMEDIATE')
        self.estado.db.execute("UPDATE tarefas SET status='CANCELLED'")
        antes = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.estado_raiz.rglob('*') if p.is_file()}
        conectar = sqlite3.connect
        def sem_shm(endereco, **opcoes):
            from urllib.parse import unquote, urlparse
            copia = Path(unquote(urlparse(endereco).path))
            self.assertFalse(Path(str(copia) + '-shm').exists())
            self.assertTrue(Path(str(copia) + '-wal').exists())
            return conectar(endereco, **opcoes)
        with patch('nucleo.consultas.sqlite3.connect', side_effect=sem_shm):
            consulta = consultar(self.estado_raiz, self.projeto)
        depois = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.estado_raiz.rglob('*') if p.is_file()}
        self.estado.db.execute('ROLLBACK')
        self.assertEqual(antes, depois)
        self.assertFalse(consulta['erros'])
        self.assertEqual(consulta['tarefas'][0]['status'], 'QUEUED')

    def test_consulta_antiga_e_sessao_concluida_nao_aprovam(self):
        self.estado.importar([self.tarefa()])
        self.estado.db.execute('DROP TABLE atividades')
        self.estado.db.execute('DROP TABLE execucoes')
        self.fechar()
        agentes = self.estado_raiz / 'agentes'
        (agentes / 'sessao.json').write_text(json.dumps(dict(sessao='sessao', raiz=str(self.projeto), estado='concluido')))
        antes = {str(p): p.read_bytes() for p in self.estado_raiz.rglob('*') if p.is_file()}
        consulta = consultar(self.estado_raiz, self.projeto)
        depois = {str(p): p.read_bytes() for p in self.estado_raiz.rglob('*') if p.is_file()}
        self.assertEqual(antes, depois)
        self.assertFalse(consulta['erros'])
        self.assertEqual(consulta['sessoes'][0]['estado'], 'Em revisão')
        self.assertEqual(consulta['tarefas'][0]['estado'], 'Pronta')
        self.assertEqual(consulta['execucoes'], [])
        self.assertEqual(consulta['atividades'], [])

    def test_consulta_ausente_nao_cria_e_link_nao_le(self):
        ausente = self.raiz / 'ausente'
        self.assertEqual(consultar(ausente)['tarefas'], [])
        self.assertFalse(ausente.exists())
        (self.pasta / 'projeto.json').symlink_to(self.fonte)
        self.assertTrue(consultar(self.estado_raiz)['erros'])

    def test_especificacao_corrompida_vira_erro_de_consulta(self):
        self.estado.importar([self.tarefa()])
        self.estado.db.execute("UPDATE tarefas SET especificacao='[]'")
        resultado = consultar(self.estado_raiz, self.projeto)
        self.assertEqual(resultado['tarefas'], [])
        self.assertTrue(resultado['erros'])

    def test_sessao_sem_cadastro_recebe_projeto_transitorio(self):
        agentes = self.estado_raiz / 'agentes'
        caminho = str(self.raiz / 'worktree-sem-cadastro')
        (agentes / 'avulsa.json').write_text(json.dumps(dict(sessao='avulsa', raiz=caminho, estado='ativo')))
        antes = {str(p): p.read_bytes() for p in self.estado_raiz.rglob('*') if p.is_file()}
        resultado = consultar(self.estado_raiz)
        self.assertFalse(resultado['erros'])
        sessao = resultado['sessoes'][0]
        projeto = next(p for p in resultado['projetos'] if p['id'] == sessao['projeto'])
        self.assertEqual(projeto['caminho'], caminho)
        self.assertEqual(projeto['id'], chave(caminho))
        self.assertEqual(antes, {str(p): p.read_bytes() for p in self.estado_raiz.rglob('*') if p.is_file()})

    def test_consulta_eventos_preserva_identidade_e_dados(self):
        cadastrar(self.estado, self.projeto)
        self.estado.importar([self.tarefa()])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVIEW_REQUIRED', {'metricas': {'chamadas': 1}}, 'texto')
        esperados = [dict(r) for r in self.estado.db.execute('SELECT seq,tarefa,data,evento,dados FROM eventos ORDER BY seq')]
        for r in esperados:
            r.update(projeto=chave(self.projeto), dados=json.loads(r['dados']))
        resultado = consultar(self.estado_raiz, self.projeto)
        self.assertFalse(resultado['erros'])
        self.assertEqual(resultado['eventos'], esperados)

    def test_catalogos_retem_sucessos_e_identifica_falhas(self):
        capacidades = subprocess.CompletedProcess([], 0, json.dumps({'perfis': [{'nome': 'codex-local'}], 'principais': []}))
        for falha in (subprocess.CalledProcessError(1, ['jangada-config']),
                      subprocess.CompletedProcess([], 0, '{inválido'),
                      subprocess.TimeoutExpired(['jangada-config'], 10)):
            with self.subTest(falha=type(falha).__name__), patch('nucleo.consultas.subprocess.run',
                    side_effect=[falha, subprocess.CompletedProcess([], 0, '{"valores": []}'), capacidades]) as rodar:
                resultado = catalogos(RAIZ)
            self.assertEqual(resultado['provedores'], [])
            self.assertEqual(resultado['perfis'], [{'nome': 'codex-local'}])
            self.assertEqual(resultado['configuracao'], {'valores': []})
            self.assertEqual(resultado['erros'], ['catálogo indisponível: provedores'])
            self.assertTrue(all(c.kwargs['timeout'] == 10 for c in rodar.call_args_list))

    def test_atividade_calculada_nao_grava_estado(self):
        cadastrar(self.estado, self.projeto)
        atividade = self.estado.criar_atividade('Leitura', 'Conferir', ['Fidelidade'])
        self.estado.importar([self.tarefa(atividade=atividade)])
        consulta = consultar(self.estado_raiz, self.projeto)
        self.assertEqual(consulta['atividades'][0]['estado'], 'Pronta')
        self.assertNotIn('estado', dict(self.estado.db.execute('SELECT * FROM atividades').fetchone()))

    def test_modos_nao_confundem_perfil_e_exigem_confirmacao(self):
        (self.config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        cadastrar(self.estado, self.projeto)
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, {'JANGADA_DELEGAR': 'local'}):
            consulta = decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'assistido')
            self.assertIsNone(consulta['executor'])
            with self.assertRaises(ValueError):
                decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'assistido', 'local')
            manual = decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'manual', 'local')
            self.assertEqual(manual['executor'], 'local')
            automatico = decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'automatico_supervisionado')
            self.assertIsNone(automatico['executor'])

    def test_automatico_exige_saude_atual_e_politica(self):
        (self.config / 'delegacao.json').write_text(json.dumps({'leitura_documental': ['local']}))
        cadastrar(self.estado, self.projeto)
        self.estado.importar([self.tarefa()])
        global_estado = Estado(self.estado_raiz / 'agentes/runtime', raiz=self.estado_raiz)
        try:
            saude = Saude(global_estado)
            saude.observar('local', 'AVAILABLE', 'serviço local conferido', validade=60)
            with patch.dict(os.environ, {'JANGADA_DELEGAR': 'local'}):
                rota = decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'automatico_supervisionado')
                self.assertEqual(rota['executor'], 'local')
                cadastrar(self.estado, self.projeto, {'provedores': []})
                rota = decidir(self.estado_raiz, self.projeto, RAIZ, self.config, 'T1', 'automatico_supervisionado')
                self.assertIsNone(rota['executor'])
        finally:
            global_estado.fechar()

    def test_acoes_encaminham_sem_shell_e_exigem_confirmacao(self):
        with patch('subprocess.run') as chamar:
            acao(RAIZ, 'tarefa', ['T1', 'pausar'])
            self.assertEqual(chamar.call_args.args[0], [str(RAIZ / 'bin/jangada-task'), 'T1', 'pausar'])
            self.assertNotIn('shell', chamar.call_args.kwargs)
            with self.assertRaises(ValueError):
                acao(RAIZ, 'integrar', ['sessao'])
            with self.assertRaises(ValueError):
                acao(RAIZ, 'tarefa', ['T1', 'cancelar'])

    def test_cli_isolado_recusa_politica_reassociacao_e_ciclo_de_sessao(self):
        cadastrar(self.estado, self.projeto, {'dados': 'local'})
        politica = self.raiz / 'politica.json'
        politica.write_text('{}')
        ambiente = dict(os.environ, JANGADA_ESTADO=str(self.estado_raiz), JANGADA_CORE_PATH=str(RAIZ),
                        JANGADA_CONFIG=str(self.config), PYTHONPATH=str(RAIZ), JANGADA_ISOLADO='1')
        comando = [sys.executable, str(RAIZ / 'nucleo/cli.py'), '--projeto', str(self.projeto)]
        antes = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.estado_raiz.rglob('*') if p.is_file()}
        for argumentos in (['cadastrar', '--politica', str(politica)],
                           ['reassociar', str(self.raiz / 'novo')],
                           ['sessao-iniciar', 'nova', '--executor', 'codex'],
                           ['sessao-abortar', 'nova', '--execucao', 'exe-inexistente'],
                           ['sessao-encerrar', 'nova', '--integrada']):
            with self.subTest(argumentos=argumentos):
                resposta = subprocess.run([*comando, *argumentos], env=ambiente, capture_output=True, text=True)
                self.assertNotEqual(resposta.returncode, 0)
                self.assertIn('fora do isolamento', resposta.stderr)
                self.assertEqual(antes, {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                                         for p in self.estado_raiz.rglob('*') if p.is_file()})

    def test_cli_cadastro_atividade_consulta_sem_provedor(self):
        ambiente = dict(os.environ, JANGADA_CORE_PATH=str(RAIZ), XDG_CONFIG_HOME=str(self.config),
                        XDG_STATE_HOME=str(self.estado_raiz.parent), JANGADA_ISOLADO='')
        comando = [str(RAIZ / 'bin/jangada-projeto'), '--projeto', str(self.projeto)]
        resposta = subprocess.run([*comando, 'atividade', '--titulo', 'Teste', '--objetivo', 'Conferir',
                                   '--criterio', 'Critério'], env=ambiente, capture_output=True, text=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        consulta = subprocess.run([*comando, 'consultar'], env=ambiente, capture_output=True, text=True)
        self.assertEqual(len(json.loads(consulta.stdout)['atividades']), 1)


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
