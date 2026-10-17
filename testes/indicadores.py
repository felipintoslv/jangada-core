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


def classificar_resposta(texto, caminho='/nao-existe'):
    validar = (RAIZ / 'bin/jangada-validar').read_text(encoding='utf-8')
    bloco = validar.split('resposta_json="$(python3 - "$resposta"', 1)[1].split("<<'PY'\n", 1)[1].split('\nPY', 1)[0]
    saida = subprocess.check_output(['python3', '-', texto, str(caminho), 'sessao', 'execucao', '2'],
                                    input=bloco, text=True)
    return json.loads(saida)


def main():
    classificacao = classificar_resposta('1: corrigido; 2. rejeitado: x; 3 talvez')
    assert (classificacao['corrigidos'], classificacao['rejeitados'],
            classificacao['sem_classificar']) == (1, 1, 1)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        anteriores = [dict(rotulo='sessao', execucao='execucao', rodada=1, etapa='revisor',
                           resultado='revisar', revisor=revisor, modelo=modelo)
                      for revisor, modelo in [('claude', 'opus'), ('codex', 'm'), ('agy', 'a')]]
        gravar(base, 'rodadas.jsonl', anteriores + [
            dict(anteriores[0], rodada=2), dict(anteriores[0], rodada=3),
            dict(anteriores[0], execucao='outra'), dict(anteriores[0], rotulo='outra'),
            dict(anteriores[0], resultado='erro')])
        respondida = classificar_resposta('1 corrigido', base / 'rodadas.jsonl')['responde_a']
        assert respondida == dict(rodada=1, revisor='agy', modelo='a')
        estado = base / 'state' / 'jangada'
        home = base / 'home'
        (estado / 'agentes').mkdir(parents=True)
        sessao = 's1'
        gravar(estado, 'consumo-tarefas.jsonl', [dict(sessao=sessao, projeto='p', execucao='e1', autor='claude',
            modelo='m', tokens=dict(entrada=50, saida=20, cache_lido=5), motivo=None,
            inicio='2026-01-01', fim='2026-01-02'),
            dict(sessao='sem-medicao', projeto='p', execucao='e4', autor='claude', modelo=None,
                 tokens=dict(entrada=None, saida=None, cache_lido=None), motivo='registro ausente',
                 inicio='2026-01-01', fim='2026-01-02')])
        gravar(estado, 'validar.jsonl', [
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='codex', modelo='r', itens=3, segundos=8),
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=2, etapa='revisor', resultado='aprovado',
                 revisor='claude', modelo='opus', itens=1, segundos=4,
                 responde_a=dict(rodada=1, revisor='codex', modelo='r'),
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
        (estado / 'agentes' / 'claude-sem-worktree.json').write_text(json.dumps(dict(
            sessao='claude-sem-worktree', agente='claude', estado='trabalhando', execucao='e5',
            raiz='p', desde='2026-01-01T00:00:00Z')), encoding='utf-8')
        projeto_claude = base / 'claude.projeto'
        import re
        pasta_claude = home / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', str(projeto_claude.resolve()))
        pasta_claude.mkdir(parents=True)
        resposta = {'type': 'assistant', 'requestId': 'q', 'timestamp': '2026-01-01T00:00:00Z',
                    'message': {'id': 'm', 'model': 'claude-test', 'usage': {
                        'input_tokens': 11, 'output_tokens': 3, 'cache_read_input_tokens': 7}}}
        antiga = dict(resposta, requestId='antiga', timestamp='2025-12-31T23:59:59Z',
                      message=dict(resposta['message'], id='antiga', usage=dict(
                          input_tokens=1000, output_tokens=1000, cache_read_input_tokens=1000)))
        (pasta_claude / 'a.jsonl').write_text(json.dumps(antiga) + '\n' + json.dumps(resposta) + '\n', encoding='utf-8')
        (pasta_claude / 'b.jsonl').write_text(json.dumps(resposta) + '\n', encoding='utf-8')
        (base / 'fora.jsonl').write_text(json.dumps(dict(resposta, requestId='link')) + '\n', encoding='utf-8')
        (pasta_claude / 'link.jsonl').symlink_to(base / 'fora.jsonl')
        if hasattr(os, 'mkfifo'):
            os.mkfifo(pasta_claude / 'fifo.jsonl')
        sys.path.insert(0, str(RAIZ / 'orquestracao'))
        from consumo_tarefa import medir
        c = medir(estado, 'aberta', 'codex', 'p')
        assert (c['entrada'], c['saida'], c['cache_lido'], c['modelo']) == (100, 25, 30, 'codex-test')
        cl = medir(estado, 'claude-sessao', 'claude', projeto_claude, home,
                   inicio='2026-01-01T00:00:00Z', worktree=True)
        assert (cl['entrada'], cl['saida'], cl['cache_lido'], cl['modelo']) == (11, 3, 7, 'claude-test')
        sem_worktree = medir(estado, 'claude-sessao', 'claude', projeto_claude, home,
                             inicio='2026-01-01T00:00:00Z', worktree=False)
        assert sem_worktree['entrada'] is None and 'worktree' in sem_worktree['motivo']
        env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(base / 'state'), JANGADA_CORE_PATH=str(RAIZ))
        saida = subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json'], env=env, text=True)
        d = json.loads(saida)
        assert d['versao'] == 1
        t = d['tarefas'][0]
        assert t['tokens'] == dict(entrada=50, saida=20, cache_lido=5, modelo='m', motivo=None)
        assert t['rodadas'] == 2 and t['segundos_revisao'] == 12
        aberta = next(x for x in d['tarefas'] if x['sessao'] == 'aberta')
        assert (aberta['tokens']['entrada'], aberta['tokens']['saida']) == (100, 25)
        vazia = next(x for x in d['tarefas'] if x['sessao'] == 'vazia')
        assert vazia['tokens']['entrada'] is None and vazia['tokens']['motivo']
        claude_sem_worktree = next(x for x in d['tarefas'] if x['sessao'] == 'claude-sem-worktree')
        assert claude_sem_worktree['tokens']['entrada'] is None
        assert 'worktree' in claude_sem_worktree['tokens']['motivo']
        sem_medicao = next(x for x in d['tarefas'] if x['sessao'] == 'sem-medicao')
        assert sem_medicao['tokens']['entrada'] is None and sem_medicao['tokens']['motivo'] == 'registro ausente'
        r = next(x for x in d['revisores'] if x['revisor'] == 'codex')
        assert (r['pareceres'], r['apontamentos'], r['procedentes'], r['rejeitados'], r['sem_classificacao']) == (1, 3, 1, 1, 0)
        assert r['taxa_procedencia'] == 0.5 and r['casos_taxa'] == 2
        atual = next(x for x in d['revisores'] if x['revisor'] == 'claude')
        assert atual['pareceres'] == 1 and atual['apontamentos'] == 1 and atual['casos'] == 0
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
