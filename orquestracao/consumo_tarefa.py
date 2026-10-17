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
    try:
        fd = os.open(arquivo, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMITE_JSONL:
                return None
            conteudo = f.read(LIMITE_JSONL + 1)
        if len(conteudo) > LIMITE_JSONL:
            return None
        return conteudo.decode('utf-8', errors='replace').splitlines()
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
    modelo = None
    for arquivo in arquivos:
        linhas = ler_jsonl(arquivo)
        if linhas is None:
            continue
        try:
            for linha in linhas:
                try:
                    d = json.loads(linha)
                except ValueError:
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
                    modelo = corpo.get('model') or corpo.get('model_name') or modelo
        except OSError:
            continue
    if not ultimo:
        return vazio('registro Codex ausente')
    t = ultimo.get('info') if isinstance(ultimo.get('info'), dict) else ultimo
    atual = t.get('total_token_usage') or t.get('last_token_usage') or t
    if not isinstance(atual, dict):
        return vazio('registro Codex inválido')
    return dict(entrada=numero(atual.get('input_tokens')), saida=numero(atual.get('output_tokens')),
                cache_lido=numero(atual.get('cached_input_tokens')), modelo=modelo,
                motivo=None)


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
    try:
        arquivos = arquivos_dentro(pasta, '', '.jsonl')
        for arquivo in arquivos:
            linhas = ler_jsonl(arquivo)
            if linhas is None:
                continue
            try:
                for linha in linhas:
                    if '"usage"' not in linha:
                        continue
                    try:
                        d = json.loads(linha)
                    except ValueError:
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
        return vazio('registro Claude ausente')
    respostas.sort(key=lambda x: x[0])
    return dict(entrada=sum(numero(x[1].get('input_tokens')) for x in respostas),
                saida=sum(numero(x[1].get('output_tokens')) for x in respostas),
                cache_lido=sum(numero(x[1].get('cache_read_input_tokens')) for x in respostas),
                modelo=next((x[2] for x in reversed(respostas) if x[2]), None), motivo=None)


def vazio(motivo):
    return dict(entrada=None, saida=None, cache_lido=None, modelo=None, motivo=motivo)


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
