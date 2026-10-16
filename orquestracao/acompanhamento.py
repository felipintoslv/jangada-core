"""Acompanha a fila em primeiro plano, com prazo e consumo limitados."""

import collections
import contextlib
import fcntl
import os
import stat
import time

from executor import executar, PERFIS
from saude import candidatos_elegiveis, orcamento_disponivel, preferencias_delegacao, retomar
from supervisao import pendente as supervisao_pendente, candidatos as supervisores


@contextlib.contextmanager
def exclusividade(estado):
    descritor = os.open(estado.pasta / 'acompanhamento.lock',
                       os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descritor).st_mode):
            raise ValueError('trava de acompanhamento deve ser arquivo regular')
        try:
            fcntl.flock(descritor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('já existe acompanhamento ativo neste projeto') from None
        yield
    finally:
        os.close(descritor)


def acompanhar(estado, projeto, raiz, config, saude, perfil='balanced', limite=100,
               intervalo=60, duracao=28800, permitir_remoto=False, permitir_codex=False,
               emitir=None, supervisao_automatica=False, amostrar=False):
    if (perfil not in PERFIS or type(limite) is not int or not 1 <= limite <= 1000
            or type(intervalo) is not int or not 1 <= intervalo <= 3600
            or type(duracao) is not int or not 1 <= duracao <= 86400):
        raise ValueError('perfil, limite, intervalo ou duração inválidos')
    with exclusividade(estado):
        prazo = time.monotonic() + duracao
        execucoes, ciclos = 0, 0
        proxima_sonda = 0
        motivo = 'prazo_atingido'
        while time.monotonic() < prazo:
            preferencias = preferencias_delegacao(raiz, config)
            candidatos = set()
            for item in estado.listar():
                if item['status'] in {'WAITING_PROVIDER', 'WAITING_QUOTA'} and orcamento_disponivel(estado, item):
                    candidatos.update(candidatos_elegiveis(item['especificacao'], preferencias, perfil,
                                                          permitir_remoto, permitir_codex))
                if supervisao_automatica and supervisao_pendente(item) and orcamento_disponivel(estado, item):
                    candidatos.update(supervisores(item['especificacao'], item['resultado']['delegacao'].get('destino'),
                                                   perfil, permitir_remoto, permitir_codex))
            if candidatos and time.monotonic() >= proxima_sonda:
                proxima_sonda = time.monotonic() + 60
                saude.atualizar('agy' in candidatos)
                if 'codex-economico' in candidatos:
                    saude.atualizar_codex(True)
            retomadas = retomar(estado, saude, raiz, config, perfil, permitir_remoto, permitir_codex)
            if time.monotonic() >= prazo:
                break
            resultados = executar(estado, projeto, raiz, perfil, 1, permitir_remoto, saude, permitir_codex,
                                  supervisao_automatica, amostrar)
            ciclos += 1
            iniciou = any(r.get('execucao_iniciada', r['metricas']['chamadas'] != 0) for r in resultados)
            execucoes += int(iniciou)
            if emitir is not None:
                emitir({'evento': 'ciclo', 'ciclo': ciclos, 'execucoes': execucoes,
                        'retomadas': retomadas, 'resultados': resultados})
            if execucoes >= limite:
                motivo = 'limite_atingido'
                break
            if resultados and iniciou:
                continue
            tarefas = estado.listar()
            if any(t['status'] == 'QUEUED' for t in tarefas) and resultados:
                continue
            esperas = any(t['status'] == 'RUNNING' or (
                t['status'] in {'WAITING_PROVIDER', 'WAITING_QUOTA'}
                and orcamento_disponivel(estado, t)
                and candidatos_elegiveis(t['especificacao'], preferencias, perfil,
                                         permitir_remoto, permitir_codex)) for t in tarefas)
            esperas = esperas or (supervisao_automatica and any(supervisao_pendente(t)
                and orcamento_disponivel(estado, t) and supervisores(t['especificacao'],
                    t['resultado']['delegacao'].get('destino'), perfil, permitir_remoto, permitir_codex) for t in tarefas))
            if not esperas:
                motivo = 'sem_tarefas_executaveis'
                break
            restante = prazo - time.monotonic()
            if restante > 0:
                time.sleep(min(intervalo, restante))
        return {'evento': 'fim', 'motivo': motivo, 'ciclos': ciclos, 'execucoes': execucoes,
                'estados': dict(collections.Counter(t['status'] for t in estado.listar()))}
