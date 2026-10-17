"""Mede o consumo registrado pelo provedor do agente da sessão."""

import argparse
import json
import os
import re
from pathlib import Path


def numero(v):
    return v if type(v) is int and v >= 0 else 0


def codex(estado, sessao):
    arquivos = sorted((estado / 'codex' / sessao).glob('sessions/**/rollout-*.jsonl'),
                      key=lambda p: p.stat().st_mtime if p.exists() else 0)
    ultimo = None
    modelo = None
    for arquivo in arquivos:
        try:
            for linha in arquivo.read_text(encoding='utf-8', errors='replace').splitlines():
                try:
                    d = json.loads(linha)
                except ValueError:
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
    return dict(entrada=numero(atual.get('input_tokens')), saida=numero(atual.get('output_tokens')),
                cache_lido=numero(atual.get('cached_input_tokens')), modelo=modelo,
                motivo=None)


def claude(home, projeto):
    projetos = home / '.claude' / 'projects'
    chave = re.sub(r'[^A-Za-z0-9]', '-', str(Path(projeto).resolve()))
    pasta = projetos / chave
    vistos, respostas = set(), []
    try:
        arquivos = pasta.rglob('*.jsonl')
        for arquivo in arquivos:
            try:
                with arquivo.open(encoding='utf-8', errors='replace') as f:
                    for linha in f:
                        if '"usage"' not in linha:
                            continue
                        try:
                            d = json.loads(linha)
                        except ValueError:
                            continue
                        msg = d.get('message') or {}
                        uso = msg.get('usage')
                        if not isinstance(uso, dict):
                            continue
                        chave_msg = (msg.get('id'), d.get('requestId'))
                        if chave_msg in vistos:
                            continue
                        vistos.add(chave_msg)
                        respostas.append((d.get('timestamp') or '', uso, msg.get('model')))
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


def medir(estado, sessao, autor, projeto, home=None):
    estado = Path(estado)
    if autor == 'codex':
        return codex(estado, sessao)
    if autor == 'claude':
        if not projeto:
            return vazio('pasta do projeto ausente')
        return claude(Path(home or os.environ.get('HOME', '~')).expanduser(), projeto)
    return vazio('provedor sem medição disponível')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('estado'); p.add_argument('sessao'); p.add_argument('autor')
    p.add_argument('--projeto', default=''); p.add_argument('--home')
    a = p.parse_args()
    print(json.dumps(medir(a.estado, a.sessao, a.autor, a.projeto, a.home), ensure_ascii=False))


if __name__ == '__main__':
    main()
