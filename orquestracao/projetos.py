"""Identidade e política de projetos, sem executar conteúdo dos registros."""

import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sqlite3
import tempfile
import time


def chave(caminho):
    return hashlib.sha256(str(Path(caminho).resolve()).encode()).hexdigest()


def ler_json(caminho):
    fd = os.open(caminho, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as arquivo:
        if not stat.S_ISREG(os.fstat(arquivo.fileno()).st_mode):
            raise ValueError('registro deve ser arquivo regular')
        bruto = arquivo.read(1024 * 1024 + 1)
    if len(bruto) > 1024 * 1024:
        raise ValueError('registro excede 1 MiB')
    return json.loads(bruto)


def politica_valida(politica):
    if not isinstance(politica, dict) or politica.keys() - {'dados', 'provedores', 'orcamento', 'revisao_minima'}:
        raise ValueError('política de projeto inválida')
    if politica.get('dados', 'remoto_permitido') not in {'local', 'remoto_permitido'}:
        raise ValueError('política de dados inválida')
    provedores = politica.get('provedores', [])
    if (not isinstance(provedores, list) or any(not isinstance(p, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', p) for p in provedores)
            or len(provedores) != len(set(provedores))):
        raise ValueError('provedores da política inválidos')
    orcamento = politica.get('orcamento', {})
    if not isinstance(orcamento, dict) or orcamento.keys() - {'chamadas', 'custo_estimado', 'periodo_segundos'}:
        raise ValueError('orçamento de projeto inválido')
    for campo in ('chamadas', 'periodo_segundos'):
        if campo in orcamento and (type(orcamento[campo]) is not int or orcamento[campo] <= 0):
            raise ValueError(f'{campo} deve ser inteiro positivo')
    if 'custo_estimado' in orcamento and (type(orcamento['custo_estimado']) not in (int, float)
            or not math.isfinite(orcamento['custo_estimado']) or orcamento['custo_estimado'] < 0):
        raise ValueError('custo estimado inválido')
    revisao = politica.get('revisao_minima', {})
    if not isinstance(revisao, dict):
        raise ValueError('política de revisão inválida')
    for risco, regra in revisao.items():
        if (risco not in {'0', '1', '2', '3', '4'} or not isinstance(regra, dict)
                or regra.keys() - {'independente', 'contexto'}
                or type(regra.get('independente', True)) is not bool
                or regra.get('contexto', 'diff') not in {'diff', 'repositorio'}):
            raise ValueError('regra de revisão inválida')


def ler_projeto(pasta):
    try:
        dados = ler_json(Path(pasta) / 'projeto.json')
    except FileNotFoundError:
        return None
    if (not isinstance(dados, dict) or not isinstance(dados.get('id'), str)
            or len(dados['id']) != 64 or any(c not in '0123456789abcdef' for c in dados['id'])
            or not isinstance(dados.get('caminho'), str) or not Path(dados['caminho']).is_absolute()
            or not isinstance(dados.get('nome'), str) or not dados['nome'].strip()
            or not isinstance(dados.get('caminhos_anteriores', []), list)
            or any(not isinstance(c, str) or not Path(c).is_absolute() for c in dados.get('caminhos_anteriores', []))):
        raise ValueError('registro de projeto inválido')
    politica_valida(dados.get('politica', {}))
    return dados


def gravar_json(caminho, dados):
    caminho = Path(caminho)
    if caminho.is_symlink():
        raise ValueError('registro não pode ser ligação simbólica')
    fd, temporario = tempfile.mkstemp(prefix='.projeto-', dir=caminho.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, allow_nan=False)
            arquivo.write('\n')
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        Path(temporario).unlink(missing_ok=True)


@contextlib.contextmanager
def trava_projetos(raiz, exclusiva=False):
    raiz = Path(raiz)
    raiz.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(raiz / 'projetos.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('trava de projetos deve ser arquivo regular')
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusiva else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('projeto em uso; tente novamente depois da operação atual') from None
        yield
    finally:
        os.close(fd)


def cadastrar(estado, caminho, politica=None):
    caminho = str(Path(caminho).resolve(strict=True))
    politica_valida(politica if politica is not None else {})
    with estado.transacao():
        existente = ler_projeto(estado.pasta)
        dados = existente or dict(id=chave(caminho), caminho=caminho,
                                                 nome=Path(caminho).name, criado=time.time(), politica={})
        if dados['caminho'] != caminho:
            raise ValueError('estado pertence a outro caminho')
        if existente is not None and politica is None:
            return dados
        if politica is not None:
            if estado.db.execute("SELECT 1 FROM execucoes WHERE status='RUNNING'").fetchone():
                raise ValueError('política não pode mudar durante execução; para encerrar registro de sessão órfã, '
                                 'use jangada-projeto --projeto PASTA sessao-encerrar NOME fora do isolamento')
            if 'chamadas' in politica.get('orcamento', {}):
                estado.chamadas_usadas(politica['orcamento'])
            dados['politica'] = politica
        gravar_json(estado.pasta / 'projeto.json', dados)
    return dados


def especificacao_atual(tarefa, projeto):
    if projeto is None:
        return tarefa
    tarefa = dict(tarefa)
    atuais = Path(projeto['caminho'])

    def resolver(nome):
        caminho = Path(nome)
        for anterior in reversed(projeto.get('caminhos_anteriores', [])):
            if caminho.is_relative_to(anterior):
                return str(atuais / caminho.relative_to(anterior))
        return nome

    for campo in ('fontes', 'contexto'):
        if campo in tarefa:
            tarefa[campo] = [resolver(f) for f in tarefa[campo]]
    if 'hashes_fontes' in tarefa:
        tarefa['hashes_fontes'] = {resolver(f): h for f, h in tarefa['hashes_fontes'].items()}
    if 'esquema' in tarefa:
        tarefa['esquema'] = resolver(tarefa['esquema'])
    return tarefa


def provedor_de(executor):
    return {'local': 'ollama', 'codex-economico': 'codex', 'codex-principal': 'codex'}.get(executor, executor)


def executor_permitido(projeto, executor):
    if projeto is None or executor == 'deterministico':
        return True
    politica = projeto['politica']
    provedor = provedor_de(executor)
    return (('provedores' not in politica or provedor in politica['provedores'])
            and (politica.get('dados') != 'local' or provedor == 'ollama'))


def reassociar(raiz, antigo, novo):
    raiz = Path(raiz).resolve()
    antigo, novo = Path(antigo).resolve(), Path(novo).resolve(strict=True)
    if not novo.is_dir() or antigo == novo:
        raise ValueError('novo caminho deve ser uma pasta diferente')
    origem = raiz / 'agentes/projetos' / chave(antigo)
    destino = raiz / 'agentes/projetos' / chave(novo)
    with trava_projetos(raiz, exclusiva=True):
        if origem.is_symlink() or not origem.is_dir() or origem.parent.is_symlink():
            raise ValueError('estado de origem ausente ou com ligação simbólica')
        if destino.exists() or destino.is_symlink():
            raise ValueError('novo caminho já tem estado; reassociação recusada')
        for arquivo in (raiz / 'agentes').glob('*.json'):
            sessao = ler_json(arquivo)
            if isinstance(sessao, dict) and sessao.get('raiz') == str(antigo):
                raise ValueError('encerre as sessões do projeto antes de reassociar')
        banco = origem / 'tarefas.sqlite'
        if any((origem / n).is_symlink() for n in ('tarefas.sqlite', 'tarefas.sqlite-wal', 'tarefas.sqlite-shm')):
            raise ValueError('banco não pode ser ligação simbólica')
        with contextlib.closing(sqlite3.connect(banco.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM tarefas WHERE status='RUNNING'").fetchone():
                raise ValueError('projeto tem reserva ativa')
        dados = ler_projeto(origem) or dict(id=chave(antigo), nome=antigo.name, criado=time.time(),
                                           caminho=str(antigo), politica={})
        if dados['caminho'] != str(antigo):
            raise ValueError('registro pertence a outro caminho')
        atual = {**dados, 'caminho': str(novo), 'nome': novo.name,
                 'caminhos_anteriores': [*dados.get('caminhos_anteriores', []), str(antigo)]}
        origem.rename(destino)
        try:
            gravar_json(destino / 'projeto.json', atual)
        except BaseException:
            destino.rename(origem)
            raise
        return atual
