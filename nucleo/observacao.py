"""Caminhos públicos para a Central acompanhar mudanças de estado."""
import json
import os
from pathlib import Path
import stat
import sys

LIMITE_CAMINHOS = 4096
LIMITE_COMPRIMENTO = 4096
LIMITE_ENTRADAS = 16384
LIMITE_SAIDA = 1024 * 1024


def existentes(caminho, estado):
    atual = estado
    while True:
        try:
            info = atual.lstat()
        except FileNotFoundError:
            if atual == atual.parent:
                raise ValueError('Não há antepassado existente para observar.')
            atual = atual.parent
            continue
        if stat.S_ISDIR(info.st_mode):
            break
        if atual == atual.parent:
            raise ValueError('Não há diretório existente para observar.')
        atual = atual.parent
    for parte in caminho.relative_to(atual).parts:
        seguinte = atual / parte
        try:
            info = seguinte.lstat()
        except FileNotFoundError:
            return atual
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            return atual
        atual = seguinte
    return atual


def adicionar(caminhos, caminho):
    nome = str(caminho)
    if len(nome) > LIMITE_COMPRIMENTO or any(ord(c) < 32 for c in nome):
        return False
    caminhos.add(nome)
    if len(caminhos) > LIMITE_CAMINHOS:
        raise ValueError('A observação excedeu o limite de caminhos.')
    return True


def observar(estado):
    estado = Path(estado)
    if not estado.is_absolute() or any(ord(c) < 32 for c in str(estado)):
        raise ValueError('A pasta de estado precisa ser absoluta e válida.')
    estado = estado.resolve()
    caminhos = set()
    entradas = 0
    bases = (estado / 'agentes', estado / 'revisoes', estado / 'agentes/projetos')

    def contar_entrada():
        nonlocal entradas
        entradas += 1
        if entradas > LIMITE_ENTRADAS:
            raise ValueError('A observação excedeu o limite de entradas lidas.')

    for base in bases:
        pasta = existentes(base, estado)
        if not adicionar(caminhos, pasta):
            continue
        if pasta != base or not base.is_dir() or base.is_symlink():
            continue
        with os.scandir(base) as itens:
            for item in itens:
                contar_entrada()
                if base.name == 'projetos' and len(item.path) <= LIMITE_COMPRIMENTO \
                        and not any(ord(c) < 32 for c in item.path):
                    try:
                        if not item.is_dir(follow_symlinks=False):
                            if (item.name.endswith('.json') or item.name.startswith('tarefas.sqlite')) \
                                    and item.is_file(follow_symlinks=False):
                                adicionar(caminhos, item.path)
                            continue
                        projeto_caminhos = {item.path}
                        with os.scandir(item.path) as itens_projeto:
                            for arquivo in itens_projeto:
                                contar_entrada()
                                if arquivo.name.startswith('tarefas.sqlite') and arquivo.is_file(follow_symlinks=False):
                                    nome = arquivo.path
                                    if len(nome) <= LIMITE_COMPRIMENTO and not any(ord(c) < 32 for c in nome):
                                        projeto_caminhos.add(nome)
                    except (FileNotFoundError, PermissionError):
                        continue
                    for caminho in projeto_caminhos:
                        adicionar(caminhos, caminho)
                elif (item.name.endswith('.json') or item.name.startswith('tarefas.sqlite')) \
                        and item.is_file(follow_symlinks=False):
                    adicionar(caminhos, item.path)
    resposta = json.dumps({'versao': 1, 'caminhos': sorted(caminhos)}, ensure_ascii=False)
    if len(resposta.encode('utf-8')) > LIMITE_SAIDA:
        raise ValueError('A observação excedeu o limite de saída.')
    return resposta


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Informe a pasta de estado.')
        print(observar(sys.argv[1]))
    except (OSError, ValueError, RecursionError) as erro:
        print(f'jangada-agentes: {erro}', file=sys.stderr)
        raise SystemExit(1)
