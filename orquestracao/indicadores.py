"""Resume os registros locais de custo, revisão e destino."""

import argparse
import json
import os
import re
import statistics
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from consumo_tarefa import medir


def linhas(path):
    try:
        with path.open(encoding='utf-8') as f:
            for linha in f:
                try:
                    d = json.loads(linha)
                    if isinstance(d, dict):
                        yield d
                except ValueError:
                    continue
    except OSError:
        return


def tokens(d, autor):
    dados = d.get('tokens') if isinstance(d.get('tokens'), dict) else d
    return {campo: dados.get(campo, d.get(campo)) for campo in
            ('entrada', 'saida', 'cache_lido', 'modelo', 'motivo')}


def texto_terminal(valor):
    return re.sub(r'[\x00-\x1f\x7f]', '', str(valor))


def inteiro(valor):
    return valor if type(valor) is int and valor >= 0 else 0


def carregar(estado, projeto, desde):
    consumos = [x for x in linhas(estado / 'consumo-tarefas.jsonl')
                if isinstance(x.get('sessao'), str) and x['sessao']
                and (x.get('execucao') is None or isinstance(x.get('execucao'), str))]
    validacoes = list(linhas(estado / 'validar.jsonl')) + list(linhas(estado / 'revisoes' / 'validar.jsonl'))
    delegacoes = list(linhas(estado / 'delegacoes.jsonl'))
    if desde:
        consumos = [x for x in consumos if isinstance(x.get('fim'), str) and x['fim'][:10] >= desde]
        validacoes = [x for x in validacoes if isinstance(x.get('data'), str) and x['data'][:10] >= desde]
        delegacoes = [x for x in delegacoes if isinstance(x.get('data'), str) and x['data'][:10] >= desde]
    if projeto:
        consumos = [x for x in consumos if x.get('projeto') == projeto]
        validacoes = [x for x in validacoes if x.get('projeto') == projeto]
        delegacoes = [x for x in delegacoes if x.get('projeto') == projeto]
    return consumos, validacoes, delegacoes


def montar(estado, projeto='', desde=''):
    estado = Path(estado)
    consumos, validacoes, delegacoes = carregar(estado, projeto, desde)
    tarefas = {}
    por_chave = {}
    for c in consumos:
        chave = (c.get('sessao'), c.get('execucao'))
        por_chave[chave] = c
    abertos = estado / 'agentes'
    if abertos.is_dir():
        for arq in abertos.glob('*.json'):
            try: m = json.loads(arq.read_text(encoding='utf-8'))
            except (OSError, ValueError): continue
            if not isinstance(m, dict): continue
            sessao = m.get('sessao', arq.stem)
            if not isinstance(sessao, str) or not sessao: continue
            execucao = m.get('execucao')
            if not isinstance(execucao, str): execucao = None
            chave = (sessao, execucao)
            if chave not in por_chave:
                raiz = m.get('raiz') or m.get('dir') or ''
                if not isinstance(raiz, str): continue
                projeto_aberto = Path(raiz).name
                if projeto and projeto_aberto != projeto:
                    continue
                inicio = m.get('desde') if isinstance(m.get('desde'), str) else ''
                if desde and inicio[:10] < desde:
                    continue
                agente = m.get('agente') if isinstance(m.get('agente'), str) else ''
                provedor = agente.split()
                autor = os.path.basename(provedor[0]) if provedor else ''
                tem_worktree = bool(m.get('worktree'))
                caminho = m.get('worktree') or m.get('dir') or raiz
                if not isinstance(caminho, str): continue
                medido = medir(estado, sessao, autor, caminho, inicio=inicio, worktree=tem_worktree)
                por_chave[chave] = dict(sessao=sessao, projeto=projeto_aberto, execucao=execucao,
                    autor=autor, tokens=medido, inicio=inicio or None, fim=None)
    for (sessao, execucao), c in por_chave.items():
        v = [x for x in validacoes if x.get('rotulo') == sessao and x.get('execucao') == execucao
             and x.get('etapa') == 'revisor' and x.get('resultado') in ('aprovado', 'revisar')]
        ds = [x for x in delegacoes if x.get('sessao') == sessao and x.get('execucao') == execucao]
        ultima = v[-1] if v else {}
        t = tokens(c, c.get('autor'))
        tarefas[f'{sessao}:{execucao or ""}'] = dict(sessao=sessao, autor=c.get('autor'), tokens=t,
            rodadas=len(v), ultimo_resultado=ultima.get('resultado'),
            delegacoes=[dict(papel=x.get('papel'), destino=x.get('destino'), modelo=x.get('modelo'),
                tokens_entrada=x.get('tokens_local_entrada') if x.get('destino') == 'local' else None,
                tokens_saida=x.get('tokens_local_saida') if x.get('destino') == 'local' else None,
                tokens_agy=x.get('tokens_agy'))
                for x in ds], segundos_revisao=sum(x.get('segundos', 0) for x in v
                    if isinstance(x.get('segundos'), (int, float))))
    grupos = {}
    for v in validacoes:
        if v.get('etapa') != 'revisor' or v.get('resultado') not in ('aprovado', 'revisar'): continue
        revisor = v.get('revisor') if isinstance(v.get('revisor'), str) else '?'
        modelo = v.get('modelo') if isinstance(v.get('modelo'), str) else '?'
        k = (revisor or '?', modelo or '?')
        g = grupos.setdefault(k, dict(revisor=k[0], modelo=k[1], pareceres=0, apontamentos=0,
            procedentes=0, rejeitados=0, sem_classificacao=0, casos=0))
        g['pareceres'] += 1; g['apontamentos'] += inteiro(v.get('itens'))
        r = v.get('resposta')
        responde_a = v.get('responde_a')
        if isinstance(r, dict) and isinstance(responde_a, dict):
            revisor_alvo = responde_a.get('revisor') if isinstance(responde_a.get('revisor'), str) else '?'
            modelo_alvo = responde_a.get('modelo') if isinstance(responde_a.get('modelo'), str) else '?'
            alvo = (revisor_alvo or '?', modelo_alvo or '?')
            classificado = grupos.setdefault(alvo, dict(revisor=alvo[0], modelo=alvo[1], pareceres=0,
                apontamentos=0, procedentes=0, rejeitados=0, sem_classificacao=0, casos=0))
            classificado['procedentes'] += inteiro(r.get('corrigidos'))
            classificado['rejeitados'] += inteiro(r.get('rejeitados'))
            classificado['sem_classificacao'] += inteiro(r.get('sem_classificar'))
            classificado['casos'] += sum(inteiro(r.get(x)) for x in ('corrigidos', 'rejeitados', 'sem_classificar'))
    revisores = []
    for g in grupos.values():
        n = g['procedentes'] + g['rejeitados']
        g['taxa_procedencia'] = g['procedentes'] / n if n else None
        g['casos_taxa'] = n
        revisores.append(g)
    destinos = {}
    for d in delegacoes:
        destino = d.get('destino') if isinstance(d.get('destino'), str) else '?'
        papel = d.get('papel') if isinstance(d.get('papel'), str) else '?'
        tent = d.get('tentativas') if isinstance(d.get('tentativas'), list) else []
        if destino != 'local' and any(x.get('destino') == 'local' for x in tent if isinstance(x, dict)):
            local = destinos.setdefault((papel or '?', 'local'), dict(papel=papel or '?', destino='local',
                chamadas=0, sucesso=0, recusas=0, segundos=[], tokens_entrada=None, tokens_saida=None,
                mudancas_local=0))
            local['mudancas_local'] += 1
        if destino not in {'local', 'agy'}:
            continue
        k = (papel, destino)
        g = destinos.setdefault(k, dict(papel=papel, destino=destino, chamadas=0, sucesso=0, recusas=0,
            segundos=[], tokens_entrada=None, tokens_saida=None, mudancas_local=0))
        g['chamadas'] += 1
        g['sucesso'] += int(d.get('codigo_saida') == 0 and not d.get('recusa'))
        g['recusas'] += int(bool(d.get('recusa')))
        if isinstance(d.get('segundos'), (int, float)): g['segundos'].append(d['segundos'])
        ti = d.get('tokens_local_entrada') if destino == 'local' else None
        ts = d.get('tokens_local_saida') if destino == 'local' else None
        if isinstance(ti, int): g['tokens_entrada'] = (g['tokens_entrada'] or 0) + ti
        if isinstance(ts, int): g['tokens_saida'] = (g['tokens_saida'] or 0) + ts
    for g in destinos.values():
        segundos = g.pop('segundos')
        g['segundos_medianos'] = statistics.median(segundos) if segundos else None
    return dict(versao=1, tarefas=list(tarefas.values()), revisores=revisores, local_vs_agy=list(destinos.values()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--estado', default=os.environ.get('JANGADA_ESTADO', str(Path.home() / '.local/state/jangada')))
    p.add_argument('--json', action='store_true'); p.add_argument('--projeto', default=''); p.add_argument('--desde', default='')
    a = p.parse_args()
    dados = montar(a.estado, a.projeto, a.desde)
    if a.json:
        print(json.dumps(dados, ensure_ascii=False))
    else:
        print(f"Tarefas: {len(dados['tarefas'])}")
        for t in dados['tarefas']:
            tokens = t['tokens']
            print(f"  {texto_terminal(t['sessao'])}: entrada {tokens.get('entrada')}, saída {tokens.get('saida')}, "
                  f"cache lido {tokens.get('cache_lido')}, rodadas {t['rodadas']}, revisão {t['segundos_revisao']} s")
        print(f"Revisores: {len(dados['revisores'])}")
        for r in dados['revisores']:
            taxa = 'sem casos' if r['taxa_procedencia'] is None else f"{r['taxa_procedencia']:.0%} ({r['casos_taxa']} casos)"
            print(f"  {texto_terminal(r['revisor'])} / {texto_terminal(r['modelo'])}: "
                  f"{r['procedentes']} procedentes, {r['rejeitados']} rejeitados, taxa {taxa}")
        print('Local e agy:')
        for d in dados['local_vs_agy']:
            print(f"  {texto_terminal(d['destino'])} / {texto_terminal(d['papel'])}: "
                  f"{d['chamadas']} chamadas, {d['sucesso']} sucesso(s), "
                  f"{d['recusas']} recusa(s), mediana {d['segundos_medianos']} s, "
                  f"tokens entrada {d['tokens_entrada']}, saída {d['tokens_saida']}, local transferido {d['mudancas_local']}")


if __name__ == '__main__': main()
