"""Consulta dos coordenadores abertos pelo jangada-coordenador, só leitura."""

from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True

from contexto import objeto, pasta_leitura  # noqa: E402
from sessoes import LIMITE, eh_sessao, nome_valido  # noqa: E402

REGISTROS_MAX = 4096
LINHA_MAX = 200
ESTADOS = ('iniciado', 'trabalhando', 'aguardando', 'concluido', 'encerrado')
PROVEDORES = ('claude', 'codex')
ANSI = re.compile('\x1b\\[[0-?]*[ -/]*[@-~]')
CONTROLE = re.compile('[\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]')


def texto(dados, nome, limite=4096):
    valor = dados.get(nome)
    if not isinstance(valor, str) or len(valor) > limite or CONTROLE.search(valor):
        return None
    return valor


def data(dados, nome):
    valor = texto(dados, nome, 64)
    try:
        datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    return valor


def ultima_linha(dados):
    valor = dados.get('ultima_linha')
    if not isinstance(valor, str):
        return None
    return CONTROLE.sub(' ', ANSI.sub('', valor)).strip()[:LINHA_MAX]


def arquivos(fd, sufixo='.json'):
    """Nomes SESSAO.json de arquivos regulares, sem seguir links."""
    nomes = []
    with os.scandir(fd) as entradas:
        for entrada in entradas:
            nome = entrada.name
            if not nome.endswith(sufixo) or not eh_sessao(nome) or not nome_valido(nome[:-5]):
                continue
            try:
                info = os.stat(nome, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                nomes.append(nome)
            if len(nomes) > REGISTROS_MAX:
                raise ValueError('Consulta excedeu %d registros.' % REGISTROS_MAX)
    return sorted(nomes)


def tarefas_por_coordenador(estado, vivas):
    """Tarefas lidas das cópias em revisoes/, que o agente isolado não grava.
    Cópia ilegível fica de fora."""
    tarefas = {}
    with pasta_leitura(Path(estado) / 'revisoes') as fd:
        if fd is None:
            return tarefas
        for nome in arquivos(fd):
            try:
                dados = objeto(fd, nome)
            except (OSError, ValueError):
                continue
            coordenador = dados.get('coordenador_sessao')
            if isinstance(coordenador, str) and nome_valido(coordenador):
                sessao = nome[:-5]
                tarefas.setdefault(coordenador, []).append({'sessao': sessao, 'viva': sessao in vivas})
    return tarefas


def coordenadores(estado, vivas):
    tarefas = tarefas_por_coordenador(estado, vivas)
    lista = []
    with pasta_leitura(Path(estado) / 'coordenadores') as fd:
        if fd is not None:
            # A pasta guarda também a aprovação dos hooks do Codex.
            for nome in arquivos(fd, '--coordenador.json'):
                try:
                    dados = objeto(fd, nome)
                except FileNotFoundError:
                    continue
                sessao = nome[:-5]
                estado_atual = dados.get('estado') if dados.get('estado') in ESTADOS else None
                provedor = dados.get('provedor') if dados.get('provedor') in PROVEDORES else None
                encerrado = data(dados, 'encerrado') is not None
                projeto = texto(dados, 'projeto')
                lista.append({
                    'sessao': sessao,
                    'projeto': projeto if projeto and projeto.startswith('/') else None,
                    'provedor': provedor,
                    'estado': estado_atual,
                    'ultima_linha': ultima_linha(dados),
                    'atualizado': data(dados, 'atualizado'),
                    'viva': sessao in vivas and not encerrado,
                    'tarefas': tarefas.get(sessao, []),
                })
    return {'versao': 1, 'coordenadores': lista}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Uso: coordenadores.py ESTADO')
        bruto = sys.stdin.buffer.read(LIMITE + 1)
        if len(bruto) > LIMITE:
            raise ValueError('Lista de sessões vivas excedeu 1 MiB.')
        vivas = {s for s in bruto.decode('utf-8').splitlines() if s}
        resposta = json.dumps(coordenadores(sys.argv[1], vivas), ensure_ascii=False, allow_nan=False) + '\n'
        if len(resposta.encode('utf-8')) > LIMITE:
            raise ValueError('Resposta excedeu 1 MiB.')
        sys.stdout.write(resposta)
    except (OSError, ValueError, RecursionError) as erro:
        sys.stderr.write('Não foi possível consultar os coordenadores: ' + str(erro) + '\n')
        sys.exit(1)
