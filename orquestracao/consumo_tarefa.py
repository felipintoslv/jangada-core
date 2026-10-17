"""Mede o consumo registrado pelo provedor do agente da sessão."""

import argparse
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

LIMITE_JSONL = 16 * 1024 * 1024


def ler_jsonl(arquivo):
    linhas = []
    parcial = False
    try:
        fd = os.open(arquivo, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None
            while True:
                linha = f.readline(LIMITE_JSONL + 1)
                if not linha:
                    break
                if len(linha) > LIMITE_JSONL and not linha.endswith(b'\n'):
                    parcial = True
                    while linha and not linha.endswith(b'\n'):
                        linha = f.readline(LIMITE_JSONL + 1)
                    continue
                if len(linha) > LIMITE_JSONL:
                    parcial = True
                    continue
                linhas.append(linha.decode('utf-8', errors='replace').rstrip('\r\n'))
        return linhas, parcial
    except OSError:
        return None


def numero(v):
    return v if type(v) is int and v >= 0 else 0


def instante(valor):
    if not isinstance(valor, str) or not valor:
        return None
    if valor.endswith('Z'):
        valor = valor[:-1] + '+00:00'
    try:
        data = datetime.fromisoformat(valor)
        return data if data.utcoffset() is not None else None
    except ValueError:
        return None


def diretorio_sem_link(pasta):
    try:
        return stat.S_ISDIR(pasta.lstat().st_mode)
    except OSError:
        return False


def arquivos_dentro(pasta, prefixo='', sufixo='.jsonl'):
    try:
        raiz = pasta.resolve(strict=True)
    except OSError:
        return []
    encontrados = []
    for diretorio, subpastas, nomes in os.walk(pasta, followlinks=False):
        atual = Path(diretorio)
        subpastas[:] = sorted(nome for nome in subpastas
                              if not (atual / nome).is_symlink())
        for nome in sorted(nomes):
            if not nome.startswith(prefixo) or not nome.endswith(sufixo):
                continue
            arquivo = atual / nome
            try:
                resolvido = arquivo.resolve(strict=True)
                if os.path.commonpath((str(raiz), str(resolvido))) != str(raiz):
                    continue
            except (OSError, RuntimeError, ValueError):
                continue
            encontrados.append(arquivo)
    return encontrados


def codex(estado, sessao, inicio):
    if sessao in {'.', '..'} or not re.fullmatch(r'[A-Za-z0-9_.-]+', sessao):
        return vazio('nome de sessão inválido')
    limite = instante(inicio) if inicio else None
    if inicio and limite is None:
        return vazio('início da sessão inválido')
    codex_home = estado / 'codex'
    pasta = codex_home / sessao
    sessions = pasta / 'sessions'
    if (not diretorio_sem_link(codex_home) or not diretorio_sem_link(pasta)
            or not diretorio_sem_link(sessions)):
        return vazio('pasta sessions do Codex ausente ou inválida')
    arquivos = arquivos_dentro(sessions, 'rollout-', '.jsonl')
    def instante_arquivo(caminho):
        try:
            info = caminho.lstat()
            return info.st_mtime if stat.S_ISREG(info.st_mode) else 0
        except OSError:
            return 0

    arquivos.sort(key=instante_arquivo)
    ultimo = None
    primeiro = None
    modelo = None
    parcial = False
    for arquivo in arquivos:
        lidas = ler_jsonl(arquivo)
        if lidas is None:
            continue
        linhas, descartou = lidas
        parcial = parcial or descartou
        try:
            for linha in linhas:
                try:
                    d = json.loads(linha)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(d, dict):
                    continue
                data = instante(d.get('timestamp'))
                if data is None or (limite and data < limite):
                    continue
                corpo = d.get('payload') if isinstance(d.get('payload'), dict) else d
                if corpo.get('type') in {'session_meta', 'turn_context'} or d.get('type') in {'session_meta', 'turn_context'}:
                    modelo = corpo.get('model') or modelo
                contagem = corpo.get('token_count')
                if contagem is None and corpo.get('type') == 'token_count':
                    contagem = corpo
                if isinstance(contagem, dict):
                    ultimo = contagem
                    inicial = uso_codex(contagem)
                    # O primeiro token_count costuma vir sem info, só com os limites.
                    if inicial is not None and (primeiro is None or data < primeiro[0]):
                        primeiro = (data, inicial)
                    modelo = corpo.get('model') or corpo.get('model_name') or modelo
        except OSError:
            continue
    if not ultimo:
        return vazio('medição parcial' if parcial else 'registro Codex ausente')
    t = ultimo.get('info') if isinstance(ultimo.get('info'), dict) else ultimo
    atual = t.get('total_token_usage') or t.get('last_token_usage') or t
    if not isinstance(atual, dict):
        return vazio('registro Codex inválido')
    # No Codex, input_tokens já inclui os cached_input_tokens.
    contexto = numero(primeiro[1].get('input_tokens')) if primeiro else None
    return dict(entrada=numero(atual.get('input_tokens')), saida=numero(atual.get('output_tokens')),
                cache_lido=numero(atual.get('cached_input_tokens')), modelo=modelo,
                motivo='medição parcial' if parcial else None,
                contexto_inicial=contexto,
                motivo_contexto=None if primeiro else 'primeiro token_count sem uso registrado')


def uso_codex(contagem):
    info = contagem.get('info') if isinstance(contagem.get('info'), dict) else None
    if info is None and 'input_tokens' in contagem:
        info = {'last_token_usage': contagem}
    if info is None:
        return None
    uso = info.get('last_token_usage') or info.get('total_token_usage')
    return uso if isinstance(uso, dict) and type(uso.get('input_tokens')) is int else None


def claude(home, projeto, inicio):
    limite = instante(inicio) if inicio else None
    if inicio and limite is None:
        return vazio('início da sessão inválido')
    claude_home = home / '.claude'
    projetos = claude_home / 'projects'
    chave = re.sub(r'[^A-Za-z0-9]', '-', str(Path(projeto).resolve()))
    pasta = projetos / chave
    if (not diretorio_sem_link(claude_home) or not diretorio_sem_link(projetos)
            or not diretorio_sem_link(pasta)):
        return vazio('pasta do projeto Claude ausente ou inválida')
    vistos, respostas = set(), []
    parcial = False
    try:
        arquivos = arquivos_dentro(pasta, '', '.jsonl')
        for arquivo in arquivos:
            lidas = ler_jsonl(arquivo)
            if lidas is None:
                continue
            linhas, descartou = lidas
            parcial = parcial or descartou
            try:
                for linha in linhas:
                    if '"usage"' not in linha:
                        continue
                    try:
                        d = json.loads(linha)
                    except (ValueError, RecursionError):
                        continue
                    if not isinstance(d, dict):
                        continue
                    msg = d.get('message')
                    if not isinstance(msg, dict):
                        continue
                    uso = msg.get('usage')
                    if not isinstance(uso, dict):
                        continue
                    timestamp = d.get('timestamp') or ''
                    data = instante(timestamp)
                    if data is None or (limite and data < limite):
                        continue
                    chave_msg = (msg.get('id'), d.get('requestId'))
                    if chave_msg in vistos:
                        continue
                    vistos.add(chave_msg)
                    respostas.append((timestamp, uso, msg.get('model')))
            except OSError:
                continue
    except OSError:
        return vazio('não foi possível ler registros Claude')
    if not respostas:
        return vazio('medição parcial' if parcial else 'registro Claude ausente')
    respostas.sort(key=lambda x: instante(x[0]))
    primeira = respostas[0][1]
    return dict(entrada=sum(numero(x[1].get('input_tokens')) for x in respostas),
                saida=sum(numero(x[1].get('output_tokens')) for x in respostas),
                cache_lido=sum(numero(x[1].get('cache_read_input_tokens')) for x in respostas),
                modelo=next((x[2] for x in reversed(respostas) if x[2]), None),
                motivo='medição parcial' if parcial else None,
                contexto_inicial=sum(numero(primeira.get(campo)) for campo in
                                     ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')),
                motivo_contexto=None)


def vazio(motivo):
    return dict(entrada=None, saida=None, cache_lido=None, modelo=None, motivo=motivo,
                contexto_inicial=None, motivo_contexto=motivo)


def medir(estado, sessao, autor, projeto, home=None, inicio=None, worktree=True):
    estado = Path(estado)
    if autor == 'codex':
        return codex(estado, sessao, inicio)
    if autor == 'claude':
        if not projeto:
            return vazio('pasta do projeto ausente')
        if not worktree:
            return vazio('sem worktree para separar conversas do projeto')
        return claude(Path(home or os.environ.get('HOME', '~')).expanduser(), projeto, inicio)
    return vazio('provedor sem medição disponível')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('estado'); p.add_argument('sessao'); p.add_argument('autor')
    p.add_argument('--projeto', default=''); p.add_argument('--home'); p.add_argument('--inicio')
    p.add_argument('--sem-worktree', action='store_true')
    a = p.parse_args()
    print(json.dumps(medir(a.estado, a.sessao, a.autor, a.projeto, a.home, a.inicio,
                           not a.sem_worktree), ensure_ascii=False))


if __name__ == '__main__':
    main()
