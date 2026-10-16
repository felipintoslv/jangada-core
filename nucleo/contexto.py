"""Consultas explícitas do terminal; conteúdo repassado nunca é autorização."""

import contextlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True

from sessoes import LIMITE, TEXTO_MAX, eh_sessao, nome_valido


@contextlib.contextmanager
def pasta_leitura(caminho):
    try:
        fd = os.open(caminho, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        fd = None
    try:
        yield fd
    finally:
        if fd is not None:
            os.close(fd)


def ler(fd, nome):
    arquivo_fd = os.open(nome, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(arquivo_fd, 'rb') as arquivo:
        info = os.fstat(arquivo.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMITE:
            raise ValueError('Fonte deve ser regular e ter no máximo 1 MiB.')
        bruto = arquivo.read(LIMITE + 1)
    if len(bruto) > LIMITE:
        raise ValueError('Fonte excedeu 1 MiB.')
    return bruto.decode('utf-8')


def objeto(fd, nome):
    dados = json.loads(ler(fd, nome))
    if not isinstance(dados, dict):
        raise ValueError('Registro deve ser objeto JSON.')
    return dados


def campo(dados, nome):
    valor = dados.get(nome)
    if valor is None:
        return ''
    limite = LIMITE if nome == 'tarefa' else TEXTO_MAX
    if not isinstance(valor, str) or len(valor) > limite or '\x00' in valor:
        raise ValueError('Campo inválido: ' + nome)
    valor.encode('utf-8')
    return valor


def sessao_worktree(raiz, worktree):
    if not Path(worktree).is_absolute() or len(worktree) > 4096:
        raise ValueError('Worktree deve ser caminho absoluto de até 4096 caracteres.')
    achadas = []
    quantidade = 0
    with pasta_leitura(Path(raiz).resolve() / 'agentes') as fd:
        if fd is not None:
            with os.scandir(fd) as entradas:
                for entrada in entradas:
                    nome = entrada.name
                    if not eh_sessao(nome):
                        continue
                    try:
                        info = os.stat(nome, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            continue
                        if not nome_valido(nome[:-5]):
                            raise ValueError('Nome de sessão inválido.')
                        dados = objeto(fd, nome)
                    except FileNotFoundError:
                        continue
                    quantidade += 1
                    if quantidade > 4096:
                        raise ValueError('Consulta excedeu 4096 registros.')
                    if campo(dados, 'worktree') == worktree:
                        achadas.append(nome[:-5])
    if len(achadas) > 1:
        raise ValueError('Worktree associado a várias sessões: ' + ', '.join(achadas))
    return {'versao': 1, 'sessao': achadas[0] if achadas else None}


def contexto_sessao(raiz, sessao):
    if not nome_valido(sessao):
        raise ValueError('Nome de sessão inválido.')
    tarefa, parecer = '', None
    padrao = re.compile(r'validacao-' + re.escape(sessao) + r'-r([0-9]+)\.md')
    quantidade = 0
    empatados = 0

    def procurar(fd, prefixo='', profundidade=0):
        nonlocal parecer, quantidade, empatados
        if profundidade > 32:
            raise ValueError('Profundidade de pareceres excedida.')
        with os.scandir(fd) as entradas:
            for entrada in entradas:
                nome = entrada.name
                if not prefixo and nome in ('projetos', 'runtime'):
                    continue
                try:
                    match = padrao.fullmatch(nome)
                    diretorio = not match and entrada.is_dir(follow_symlinks=False)
                    if not match and not diretorio:
                        continue
                    quantidade += 1
                    if quantidade > 16384:
                        raise ValueError('Consulta excedeu 16384 candidatos e pastas.')
                    relativo = prefixo + nome
                    if match:
                        if len(match[1]) > 9:
                            raise ValueError('Rodada de parecer excedeu nove dígitos.')
                        rodada = int(match[1])
                        info = os.stat(nome, dir_fd=fd, follow_symlinks=False)
                        # Links e FIFO candidatos são recusados mesmo quando antigos.
                        if not stat.S_ISREG(info.st_mode):
                            raise ValueError('Parecer deve ser arquivo regular sem link.')
                        if parecer is None or rodada > parecer['rodada']:
                            if any(not nome_valido(parte) for parte in relativo.split('/')) or len(relativo) > 4096:
                                raise ValueError('Origem de parecer inválida.')
                            parecer = dict(rodada=rodada, origem=relativo)
                            empatados = 1
                        elif rodada == parecer['rodada']:
                            empatados += 1
                    else:
                        filho = os.open(nome, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            procurar(filho, relativo + '/', profundidade + 1)
                        finally:
                            os.close(filho)
                except FileNotFoundError:
                    continue

    with pasta_leitura(Path(raiz).resolve() / 'agentes') as fd:
        if fd is not None:
            try:
                tarefa = campo(objeto(fd, sessao + '.json'), 'tarefa')
            except FileNotFoundError:
                pass
            procurar(fd)
            if empatados > 1:
                raise ValueError('Parecer mais recente ambíguo.')
            if parecer:
                # Reabre cada componente sem seguir links, inclusive após a seleção.
                atual = os.dup(fd)
                partes = parecer['origem'].split('/')
                try:
                    for parte in partes[:-1]:
                        filho = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=atual)
                        os.close(atual)
                        atual = filho
                    parecer['texto'] = ler(atual, partes[-1])
                except FileNotFoundError:
                    parecer = None
                finally:
                    os.close(atual)
    return {'versao': 1, 'sessao': sessao, 'tarefa': tarefa, 'parecer': parecer}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4:
            raise ValueError('Informe operação e argumento da consulta.')
        operacao, raiz, argumento = sys.argv[1:]
        consulta = {'--sessao-worktree-json': sessao_worktree, '--contexto-json': contexto_sessao}[operacao]
        resposta = json.dumps(consulta(raiz, argumento), ensure_ascii=False, allow_nan=False) + '\n'
        if len(resposta.encode('utf-8')) > LIMITE:
            raise ValueError('Resposta excedeu 1 MiB.')
        sys.stdout.write(resposta)
    except (OSError, ValueError, KeyError, RecursionError) as erro:
        sys.stderr.write('Não foi possível consultar o terminal: ' + str(erro) + '\n')
        sys.exit(1)
