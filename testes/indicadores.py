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


def acrescentar_linha_aninhada(caminho):
    with caminho.open('a', encoding='utf-8') as f:
        f.write('[' * 100000 + '\n')


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
        acrescentar_linha_aninhada(base / 'rodadas.jsonl')
        respondida = classificar_resposta('1 corrigido', base / 'rodadas.jsonl')['responde_a']
        assert respondida == dict(rodada=1, revisor='agy', modelo='a')
        estado = base / 'state' / 'jangada'
        home = base / 'home'
        (estado / 'agentes').mkdir(parents=True)
        (estado / 'revisoes').mkdir()
        sessao = 's1'
        gravar(estado, 'consumo-tarefas.jsonl', [dict(sessao=sessao, projeto='p', execucao='e1', autor='claude',
            modelo='m', tokens=dict(entrada=50, saida=20, cache_lido=5), motivo=None,
            inicio='2026-01-01', fim='2026-01-02', contexto_inicial=40, motivo_contexto=None),
            dict(sessao='sem-medicao', projeto='p', execucao='e4', autor='claude', modelo=None,
                 tokens=dict(entrada=None, saida=None, cache_lido=None), motivo='registro ausente',
                 inicio='2026-01-01', fim='2026-01-02')])
        gravar(estado, 'validar.jsonl', [dict(rotulo=sessao, execucao='e1', projeto='p', rodada=99,
            etapa='revisor', resultado='aprovado', revisor='forjado', modelo='hostil', itens=99,
            segundos=999, resposta=dict(corrigidos=99), responde_a=dict(revisor='codex', modelo='r')),
            dict(rotulo='aberta', execucao='e2', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='codex', modelo='sessao', itens=4, segundos=7),
            dict(rotulo='sem-copia', execucao='e9', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='codex', modelo='sessao', itens=2, segundos=5)])
        gravar(estado / 'revisoes', 'validar.jsonl', [
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='codex', modelo='r', itens=3, segundos=8),
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=2, etapa='revisor', resultado='aprovado',
                 revisor='claude', modelo='opus', itens=1, segundos=4,
                 responde_a=dict(rodada=1, revisor='codex', modelo='r'),
                 resposta=dict(corrigidos=1, rejeitados=1, sem_classificar=0)),
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=3, etapa='revisor', resultado='erro',
                 revisor='codex', modelo='r', itens=20, segundos=200),
            dict(rotulo=sessao, execucao='e1', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='codex', modelo='r', itens=2, segundos=6),
            dict(rotulo='parada', execucao='e6', projeto='p', rodada=1, etapa='revisor', resultado='aprovado',
                 revisor='codex', modelo='r', itens=0, segundos=2),
            dict(rotulo='encerrada-sem-copia', execucao='e10', projeto='p', rodada=1, etapa='revisor',
                 resultado='revisar', revisor='extra', modelo='r', itens=0, segundos=1),
            dict(rotulo='controle', execucao='e7', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='rev\x1b[31m', modelo='mod\x7f', itens=1, segundos=1),
            dict(rotulo='antiga', execucao='e0', projeto='p', rodada=1, etapa='revisor', resultado='revisar',
                 revisor='legado', modelo='r0', itens=2)])
        acrescentar_linha_aninhada(estado / 'revisoes' / 'validar.jsonl')
        gravar(estado, 'delegacoes.jsonl', [dict(sessao=sessao, execucao='e1', projeto='p', papel='leitor',
            destino='agy', modelo='a', segundos=9, codigo_saida=0, recusa=False, tokens_agy=12,
            tokens_retorno=10, tentativas=[dict(destino='local'), dict(destino='agy')]),
            dict(sessao=sessao, execucao='e1', projeto='p', papel='leitor', destino='local', modelo='l',
                 segundos=3, codigo_saida=4, recusa=True, tokens_local_entrada=7,
                 tokens_local_saida=0, tentativas=[dict(destino='local', codigo_saida=4)]),
            dict(sessao=sessao, execucao='e1', projeto='p', papel='leitor', destino='codex-economico',
                 tentativas=[dict(destino='local')]),
            dict(sessao='controle', execucao='e7', projeto='p', papel='pap\x1b[31m', destino='agy')])
        acrescentar_linha_aninhada(estado / 'validar.jsonl')
        acrescentar_linha_aninhada(estado / 'delegacoes.jsonl')
        codex = estado / 'codex' / 'aberta' / 'sessions' / 'a'
        codex.mkdir(parents=True)
        (codex / 'rollout-1.jsonl').write_text(
            json.dumps([]) + '\n' +
            json.dumps({'timestamp': '2026-01-01T11:00:00Z', 'payload': {'type': 'token_count', 'info': {
                'total_token_usage': {'input_tokens': 900, 'output_tokens': 900}}}}) + '\n' +
            json.dumps({'timestamp': '2026-01-01T14:00:00Z',
                        'payload': {'type': 'turn_context', 'model': 'codex-test'}}) + '\n' +
            # O primeiro token_count da sessão vem sem info, só com os limites.
            json.dumps({'timestamp': '2026-01-01T14:00:30Z', 'payload': {'type': 'token_count', 'info': None,
                'rate_limits': {}}}) + '\n' +
            json.dumps({'timestamp': '2026-01-01T14:01:00Z', 'payload': {'type': 'token_count', 'info': {
                'total_token_usage': {'input_tokens': 100, 'output_tokens': 25,
                                      'cached_input_tokens': 30}}}}) + '\n', encoding='utf-8')
        sys.path.insert(0, str(RAIZ / 'orquestracao'))
        import consumo_tarefa
        consumo_tarefa.LIMITE_JSONL = 250
        (codex / 'rollout-longo.jsonl').write_text(
            json.dumps({'timestamp': '2026-01-01T14:02:00Z', 'payload': {'type': 'token_count',
                'info': {'total_token_usage': {'input_tokens': 999, 'output_tokens': 999}},
                'nota': 'x' * 500}}) + '\n' +
            json.dumps({'timestamp': '2026-01-01T14:03:00Z', 'payload': {'type': 'token_count', 'info': {
                'total_token_usage': {'input_tokens': 110, 'output_tokens': 26}}}}) + '\n', encoding='utf-8')
        (estado / 'agentes' / 'aberta.json').write_text(json.dumps(dict(sessao='aberta', agente='/usr/bin/codex --flag',
            estado='trabalhando', execucao='e2', raiz='p', desde='2026-01-01T10:00:00-03:00')), encoding='utf-8')
        (estado / 'revisoes' / 'aberta.json').write_text(json.dumps(dict(sessao='aberta', agente='/usr/bin/codex --flag',
            execucao='e2', raiz='p', worktree='p', desde='2026-01-01T10:00:00-03:00')), encoding='utf-8')
        (estado / 'agentes' / 'vazia.json').write_text(json.dumps(dict(sessao='vazia', agente='',
            estado='trabalhando', execucao='e3', raiz='p')), encoding='utf-8')
        (estado / 'agentes' / 'claude-sem-worktree.json').write_text(json.dumps(dict(
            sessao='claude-sem-worktree', agente='/usr/bin/claude --flag', estado='trabalhando', execucao='e5',
            raiz='p', desde='2026-01-01T00:00:00Z')), encoding='utf-8')
        (estado / 'revisoes' / 'claude-sem-worktree.json').write_text(json.dumps(dict(
            sessao='claude-sem-worktree', agente='/usr/bin/claude --flag', execucao='e5', raiz='p',
            desde='2026-01-01T00:00:00Z')), encoding='utf-8')
        (estado / 'agentes' / 'parada.json').write_text(json.dumps(dict(sessao='parada', agente='codex',
            estado='concluido', execucao='e6', raiz='p')), encoding='utf-8')
        (estado / 'revisoes' / 'parada.json').write_text(json.dumps(dict(sessao='parada', agente='codex',
            execucao='e6', raiz='p', worktree='p')), encoding='utf-8')
        (estado / 'agentes' / 'sem-copia.json').write_text(json.dumps(dict(sessao='sem-copia',
            agente='claude', estado='trabalhando', execucao='forjada', raiz='fora')), encoding='utf-8')
        (estado / 'agentes' / 'controle.json').write_text(json.dumps(dict(sessao='../controle', agente='codex',
            estado='trabalhando', execucao='e7', raiz='p')), encoding='utf-8')
        (estado / 'agentes' / '...json').write_text(json.dumps(dict(sessao='..', agente='codex',
            estado='trabalhando', execucao='e8', raiz='p')), encoding='utf-8')
        (estado / 'revisoes' / '..json').write_text(json.dumps(dict(sessao='..', agente='codex',
            execucao='e8', raiz='p')), encoding='utf-8')
        (estado / 'agentes' / 'lista.json').write_text('[]', encoding='utf-8')
        (estado / 'agentes' / 'sessao-invalida.json').write_text(
            json.dumps(dict(sessao=[], agente='codex', estado='trabalhando', raiz='p')), encoding='utf-8')
        projeto_claude = base / 'claude.projeto'
        import re
        pasta_claude = home / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', str(projeto_claude.resolve()))
        pasta_claude.mkdir(parents=True)
        resposta = {'type': 'assistant', 'requestId': 'q', 'timestamp': '2026-01-01T14:00:00Z',
                    'message': {'id': 'm', 'model': 'claude-test', 'usage': {
                        'input_tokens': 11, 'output_tokens': 3, 'cache_read_input_tokens': 7,
                        'cache_creation_input_tokens': 5}}}
        antiga = dict(resposta, requestId='antiga', timestamp='2026-01-01T11:00:00Z',
                      message=dict(resposta['message'], id='antiga', usage=dict(
                          input_tokens=1000, output_tokens=1000, cache_read_input_tokens=1000)))
        (pasta_claude / 'a.jsonl').write_text(json.dumps(antiga) + '\n' + json.dumps(resposta) + '\n' +
            json.dumps(dict(resposta, timestamp='nao-e-data', requestId='data-invalida')) + '\n' +
            json.dumps(dict(resposta, requestId='msg-invalida', message='x')) + '\n' +
            # Contém "usage": passa pelo filtro e chega ao json.loads.
            '{"usage": ' + '[' * 100000 + '\n', encoding='utf-8')
        seguinte = dict(resposta, requestId='q2', timestamp='2026-01-01T15:00:00Z',
                        message=dict(resposta['message'], id='m2', usage=dict(
                            input_tokens=2, output_tokens=1, cache_read_input_tokens=40)))
        (pasta_claude / 'b.jsonl').write_text(json.dumps(seguinte) + '\n' + json.dumps(resposta) + '\n',
                                              encoding='utf-8')
        (base / 'fora.jsonl').write_text(json.dumps(dict(resposta, requestId='link')) + '\n', encoding='utf-8')
        (pasta_claude / 'link.jsonl').symlink_to(base / 'fora.jsonl')
        if hasattr(os, 'mkfifo'):
            os.mkfifo(pasta_claude / 'fifo.jsonl')
        from consumo_tarefa import medir
        parcial = medir(estado, 'aberta', 'codex', 'p')
        assert parcial['entrada'] == 110 and parcial['motivo'] == 'medição parcial'
        assert parcial['contexto_inicial'] == 900 and parcial['motivo_contexto'] is None
        (codex / 'rollout-longo.jsonl').unlink()
        consumo_tarefa.LIMITE_JSONL = 16 * 1024 * 1024
        acrescentar_linha_aninhada(codex / 'rollout-1.jsonl')
        c = medir(estado, 'aberta', 'codex', 'p', inicio='2026-01-01T10:00:00-03:00')
        assert (c['entrada'], c['saida'], c['cache_lido'], c['modelo']) == (100, 25, 30, 'codex-test')
        assert c['contexto_inicial'] == 100 and c['motivo_contexto'] is None
        sessions = codex.parent
        sessions.rename(base / 'sessions-originais')
        (base / 'sessions-externas').mkdir()
        sessions.symlink_to(base / 'sessions-externas', target_is_directory=True)
        sessions_link = medir(estado, 'aberta', 'codex', 'p')
        assert sessions_link['entrada'] is None and 'sessions' in sessions_link['motivo']
        assert sessions_link['contexto_inicial'] is None and 'sessions' in sessions_link['motivo_contexto']
        cl = medir(estado, 'claude-sessao', 'claude', projeto_claude, home,
                   inicio='2026-01-01T10:00:00-03:00', worktree=True)
        assert (cl['entrada'], cl['saida'], cl['cache_lido'], cl['modelo']) == (13, 4, 47, 'claude-test')
        # Primeira resposta: entrada, cache criado e cache lido.
        assert cl['contexto_inicial'] == 11 + 5 + 7 and cl['motivo_contexto'] is None
        projeto_link = base / 'claude-projeto-link'
        chave_link = re.sub(r'[^A-Za-z0-9]', '-', str(projeto_link.resolve()))
        (home / '.claude' / 'projects' / chave_link).symlink_to(pasta_claude, target_is_directory=True)
        claude_link = medir(estado, 'claude-sessao', 'claude', projeto_link, home, worktree=True)
        assert claude_link['entrada'] is None and 'pasta do projeto Claude' in claude_link['motivo']
        sem_worktree = medir(estado, 'claude-sessao', 'claude', projeto_claude, home,
                             inicio='2026-01-01T00:00:00Z', worktree=False)
        assert sem_worktree['entrada'] is None and 'worktree' in sem_worktree['motivo']
        assert sem_worktree['contexto_inicial'] is None and 'worktree' in sem_worktree['motivo_contexto']
        sem_registro = medir(estado, 'claude-sessao', 'claude', projeto_claude, home,
                             inicio='2027-01-01T00:00:00Z', worktree=True)
        assert sem_registro['contexto_inicial'] is None
        assert sem_registro['motivo_contexto'] == 'registro Claude ausente'
        sessao_invalida = medir(estado, '../fora', 'codex', 'p')
        assert sessao_invalida['entrada'] is None and 'nome de sessão' in sessao_invalida['motivo']
        env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(base / 'state'), JANGADA_CORE_PATH=str(RAIZ))
        saida = subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json'], env=env, text=True)
        d = json.loads(saida)
        assert d['versao'] == 1
        t = d['tarefas'][0]
        assert t['tokens'] == dict(entrada=50, saida=20, cache_lido=5, modelo='m', motivo=None)
        assert t['contexto_inicial'] == 40 and t['motivo_contexto'] is None
        assert t['rodadas'] == 3 and t['rodadas_sessao'] == 1 and t['segundos_revisao'] == 18
        assert t['ultimo_resultado'] == 'revisar'
        assert not any(x['sessao'] in {'aberta', 'vazia', 'claude-sem-worktree', 'sem-copia'}
                       for x in d['tarefas'])
        parada = next(x for x in d['tarefas'] if x['sessao'] == 'parada')
        assert parada['rodadas'] == 1 and parada['ultimo_resultado'] == 'aprovado'
        assert parada['tokens']['entrada'] is None
        assert parada['tokens']['motivo'] == 'tarefa aberta; consumo medido no encerramento'
        assert parada['contexto_inicial'] is None
        assert parada['motivo_contexto'] == 'tarefa aberta; consumo medido no encerramento'
        encerrada_sem_copia = next(x for x in d['tarefas'] if x['sessao'] == 'encerrada-sem-copia')
        assert encerrada_sem_copia['tokens']['motivo'] == 'consumo não registrado no encerramento'
        assert not any(x['sessao'] == '../controle' for x in d['tarefas'])
        assert not any(x['sessao'] == '..' for x in d['tarefas'])
        forjado = next(x for x in d['revisores'] if x['revisor'] == 'forjado')
        assert forjado['origem'] == 'sessao' and forjado['pareceres'] == 1
        sem_medicao = next(x for x in d['tarefas'] if x['sessao'] == 'sem-medicao')
        assert sem_medicao['tokens']['entrada'] is None and sem_medicao['tokens']['motivo'] == 'registro ausente'
        assert sem_medicao['rodadas'] == 0 and sem_medicao['rodadas_sessao'] == 0
        assert sem_medicao['ultimo_resultado'] is None and sem_medicao['segundos_revisao'] == 0
        assert sem_medicao['contexto_inicial'] is None
        assert sem_medicao['motivo_contexto'] == 'registro anterior à medição do contexto inicial'
        r = next(x for x in d['revisores'] if x['revisor'] == 'codex' and x['origem'] == 'protegida')
        assert (r['pareceres'], r['apontamentos'], r['procedentes'], r['rejeitados'], r['sem_classificacao']) == (3, 5, 1, 1, 0)
        assert r['taxa_procedencia'] == 0.5 and r['casos_taxa'] == 2
        atual = next(x for x in d['revisores'] if x['revisor'] == 'claude' and x['origem'] == 'protegida')
        assert atual['pareceres'] == 1 and atual['apontamentos'] == 1 and atual['casos'] == 0
        legado = next(x for x in d['revisores'] if x['revisor'] == 'legado' and x['origem'] == 'protegida')
        assert legado['pareceres'] == 1 and legado['casos'] == 0 and legado['taxa_procedencia'] is None
        local = next(x for x in d['local_vs_agy'] if x['destino'] == 'local')
        agy = next(x for x in d['local_vs_agy'] if x['destino'] == 'agy')
        assert (local['chamadas'], local['recusas'], local['mudancas_local']) == (1, 1, 2)
        assert (agy['chamadas'], agy['sucesso'], agy['tokens_entrada'], agy['tokens_saida']) == (1, 1, None, None)
        assert agy['origem'] == 'sessao' and local['origem'] == 'sessao'
        pap = next(x for x in d['local_vs_agy'] if x['papel'] == 'pap\x1b[31m')
        assert pap['segundos_medianos'] is None and 'segundos' not in pap
        assert t['delegacoes'][0]['tokens_agy'] == 12
        assert t['delegacoes'][0]['origem'] == 'sessao'
        filtrado = json.loads(subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json',
            '--projeto', 'ausente'], env=env, text=True))
        assert not filtrado['tarefas'] and not filtrado['revisores'] and not filtrado['local_vs_agy']
        recente = json.loads(subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json',
            '--desde', '2027-01-01'], env=env, text=True))
        assert not recente['tarefas'] and not recente['revisores'] and not recente['local_vs_agy']
        with (estado / 'consumo-tarefas.jsonl').open('a', encoding='utf-8') as f:
            for i in range(12):
                f.write(json.dumps(dict(sessao=f'antiga-{i:02}', projeto='p', execucao=f'x{i}', autor='codex',
                    tokens=dict(entrada=1, saida=None, cache_lido=None), motivo=None,
                    inicio='2025-01-01', fim=f'2025-01-{i + 1:02}')) + '\n')
        total = len(json.loads(subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--json'],
            env=env, text=True))['tarefas'])
        texto = subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores')], env=env, text=True)
        assert 'None' not in texto and 'sem dado' in texto
        tarefas = texto[:texto.index('Revisores:')].splitlines()
        assert tarefas[0] == f'Tarefas: {total} (as 10 mais recentes; --todas lista todas)'
        assert tarefas[1].startswith('  total: entrada 62, saída 20, cache lido 5, sem medição')
        assert len(tarefas) == 12
        assert f'  {sessao}: entrada 50,' in texto and 'contexto inicial 40,' in texto and 'antiga-11:' in texto and 'antiga-04:' in texto
        assert 'antiga-03:' not in texto and 'parada:' not in texto
        todas = subprocess.check_output([str(RAIZ / 'bin/jangada-indicadores'), '--todas'], env=env, text=True)
        assert 'None' not in todas and 'parada:' in todas and 'antiga-00:' in todas
        assert len(todas[:todas.index('Revisores:')].splitlines()) == total + 2
        assert all(rotulo in texto for rotulo in ('Tarefas:', 'Revisores:', 'Local e agy:', 'taxa'))
        assert 'mediana sem dado' in texto
        assert '  total protegida: 7 pareceres, 1 procedentes, 1 rejeitados, taxa 50% (2 casos)' in texto
        assert '  total sessao: 3 pareceres, 99 procedentes, 0 rejeitados' in texto
        assert 'forjado / hostil [sessao]' in texto
        assert 'rodadas sessão 1' in texto
        assert 'agy / leitor [sessao]' in texto
        assert not any((ord(c) < 32 and c != '\n') or ord(c) == 127 for c in texto)
        print('indicadores: ok')


if __name__ == '__main__':
    main()
