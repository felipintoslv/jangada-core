"""Fila persistente de tarefas e artefatos, sem executar comandos do estado."""

import contextlib
import hashlib
import json
import math
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time
import uuid

from deterministico import conferir as conferir_deterministica
from metricas_projeto import amostragem, identidade
from projetos import ler_projeto, especificacao_atual, provedor_de, trava_projetos, executor_permitido
from supervisao import amostravel, aprovacao_valida, elegivel as elegivel_supervisao, pendente as supervisao_pendente
from confianca import exigir_controlador, autorizar_conclusao, conferir_conclusao, auditar_recusa

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nucleo.consultas import consumo_tarefa, listar_tarefas  # noqa: E402

ESTADOS = {
    'QUEUED', 'RUNNING', 'COMPLETED', 'REVIEW_REQUIRED', 'REVISION_REQUIRED',
    'WAITING_PROVIDER', 'WAITING_QUOTA', 'WAITING_REVIEWER', 'FAILED', 'CANCELLED', 'PAUSED', 'BLOCKED',
}
FINAIS = {'COMPLETED', 'FAILED', 'CANCELLED'}
IDENTIFICADOR = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$')
PRIORIDADES = ('critical', 'high', 'normal', 'low', 'background')


def serializar(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, allow_nan=False)


def tarefa_valida(tarefa):
    if not isinstance(tarefa, dict):
        raise ValueError('tarefa deve ser um objeto')
    obrigatorios = {'id', 'pedido', 'papel', 'capacidade', 'risco', 'qualidade', 'fontes'}
    if not obrigatorios <= tarefa.keys():
        raise ValueError('campos obrigatórios ausentes na tarefa')
    if not isinstance(tarefa['id'], str) or not IDENTIFICADOR.fullmatch(tarefa['id']):
        raise ValueError('identificador inválido')
    for campo in ('pedido', 'papel', 'capacidade'):
        if not isinstance(tarefa[campo], str) or not tarefa[campo].strip():
            raise ValueError(f'{campo} deve ser texto não vazio')
    if 'atividade' in tarefa and (not isinstance(tarefa['atividade'], str)
            or not re.fullmatch(r'atv-[0-9a-f]{12}', tarefa['atividade'])):
        raise ValueError('atividade inválida')
    for campo in ('criterios_aceite', 'entradas', 'saidas', 'contexto'):
        if campo in tarefa and (not isinstance(tarefa[campo], list) or any(
                not isinstance(item, str) or not item.strip() for item in tarefa[campo])
                or len(tarefa[campo]) != len(set(tarefa[campo]))):
            raise ValueError(f'{campo} deve ser lista de textos sem repetição')
    if type(tarefa['risco']) is not int or not 0 <= tarefa['risco'] <= 4:
        raise ValueError('risco deve estar entre 0 e 4')
    if tarefa['qualidade'] not in ('low', 'medium', 'high', 'critical'):
        raise ValueError('qualidade inválida')
    if tarefa.get('prioridade', 'normal') not in PRIORIDADES:
        raise ValueError('prioridade inválida')
    if not isinstance(tarefa['fontes'], list) or not tarefa['fontes'] or any(
        not isinstance(fonte, str) or not fonte for fonte in tarefa['fontes']
    ):
        raise ValueError('fontes devem ser uma lista não vazia de caminhos')
    dependencias = tarefa.get('dependencias', [])
    if not isinstance(dependencias, list) or any(
        not isinstance(dep, str) or not IDENTIFICADOR.fullmatch(dep) for dep in dependencias
    ) or len(dependencias) != len(set(dependencias)):
        raise ValueError('dependências inválidas ou repetidas')
    if tarefa['id'] in dependencias:
        raise ValueError('tarefa não pode depender de si mesma')
    requisitos = tarefa.get('requisitos', [])
    if not isinstance(requisitos, list) or any(
        not isinstance(item, str) or not item.strip() or item.startswith('-') or '\n' in item
        for item in requisitos
    ) or len(requisitos) != len(set(requisitos)):
        raise ValueError('requisitos inválidos ou repetidos')
    for campo, padrao in (('max_tentativas', 2), ('tempo_total', 600), ('max_chamadas', 8)):
        valor = tarefa.get(campo, padrao)
        if type(valor) is not int or not 1 <= valor <= 999999:
            raise ValueError(f'{campo} deve ser inteiro positivo')
    for campo in ('permitir_remoto', 'permitir_codex', 'intermediaria', 'supervisao_automatica', 'amostragem'):
        if campo in tarefa and type(tarefa[campo]) is not bool:
            raise ValueError(f'{campo} deve ser booleano')
    if tarefa.get('supervisao_automatica') and not elegivel_supervisao(tarefa):
        raise ValueError('supervisão automática exige leitor intermediário, risco 1 e qualidade baixa ou média')
    if tarefa.get('amostragem') and not amostravel(tarefa):
        raise ValueError('amostragem exige leitor intermediário, risco 1 e qualidade baixa ou média')
    if 'esquema' in tarefa and (tarefa['capacidade'] != 'validacao_json' or not isinstance(tarefa['esquema'], str)
                                or not tarefa['esquema'] or not isinstance(tarefa.get('hash_esquema'), str)):
        raise ValueError('esquema exige validação JSON, caminho e resumo do arquivo')
    serializar(tarefa)


def prioridades_efetivas(tarefas, estados):
    mapa = {t['id']: t for t in tarefas}
    prioridades = {t['id']: PRIORIDADES.index(t['especificacao'].get('prioridade', 'normal')) for t in tarefas}

    propagadas = {}
    pendentes = [(t['id'], prioridades[t['id']]) for t in tarefas if estados[t['id']] == 'QUEUED']
    while pendentes:
        identificador, prioridade = pendentes.pop()
        if estados[identificador] != 'QUEUED':
            continue
        prioridade = min(prioridades[identificador], prioridade)
        if propagadas.get(identificador, len(PRIORIDADES)) <= prioridade:
            continue
        prioridades[identificador] = prioridade
        propagadas[identificador] = prioridade
        pendentes.extend((dep, prioridade) for dep in mapa[identificador]['especificacao'].get('dependencias', []))
    return prioridades


class Estado:
    def __init__(self, pasta, raiz=None):
        exigir_controlador()
        original = pathlib.Path(pasta).absolute()
        base = pathlib.Path(raiz).absolute() if raiz is not None else original.parent
        relativo = original.relative_to(base)
        if '..' in relativo.parts:
            raise ValueError('pasta de estado fora da raiz configurada')
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.trava = trava_projetos(base)
        self.trava.__enter__()
        try:
            self.pasta = base.resolve()
            for componente in relativo.parts:
                self.pasta /= componente
                if self.pasta.is_symlink():
                    raise ValueError('pasta de estado não pode conter links simbólicos')
                self.pasta.mkdir(mode=0o700, exist_ok=True)
            if self.pasta.is_symlink() or any((self.pasta / nome).is_symlink() for nome in (
                'tarefas.sqlite', 'tarefas.sqlite-wal', 'tarefas.sqlite-shm',
            )):
                raise ValueError('estado não pode usar links simbólicos')
            try:
                fd = os.open(self.pasta / 'tarefas.sqlite', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
            self.db = sqlite3.connect(self.pasta / 'tarefas.sqlite', timeout=30, isolation_level=None)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS tarefas (
                    id TEXT PRIMARY KEY, especificacao TEXT NOT NULL, status TEXT NOT NULL,
                    tentativas INTEGER NOT NULL DEFAULT 0, dono TEXT, prazo REAL,
                    artefato TEXT, hash_artefato TEXT, resultado TEXT, motivo TEXT,
                    criado REAL NOT NULL, atualizado REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS eventos (
                    seq INTEGER PRIMARY KEY, tarefa TEXT NOT NULL, data REAL NOT NULL,
                    evento TEXT NOT NULL, dados TEXT NOT NULL,
                    FOREIGN KEY(tarefa) REFERENCES tarefas(id)
                );
                CREATE INDEX IF NOT EXISTS tarefas_status ON tarefas(status);
                CREATE INDEX IF NOT EXISTS eventos_tarefa ON eventos(tarefa, evento);
                CREATE TABLE IF NOT EXISTS atividades (
                    id TEXT PRIMARY KEY, titulo TEXT NOT NULL, objetivo TEXT NOT NULL,
                    criterios TEXT NOT NULL, criado REAL NOT NULL, atualizado REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execucoes (
                    id TEXT PRIMARY KEY, tarefa TEXT, sessao TEXT, atividade TEXT,
                    dono TEXT UNIQUE, funcao TEXT NOT NULL, agente TEXT, provedor TEXT, modelo TEXT,
                    inicio REAL NOT NULL, fim REAL, status TEXT NOT NULL,
                    chamadas INTEGER, tokens_entrada INTEGER, tokens_saida INTEGER, segundos REAL,
                    motivo_codigo TEXT, roteamento TEXT, destino_dados TEXT, artefato TEXT,
                    limite_chamadas INTEGER, FOREIGN KEY(tarefa) REFERENCES tarefas(id),
                    CHECK(tarefa IS NOT NULL OR sessao IS NOT NULL)
                );
                CREATE INDEX IF NOT EXISTS execucoes_tarefa ON execucoes(tarefa, inicio);
            ''')

        except BaseException:
            self.trava.__exit__(None, None, None)
            raise

    def fechar(self):
        self.db.close()
        self.trava.__exit__(None, None, None)

    @contextlib.contextmanager
    def transacao(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def evento(self, tarefa, evento, dados):
        dados = dict(dados)
        if evento == 'reservada':
            spec = json.loads(self.db.execute('SELECT especificacao FROM tarefas WHERE id=?', (tarefa,)).fetchone()[0])
            dados['execucao'] = 'exe-' + uuid.uuid4().hex[:16]
            self.db.execute('''INSERT INTO execucoes
                (id,tarefa,atividade,dono,funcao,agente,provedor,modelo,inicio,status,limite_chamadas,roteamento)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (dados['execucao'], tarefa, spec.get('atividade'), dados['dono'],
                'supervisao' if dados.get('fase') == 'supervisao' else 'execucao', dados.get('executor'),
                provedor_de(dados.get('executor')), dados.get('modelo'), time.time(), 'RUNNING',
                self.limite_projeto(spec), serializar(dados.get('roteamento'))))
        elif evento in {'execucao_encerrada', 'reserva_expirada'}:
            execucao = self.db.execute("SELECT * FROM execucoes WHERE tarefa=? AND dono=? AND status='RUNNING'",
                                      (tarefa, dados.get('dono'))).fetchone()
            if execucao:
                dados['execucao'] = execucao['id']
                resultado = dados.get('resultado', {})
                registro = resultado.get('delegacao', {})
                registro = registro if isinstance(registro, dict) else {}
                metricas = resultado.get('metricas', {})
                executor, modelo = identidade(resultado)
                modelo = modelo or resultado.get('modelo') or resultado.get('modelo_declarado') or execucao['modelo']
                tokens = [registro.get('tokens_codex_' + c, registro.get('tokens_local_' + c)) for c in ('entrada', 'saida')]
                tokens = [v if type(v) is int and v >= 0 else None for v in tokens]
                self.db.execute('''UPDATE execucoes SET fim=?,status=?,agente=?,provedor=?,modelo=?,
                    chamadas=?,tokens_entrada=?,tokens_saida=?,segundos=?,motivo_codigo=?,roteamento=?,
                    destino_dados=?,artefato=? WHERE id=?''', (time.time(), dados.get('status', 'REVISION_REQUIRED'),
                    executor if executor != 'nao_informado' else execucao['agente'],
                    provedor_de(executor) if executor != 'nao_informado' else execucao['provedor'], modelo,
                    metricas.get('chamadas'), *tokens, metricas.get('segundos'),
                    registro.get('motivo_codigo') or resultado.get('motivo_codigo')
                    or ('reserva_expirada' if evento == 'reserva_expirada' else None),
                    serializar({'escolha': json.loads(execucao['roteamento']) if execucao['roteamento'] else None,
                                'decisao': registro.get('decisao'), 'tentativas': registro.get('tentativas', [])}),
                    'local' if executor in {'local', 'deterministico'} else None, dados.get('artefato'), execucao['id']))
        self.db.execute('INSERT INTO eventos(tarefa,data,evento,dados) VALUES(?,?,?,?)',
                        (tarefa, time.time(), evento, serializar(dados)))

    def criar_atividade(self, titulo, objetivo, criterios):
        if (any(not isinstance(v, str) or not v.strip() for v in (titulo, objetivo))
                or not isinstance(criterios, list) or not criterios
                or any(not isinstance(v, str) or not v.strip() for v in criterios)
                or len(criterios) != len(set(criterios))):
            raise ValueError('atividade exige título, objetivo e critérios sem repetição')
        identificador, agora = 'atv-' + uuid.uuid4().hex[:12], time.time()
        with self.transacao():
            self.db.execute('INSERT INTO atividades VALUES(?,?,?,?,?,?)',
                            (identificador, titulo, objetivo, serializar(criterios), agora, agora))
        return identificador

    def atual(self, tarefa):
        return especificacao_atual(tarefa, ler_projeto(self.pasta))

    def permite_executor(self, executor):
        return executor_permitido(ler_projeto(self.pasta), executor)

    def impedimentos_politica(self):
        return [dict(destino=d, motivo='política do projeto impede este provedor', motivo_codigo='provedor_pausado')
                for d in ('local', 'agy', 'codex-economico') if not self.permite_executor(d)]

    def limite_projeto(self, tarefa):
        projeto = ler_projeto(self.pasta)
        if projeto is None:
            return tarefa.get('max_chamadas', 8)
        orcamento = projeto['politica'].get('orcamento', {})
        if tarefa['capacidade'] == 'validacao_json':
            return 0
        if 'custo_estimado' in orcamento:
            raise ValueError('teto de custo exige limite de consumo comprovável; os executores atuais não o garantem')
        limite = tarefa.get('max_chamadas', 8)
        if 'chamadas' not in orcamento:
            return limite
        usadas = self.chamadas_usadas(orcamento)
        return max(0, min(limite, orcamento['chamadas'] - usadas))

    def chamadas_usadas(self, orcamento):
        desde = time.time() - orcamento.get('periodo_segundos', 86400)
        usadas = 0
        for evento in self.db.execute("SELECT evento,dados FROM eventos WHERE data>=? AND evento IN ('execucao_encerrada','reserva_expirada')", (desde,)):
            if evento['evento'] == 'reserva_expirada':
                raise ValueError('reserva expirada com consumo desconhecido; aguarde o fim da janela '
                                 f"do orçamento ({orcamento.get('periodo_segundos', 86400)} segundos)")
            dados = json.loads(evento['dados'])
            quantidade = dados.get('resultado', {}).get('metricas', {}).get('chamadas')
            if type(quantidade) is not int or quantidade < 0:
                raise ValueError('consumo do projeto desconhecido; execução bloqueada')
            usadas += quantidade
        for execucao in self.db.execute("SELECT limite_chamadas FROM execucoes WHERE status='RUNNING'"):
            if execucao['limite_chamadas'] is None:
                raise ValueError('reserva com consumo desconhecido no projeto; para encerrar registro de sessão órfã, '
                                 'use jangada-projeto --projeto PASTA sessao-encerrar NOME fora do isolamento')
            usadas += execucao['limite_chamadas']
        for execucao in self.db.execute("SELECT chamadas FROM execucoes WHERE (sessao IS NOT NULL OR funcao='revisao') AND status!='RUNNING' AND (inicio>=? OR fim>=?)", (desde, desde)):
            if execucao['chamadas'] is None:
                raise ValueError('consumo de sessão ou revisão desconhecido; execução bloqueada; aguarde o fim da janela '
                                 f"do orçamento ({orcamento.get('periodo_segundos', 86400)} segundos)")
            usadas += execucao['chamadas']
        return usadas

    def importar(self, tarefas):
        if not isinstance(tarefas, list) or not tarefas:
            raise ValueError('plano deve conter uma lista não vazia de tarefas')
        for tarefa in tarefas:
            tarefa_valida(tarefa)
        if len({t['id'] for t in tarefas}) != len(tarefas):
            raise ValueError('identificadores repetidos no plano')
        with self.transacao():
            atividades = {r['id'] for r in self.db.execute('SELECT id FROM atividades')}
            if any(t.get('atividade') is not None and t['atividade'] not in atividades for t in tarefas):
                raise ValueError('atividade inexistente')
            existentes = {r['id']: json.loads(r['especificacao']) for r in self.db.execute('SELECT * FROM tarefas')}
            mapa = existentes | {t['id']: t for t in tarefas}
            visitados, caminho = set(), set()

            def visitar(identificador):
                if identificador in caminho:
                    raise ValueError('ciclo nas dependências')
                if identificador in visitados:
                    return
                if identificador not in mapa:
                    raise ValueError(f'dependência inexistente: {identificador}')
                caminho.add(identificador)
                for dep in mapa[identificador].get('dependencias', []):
                    visitar(dep)
                caminho.remove(identificador)
                visitados.add(identificador)

            for identificador in mapa:
                visitar(identificador)
            agora = time.time()
            for tarefa in tarefas:
                anterior = existentes.get(tarefa['id'])
                if anterior is not None:
                    if serializar(anterior) != serializar(tarefa):
                        raise ValueError(f'tarefa existente mudou: {tarefa["id"]}; use outro identificador')
                    continue
                self.db.execute('INSERT INTO tarefas(id,especificacao,status,criado,atualizado) VALUES(?,?,?,?,?)',
                                (tarefa['id'], serializar(tarefa), 'QUEUED', agora, agora))
                self.evento(tarefa['id'], 'criada', {'especificacao': tarefa})

    def listar(self):
        return listar_tarefas(self.db, self.pasta)

    def consumo(self, identificador):
        return consumo_tarefa(self.db, identificador)

    def reservar(self, duracao=660):
        if not isinstance(duracao, (int, float)) or not math.isfinite(duracao) or duracao <= 0:
            raise ValueError('duração da reserva inválida')
        with self.transacao():
            agora = time.time()
            for antiga in self.db.execute('SELECT * FROM tarefas WHERE status=? AND prazo<=?', ('RUNNING', agora)).fetchall():
                self.db.execute('UPDATE tarefas SET status=?,dono=NULL,prazo=NULL,motivo=?,atualizado=? WHERE id=?',
                                ('REVISION_REQUIRED', 'executor interrompido; conferir antes de repetir', agora, antiga['id']))
                self.evento(antiga['id'], 'reserva_expirada', {'dono': antiga['dono']})
            # Só a fila é lida por inteiro: o histórico entra pelo estado, sem
            # interpretar especificação nem resultado sob a transação de escrita.
            estados = {r['id']: conferir_conclusao(self.pasta, dict(r))['status']
                       for r in self.db.execute('SELECT * FROM tarefas')}
            tarefas = [dict(r, especificacao=json.loads(r['especificacao'])) for r in self.db.execute(
                'SELECT id,especificacao,tentativas,criado FROM tarefas WHERE status=? ORDER BY criado,id', ('QUEUED',))]
            for tarefa in tarefas:
                if tarefa['tentativas'] >= tarefa['especificacao'].get('max_tentativas', 2):
                    self.db.execute('UPDATE tarefas SET status=?,motivo=?,atualizado=? WHERE id=?',
                                    ('FAILED', 'limite de tentativas atingido', agora, tarefa['id']))
                    estados[tarefa['id']] = 'FAILED'
                    self.evento(tarefa['id'], 'limite_tentativas', {})
            alterou = True
            while alterou:
                alterou = False
                for tarefa in tarefas:
                    bloqueadas = [dep for dep in tarefa['especificacao'].get('dependencias', [])
                                  if estados[dep] in {'FAILED', 'CANCELLED', 'BLOCKED'}]
                    if estados[tarefa['id']] == 'QUEUED' and bloqueadas:
                        self.db.execute('UPDATE tarefas SET status=?,motivo=?,atualizado=? WHERE id=?',
                                        ('BLOCKED', 'dependências impedidas: ' + ', '.join(bloqueadas), agora, tarefa['id']))
                        estados[tarefa['id']] = 'BLOCKED'
                        self.evento(tarefa['id'], 'dependencia_impedida', {'dependencias': bloqueadas})
                        alterou = True
            prioridades = prioridades_efetivas(tarefas, estados)
            for tarefa in sorted(tarefas, key=lambda t: (prioridades[t['id']], t['criado'], t['id'])):
                selecao = getattr(self, 'selecao', None)
                if selecao is not None and tarefa['id'] != selecao['tarefa']:
                    continue
                spec = tarefa['especificacao']
                if estados[tarefa['id']] != 'QUEUED' or any(estados[dep] != 'COMPLETED' for dep in spec.get('dependencias', [])):
                    continue
                try:
                    limite = self.limite_projeto(spec)
                except ValueError as erro:
                    self.db.execute('UPDATE tarefas SET status=?,motivo=?,atualizado=? WHERE id=?',
                                    ('WAITING_QUOTA', str(erro), agora, tarefa['id']))
                    estados[tarefa['id']] = 'WAITING_QUOTA'
                    self.evento(tarefa['id'], 'orcamento_impedido', {'motivo': str(erro)})
                    continue
                if limite == 0 and spec['capacidade'] != 'validacao_json':
                    continue
                dono = str(uuid.uuid4())
                self.db.execute('UPDATE tarefas SET status=?,tentativas=tentativas+1,dono=?,prazo=?,atualizado=? WHERE id=?',
                                ('RUNNING', dono, agora + duracao, agora, tarefa['id']))
                self.evento(tarefa['id'], 'reservada', {'dono': dono,
                            'roteamento': selecao,
                            'prioridade': spec.get('prioridade', 'normal'),
                            'prioridade_efetiva': PRIORIDADES[prioridades[tarefa['id']]]})
                return spec, dono
        return None

    def reservar_principal(self, identificador, executor, modelo=None):
        if executor not in ('claude', 'codex') or (modelo is not None and (
            not isinstance(modelo, str) or not modelo.strip() or len(modelo) > 128
        )):
            raise ValueError('agente principal ou modelo inválido')
        with self.transacao():
            if not self.permite_executor(executor):
                raise ValueError('política do projeto impede este executor')
            mapa = {t['id']: t for t in self.listar()}
            tarefa = mapa.get(identificador)
            if not tarefa or tarefa['status'] not in {'QUEUED', 'WAITING_PROVIDER', 'WAITING_REVIEWER'}:
                raise ValueError('tarefa não está disponível para o agente principal')
            spec = tarefa['especificacao']
            if spec['risco'] == 4 or not (spec['risco'] == 3 or spec['qualidade'] in {'high', 'critical'}):
                raise ValueError('reserva principal exige alta qualidade ou risco 3; risco 4 não é permitido')
            if any(mapa[dep]['status'] != 'COMPLETED' for dep in spec.get('dependencias', [])):
                raise ValueError('dependências ainda não concluídas')
            consumo = self.consumo(identificador)
            if self.limite_projeto(spec) == 0 and spec['capacidade'] != 'validacao_json':
                raise ValueError('orçamento do projeto esgotado')
            tempo = spec.get('tempo_total', 600) - consumo['segundos']
            if (consumo['chamadas'] is None or consumo['chamadas'] >= spec.get('max_chamadas', 8)
                    or tempo <= 0 or tarefa['tentativas'] >= spec.get('max_tentativas', 2)):
                raise ValueError('consumo desconhecido ou orçamento da tarefa esgotado')
            agora, dono = time.time(), str(uuid.uuid4())
            self.db.execute('UPDATE tarefas SET status=?,tentativas=tentativas+1,dono=?,prazo=?,atualizado=? WHERE id=?',
                            ('RUNNING', dono, agora + tempo, agora, identificador))
            self.evento(identificador, 'reservada', {'dono': dono, 'modo': 'sessao_principal',
                        'executor': executor, 'modelo': modelo, 'inicio': agora})
            return spec, dono, agora + tempo

    def reservar_supervisao(self, identificador):
        with self.transacao():
            item = next((t for t in self.listar() if t['id'] == identificador), None)
            if not item or not supervisao_pendente(item):
                raise ValueError('tarefa não aguarda supervisão automática')
            spec = item['especificacao']
            consumo = self.consumo(identificador)
            if self.limite_projeto(spec) == 0:
                raise ValueError('orçamento do projeto esgotado')
            restante = spec.get('tempo_total', 600) - consumo['segundos']
            if (consumo['chamadas'] is None or consumo['chamadas'] >= spec.get('max_chamadas', 8)
                    or restante <= 0 or item['tentativas'] >= spec.get('max_tentativas', 2)):
                raise ValueError('supervisão sem orçamento ou com consumo desconhecido')
            agora, dono = time.time(), str(uuid.uuid4())
            self.db.execute('UPDATE tarefas SET status=?,tentativas=tentativas+1,dono=?,prazo=?,atualizado=? WHERE id=?',
                            ('RUNNING', dono, agora + restante + 60, agora, identificador))
            self.evento(identificador, 'reservada', {'dono': dono, 'fase': 'supervisao', 'artefato': item['artefato']})
            return item, dono, restante, spec.get('max_chamadas', 8) - consumo['chamadas']

    @auditar_recusa
    def finalizar(self, identificador, dono, status, resultado, artefato=None):
        exigir_controlador()
        if status not in {'COMPLETED', 'REVIEW_REQUIRED', 'REVISION_REQUIRED', 'FAILED',
                          'WAITING_PROVIDER', 'WAITING_QUOTA', 'WAITING_REVIEWER'}:
            raise ValueError('estado de conclusão da execução inválido')
        if artefato is not None and not isinstance(artefato, str):
            raise ValueError('artefato deve ser texto')
        if status in {'COMPLETED', 'REVIEW_REQUIRED'} and (artefato is None or not artefato.strip()):
            raise ValueError('conclusão ou revisão exige artefato não vazio')
        if not isinstance(resultado, dict):
            raise ValueError('resultado deve ser um objeto')
        metricas = resultado.get('metricas', {})
        if not isinstance(metricas, dict):
            raise ValueError('métricas devem ser um objeto')
        if metricas.get('chamadas') is not None and (
            type(metricas['chamadas']) is not int or metricas['chamadas'] < 0
        ):
            raise ValueError('quantidade de chamadas inválida')
        segundos = metricas.get('segundos', 0)
        if type(segundos) is not int or segundos < 0:
            raise ValueError('tempo de execução inválido')
        serializar(resultado)
        with self.transacao():
            tarefa = self.db.execute('SELECT * FROM tarefas WHERE id=?', (identificador,)).fetchone()
            if not tarefa or tarefa['status'] != 'RUNNING' or tarefa['dono'] != dono or tarefa['prazo'] <= time.time():
                raise ValueError('executor não possui reserva válida da tarefa')
            if status == 'COMPLETED':
                spec = json.loads(tarefa['especificacao'])
                regra = (ler_projeto(self.pasta) or {}).get('politica', {}).get('revisao_minima', {}).get(str(spec['risco']), {})
                if regra.get('independente') and not aprovacao_valida(self.atual(spec), artefato, resultado):
                    raise ValueError('política exige revisão independente executada pelo controlador')
                if spec.get('criterios_aceite'):
                    raise ValueError('critérios de aceite exigem revisão separada por critério')
                if spec['capacidade'] == 'validacao_json':
                    if artefato != conferir_deterministica(self.atual(spec)):
                        raise ValueError('artefato não corresponde à conferência determinística das fontes')
                    if metricas.get('chamadas') != 0 or resultado.get('execucao_iniciada') is not True:
                        raise ValueError('conferência determinística exige execução local sem chamadas a modelos')
                elif not (aprovacao_valida(self.atual(spec), artefato, resultado)
                          or self.fora_da_amostra(spec, artefato, resultado)):
                    raise ValueError('conclusão intermediária exige supervisão remota independente válida '
                                     'ou sorteio fora da amostra de revisão')
            hash_artefato = None
            if artefato is not None:
                hash_artefato = hashlib.sha256(artefato.encode()).hexdigest()
                objetos = self.pasta / 'artefatos'
                objetos.mkdir(exist_ok=True)
                if objetos.is_symlink():
                    raise ValueError('pasta de artefatos não pode ser link simbólico')
                destino = objetos / f'{hash_artefato}.txt'
                if destino.exists() or destino.is_symlink():
                    self.ler_artefato(hash_artefato)
                else:
                    fd, temporario = tempfile.mkstemp(prefix='.artefato-', dir=objetos)
                    try:
                        with os.fdopen(fd, 'w', encoding='utf-8') as arquivo:
                            arquivo.write(artefato)
                            arquivo.flush()
                            os.fsync(arquivo.fileno())
                        os.replace(temporario, destino)
                    finally:
                        pathlib.Path(temporario).unlink(missing_ok=True)
            self.db.execute('UPDATE tarefas SET status=?,resultado=?,artefato=?,hash_artefato=?,motivo=?,dono=NULL,prazo=NULL,atualizado=? WHERE id=?',
                            (status, serializar(resultado), hash_artefato, hash_artefato,
                             resultado.get('motivo') if isinstance(resultado.get('motivo'), str) else None,
                             time.time(), identificador))
            if resultado.get('execucao_iniciada') is False:
                self.db.execute('UPDATE tarefas SET tentativas=tentativas-1 WHERE id=?', (identificador,))
            self.evento(identificador, 'execucao_encerrada', {'dono': dono, 'status': status, 'resultado': resultado, 'artefato': hash_artefato})
            if status == 'COMPLETED':
                autorizar_conclusao(self.pasta, self.db.execute('SELECT * FROM tarefas WHERE id=?', (identificador,)).fetchone())

    def fora_da_amostra(self, spec, artefato, resultado):
        sorteio = resultado.get('amostragem')
        return (amostravel(spec) and 'supervisao' not in resultado
                and resultado.get('verificacao') == 'referencias_e_requisitos_validos'
                and type(resultado.get('metricas', {}).get('chamadas')) is int
                and isinstance(sorteio, dict) and sorteio.get('selecionada') is False
                and sorteio == amostragem(self, spec, resultado, artefato))

    def revisar(self, identificador, parecer, aprovar, revisor='humano', modelo=None, contexto='repositorio'):
        self.revisar_lote([identificador], parecer, aprovar, revisor, modelo, contexto)

    @auditar_recusa
    def revisar_lote(self, identificadores, parecer, aprovar, revisor='humano', modelo=None, contexto='repositorio'):
        exigir_controlador()
        if os.environ.get('JANGADA_ISOLADO'):
            raise ValueError('revisão da fila exige execução fora do isolamento')
        if (revisor not in {'humano', 'claude', 'codex', 'agy'}
                or contexto not in {'diff', 'repositorio'}
                or modelo is not None and (not isinstance(modelo, str) or not modelo.strip())):
            raise ValueError('identidade ou contexto do revisor inválido')
        if not isinstance(parecer, str) or not parecer.strip() or type(aprovar) is not bool:
            raise ValueError('revisão exige parecer e decisão explícitos')
        if not identificadores or len(set(identificadores)) != len(identificadores):
            raise ValueError('revisão exige identificadores sem repetição')
        if revisor != 'humano':
            # Rótulos e texto enviados pelo chamador não comprovam execução de
            # um modelo. Não registrar como realizada uma revisão inexistente.
            with self.transacao():
                for identificador in identificadores:
                    self.evento(identificador, 'autorizacao_recusada', {
                        'motivo': 'revisão de modelo sem comprovante de execução', 'revisor_declarado': revisor})
            raise ValueError('revisão de modelo exige execução verificável; rótulo fornecido não comprova independência')
        status = 'COMPLETED' if aprovar else 'REVISION_REQUIRED'
        with self.transacao():
            for identificador in identificadores:
                tarefa = self.db.execute('SELECT * FROM tarefas WHERE id=?', (identificador,)).fetchone()
                if tarefa and tarefa['status'] == 'COMPLETED' and conferir_conclusao(self.pasta, dict(tarefa))['status'] != 'COMPLETED':
                    self.evento(identificador, 'conclusao_nao_comprovada', {'estado_anterior': dict(tarefa)})
                    self.db.execute("UPDATE tarefas SET status='REVIEW_REQUIRED' WHERE id=?", (identificador,))
                    tarefa = self.db.execute('SELECT * FROM tarefas WHERE id=?', (identificador,)).fetchone()
                if not tarefa or tarefa['status'] != 'REVIEW_REQUIRED' or not tarefa['hash_artefato']:
                    raise ValueError(f'tarefa sem artefato aguardando revisão: {identificador}')
                self.ler_artefato(tarefa['hash_artefato'])
                spec = json.loads(tarefa['especificacao'])
                resultado = json.loads(tarefa['resultado']) if tarefa['resultado'] else {}
                autor, modelo_autor = identidade(resultado)
                modelo_autor = modelo_autor or resultado.get('modelo_declarado') or resultado.get('modelo')
                if revisor != 'humano' and (provedor_de(autor) == revisor or autor == 'nao_informado'
                        or not modelo or not modelo_autor or modelo == modelo_autor):
                    raise ValueError('revisão exige autor e revisor independentes e identificados')
                projeto = ler_projeto(self.pasta)
                regra = (projeto or {}).get('politica', {}).get('revisao_minima', {}).get(str(spec['risco']), {})
                if aprovar and regra.get('independente') and revisor == 'humano':
                    raise ValueError('política exige revisor independente com provedor e modelo identificados')
                if regra.get('contexto') == 'repositorio' and contexto != 'repositorio':
                    raise ValueError('política exige revisão com contexto do repositório')
                criterios = spec.get('criterios_aceite', [])
                if criterios:
                    documento = json.loads(parecer)
                    itens = documento.get('criterios') if isinstance(documento, dict) else None
                    if (not isinstance(itens, list) or len(itens) != len(criterios)
                            or documento.get('tarefa') != identificador
                            or documento.get('artefato_sha256') != tarefa['hash_artefato']
                            or any(not isinstance(i, dict) or i.get('criterio') != c
                                   or i.get('resultado') not in {'APROVADO', 'REVISAR'}
                                   or not isinstance(i.get('justificativa'), str) or not i['justificativa'].strip()
                                   for i, c in zip(itens, criterios))
                            or aprovar and any(i['resultado'] != 'APROVADO' for i in itens)):
                        raise ValueError('parecer não confere todos os critérios e o artefato atual')
                self.db.execute('UPDATE tarefas SET status=?,motivo=?,atualizado=? WHERE id=?',
                                (status, parecer, time.time(), identificador))
                execucao = 'exe-' + uuid.uuid4().hex[:16]
                agora = time.time()
                self.db.execute('''INSERT INTO execucoes
                    (id,tarefa,atividade,funcao,agente,provedor,modelo,inicio,fim,status,artefato,chamadas)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (execucao, identificador, spec.get('atividade'), 'revisao',
                    revisor, revisor, modelo, agora, agora, status, tarefa['hash_artefato'],
                    0 if revisor == 'humano' else None))
                self.evento(identificador, 'revisada', {'status': status, 'parecer': parecer, 'execucao': execucao,
                            'autor': autor, 'modelo_autor': modelo_autor, 'revisor': revisor, 'modelo': modelo,
                            'independente': True if revisor != 'humano' else None, 'contexto': contexto,
                            'artefato_sha256': tarefa['hash_artefato'], 'criterios_aceite': criterios})
                if aprovar:
                    autorizar_conclusao(self.pasta, self.db.execute('SELECT * FROM tarefas WHERE id=?', (identificador,)).fetchone())

    def ler_artefato(self, resumo):
        if not isinstance(resumo, str) or not re.fullmatch(r'[0-9a-f]{64}', resumo):
            raise ValueError('identificador de artefato inválido')
        pasta = self.pasta / 'artefatos'
        objeto = pasta / f'{resumo}.txt'
        if pasta.is_symlink() or objeto.is_symlink():
            raise ValueError('artefato não pode usar links simbólicos')
        conteudo = objeto.read_bytes()
        if hashlib.sha256(conteudo).hexdigest() != resumo:
            raise ValueError('artefato adulterado antes da revisão')
        return conteudo.decode('utf-8')

    def alterar(self, identificador, acao):
        destinos = {'cancelar': 'CANCELLED', 'pausar': 'PAUSED', 'retomar': 'QUEUED', 'repetir': 'QUEUED'}
        if acao not in destinos:
            raise ValueError('ação desconhecida')
        with self.transacao():
            tarefa = self.db.execute('SELECT * FROM tarefas WHERE id=?', (identificador,)).fetchone()
            if not tarefa or tarefa['status'] in FINAIS or tarefa['status'] == 'RUNNING':
                raise ValueError('tarefa inexistente, finalizada ou em execução')
            if acao == 'pausar' and tarefa['status'] in {'REVIEW_REQUIRED', 'REVISION_REQUIRED'}:
                raise ValueError('tarefa aguardando conferência não pode contornar a revisão por pausa')
            permitidos = {'retomar': {'PAUSED', 'WAITING_PROVIDER', 'WAITING_QUOTA', 'WAITING_REVIEWER'},
                          'repetir': {'REVISION_REQUIRED'}}
            if acao in permitidos and tarefa['status'] not in permitidos[acao]:
                raise ValueError('transição de tarefa inválida')
            self.db.execute('UPDATE tarefas SET status=?,motivo=NULL,atualizado=? WHERE id=?',
                            (destinos[acao], time.time(), identificador))
            if destinos[acao] == 'QUEUED':
                self.db.execute('UPDATE tarefas SET artefato=NULL,hash_artefato=NULL,resultado=NULL WHERE id=?', (identificador,))
            self.evento(identificador, acao, {})
