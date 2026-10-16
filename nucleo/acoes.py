"""Ações encaminhadas aos comandos que impõem as regras do backend."""

from pathlib import Path
import subprocess


def comando(raiz, acao, argumentos, confirmar=False):
    comandos = {'iniciar': 'jangada-agente', 'importar': 'jangada-fila', 'tarefa': 'jangada-task',
                'executar': 'jangada-executar', 'provedor': 'jangada-provedor',
                'integrar': 'jangada-agente-fim', 'encerrar': 'jangada-agente-fim',
                'projeto': 'jangada-projeto'}
    if acao not in comandos or not isinstance(argumentos, list) or any(not isinstance(a, str) for a in argumentos):
        raise ValueError('ação ou argumentos inválidos')
    if (acao in {'integrar', 'encerrar'} or acao == 'tarefa' and 'cancelar' in argumentos) and not confirmar:
        raise ValueError('ação exige confirmação explícita')
    if acao == 'integrar':
        if '--confirmacao' not in argumentos:
            raise ValueError('integração exige os SHA completos confirmados')
        argumentos = ['--integrar', *argumentos]
    return [str(Path(raiz) / 'bin' / comandos[acao]), *argumentos]


def executar(raiz, acao, argumentos, confirmar=False):
    return subprocess.run(comando(raiz, acao, argumentos, confirmar), check=False)
