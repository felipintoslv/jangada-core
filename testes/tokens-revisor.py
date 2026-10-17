"""Confere a leitura dos tokens do revisor e a soma por tarefa, com registros falsos."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / 'orquestracao/consumo_tarefa.py'
sys.dont_write_bytecode = True
NULOS = dict(entrada=None, saida=None, cache_lido=None, total=None)


def ler(revisor, *args, entrada=''):
    r = subprocess.run([sys.executable, str(MODULO), 'revisor', revisor, *args],
                       input=entrada, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        resposta, log = base / 'parecer.md', base / 'parecer.md.log'

        # Codex: o log do codex exec termina com o rodapé e a resposta final.
        resposta.write_text('STATUS: APROVADO\n')
        log.write_text('user\nlinha do pedido\ntokens used\n1\ncodex\nSTATUS: APROVADO\n'
                       'tokens used\n32.353\nSTATUS: APROVADO\n')
        assert ler('codex', '--resposta', str(resposta), '--log', str(log)) == dict(
            tokens_revisor=dict(NULOS, total=32353)), 'Codex com separador de milhar'
        log.write_text('tokens used\n9,488\nSTATUS: APROVADO\n')
        assert ler('codex', '--resposta', str(resposta), '--log', str(log))['tokens_revisor']['total'] == 9488
        # Resposta que cita um rodapé: vale o que vem antes da resposta inteira.
        resposta.write_text('STATUS: REVISAR\n1. x\ntokens used\n7\n')
        log.write_text('tokens used\n500\nSTATUS: REVISAR\n1. x\ntokens used\n7\n')
        assert ler('codex', '--resposta', str(resposta), '--log', str(log))['tokens_revisor']['total'] == 500
        log.write_text('codex\nSTATUS: REVISAR\n')
        sem = ler('codex', '--resposta', str(resposta), '--log', str(log))
        assert sem['tokens_revisor'] == NULOS and 'tokens used' in sem['motivo_tokens_revisor'], sem
        sem = ler('codex', '--resposta', str(resposta), '--log', str(base / 'ausente.log'))
        assert sem['tokens_revisor'] == NULOS and sem['motivo_tokens_revisor'], sem

        # Claude com --output-format json: usage com cache.
        resposta.write_text(json.dumps(dict(type='result', result='STATUS: APROVADO', usage=dict(
            input_tokens=12, cache_creation_input_tokens=300, cache_read_input_tokens=4000, output_tokens=80))))
        assert ler('claude', '--resposta', str(resposta)) == dict(tokens_revisor=dict(
            entrada=12, saida=80, cache_lido=4000, total=4392)), 'Claude com usage'
        # Claude em texto, o formato da chamada atual.
        resposta.write_text('STATUS: APROVADO\n')
        sem = ler('claude', '--resposta', str(resposta))
        assert sem['tokens_revisor'] == NULOS and 'não é JSON' in sem['motivo_tokens_revisor'], sem
        resposta.write_text(json.dumps(dict(usage=dict(input_tokens=-3, output_tokens='5'))))
        sem = ler('claude', '--resposta', str(resposta))
        assert sem['tokens_revisor'] == NULOS and sem['motivo_tokens_revisor'], sem

        # agy: usage.total_tokens na saída JSON, lida pela entrada padrão.
        saida_agy = json.dumps(dict(status='SUCCESS', response='STATUS: APROVADO', usage=dict(total_tokens=61000)))
        assert ler('agy', '--saida-stdin', entrada=saida_agy) == dict(tokens_revisor=dict(NULOS, total=61000))
        sem = ler('agy', '--saida-stdin', entrada=json.dumps(dict(status='SUCCESS', response='x')))
        assert sem['tokens_revisor'] == NULOS and 'usage' in sem['motivo_tokens_revisor'], sem
        sem = ler('agy', '--saida-stdin', entrada='[1, 2')
        assert sem['tokens_revisor'] == NULOS and sem['motivo_tokens_revisor'], sem

        # Provedor sem contagem conhecida.
        sem = ler('novo')
        assert sem['tokens_revisor'] == NULOS and sem['motivo_tokens_revisor'], sem

        # Soma por sessão e execução, só de revisoes/: as linhas do validar.jsonl
        # do estado, graváveis pelo agente, ficam fora mesmo com tokens.
        estado = base / 'estado'
        (estado / 'revisoes').mkdir(parents=True)

        def rodada(data, resultado='revisar', execucao='exe-1', rotulo='s', tokens=None):
            d = dict(data=data, rotulo=rotulo, rodada=1, resultado=resultado, etapa='revisor', execucao=execucao)
            return json.dumps(d if tokens is None else dict(d, tokens_revisor=tokens)) + '\n'

        (estado / 'validar.jsonl').write_text(
            rodada('2026-10-17T10:00:00-03:00', tokens=dict(NULOS, total=1000))
            + rodada('2026-10-17T10:10:00-03:00', tokens=NULOS)
            + rodada('2026-10-17T10:20:00-03:00', execucao='exe-2', tokens=dict(NULOS, total=9))
            + rodada('2026-10-17T10:30:00-03:00', rotulo='outra', tokens=dict(NULOS, total=9))
            + rodada('2026-10-16T10:00:00-03:00', tokens=dict(NULOS, total=9))
            + rodada('2026-10-17T10:40:00-03:00', resultado='erro')
            + '{"quebrada":\n[]\n')
        (estado / 'revisoes/validar.jsonl').write_text(rodada(
            '2026-10-17T11:00:00-03:00', 'aprovado',
            tokens=dict(entrada=300, saida=40, cache_lido=200, total=560)))
        r = subprocess.run([sys.executable, str(MODULO), 'soma-revisor', str(estado), 's', '--execucao', 'exe-1',
                            '--inicio', '2026-10-17T00:00:00-03:00'], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout) == dict(entrada=300, saida=40, cache_lido=200, total=560,
                                            rodadas_medidas=1, rodadas=1), r.stdout
        r = subprocess.run([sys.executable, str(MODULO), 'soma-revisor', str(base / 'vazio'), 's'],
                           capture_output=True, text=True, timeout=30)
        assert json.loads(r.stdout) == dict(NULOS, rodadas_medidas=0, rodadas=0), r.stdout
    print('tokens do revisor: ok')


if __name__ == '__main__':
    main()
