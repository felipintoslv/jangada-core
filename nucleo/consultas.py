"""Visão conjunta somente leitura; ausência de registro não é aprovação."""

import contextlib
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'orquestracao'))
from projetos import chave, ler_json, ler_projeto  # noqa: E402
from confianca import conferir_conclusao  # noqa: E402

ESTADOS = {'QUEUED': 'Pronta', 'RUNNING': 'Executando', 'COMPLETED': 'Concluída',
           'REVIEW_REQUIRED': 'Em revisão', 'REVISION_REQUIRED': 'Em revisão',
           'WAITING_REVIEWER': 'Em revisão', 'WAITING_PROVIDER': 'Bloqueada',
           'WAITING_QUOTA': 'Bloqueada', 'BLOCKED': 'Bloqueada', 'PAUSED': 'Bloqueada',
           'FAILED': 'Falhou', 'CANCELLED': 'Cancelada'}
SESSOES = {'iniciado': 'Executando', 'ativo': 'Executando', 'trabalhando': 'Executando',
           'aguardando': 'Bloqueada', 'concluido': 'Em revisão', 'interrompido': 'Bloqueada'}


@contextlib.contextmanager
def banco_leitura(caminho, limite=None):
    # Mesmo mode=ro pode criar WAL/SHM na origem. Uma cópia estável inclui o WAL
    # para não perder transações já confirmadas que ainda não chegaram ao banco.
    caminho = Path(caminho)
    with tempfile.TemporaryDirectory(prefix='jangada-consulta-') as pasta:
        copia = Path(pasta) / caminho.name
        for _ in range(3):
            antes = {}
            for nome in (caminho, Path(str(caminho) + '-wal')):
                destino = Path(pasta) / nome.name
                try:
                    fd = os.open(nome, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                except FileNotFoundError:
                    destino.unlink(missing_ok=True)
                    antes[nome] = None
                    continue
                with os.fdopen(fd, 'rb') as origem, destino.open('wb') as saida:
                    info = os.fstat(origem.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError('banco deve ser arquivo regular')
                    if limite is not None and info.st_size > limite:
                        raise ValueError('banco excedeu limite de leitura')
                    antes[nome] = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                    tamanho = 0
                    while bloco := origem.read(1024 * 1024):
                        tamanho += len(bloco)
                        if limite is not None and tamanho > limite:
                            raise ValueError('banco excedeu limite de leitura')
                        saida.write(bloco)
            depois = {}
            for nome in antes:
                try:
                    info = nome.lstat()
                    depois[nome] = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                except FileNotFoundError:
                    depois[nome] = None
            if antes == depois:
                break
        else:
            raise ValueError('banco mudou durante a consulta; tente novamente')
        db = sqlite3.connect(copia.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=5)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            yield db
        finally:
            db.close()


def listar_tarefas(db, pasta):
    resultado = []
    for linha in db.execute('SELECT * FROM tarefas ORDER BY criado,id'):
        item = conferir_conclusao(pasta, dict(linha))
        item['especificacao'] = json.loads(item['especificacao'])
        item['resultado'] = json.loads(item['resultado']) if item['resultado'] else None
        resultado.append(item)
    return resultado


def consumo_tarefa(db, identificador):
    chamadas, segundos = 0, 0
    for linha in db.execute('SELECT evento,dados FROM eventos WHERE tarefa=? AND evento IN (?,?)',
                            (identificador, 'execucao_encerrada', 'reserva_expirada')):
        if linha['evento'] == 'reserva_expirada':
            chamadas = None
            continue
        resultado = json.loads(linha['dados']).get('resultado')
        metrica = resultado.get('metricas') if isinstance(resultado, dict) else None
        if not isinstance(metrica, dict):
            chamadas = None
            continue
        quantidade = metrica.get('chamadas')
        duracao = metrica.get('segundos')
        if type(quantidade) is not int or quantidade < 0:
            chamadas = None
        elif chamadas is not None:
            chamadas += quantidade
        if type(duracao) is int and duracao >= 0:
            segundos += duracao
        else:
            chamadas = None
    return {'chamadas': chamadas, 'segundos': segundos}


def listar_provedores(db):
    mapa = {linha['id']: dict(linha) for linha in db.execute('SELECT * FROM provedores')}
    for provedor in ('local', 'agy'):
        mapa.setdefault(provedor, {'id': provedor, 'status': 'UNKNOWN', 'pausado': 0,
                                   'falhas': 0, 'motivo': 'sem observação', 'atualizado': 0,
                                   'valido_ate': 0, 'cota': None, 'modelo': None})
    agora = time.time()
    for item in mapa.values():
        if item['pausado']:
            item.update(status='UNAVAILABLE', motivo='provedor pausado')
        elif item['valido_ate'] <= agora:
            item.update(status='UNKNOWN', motivo='observação ausente ou expirada', cota=None)
        elif item['id'] in {'agy', 'codex'} and item['status'] == 'AVAILABLE' and item['cota'] is None:
            item.update(status='UNKNOWN', motivo='cota não confirmada')
        item['espera_segundos'] = max(0, math.ceil(item['valido_ate'] - agora)) if item['status'] == 'COOLDOWN' else 0
    return [mapa[nome] for nome in sorted(mapa)]


def agregado(estados):
    if not estados:
        return 'Planejada'
    if all(e == 'Concluída' for e in estados):
        return 'Concluída'
    if all(e == 'Cancelada' for e in estados):
        return 'Cancelada'
    return next((e for e in ('Executando', 'Falhou', 'Em revisão', 'Bloqueada', 'Pronta', 'Planejada')
                 if e in estados), 'Bloqueada')


def consultar(raiz, projeto=None):
    raiz = Path(raiz).resolve()
    filtro = str(Path(projeto).resolve()) if projeto is not None else None
    resultado = dict(projetos=[], atividades=[], tarefas=[], sessoes=[], execucoes=[], revisoes=[], eventos=[], erros=[])
    pastas = raiz / 'agentes/projetos'
    if pastas.is_symlink() or (raiz / 'agentes').is_symlink():
        resultado['erros'].append('estado operacional com ligação simbólica')
        return resultado
    for pasta in sorted(pastas.glob('*')):
        if filtro and pasta.name != chave(filtro):
            continue
        if not pasta.is_dir():
            continue
        try:
            if pasta.is_symlink():
                raise ValueError('pasta do projeto com ligação simbólica')
            dados = ler_projeto(pasta)
            if filtro and dados and dados['caminho'] != filtro:
                raise ValueError('registro pertence a outro caminho')
            dados = dados or dict(id=pasta.name, caminho=filtro, nome='projeto-' + pasta.name[:12], politica={})
            resultado['projetos'].append(dados)
            banco = pasta / 'tarefas.sqlite'
            if not banco.exists():
                continue
            if any((pasta / n).is_symlink() for n in ('tarefas.sqlite', 'tarefas.sqlite-wal', 'tarefas.sqlite-shm')):
                raise ValueError('banco com ligação simbólica')
            with banco_leitura(banco) as db:
                tabelas = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                tarefas = [conferir_conclusao(pasta, dict(r)) for r in db.execute('SELECT * FROM tarefas ORDER BY criado,id')]
                estados = {t['id']: t['status'] for t in tarefas}
                for tarefa in tarefas:
                    spec = json.loads(tarefa['especificacao'])
                    if not isinstance(spec, dict):
                        raise ValueError('especificação de tarefa inválida')
                    tarefa['especificacao'] = spec
                    tarefa['resultado'] = json.loads(tarefa['resultado']) if tarefa['resultado'] else None
                    if tarefa['resultado'] is not None and not isinstance(tarefa['resultado'], dict):
                        raise ValueError('resultado de tarefa inválido')
                    bloqueada = tarefa['status'] == 'QUEUED' and any(estados.get(d) != 'COMPLETED' for d in spec.get('dependencias', []))
                    tarefa.update(projeto=dados['id'], atividade=spec.get('atividade'),
                                  estado='Bloqueada' if bloqueada else ESTADOS.get(tarefa['status'], 'Bloqueada'))
                    resultado['tarefas'].append(tarefa)
                if 'atividades' in tabelas:
                    for r in db.execute('SELECT * FROM atividades ORDER BY criado,id'):
                        atividade = dict(r, projeto=dados['id'])
                        atividade['criterios'] = json.loads(atividade['criterios'])
                        resultado['atividades'].append(atividade)
                if 'execucoes' in tabelas:
                    for r in db.execute('SELECT * FROM execucoes ORDER BY inicio,id'):
                        execucao = dict(r, projeto=dados['id'])
                        if execucao.get('roteamento'):
                            execucao['roteamento'] = json.loads(execucao['roteamento'])
                        resultado['execucoes'].append(execucao)
                for r in db.execute("SELECT tarefa,data,dados FROM eventos WHERE evento='revisada' ORDER BY seq"):
                    resultado['revisoes'].append(dict(projeto=dados['id'], tarefa=r['tarefa'], data=r['data'],
                                                      **json.loads(r['dados'])))
                for r in db.execute('SELECT seq,tarefa,data,evento,dados FROM eventos ORDER BY seq'):
                    resultado['eventos'].append(dict(projeto=dados['id'], seq=r['seq'], tarefa=r['tarefa'],
                                                     data=r['data'], evento=r['evento'], dados=json.loads(r['dados'])))
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as erro:
            resultado['erros'].append(f'{pasta.name}: {erro}')
    for arquivo in sorted((raiz / 'agentes').glob('*.json')):
        pertence = False
        try:
            dados = ler_json(arquivo)
            if not isinstance(dados, dict) or not isinstance(dados.get('sessao'), str):
                continue
            caminho = dados.get('raiz')
            if not isinstance(caminho, str) or not Path(caminho).is_absolute():
                raise ValueError('sessão sem raiz válida')
            pertence = filtro is not None and str(Path(caminho).resolve()) == filtro
            if filtro and not pertence:
                continue
            p = next((p for p in resultado['projetos'] if p['caminho'] == caminho or p['id'] == chave(caminho)), None)
            if p is None:
                p = dict(id=chave(caminho), caminho=caminho, nome=Path(caminho).name, politica={})
                resultado['projetos'].append(p)
            resultado['sessoes'].append({**dados, 'projeto': p['id'],
                                         'estado_persistido': dados.get('estado'),
                                         'estado': SESSOES.get(dados.get('estado'), 'Bloqueada')})
        except (OSError, ValueError, KeyError, TypeError) as erro:
            if filtro is None or pertence:
                resultado['erros'].append(f'{arquivo.name}: {erro}')
    for atividade in resultado['atividades']:
        estados = [t['estado'] for t in resultado['tarefas'] if t['projeto'] == atividade['projeto']
                   and t['atividade'] == atividade['id']]
        estados += [s['estado'] for s in resultado['sessoes'] if s['projeto'] == atividade['projeto']
                    and s.get('atividade') == atividade['id']]
        atividade['estado'] = agregado(estados)
    return resultado


def registro_provedores(raiz):
    resposta = subprocess.run([str(Path(raiz) / 'bin/jangada-config'), '--provedores-json'],
                              capture_output=True, text=True, timeout=10, check=True)
    dados = json.loads(resposta.stdout)
    if not isinstance(dados, list) or any(not isinstance(p, dict) or not isinstance(p.get('id'), str) for p in dados):
        raise ValueError('registro de provedores inválido')
    return dados


def catalogos(raiz):
    raiz = Path(raiz)
    dados = {'provedores': [], 'perfis': [], 'principais': [], 'configuracao': None, 'erros': []}
    for comando, campo in [(['jangada-config', '--provedores-json'], 'provedores'),
                           (['jangada-config', '--publico-json'], 'configuracao'),
                           (['jangada-agente', '--capacidades-json'], 'capacidades')]:
        try:
            resposta = subprocess.run([str(raiz / 'bin' / comando[0]), *comando[1:]],
                                      capture_output=True, text=True, timeout=10, check=True)
            valor = json.loads(resposta.stdout)
            if campo == 'capacidades':
                dados['perfis'] = valor['perfis']
                dados['principais'] = valor['principais']
            else:
                dados[campo] = valor
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            dados['erros'].append('catálogo indisponível: ' + campo)
    return dados


class ConsultaFila:
    """Adaptador interno para métricas existentes, sobre cópia privada."""

    def __init__(self, db, pasta):
        self.db, self.pasta = db, pasta

    def listar(self):
        return listar_tarefas(self.db, self.pasta)


def consultar_filas(raiz, projetos=(), precos=None):
    """Contrato v1: filas, consumo, métricas e provedores, sem caminhos de bancos."""
    from metricas_projeto import calcular

    raiz = Path(raiz).resolve()
    caminhos = {chave(p): str(p) for p in projetos}
    resultado = dict(versao=1, projetos=[], provedores=[], erros=[])
    limite = 1024 * 1024

    def conferir_resposta(dados, reserva=0):
        if len(json.dumps(dados, ensure_ascii=False, allow_nan=False).encode('utf-8')) > limite - reserva:
            raise ValueError('Resposta das filas excedeu 1 MiB.')

    @contextlib.contextmanager
    def diretorio(pasta):
        try:
            fd = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            fd = None
        try:
            # O descritor fixa cada componente abaixo da raiz contra troca por link.
            yield Path('/proc/self/fd') / str(fd) if fd is not None else None
        finally:
            if fd is not None:
                os.close(fd)

    def banco(pasta):
        for sufixo in ('', '-wal', '-shm'):
            arquivo = pasta / ('tarefas.sqlite' + sufixo)
            try:
                info = arquivo.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Banco deve ser regular sem link.')
        return (pasta / 'tarefas.sqlite').exists()

    def conferir_db(db, tabelas):
        # O esquema legado usa user_version=0. Versão desconhecida exige migração.
        if db.execute('PRAGMA user_version').fetchone()[0] != 0:
            raise ValueError('Versão do banco desconhecida.')
        for tabela in tabelas:
            quantidade = db.execute('SELECT count(*) FROM ' + tabela).fetchone()[0]
            if quantidade > 16384:
                raise ValueError('Fila excedeu 16384 registros por tabela.')

    try:
        with diretorio(raiz / 'agentes') as agentes:
            if agentes is None:
                return resultado
            try:
                with diretorio(agentes / 'runtime') as runtime:
                    if runtime is not None and banco(runtime):
                        with banco_leitura(runtime / 'tarefas.sqlite', limite=64 * limite) as db:
                            conferir_db(db, ('provedores',))
                            provedores = listar_provedores(db)
                            conferir_resposta(dict(resultado, provedores=provedores), reserva=1024)
                            resultado['provedores'] = provedores
            except (OSError, ValueError, KeyError, TypeError, RecursionError, sqlite3.Error) as erro:
                resultado['erros'].append(dict(projeto=None, caminho=None, mensagem='provedores: ' + str(erro)))
            try:
                with diretorio(agentes / 'projetos') as pastas:
                    nomes = sorted(pastas.iterdir()) if pastas is not None else []
                    if len(nomes) > 4096:
                        raise ValueError('Consulta excedeu 4096 projetos.')
                    for pasta in nomes:
                        identificador = pasta.name
                        caminho = caminhos.get(identificador)
                        try:
                            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', identificador) or identificador in ('.', '..'):
                                raise ValueError('Identificador de projeto inválido.')
                            with diretorio(pasta) as fixa:
                                if fixa is None or not banco(fixa):
                                    continue
                                with banco_leitura(fixa / 'tarefas.sqlite', limite=64 * limite) as db:
                                    conferir_db(db, ('tarefas',))
                                    consulta = ConsultaFila(db, raiz / 'agentes/projetos' / identificador)
                                    tarefas = consulta.listar()
                                    for tarefa in tarefas:
                                        spec = tarefa['especificacao']
                                        if not isinstance(spec, dict) or (tarefa['resultado'] is not None
                                                and not isinstance(tarefa['resultado'], dict)):
                                            raise ValueError('Especificação ou resultado deve ser objeto JSON.')
                                        if (not isinstance(tarefa['id'], str) or not tarefa['id']
                                                or len(tarefa['id']) > 255 or any(ord(c) < 32 for c in tarefa['id'])
                                                or not isinstance(tarefa['status'], str)
                                                or type(tarefa['tentativas']) is not int or tarefa['tentativas'] < 0
                                                or tarefa['motivo'] is not None and not isinstance(tarefa['motivo'], str)):
                                            raise ValueError('Campos de tarefa inválidos.')
                                        if (any(not isinstance(spec.get(c), str) for c in ('papel', 'capacidade'))
                                                or not isinstance(spec.get('dependencias', []), list)
                                                or any(not isinstance(d, str) for d in spec.get('dependencias', []))
                                                or any(type(spec.get(c, padrao)) is not int or spec.get(c, padrao) < 0
                                                       for c, padrao in (('max_chamadas', 8), ('tempo_total', 600)))):
                                            raise ValueError('Campos da especificação inválidos.')
                                    apresentacao = []
                                    for t in tarefas:
                                        item_tarefa = {c: t[c] for c in ('id', 'status', 'tentativas', 'motivo', 'atualizado')}
                                        item_tarefa['especificacao'] = {c: t['especificacao'][c] for c in
                                            ('papel', 'capacidade', 'prioridade', 'dependencias', 'max_chamadas', 'tempo_total')
                                            if c in t['especificacao']}
                                        apresentacao.append(item_tarefa)
                                    item = dict(id=identificador, caminho=caminho, tarefas=apresentacao,
                                                consumos={t['id']: consumo_tarefa(db, t['id']) for t in tarefas},
                                                metricas=calcular(consulta, precos))
                                    conferir_resposta(dict(resultado, projetos=resultado['projetos'] + [item]),
                                                       reserva=1024)
                            resultado['projetos'].append(item)
                        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, sqlite3.Error) as erro:
                            resultado['erros'].append(dict(projeto=identificador, caminho=caminho,
                                                           mensagem=type(erro).__name__ + ': ' + str(erro)))
            except (OSError, ValueError) as erro:
                resultado['erros'].append(dict(projeto=None, caminho=None, mensagem=str(erro)))
    except (OSError, ValueError) as erro:
        resultado['erros'].append(dict(projeto=None, caminho=None, mensagem=str(erro)))
    try:
        conferir_resposta(resultado)
    except ValueError:
        quantidade = len(resultado['erros'])
        resultado['erros'] = [dict(projeto=None, caminho=None,
            mensagem=f'{quantidade} erros nas filas; detalhes excederam o limite de resposta.')]
        conferir_resposta(resultado)
    return resultado
