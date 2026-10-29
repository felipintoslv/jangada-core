"""Executa análise principal documental, sem ferramentas ou aprovação final."""

import fcntl
import importlib.util
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import sys
import time

from executor import assumir_principal, contexto_principal
from processos import Processo

CAPACIDADES = {'analise_documental', 'sintese', 'revisao_critica'}


def parar_processo(processo):
    try:
        processo.encerrar()
    finally:
        for canal in (processo.stdin, processo.stdout, processo.stderr):
            if canal is not None:
                canal.close()


def executar_principal(estado, identificador, projeto, raiz, saude, permitir_remoto=False, permitir_codex=False):
    raiz_estado = os.environ.get('JANGADA_ESTADO')
    if not raiz_estado:
        raise ValueError('pasta de estado do Jangada não configurada')
    tarefa, dependencias = contexto_principal(estado, identificador, projeto)
    if (not permitir_remoto or not permitir_codex or not tarefa.get('permitir_remoto')
            or not tarefa.get('permitir_codex') or (os.environ.get('JANGADA_DELEGAR') or 'agy') != 'agy'):
        raise ValueError('execução principal exige autorização remota, Codex e perfil agy')
    if tarefa['capacidade'] not in CAPACIDADES:
        raise ValueError('execução principal automática aceita somente análise, síntese e revisão documentais')
    modelo = os.environ.get('JANGADA_CODEX_PRINCIPAL_MODELO', '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', modelo):
        raise ValueError('modelo principal Codex não configurado ou inválido')
    bloqueios = [i for i in saude.impedimentos() if i['destino'] == 'codex-economico']
    if bloqueios:
        raise ValueError('Codex indisponível: ' + bloqueios[0]['motivo'])
    trava = pathlib.Path(raiz_estado) / 'agentes/codex-economico.lock'
    trava.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(trava, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('trava do Codex deve ser arquivo regular')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Codex já possui uma execução documental ativa') from None
        reserva = assumir_principal(estado, identificador, projeto, 'codex', modelo, monitorar=True)
        dono = reserva['dono']
        tempo = max(1, math.floor(reserva['prazo'] - time.time()))
        resultado = {'executor': 'codex-principal', 'modo': 'principal_automatico', 'modelo': modelo,
                     'execucao': reserva['execucao'],
                     'execucao_iniciada': False, 'metricas': {'chamadas': 0, 'segundos': 0}}
        texto = None
        inicio = time.monotonic()

        def encerrar(status, motivo):
            resultado['motivo'] = motivo
            resultado['metricas']['segundos'] = math.ceil(time.monotonic() - inicio)
            estado.finalizar(identificador, dono, status, resultado, texto)
            return {'tarefa': identificador, 'status': status, **resultado}

        try:
            estado.evento(identificador, 'principal_automatico', {'executor': 'codex', 'modelo': modelo,
                          'motivo': 'execução principal solicitada explicitamente; sem escalada de worker'})
            with estado.transacao():
                estado.db.execute('UPDATE tarefas SET prazo=? WHERE id=? AND dono=?',
                                  (time.time() + tempo + 60, identificador, dono))
            fontes = tarefa['fontes'] + [d['arquivo'] for d in dependencias]
            pedido = tarefa['pedido']
            if tarefa.get('requisitos'):
                pedido += '\nUse os títulos Markdown abaixo, com explicação e referência em cada seção:\n'
                pedido += '\n'.join('## ' + r for r in tarefa['requisitos'])
            ambiente = os.environ.copy()
            ambiente.update(JANGADA_CORE_PATH=str(raiz), JANGADA_DELEGAR_DONO_PID=str(os.getpid()),
                            JANGADA_EXECUCAO=reserva['execucao'])
            argumentos = [sys.executable, str(raiz / 'delegacao/codex.py'), '--pasta', str(estado.pasta),
                          '--papel', 'principal', '--tempo', str(tempo), *fontes]
            processo = Processo(argumentos, cwd=projeto, env=ambiente, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding='utf-8', start_new_session=True)
            resultado.update(execucao_iniciada=True, metricas={'chamadas': None, 'segundos': 0})
            try:
                # O filho precisa concluir a limpeza das credenciais antes do prazo do pai.
                bruto, _ = processo.communicate(pedido, timeout=tempo + 5)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as interrupcao:
                parar_processo(processo)
                encerrado = encerrar('REVISION_REQUIRED', 'execução principal interrompida; consumo desconhecido')
                if isinstance(interrupcao, KeyboardInterrupt):
                    raise
                return encerrado
            except (OSError, UnicodeError):
                parar_processo(processo)
                raise
            registro = json.loads(bruto)
            if (processo.returncode != 0 or not isinstance(registro, dict)
                    or type(registro.get('chamadas')) is not int or registro['chamadas'] not in (0, 1)
                    or registro.get('modelo') != modelo or not isinstance(registro.get('motivo_codigo'), str)
                    or not isinstance(registro.get('relatorio'), str)
                    or any(registro.get(c) is not None and (type(registro[c]) is not int or registro[c] < 0)
                           for c in ('tokens_entrada', 'tokens_saida'))):
                raise ValueError('executor principal não devolveu contagem e modelo confiáveis')
            resultado['metricas']['chamadas'] = registro['chamadas']
            resultado['execucao_iniciada'] = registro['chamadas'] != 0
            resultado['delegacao'] = {'destino': 'codex-principal', 'modelo': modelo,
                'tokens_codex_entrada': registro.get('tokens_entrada'), 'tokens_codex_saida': registro.get('tokens_saida'),
                'cota_antes': registro.get('cota_antes'), 'motivo_codigo': registro.get('motivo_codigo'),
                'tentativas': [{'destino': 'codex-principal', 'chamadas': registro['chamadas']}]}
            codigo = registro.get('motivo_codigo')
            saude.registrar_delegacao({**resultado['delegacao'], 'destino': 'codex-economico'}, 4 if codigo else 0)
            if codigo:
                return encerrar('WAITING_QUOTA' if codigo in {'cota_insuficiente', 'cota_desconhecida'}
                                else 'WAITING_PROVIDER' if codigo == 'indisponivel' else 'REVISION_REQUIRED', codigo)
            if registro['chamadas'] != 1 or not isinstance(registro.get('relatorio'), str):
                raise ValueError('relatório principal sem chamada comprovada')
            texto = registro['relatorio']
            if len(texto.encode('utf-8')) > 64000 or not texto.strip():
                raise ValueError('relatório principal vazio ou acima de 64 mil bytes')
            _, atuais = contexto_principal(estado, identificador, projeto)
            if atuais != dependencias:
                raise ValueError('dependências alteradas durante a execução principal')
            spec = importlib.util.spec_from_file_location('validar_principal', raiz / 'delegacao/validar.py')
            gate = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gate)
            gate.verificar(texto, fontes, tarefa.get('requisitos', []))
            resultado['verificacao'] = 'referencias_e_requisitos_validos'
            return encerrar('REVIEW_REQUIRED', 'análise principal produzida; conteúdo aguarda revisão separada')
        except (OSError, ValueError, UnicodeError, KeyError, subprocess.SubprocessError) as erro:
            return encerrar('REVISION_REQUIRED', str(erro))
    finally:
        os.close(fd)
