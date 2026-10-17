"""Confere o contrato dos indicadores com registros sintéticos."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def gravar(pasta, nome, objetos):
    (pasta / nome).write_text(''.join(json.dumps(x) + '\n' for x in objetos), encoding='utf-8')


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        estado = base / 'state' / 'jangada'
        home = base / 'home'
        (estado / 'agentes').mkdir(parents=True)
        sessao = 's1'
        gravar(estado, 'consumo-tarefas.jsonl', [dict(sessao=sessao, projeto='p', execucao='e1', autor='claude',
            tokens=dict(entrada=50, saida=20, cache_lido=5, modelo='m'), inicio='2026-01-01', fim='2026-01-02')])
        gravar(estado, 'validar.jsonl', [
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='codex', modelo='r', itens=3, segundos=8),
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=2, etapa='revisor', resultado='aprovado',
                 revisor='codex', modelo='r', itens=1, segundos=4,
                 resposta=dict(corrigidos=1, rejeitados=1, sem_classificar=0)),
            dict(rotulo='antiga', execucao='e0', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='legado', modelo='r0', itens=2)])
        gravar(estado, 'delegacoes.jsonl', [dict(sessao=sessao, execucao='e1', projeto='p', papel='leitor',
            destino='agy', modelo='a', segundos=9, codigo_saida=0, recusa=False, tokens_agy=12,
            tokens_retorno=10, tentativas=[dict(destino='local'), dict(destino='agy')]),
            dict(sessao=sessao, execucao='e1', projeto='p', papel='leitor', destino='local', modelo='l',
                 segundos=3, codigo_saida=4, recusa=True, tokens_local_entrada=7,
                 tokens_local_saida=0, tentativas=[dict(destino='local', codigo_saida=4)])])
        codex = estado / 'codex' / 'aberta' / 'sessions' / 'a'
        codex.mkdir(parents=True)
        (codex / 'rollout-1.jsonl').write_text(
            json.dumps({'payload': {'type': 'turn_context', 'model': 'codex-test'}}) + '\n' +
            json.dumps({'payload': {'type': 'token_count', 'info': {
                'total_token_usage': {'input_tokens': 100, 'output_tokens': 25,
                                      'cached_input_tokens': 30}}}}) + '\n', encoding='utf-8')
        (estado / 'agentes' / 'aberta.json').write_text(json.dumps(dict(sessao='aberta', agente='codex',
            estado='trabalhando', execucao='e2', raiz='p')), encoding='utf-8')
        (estado / 'agentes' / 'vazia.json').write_text(json.dumps(dict(sessao='vazia', agente='',
            estado='trabalhando', execucao='e3', raiz='p')), encoding='utf-8')
        projeto_claude = base / 'claude.projeto'
        import re
        pasta_claude = home / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', str(projeto_claude.resolve()))
        pasta_claude.mkdir(parents=True)
        resposta = {'type': 'assistant', 'requestId': 'q', 'timestamp': '2026-01-01T00:00:00Z',
                    'message': {'id': 'm', 'model': 'claude-test', 'usage': {
                        'input_tokens': 11, 'output_tokens': 3, 'cache_read_input_tokens': 7}}}
        (pasta_claude / 'a.jsonl').write_text(json.dumps(resposta) + '\n', encoding='utf-8')
        (pasta_claude / 'b.jsonl').write_text(json.dumps(resposta) + '\n', encoding='utf-8')
        sys.path.insert(0, str(RAIZ / 'orquestracao'))
        from consumo_tarefa import medir
        c = medir(estado, 'aberta', 'codex', 'p')
        assert (c['entrada'], c['saida'], c['cache_lido'], c['modelo']) == (100, 25, 30, 'codex-test')
        cl = medir(estado, 'claude-sessao', 'claude', projeto_claude, home)
        assert (cl['entrada'], cl['saida'], cl['cache_lido'], cl['modelo']) == (11, 3, 7, 'claude-test')
        env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(base / 'state'), JANGADA_CORE_PATH=str(RAIZ))
        saida = subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json'], env=env, text=True)
        d = json.loads(saida)
        assert d['versao'] == 1
        t = d['tarefas'][0]
        assert t['tokens']['entrada'] == 50 and t['rodadas'] == 2 and t['segundos_revisao'] == 12
        aberta = next(x for x in d['tarefas'] if x['sessao'] == 'aberta')
        assert (aberta['tokens']['entrada'], aberta['tokens']['saida']) == (100, 25)
        vazia = next(x for x in d['tarefas'] if x['sessao'] == 'vazia')
        assert vazia['tokens']['entrada'] is None and vazia['tokens']['motivo']
        r = d['revisores'][0]
        assert (r['pareceres'], r['apontamentos'], r['procedentes'], r['rejeitados'], r['sem_classificacao']) == (2, 4, 1, 1, 0)
        assert r['taxa_procedencia'] == 0.5 and r['casos_taxa'] == 2
        legado = next(x for x in d['revisores'] if x['revisor'] == 'legado')
        assert legado['pareceres'] == 1 and legado['casos'] == 0 and legado['taxa_procedencia'] is None
        local = next(x for x in d['local_vs_agy'] if x['destino'] == 'local')
        agy = next(x for x in d['local_vs_agy'] if x['destino'] == 'agy')
        assert (local['chamadas'], local['recusas'], local['mudancas_local']) == (1, 1, 1)
        assert (agy['chamadas'], agy['sucesso'], agy['tokens_entrada'], agy['tokens_saida']) == (1, 1, None, None)
        assert t['delegacoes'][0]['tokens_agy'] == 12
        filtrado = json.loads(subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json',
            '--projeto', 'ausente'], env=env, text=True))
        assert not filtrado['tarefas'] and not filtrado['revisores'] and not filtrado['local_vs_agy']
        recente = json.loads(subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json',
            '--desde', '2027-01-01'], env=env, text=True))
        assert not recente['tarefas'] and not recente['revisores'] and not recente['local_vs_agy']
        texto = subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores')], env=env, text=True)
        assert all(rotulo in texto for rotulo in ('Tarefas:', 'Revisores:', 'Local e agy:', 'taxa'))
        print('indicadores: ok')


if __name__ == '__main__':
    main()
