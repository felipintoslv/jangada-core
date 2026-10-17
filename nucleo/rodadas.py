"""Consulta das rodadas de revisão de uma sessão, só leitura e sem pareceres."""

import bisect
import collections
import contextlib
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'orquestracao'))

from contexto import objeto, pasta_leitura  # noqa: E402
from indicadores import rodada_valida  # noqa: E402
from sessoes import LIMITE, nome_valido  # noqa: E402

LINHAS_MAX = 5000
RODADAS_MAX = 50
LINHA_MAX = 64 * 1024
CAUDA_MAX = 8 * 1024 * 1024
CANDIDATOS_MAX = 16384
# Mesma janela de docs/registros.md, seção 2: parecer e linha caem no mesmo segundo.
JANELA = 60
TEXTO = re.compile(r'[A-Za-z0-9_.:/@+\[\]-]{0,128}')


class Uso(ValueError):
    pass


@contextlib.contextmanager
def subpasta(fd, nome):
    try:
        filho = os.open(nome, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    except FileNotFoundError:
        filho = None
    try:
        yield filho
    finally:
        if filho is not None:
            os.close(filho)


def linhas(fd, nome):
    """Últimas LINHAS_MAX linhas válidas; arquivo ausente não tem linhas."""
    try:
        arquivo_fd = os.open(nome, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return []
    with os.fdopen(arquivo_fd, 'rb') as arquivo:
        info = os.fstat(arquivo.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Registro de validação deve ser arquivo regular.')
        cauda = info.st_size > CAUDA_MAX
        if cauda:
            arquivo.seek(info.st_size - CAUDA_MAX)
        ultimas = collections.deque(maxlen=LINHAS_MAX)
        while True:
            linha = arquivo.readline(LINHA_MAX + 1)
            if not linha:
                break
            longa = len(linha) > LINHA_MAX
            pedaco = linha
            while len(pedaco) > LINHA_MAX and not pedaco.endswith(b'\n'):
                pedaco = arquivo.readline(LINHA_MAX + 1)
            if cauda:
                # A primeira linha da cauda pode começar no meio.
                cauda = False
                continue
            if not longa:
                ultimas.append(linha)
    registros = []
    for linha in ultimas:
        try:
            dados = json.loads(linha.decode('utf-8'))
        except (ValueError, RecursionError):
            continue
        if isinstance(dados, dict):
            registros.append(dados)
    return registros


def texto(valor):
    return valor if isinstance(valor, str) and TEXTO.fullmatch(valor) else None


def inteiro(valor, minimo=0):
    return valor if type(valor) is int and minimo <= valor <= 2 ** 53 else None


def numero(valor):
    if type(valor) is int:
        return inteiro(valor)
    return valor if type(valor) is float and math.isfinite(valor) and 0 <= valor <= 2 ** 53 else None


def momento(valor):
    if not isinstance(valor, str) or len(valor) > 64:
        return None
    try:
        quando = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return quando.timestamp() if quando.tzinfo else None


def execucao_valida(valor):
    return valor is None or (isinstance(valor, str) and 0 < len(valor) <= 128 and bool(TEXTO.fullmatch(valor)))


def pareceres(fd, sessao):
    """Mtime de cada validacao-SESSAO-rN.md do topo de agentes/, sem abrir o arquivo."""
    padrao = re.compile(r'validacao-' + re.escape(sessao) + r'-r[0-9]{1,9}\.md')
    achados = []
    with os.scandir(fd) as entradas:
        for entrada in entradas:
            if not padrao.fullmatch(entrada.name):
                continue
            if len(achados) >= CANDIDATOS_MAX:
                raise ValueError('Consulta excedeu 16384 pareceres.')
            try:
                info = os.stat(entrada.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                achados.append((info.st_mtime, entrada.name))
    return achados


def associar(candidatos, registros):
    """Parecer de cada registro só quando a correspondência por horário é única nos dois sentidos.

    Considera todas as linhas da sessão, de qualquer etapa e execução, antes do
    limite de rodadas: um parecer perto de duas linhas, ou duas perto de uma
    linha, fica sem dono.
    """
    candidatos = sorted(candidatos)
    horarios = [mtime for mtime, _ in candidatos]
    perto_do_registro, perto_do_parecer = {}, {}
    for posicao, registro in registros:
        quando = momento(registro.get('data'))
        if quando is None:
            continue
        inicio = bisect.bisect_left(horarios, quando - JANELA)
        fim = bisect.bisect_right(horarios, quando + JANELA)
        for _, nome in candidatos[inicio:fim]:
            perto_do_registro.setdefault(posicao, set()).add(nome)
            perto_do_parecer.setdefault(nome, set()).add(posicao)
    por_posicao = {posicao: registro for posicao, registro in registros}
    return {id(por_posicao[posicao]): nome for posicao, nomes in perto_do_registro.items()
            for nome in nomes if len(nomes) == 1 and perto_do_parecer[nome] == {posicao}}


def rodadas_sessao(raiz, sessao):
    if not nome_valido(sessao):
        raise Uso('Nome de sessão inválido.')
    raiz = Path(raiz).resolve()
    validacoes, candidatos = [], []
    execucao, aberta = None, False
    with pasta_leitura(raiz) as fd_raiz:
        if fd_raiz is not None:
            validacoes += [dict(x, origem='sessao') for x in linhas(fd_raiz, 'validar.jsonl')]
            # Exceção do contrato: em revisoes/ só este registro é aberto.
            with subpasta(fd_raiz, 'revisoes') as fd_rev:
                if fd_rev is not None:
                    validacoes += [dict(x, origem='protegida') for x in linhas(fd_rev, 'validar.jsonl')]
            with subpasta(fd_raiz, 'agentes') as fd_ag:
                if fd_ag is not None:
                    try:
                        registro = objeto(fd_ag, sessao + '.json')
                        aberta = True
                        execucao = registro.get('execucao')
                        if not execucao_valida(execucao):
                            raise ValueError('Execução inválida no registro da sessão.')
                    except FileNotFoundError:
                        pass
                    candidatos = pareceres(fd_ag, sessao)

    ordem = []
    for posicao, registro in enumerate(validacoes):
        if registro.get('rotulo') != sessao or not rodada_valida(registro):
            continue
        if not execucao_valida(registro.get('execucao')):
            continue
        quando = momento(registro.get('data'))
        ordem.append(((quando is not None, quando or 0, posicao), registro))
    ordem.sort(key=lambda par: par[0])
    if not aberta:
        execucao = ordem[-1][1].get('execucao') if ordem else None
    escolhidas = [r for _, r in ordem if r.get('execucao') == execucao][-RODADAS_MAX:]

    associados = associar(candidatos, [(posicao, r) for posicao, r in enumerate(validacoes)
                                       if r.get('origem') == 'sessao' and r.get('rotulo') == sessao])
    rodadas = []
    for registro in escolhidas:
        quando = momento(registro.get('data'))
        rodadas.append(dict(
            rodada=inteiro(registro.get('rodada'), 1),
            origem=registro['origem'],
            resultado=registro['resultado'],
            etapa=registro['etapa'],
            revisor=texto(registro.get('revisor')),
            modelo=texto(registro.get('modelo')),
            data=registro['data'] if quando is not None else None,
            segundos=numero(registro.get('segundos')),
            apontamentos=inteiro(registro.get('itens')),
            parecer_origem=associados.get(id(registro))))
    return {'versao': 1, 'sessao': sessao, 'execucao': execucao, 'rodadas': rodadas}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise Uso('Uso: rodadas.py ESTADO SESSAO')
        resposta = json.dumps(rodadas_sessao(*sys.argv[1:]), ensure_ascii=False, allow_nan=False) + '\n'
        if len(resposta.encode('utf-8')) > LIMITE:
            raise ValueError('Resposta excedeu 1 MiB.')
        sys.stdout.write(resposta)
    except Uso as erro:
        sys.stderr.write('jangada-agentes --rodadas-json: ' + str(erro) + '\n')
        sys.exit(2)
    except (OSError, ValueError, KeyError, RecursionError) as erro:
        sys.stderr.write('Não foi possível consultar as rodadas: ' + str(erro) + '\n')
        sys.exit(1)
