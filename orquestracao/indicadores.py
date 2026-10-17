"""Resume os registros locais de custo, revisão e destino."""

import argparse
import json
import os
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


def carregar(estado, projeto, desde):
    consumos = list(linhas(estado / 'consumo-tarefas.jsonl'))
    validacoes = list(linhas(estado / 'validar.jsonl')) + list(linhas(estado / 'revisoes' / 'validar.jsonl'))
    delegacoes = list(linhas(estado / 'delegacoes.jsonl'))
    if desde:
        consumos = [x for x in consumos if (x.get('fim') or '')[:10] >= desde]
        validacoes = [x for x in validacoes if (x.get('data') or '')[:10] >= desde]
        delegacoes = [x for x in delegacoes if (x.get('data') or '')[:10] >= desde]
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
            chave = (m.get('sessao') or arq.stem, m.get('execucao'))
            if chave not in por_chave and m.get('estado') not in {'concluido', 'encerrado'}:
                projeto_aberto = Path(m.get('raiz') or m.get('dir') or '').name
                if projeto and projeto_aberto != projeto:
                    continue
                if desde and (m.get('desde') or '')[:10] < desde:
                    continue
                provedor = (m.get('agente') or '').split()
                tem_worktree = bool(m.get('worktree'))
                medido = medir(estado, chave[0], os.path.basename(provedor[0]) if provedor else '',
                               m.get('worktree') or m.get('dir') or m.get('raiz'),
                               inicio=m.get('desde'), worktree=tem_worktree)
                por_chave[chave] = dict(sessao=chave[0], projeto=projeto_aberto, execucao=chave[1],
                    autor=m.get('agente'), tokens=medido, inicio=m.get('desde'), fim=None)
    for (sessao, execucao), c in por_chave.items():
        v = [x for x in validacoes if x.get('rotulo') == sessao and x.get('execucao') == execucao]
        ds = [x for x in delegacoes if x.get('sessao') == sessao and x.get('execucao') == execucao]
        ultima = max(v, key=lambda x: x.get('rodada', 0), default={})
        t = tokens(c, c.get('autor'))
        tarefas[f'{sessao}:{execucao or ""}'] = dict(sessao=sessao, autor=c.get('autor'), tokens=t,
            rodadas=len([x for x in v if x.get('etapa') == 'revisor']), ultimo_resultado=ultima.get('resultado'),
            delegacoes=[dict(papel=x.get('papel'), destino=x.get('destino'), modelo=x.get('modelo'),
                tokens_entrada=x.get('tokens_local_entrada') if x.get('destino') == 'local' else None,
                tokens_saida=x.get('tokens_local_saida') if x.get('destino') == 'local' else None,
                tokens_agy=x.get('tokens_agy'))
                for x in ds], segundos_revisao=sum(x.get('segundos', 0) for x in v if x.get('etapa') == 'revisor'))
    grupos = {}
    for v in validacoes:
        if v.get('etapa') != 'revisor': continue
        k = (v.get('revisor') or '?', v.get('modelo') or '?')
        g = grupos.setdefault(k, dict(revisor=k[0], modelo=k[1], pareceres=0, apontamentos=0,
            procedentes=0, rejeitados=0, sem_classificacao=0, casos=0))
        g['pareceres'] += 1; g['apontamentos'] += v.get('itens') or 0
        r = v.get('resposta')
        responde_a = v.get('responde_a')
        if isinstance(r, dict) and isinstance(responde_a, dict):
            alvo = (responde_a.get('revisor') or '?', responde_a.get('modelo') or '?')
            classificado = grupos.setdefault(alvo, dict(revisor=alvo[0], modelo=alvo[1], pareceres=0,
                apontamentos=0, procedentes=0, rejeitados=0, sem_classificacao=0, casos=0))
            classificado['procedentes'] += r.get('corrigidos') or 0
            classificado['rejeitados'] += r.get('rejeitados') or 0
            classificado['sem_classificacao'] += r.get('sem_classificar') or 0
            classificado['casos'] += sum(r.get(x) or 0 for x in ('corrigidos', 'rejeitados', 'sem_classificar'))
    revisores = []
    for g in grupos.values():
        n = g['procedentes'] + g['rejeitados']
        g['taxa_procedencia'] = g['procedentes'] / n if n else None
        g['casos_taxa'] = n
        revisores.append(g)
    destinos = {}
    for d in delegacoes:
        destino = d.get('destino') or '?'; papel = d.get('papel') or '?'
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
        tent = d.get('tentativas') or []
        if any(x.get('destino') == 'local' for x in tent if isinstance(x, dict)) and any(
                x.get('destino') == 'agy' for x in tent if isinstance(x, dict)):
            destinos.setdefault((papel, 'local'), dict(papel=papel, destino='local', chamadas=0,
                sucesso=0, recusas=0, segundos=[], tokens_entrada=None, tokens_saida=None,
                mudancas_local=0))['mudancas_local'] += 1
    for g in destinos.values():
        g['segundos_medianos'] = statistics.median(g.pop('segundos')) if g['segundos'] else None
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
            print(f"  {t['sessao']}: entrada {tokens.get('entrada')}, saída {tokens.get('saida')}, "
                  f"cache lido {tokens.get('cache_lido')}, rodadas {t['rodadas']}, revisão {t['segundos_revisao']} s")
        print(f"Revisores: {len(dados['revisores'])}")
        for r in dados['revisores']:
            taxa = 'sem casos' if r['taxa_procedencia'] is None else f"{r['taxa_procedencia']:.0%} ({r['casos_taxa']} casos)"
            print(f"  {r['revisor']} / {r['modelo']}: {r['procedentes']} procedentes, {r['rejeitados']} rejeitados, taxa {taxa}")
        print('Local e agy:')
        for d in dados['local_vs_agy']:
            print(f"  {d['destino']} / {d['papel']}: {d['chamadas']} chamadas, {d['sucesso']} sucesso(s), "
                  f"{d['recusas']} recusa(s), mediana {d['segundos_medianos']} s, "
                  f"tokens entrada {d['tokens_entrada']}, saída {d['tokens_saida']}, local transferido {d['mudancas_local']}")


if __name__ == '__main__': main()
