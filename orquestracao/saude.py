"""Disponibilidade compartilhada entre projetos, sem autorizar execução."""

import json
import http.client
import math
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from tarefas import IDENTIFICADOR, serializar
from executor import CAPACIDADES
from cota_codex import consultar, percentual
from prazos import restante
from processos import Processo

# A resolução do núcleo não depende de importar Estado antes deste módulo.
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from nucleo.consultas import listar_provedores  # noqa: E402

ESTADOS = {'AVAILABLE', 'DEGRADED', 'UNKNOWN', 'UNAVAILABLE', 'COOLDOWN',
           'QUOTA_LOW', 'QUOTA_EXHAUSTED', 'AUTH_ERROR', 'RATE_LIMITED', 'NETWORK_ERROR'}


def consultar_uso(comando, *, timeout, cwd, env):
    # O vigia recolhe também filhos do timeout em outros grupos de processos.
    processo = Processo(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, text=True, cwd=cwd, env=env,
                                start_new_session=True)
    try:
        saida, erro = processo.communicate(timeout=timeout)
        if processo.returncode:
            raise subprocess.CalledProcessError(processo.returncode, comando, output=saida, stderr=erro)
        return subprocess.CompletedProcess(comando, processo.returncode, saida, erro)
    finally:
        processo.encerrar()
        processo.communicate()


class Saude:
    def __init__(self, estado):
        self.estado = estado
        self.db = estado.db
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS provedores (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, pausado INTEGER NOT NULL DEFAULT 0,
                falhas INTEGER NOT NULL DEFAULT 0, motivo TEXT NOT NULL,
                atualizado REAL NOT NULL, valido_ate REAL NOT NULL,
                cota REAL, modelo TEXT
            );
            CREATE TABLE IF NOT EXISTS eventos_provedores (
                seq INTEGER PRIMARY KEY, provedor TEXT NOT NULL, data REAL NOT NULL,
                evento TEXT NOT NULL, dados TEXT NOT NULL
            );
        ''')

    def observar(self, provedor, status, motivo, validade=60, cota=None, modelo=None):
        if not isinstance(provedor, str) or not IDENTIFICADOR.fullmatch(provedor) or not isinstance(status, str) or status not in ESTADOS:
            raise ValueError('provedor ou estado inválido')
        if type(validade) is not int or not 1 <= validade <= 86400:
            raise ValueError('validade da observação inválida')
        if cota is not None and (type(cota) not in (int, float) or not math.isfinite(cota) or not 0 <= cota <= 100):
            raise ValueError('cota deve ser percentual entre 0 e 100')
        if not isinstance(motivo, str) or not motivo.strip() or (modelo is not None and not isinstance(modelo, str)):
            raise ValueError('motivo ou modelo inválido')
        if provedor in {'agy', 'codex'} and status == 'AVAILABLE':
            chave, padrao = ('JANGADA_DELEGAR_COTA_MIN', '20') if provedor == 'agy' else ('JANGADA_CODEX_COTA_MIN', '25')
            minimo = float(os.environ.get(chave, padrao))
            if not math.isfinite(minimo) or not 0 <= minimo <= 100:
                raise ValueError('reserva de cota inválida')
            if cota is None:
                status = 'UNKNOWN'
            elif cota == 0 or cota < minimo:
                status = 'QUOTA_EXHAUSTED' if cota == 0 else 'QUOTA_LOW'
        agora = time.time()
        with self.estado.transacao():
            anterior = self.db.execute('SELECT * FROM provedores WHERE id=?', (provedor,)).fetchone()
            falhas = anterior['falhas'] if anterior else 0
            if status in {'UNAVAILABLE', 'NETWORK_ERROR', 'RATE_LIMITED'}:
                falhas += 1
                if falhas >= 3:
                    status, validade = 'COOLDOWN', 900
            elif status == 'AVAILABLE':
                falhas = 0
            self.db.execute('''INSERT INTO provedores(id,status,motivo,atualizado,valido_ate,cota,modelo,falhas)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                motivo=excluded.motivo,atualizado=excluded.atualizado,valido_ate=excluded.valido_ate,
                cota=excluded.cota,modelo=excluded.modelo,falhas=excluded.falhas''',
                            (provedor, status, motivo, agora, agora + validade, cota, modelo, falhas))
            self.db.execute('INSERT INTO eventos_provedores(provedor,data,evento,dados) VALUES(?,?,?,?)',
                            (provedor, agora, 'observado', serializar({'status': status, 'motivo': motivo, 'cota': cota})))

    def listar(self):
        return listar_provedores(self.db)

    def pausar(self, provedor, pausado):
        if not isinstance(provedor, str) or not IDENTIFICADOR.fullmatch(provedor) or type(pausado) is not bool:
            raise ValueError('provedor ou pausa inválida')
        with self.estado.transacao():
            agora = time.time()
            self.db.execute('''INSERT INTO provedores(id,status,pausado,motivo,atualizado,valido_ate)
                VALUES(?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET pausado=excluded.pausado,
                status=CASE WHEN provedores.status='COOLDOWN' AND provedores.valido_ate>excluded.atualizado
                    THEN provedores.status ELSE 'UNKNOWN' END,
                valido_ate=CASE WHEN provedores.status='COOLDOWN' AND provedores.valido_ate>excluded.atualizado
                    THEN provedores.valido_ate ELSE 0 END,atualizado=excluded.atualizado''',
                            (provedor, 'UNKNOWN', int(pausado), 'aguarda verificação', agora))
            self.db.execute('INSERT INTO eventos_provedores(provedor,data,evento,dados) VALUES(?,?,?,?)',
                            (provedor, agora, 'pausado' if pausado else 'ativado', '{}'))

    def impedimentos(self):
        resultado = []
        for item in self.listar():
            if item['id'] not in {'local', 'agy', 'codex'}:
                continue
            if item['status'] in {'AVAILABLE', 'DEGRADED', 'UNKNOWN'}:
                continue
            codigo = 'cota_indisponivel' if item['status'] in {'QUOTA_LOW', 'QUOTA_EXHAUSTED'} else 'provedor_em_espera'
            if item['pausado']:
                codigo = 'provedor_pausado'
            resultado.append({'destino': 'codex-economico' if item['id'] == 'codex' else item['id'], 'motivo_codigo': codigo, 'motivo': item['motivo']})
        return resultado

    def registrar_delegacao(self, registro, codigo):
        provedor = registro.get('destino')
        for tentativa in registro.get('tentativas', []):
            if isinstance(tentativa, dict) and tentativa.get('destino') != provedor:
                self.registrar_delegacao(tentativa, tentativa.get('codigo_saida', 4))
        if provedor == 'codex-economico':
            provedor = 'codex'
        if provedor not in {'local', 'agy', 'codex'}:
            return
        motivo = registro.get('motivo_codigo')
        if motivo in {'provedor_em_espera', 'provedor_pausado', 'cota_indisponivel', 'destino_proibido'}:
            return
        if codigo == 0:
            cota = registro.get('cota_depois') if provedor in {'agy', 'codex'} else None
            if cota is not None and (type(cota) not in (int, float) or not math.isfinite(cota) or not 0 <= cota <= 100):
                cota = None
            status = 'AVAILABLE'
            if provedor in {'agy', 'codex'}:
                if cota is None:
                    status = 'UNKNOWN'
                elif cota == 0 or cota < float(os.environ.get('JANGADA_CODEX_COTA_MIN', '25') if provedor == 'codex' else os.environ.get('JANGADA_DELEGAR_COTA_MIN', '20')):
                    status = 'QUOTA_EXHAUSTED' if cota == 0 else 'QUOTA_LOW'
            self.observar(provedor, status, 'executor concluiu chamada', cota=cota, modelo=registro.get('modelo'))
        elif motivo == 'cota_insuficiente':
            cota = registro.get('cota_antes')
            if cota is not None and (type(cota) not in (int, float) or not math.isfinite(cota) or not 0 <= cota <= 100):
                cota = None
            self.observar(provedor, 'QUOTA_EXHAUSTED' if cota == 0 else 'QUOTA_LOW',
                          'cota insuficiente', validade=300, cota=cota)
        elif motivo == 'cota_desconhecida':
            self.observar(provedor, 'UNKNOWN', 'cota desconhecida')
        elif motivo in {'indisponivel', 'erro_execucao', 'modelo_ausente'}:
            self.observar(provedor, 'UNAVAILABLE', motivo)

    def atualizar(self, permitir_remoto=False, prazo=None):
        if restante(prazo, 1) <= 0:
            return
        mapa = {item['id']: item for item in self.listar()}
        if not mapa['local']['pausado'] and mapa['local']['status'] != 'COOLDOWN':
            try:
                url = os.environ.get('JANGADA_OLLAMA_URL', 'http://localhost:11434').rstrip('/') + '/api/tags'
                with urllib.request.urlopen(url, timeout=restante(prazo, 3)) as resposta:
                    dados = json.loads(resposta.read(1024 * 1024).decode('utf-8'))
                if (not isinstance(dados, dict) or not isinstance(dados.get('models'), list)
                        or any(not isinstance(m, dict) or not isinstance(m.get('name'), str) for m in dados['models'])):
                    raise ValueError('lista de modelos inválida')
                nomes = {modelo.get('name') for modelo in dados['models']}
                modelo = os.environ.get('JANGADA_LOCAL_MODELO', 'qwen3:4b')
                if modelo not in nomes:
                    self.observar('local', 'UNAVAILABLE', 'modelo local ausente')
                else:
                    self.observar('local', 'AVAILABLE', 'serviço e modelo presentes', modelo=modelo)
            except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
                if restante(prazo, 1) <= 0:
                    return
                self.observar('local', 'NETWORK_ERROR', 'serviço local não respondeu')
        if restante(prazo, 1) <= 0:
            return
        if mapa['agy']['pausado'] or mapa['agy']['status'] == 'COOLDOWN':
            return
        try:
            cache = pathlib.Path(os.environ.get('XDG_CACHE_HOME', pathlib.Path.home() / '.cache')) / 'jangada/agy-usage.json'
            idade = time.time() - cache.stat().st_mtime if cache.is_file() else math.inf
            validade = int(os.environ.get('JANGADA_DELEGAR_CACHE', '5')) * 60
            dados = json.loads(cache.read_text(encoding='utf-8')) if 0 <= idade < validade else None
            if dados is None and permitir_remoto and os.environ.get('JANGADA_DELEGAR', 'agy') == 'agy':
                espera = restante(prazo, 10)
                if espera <= 0:
                    return
                ambiente = os.environ.copy()
                ambiente.pop('JANGADA_SESSAO', None)
                ambiente['JANGADA_HOOK_DESLIGADO'] = '1'
                consulta = consultar_uso(['timeout', '--signal=KILL', str(espera), 'agy', '-p', '/usage',
                                         '--sandbox', '--output-format', 'json', '--print-timeout', '10s'],
                                        timeout=espera + 2, cwd=pathlib.Path.home(), env=ambiente)
                dados = json.loads(consulta.stdout)
                idade = 0
            grupos = dados['command']['data']['groups']
            if not isinstance(grupos, list) or any(not isinstance(g, dict) for g in grupos):
                raise ValueError('grupos de cota inválidos')
            # Como no jangada-delegar: a cota de um grupo é a menor entre as
            # janelas ativas, e vale o grupo com mais cota entre os modelos
            # de JANGADA_DELEGAR_MODELOS.
            cotas = {}
            for grupo in grupos:
                buckets = grupo.get('buckets', [])
                if not isinstance(buckets, list) or any(not isinstance(b, dict) for b in buckets):
                    raise ValueError('cotas inválidas')
                for b in buckets:
                    if isinstance(b.get('id'), str) and b.get('disabled') is not True:
                        cotas.setdefault(b['id'].split('-')[0], []).append(b.get('remaining_fraction'))
            modelos = os.environ.get(
                'JANGADA_DELEGAR_MODELOS', 'gemini-3.8-flash-high claude-sonnet-5-5-high gpt-oss-120b-medium').split()
            usados = [cotas[g] for g in {'gemini' if m.startswith('gemini-') else '3p' for m in modelos}
                      if g in cotas and cotas[g] and all(
                          type(c) in (int, float) and math.isfinite(c) and 0 <= c <= 1 for c in cotas[g])]
            if not usados:
                raise ValueError('cota inválida')
            percentual = max(min(grupo) for grupo in usados) * 100
            status = 'AVAILABLE' if percentual >= float(os.environ.get('JANGADA_DELEGAR_COTA_MIN', '20')) else 'QUOTA_LOW'
            if percentual == 0:
                status = 'QUOTA_EXHAUSTED'
            self.observar('agy', status, 'cota consultada', cota=percentual,
                          validade=max(1, min(60, int(validade - idade))) if dados is not None and math.isfinite(idade) else 60)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            if restante(prazo, 1) <= 0:
                return
            self.observar('agy', 'UNKNOWN', 'cota desconhecida ou expirada')

    def atualizar_codex(self, permitir_remoto=False, prazo=None):
        if not permitir_remoto:
            raise ValueError('consulta de cota do Codex exige --permitir-remoto')
        if restante(prazo, 1) <= 0:
            return
        atual = next((item for item in self.listar() if item['id'] == 'codex'), None)
        if atual and (atual['pausado'] or atual['status'] == 'COOLDOWN'):
            return
        try:
            dados = consultar(self.estado.pasta) if prazo is None else consultar(self.estado.pasta, prazo=prazo)
            cota, validade = percentual(dados, time.time())
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            if restante(prazo, 1) <= 0:
                return
            self.observar('codex', 'UNKNOWN', 'cota do Codex desconhecida ou expirada')
        else:
            self.observar('codex', 'AVAILABLE', 'menor saldo das janelas do grupo Codex',
                          validade=validade, cota=cota)


def preferencias_delegacao(raiz, config):
    politica = pathlib.Path(config) / 'delegacao.json'
    if not politica.is_file():
        politica = raiz / 'delegacao/roteamento.json'
    preferencias = json.loads(politica.read_text(encoding='utf-8'))
    if not isinstance(preferencias, dict) or any(
        capacidade not in CAPACIDADES or not isinstance(destinos, list) or not destinos
        or any(not isinstance(d, str) or d not in {'local', 'agy', 'codex-economico'} for d in destinos)
        or len(destinos) != len(set(destinos))
        for capacidade, destinos in preferencias.items()
    ):
        raise ValueError('política de capacidades inválida')
    return preferencias


def candidatos_elegiveis(tarefa, preferencias, perfil, permitir_remoto, permitir_codex=False):
    if tarefa['papel'] != 'leitor' or tarefa['capacidade'] not in CAPACIDADES:
        return []
    if tarefa['risco'] > 2 or tarefa['qualidade'] not in {'low', 'medium'}:
        return []
    candidatos = preferencias.get(tarefa['capacidade'], [])
    if perfil == 'offline':
        candidatos = [c for c in candidatos if c == 'local']
    elif perfil == 'quality':
        candidatos = [c for c in candidatos if c == 'agy']
    sessao = os.environ.get('JANGADA_DELEGAR') or 'agy'
    if sessao in {'claude', 'nativo'}:
        return []
    if sessao == 'local' or not permitir_remoto or not tarefa.get('permitir_remoto', False):
        candidatos = [c for c in candidatos if c == 'local']
    if not permitir_codex or not tarefa.get('permitir_codex', False) or not os.environ.get('JANGADA_CODEX_ECONOMICO_MODELO'):
        candidatos = [c for c in candidatos if c != 'codex-economico']
    return candidatos


def orcamento_disponivel(estado, item):
    tarefa = item['especificacao']
    consumo = estado.consumo(item['id'])
    return (consumo['chamadas'] is not None
            and consumo['chamadas'] < tarefa.get('max_chamadas', 8)
            and consumo['segundos'] < tarefa.get('tempo_total', 600)
            and item['tentativas'] < tarefa.get('max_tentativas', 2))


def retomar(estado, saude, raiz, config, perfil, permitir_remoto, permitir_codex=False):
    preferencias = preferencias_delegacao(raiz, config)
    disponiveis = {'codex-economico' if item['id'] == 'codex' else item['id'] for item in saude.listar() if item['status'] == 'AVAILABLE'}
    retomadas = []
    for item in estado.listar():
        tarefa = item['especificacao']
        if item['status'] not in {'WAITING_PROVIDER', 'WAITING_QUOTA'} or tarefa['papel'] != 'leitor':
            continue
        candidatos = candidatos_elegiveis(tarefa, preferencias, perfil, permitir_remoto, permitir_codex)
        if not orcamento_disponivel(estado, item):
            continue
        if any(c in disponiveis for c in candidatos):
            try:
                estado.alterar(item['id'], 'retomar')
            except ValueError:
                continue
            retomadas.append(item['id'])
    return retomadas
