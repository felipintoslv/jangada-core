"""Consultas reais em origem sintética, sem controlador, rede ou modelos."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'orquestracao'))
os.environ['JANGADA_CORE_PY'] = str(REPO)
from nucleo import consultas
from metricas_projeto import calcular


def retrato(pasta):
    return sorted((str(p.relative_to(pasta)), p.lstat().st_mode,
                   os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else '')
                  for p in pasta.rglob('*'))


def criar_banco(caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(caminho, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA wal_autocheckpoint=0;
        CREATE TABLE tarefas (id TEXT, especificacao TEXT, status TEXT, tentativas INTEGER,
          motivo TEXT, criado REAL, atualizado REAL, resultado TEXT);
        CREATE TABLE eventos (seq INTEGER PRIMARY KEY, tarefa TEXT, evento TEXT, dados TEXT);
        CREATE TABLE provedores (id TEXT, status TEXT, pausado INTEGER, falhas INTEGER,
          motivo TEXT, atualizado REAL, valido_ate REAL, cota REAL, modelo TEXT);
    ''')
    return db


class ConsultasModulos(unittest.TestCase):
    def test_coordenadores_ciclo_legado_e_consulta_sem_escrita(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            registros = raiz / 'coordenadores'
            registros.mkdir()
            copias = raiz / 'revisoes'
            copias.mkdir()
            identidade = 'a' * 32
            casos = {
                'aberto': dict(atuacao_id=identidade, ciclo='aberta', estado='concluido'),
                'vivo': dict(atuacao_id='b' * 32, ciclo='aberta', estado='trabalhando'),
                'legado': dict(estado='encerrado'),
                'encerrado': dict(estado='encerrado', encerrado='2026-10-18T12:00:00+00:00'),
                'fim': dict(atuacao_id='c' * 32, ciclo='encerrada', estado='encerrado',
                            encerrado='2026-10-18T12:00:00+00:00'),
            }
            for nome, extra in casos.items():
                dados = dict(sessao=nome + '--coordenador', projeto='/sintetico/' + nome,
                             provedor='codex', desde='2026-10-18T10:00:00+00:00', **extra)
                (registros / (dados['sessao'] + '.json')).write_text(json.dumps(dados))
            (copias / 'aberto--tarefa.json').write_text(json.dumps(dict(
                sessao='aberto--tarefa', coordenador_sessao='aberto--coordenador')))
            antes = retrato(raiz)
            consulta = subprocess.run(
                [sys.executable, str(REPO / 'nucleo/coordenadores.py'), str(raiz)],
                input='vivo--coordenador\naberto--tarefa\n', text=True, capture_output=True, check=True)
            resposta = json.loads(consulta.stdout)
            self.assertEqual(resposta['versao'], 1)
            self.assertEqual(retrato(raiz), antes)
            por_nome = {c['sessao'].split('--')[0]: c for c in resposta['coordenadores']}
            campos = {'sessao', 'projeto', 'provedor', 'estado', 'ultima_linha',
                      'atualizado', 'viva', 'tarefas', 'ciclo', 'atuacao_id', 'retomavel'}
            self.assertTrue(all(set(c) == campos for c in por_nome.values()))
            for nome in ('aberto', 'legado'):
                self.assertEqual(por_nome[nome]['ciclo'], 'aberta')
                self.assertTrue(por_nome[nome]['retomavel'])
                self.assertFalse(por_nome[nome]['viva'])
            self.assertIsNone(por_nome['legado']['atuacao_id'])
            self.assertEqual(por_nome['aberto']['atuacao_id'], identidade)
            self.assertEqual(por_nome['aberto']['tarefas'], [dict(sessao='aberto--tarefa', viva=True)])
            self.assertTrue(por_nome['vivo']['viva'])
            self.assertFalse(por_nome['vivo']['retomavel'])
            for nome in ('encerrado', 'fim'):
                self.assertEqual(por_nome[nome]['ciclo'], 'encerrada')
                self.assertFalse(por_nome[nome]['retomavel'])
                self.assertFalse(por_nome[nome]['viva'])
            self.assertIsNone(por_nome['encerrado']['atuacao_id'])
            (registros / 'invalido--coordenador.json').write_text('{')
            antes = retrato(raiz)
            consulta = subprocess.run(
                [sys.executable, str(REPO / 'nucleo/coordenadores.py'), str(raiz)],
                input='', text=True, capture_output=True)
            self.assertEqual(consulta.returncode, 1)
            self.assertEqual(consulta.stdout, '')
            self.assertEqual(retrato(raiz), antes)

    def test_filas_conteudo_precos_wal_e_provedores(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            projeto = raiz / 'projeto'
            identificador = hashlib.sha256(str(projeto).encode()).hexdigest()
            banco = raiz / 'agentes/projetos' / identificador / 'tarefas.sqlite'
            db = criar_banco(banco)
            runtime = criar_banco(raiz / 'agentes/runtime/tarefas.sqlite')
            spec = dict(papel='leitor', capacidade='leitura_documental', risco=1,
                        max_chamadas=4, tempo_total=120, dependencias=[])
            db.execute('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                       ('leitura', json.dumps(spec), 'REVIEW_REQUIRED', 1, 'aguarda', 1, 2, None))
            dependente = dict(spec, dependencias=['leitura'])
            db.execute('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                       ('dependente', json.dumps(dependente), 'QUEUED', 0, '', 1, 2, None))
            db.execute('INSERT INTO eventos VALUES (?,?,?,?)', (1, 'leitura', 'execucao_encerrada',
                       json.dumps(dict(status='REVIEW_REQUIRED', artefato='relato', resultado=dict(
                           metricas=dict(chamadas=1, segundos=5), executor='codex-economico',
                           delegacao=dict(modelo='sintetico', tokens_codex_entrada=100, tokens_codex_saida=20))))))
            runtime.execute('INSERT INTO provedores VALUES (?,?,?,?,?,?,?,?,?)',
                            ('codex', 'AVAILABLE', 0, 0, 'observado', 1, 1, 80, 'sintetico'))
            precos = dict(moeda='BRL', precos={'codex-economico': {'sintetico':
                          dict(entrada_por_milhao=10, saida_por_milhao=20)}})
            class Legado:
                def __init__(self, conexao):
                    self.db = conexao
                def listar(self):
                    tarefas = [dict(r) for r in self.db.execute('SELECT * FROM tarefas ORDER BY criado,id')]
                    for t in tarefas:
                        t['especificacao'] = json.loads(t['especificacao'])
                    return tarefas
            esperado = calcular(Legado(db), precos)
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE tarefas SET status='FAILED' WHERE id='leitura'")
            antes = retrato(raiz)
            consulta = consultas.consultar_filas(raiz, [projeto], precos)
            self.assertEqual(retrato(raiz), antes)
            self.assertEqual(consulta['versao'], 1)
            self.assertEqual(consulta['erros'], [])
            fila = consulta['projetos'][0]
            self.assertEqual(fila['caminho'], str(projeto))
            self.assertEqual(fila['metricas'], esperado)
            self.assertEqual(fila['consumos']['leitura'], dict(chamadas=1, segundos=5))
            self.assertEqual(fila['metricas']['custo_estimado'], 0.0014)
            self.assertEqual({t['id']: t['status'] for t in fila['tarefas']},
                             dict(leitura='REVIEW_REQUIRED', dependente='QUEUED'))
            codex = next(p for p in consulta['provedores'] if p['id'] == 'codex')
            self.assertEqual(codex['status'], 'UNKNOWN')
            self.assertIsNone(codex['cota'])
            with consultas.banco_leitura(banco) as copia:
                with self.assertRaises(sqlite3.OperationalError):
                    copia.execute('DELETE FROM tarefas')
            self.assertEqual(retrato(raiz), antes)
            db.execute('ROLLBACK')
            db.close()
            runtime.close()

    def test_ausencia_erro_versao_links_fifo_e_limites(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            resposta = consultas.consultar_filas(raiz)
            self.assertEqual(resposta, dict(versao=1, projetos=[], provedores=[], erros=[]))
            self.assertEqual(retrato(raiz), [])
            pasta = raiz / 'agentes/projetos/um'
            caminho = pasta / 'tarefas.sqlite'
            db = criar_banco(caminho)
            db.close()
            for fonte in ('banco', 'wal', 'shm', 'projeto', 'projetos', 'agentes', 'runtime'):
                alvo = {'banco': caminho, 'wal': Path(str(caminho) + '-wal'),
                        'shm': Path(str(caminho) + '-shm'), 'projeto': pasta,
                        'projetos': pasta.parent, 'agentes': raiz / 'agentes',
                        'runtime': raiz / 'agentes/runtime'}[fonte]
                if fonte == 'runtime':
                    alvo.mkdir()
                backup = alvo.with_name(alvo.name + '-guardado')
                existia = alvo.exists()
                if existia:
                    alvo.rename(backup)
                for tipo in ('link', 'fifo'):
                    if tipo == 'link':
                        alvo.symlink_to(backup if existia else caminho)
                    else:
                        os.mkfifo(alvo)
                    antes = retrato(raiz)
                    resultado = consultas.consultar_filas(raiz)
                    self.assertTrue(resultado['erros'], (fonte, tipo, resultado))
                    self.assertEqual(retrato(raiz), antes)
                    alvo.unlink()
                if existia:
                    backup.rename(alvo)
            for valor in ('corrompido', 'versao', 'json', 'tipo'):
                caminho.unlink()
                if valor == 'corrompido':
                    caminho.write_text('não é SQLite')
                else:
                    db = criar_banco(caminho)
                    if valor == 'versao':
                        db.execute('PRAGMA user_version=9')
                    else:
                        db.execute('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                                   ('x', '{' if valor == 'json' else '[]', 'QUEUED', 0, '', 1, 1, None))
                    db.close()
                antes = retrato(raiz)
                resultado = consultas.consultar_filas(raiz)
                self.assertEqual(resultado['projetos'], [])
                self.assertTrue(resultado['erros'], valor)
                self.assertEqual(retrato(raiz), antes)

    def test_limites_e_fila_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            caminho = raiz / 'agentes/projetos/um/tarefas.sqlite'
            db = criar_banco(caminho)
            self.assertEqual(consultas.consultar_filas(raiz)['projetos'][0]['tarefas'], [])
            db.execute('BEGIN')
            db.executemany('INSERT INTO eventos VALUES (?,?,?,?)',
                           ((n, 'x', 'observacao', '{}') for n in range(16385)))
            db.execute('COMMIT')
            self.assertEqual(consultas.consultar_filas(raiz)['erros'], [])
            db.execute('DELETE FROM eventos')
            db.execute('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                       ('x', json.dumps(dict(papel='leitor', capacidade='x', pedido='x' * 1048576)),
                        'QUEUED', 0, '', 1, 1, None))
            self.assertEqual(consultas.consultar_filas(raiz)['erros'], [])
            db.execute('DELETE FROM tarefas')
            db.execute('BEGIN')
            db.executemany('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                           ((str(n), '{}', 'QUEUED', 0, '', 1, 1, None) for n in range(16385)))
            db.execute('COMMIT')
            self.assertTrue(consultas.consultar_filas(raiz)['erros'])
            db.close()
            with caminho.open('wb') as arquivo:
                arquivo.truncate(64 * 1024 * 1024 + 1)
            antes = retrato(raiz)
            self.assertTrue(consultas.consultar_filas(raiz)['erros'])
            self.assertEqual(retrato(raiz), antes)

    def test_pedidos_longos_nao_incham_resposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            projeto = raiz / 'original'
            projeto.mkdir()
            atalho = raiz / 'atalho'
            atalho.symlink_to(projeto, target_is_directory=True)
            identificador = hashlib.sha256(str(projeto).encode()).hexdigest()
            db = criar_banco(raiz / 'agentes/projetos' / identificador / 'tarefas.sqlite')
            spec = dict(papel='leitor', capacidade='leitura_documental', pedido='p' * 9000)
            db.execute('BEGIN')
            db.executemany('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                           ((str(n), json.dumps(spec), 'QUEUED', 0, '', 1, 1, '{"relato":"privado"}') for n in range(400)))
            db.execute('COMMIT')
            antes = retrato(raiz)
            consulta = consultas.consultar_filas(raiz, [atalho])
            self.assertEqual(consulta['erros'], [])
            fila = consulta['projetos'][0]
            self.assertEqual(fila['caminho'], str(atalho))
            self.assertEqual(len(fila['tarefas']), 400)
            self.assertLess(len(json.dumps(consulta).encode()), 1024 * 1024)
            self.assertEqual(set(fila['tarefas'][0]), {'id', 'status', 'tentativas', 'motivo', 'atualizado', 'especificacao'})
            self.assertEqual(fila['tarefas'][0]['especificacao'], dict(papel='leitor', capacidade='leitura_documental'))
            self.assertEqual(retrato(raiz), antes)
            db.close()

    def test_estouro_de_projeto_preserva_provedores_e_demais_filas(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            bancos = []
            for nome, tamanho in (('a', 600000), ('b', 600000), ('c', 1)):
                db = criar_banco(raiz / 'agentes/projetos' / nome / 'tarefas.sqlite')
                spec = dict(papel='leitor', capacidade='leitura_documental')
                db.execute('INSERT INTO tarefas VALUES (?,?,?,?,?,?,?,?)',
                           ('t', json.dumps(spec), 'QUEUED', 0, 'x' * tamanho, 1, 1, None))
                bancos.append(db)
            runtime = criar_banco(raiz / 'agentes/runtime/tarefas.sqlite')
            bancos.append(runtime)
            antes = retrato(raiz)
            consulta = consultas.consultar_filas(raiz)
            self.assertEqual([p['id'] for p in consulta['projetos']], ['a', 'c'])
            self.assertEqual([e['projeto'] for e in consulta['erros']], ['b'])
            self.assertEqual({p['id'] for p in consulta['provedores']}, {'agy', 'local'})
            self.assertLessEqual(len(json.dumps(consulta).encode()), 1024 * 1024)
            self.assertEqual(retrato(raiz), antes)
            for db in bancos:
                db.close()


if __name__ == '__main__':
    unittest.main()
