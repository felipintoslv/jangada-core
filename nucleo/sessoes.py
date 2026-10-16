"""Consulta de apresentação de sessões, sem escrita nem dependência gráfica."""

from datetime import datetime
import html
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

LIMITE = 1024 * 1024
TEXTO_MAX = 16000
NOME = re.compile(r'[A-Za-z0-9_.-]+')
CAMPOS = ('estado', 'dir', 'atualizado', 'ramo', 'tarefa', 'agente',
          'raiz', 'mensagem', 'desde', 'coordenador', 'revisor')


def nome_valido(nome):
    return bool(NOME.fullmatch(nome)) and nome not in ('.', '..') and len(nome) <= 255


def eh_sessao(nome):
    return (nome.endswith('.json') and not nome.startswith(('revisao-', 'delegacao-'))
            and not re.fullmatch(r'validacao-.+-r[0-9]+\.contexto\.json', nome))


def registro(pasta_fd, nome, estrito):
    try:
        try:
            fd = os.open(nome + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=pasta_fd)
        except FileNotFoundError:
            return {}
        with os.fdopen(fd, 'rb') as arquivo:
            info = os.fstat(arquivo.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMITE:
                raise ValueError('Registro deve ser regular e ter no máximo 1 MiB.')
            bruto = arquivo.read(LIMITE + 1)
        if len(bruto) > LIMITE:
            raise ValueError('Registro excedeu 1 MiB.')
        dados = json.loads(bruto)
        if not isinstance(dados, dict):
            raise ValueError('Registro deve ser objeto JSON.')
        if estrito:
            for campo in CAMPOS:
                valor = dados.get(campo)
                if valor is not None and (not isinstance(valor, str) or len(valor) > TEXTO_MAX):
                    raise ValueError('Campo de apresentação inválido: ' + campo)
            pid = dados.get('pid')
            if pid is not None and (type(pid) is not int or pid <= 0 or pid > 2147483647):
                raise ValueError('PID inválido.')
        return dados
    except (OSError, ValueError, RecursionError):
        if estrito:
            raise
        sys.stderr.write('Registro inseguro ou ilegível ignorado na consulta TSV.\n')
        return {}


def texto_legado(valor, padrao=''):
    if valor is None or valor is False:
        valor = padrao
    return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, separators=(',', ':'))


def campos_legados(dados):
    ramo = dados.get('ramo')
    tarefa = dados.get('tarefa')
    ramo = '' if ramo is None or ramo is False else ramo
    tarefa = '' if tarefa is None or tarefa is False else tarefa
    if isinstance(ramo, str) and isinstance(tarefa, str):
        s = {campo: texto_legado(dados.get(campo)) for campo in ('dir', 'atualizado')}
        s.update(estado=texto_legado(dados.get('estado'), 'ativo'), ramo=ramo, tarefa=tarefa)
    else:
        s = dict(estado='ativo', dir='', atualizado='', ramo='', tarefa='')
    s['agente'] = texto_legado(dados.get('agente'))
    return s


def vencido(quando, horas):
    if not quando:
        return True
    comando = shutil.which('gdate') or shutil.which('date')
    marca = None
    if comando:
        try:
            resultado = subprocess.run([comando, '-d', quando, '+%s'], capture_output=True,
                                       timeout=2, check=False)
            marca = int(resultado.stdout) if resultado.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if marca is None:
        try:
            marca = int(datetime.fromisoformat(quando).timestamp())
        except (ValueError, OverflowError, OSError):
            pass
    return marca is None or int(time.time()) - marca > horas * 3600


def pid_vivo(pid):
    if pid is None:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError, OverflowError):
        return False


def selecionar(pasta, vivas, horas, horas_interrompido, estrito):
    if any(not nome_valido(s) for s in vivas):
        sys.stderr.write('Nome tmux alheio ao contrato de sessões ignorado.\n')
    vivas = [s for s in vivas if nome_valido(s)]
    try:
        pasta_fd = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        pasta_fd = None
    except OSError:
        if estrito:
            raise
        sys.stderr.write('Pasta de sessões inacessível ou insegura ignorada na consulta TSV.\n')
        pasta_fd = None
    try:
        nomes = []
        if pasta_fd is not None:
            try:
                with os.scandir(pasta_fd) as entradas:
                    for entrada in entradas:
                        if eh_sessao(entrada.name):
                            nomes.append(entrada.name[:-5])
                            if estrito and len(nomes) > 4096:
                                raise ValueError('Consulta excedeu 4096 registros.')
            except OSError:
                if estrito:
                    raise
                sys.stderr.write('Varredura da pasta de sessões falhou na consulta TSV.\n')
                nomes = []
                os.close(pasta_fd)
                pasta_fd = None
        nomes = list(dict.fromkeys(vivas + sorted(nomes)))
        if estrito and len(nomes) > 4096:
            raise ValueError('Consulta excedeu 4096 sessões.')
        sessoes = []
        tamanho = 0
        for nome in nomes:
            if not nome_valido(nome):
                if estrito:
                    raise ValueError('Nome de sessão inválido.')
                sys.stderr.write('Nome de sessão inválido ignorado na consulta TSV.\n')
                continue
            dados = (registro(pasta_fd, nome, estrito)
                     if pasta_fd is not None and eh_sessao(nome + '.json') else {})
            s = ({campo: dados.get(campo) or '' for campo in CAMPOS}
                 if estrito else campos_legados(dados))
            if not estrito:
                try:
                    for valor in s.values():
                        valor.encode('utf-8')
                except UnicodeError:
                    sys.stderr.write('Texto inválido ignorado na consulta TSV.\n')
                    dados = {}
                    s = campos_legados(dados)
            s['nome'] = nome
            if estrito:
                s['estado'] = s['estado'] or 'ativo'
            estado = s['estado']
            pid = dados.get('pid')
            if pid is False or pid == '':
                pid = None
            if not estrito and pid is not None:
                pid = texto_legado(pid)
            dir_restaurar = s['dir'] if estrito else texto_legado(dados.get('dir'))
            final = estado in ('concluido', 'aguardando')
            if nome not in vivas and not pid_vivo(pid):
                guardado = ((final or estado == 'interrompido') and
                            not vencido(s['atualizado'], horas if final else horas_interrompido))
                if not guardado:
                    restauravel = (pid is None and estado != 'interrompido' and not final
                                   and s['agente'] and s['agente'] != 'par' and dir_restaurar
                                   and Path(dir_restaurar).is_dir())
                    if not restauravel:
                        continue
                    s['estado'] = 'interrompido'
            if estrito:
                s['raiz'] = s['raiz'] or s['dir']
                s['projeto'] = Path(s['raiz']).name or 'Sem projeto'
                s['agente'] = s['agente'] or 'Não informado'
                s['coordenador'] = s['coordenador'] or 'dono'
                s['revisor'] = s['revisor'] or 'Não informado'
                tamanho += len(json.dumps(s, ensure_ascii=False).encode('utf-8'))
                if tamanho > LIMITE:
                    raise ValueError('Resposta excedeu 1 MiB.')
            sessoes.append(s)
        return sessoes
    finally:
        if pasta_fd is not None:
            os.close(pasta_fd)


def emitir(sessoes, formato):
    if formato == 'json':
        saida = json.dumps({'versao': 1, 'sessoes': sessoes}, ensure_ascii=False) + '\n'
    else:
        linhas = []
        for s in sessoes:
            tarefa = html.escape(s['tarefa'].split('\n')[0], quote=False)
            if len(tarefa) > 50:
                tarefa = tarefa[:47] + '...'
            campos = [s['estado'], s['nome'], s['dir'], s['atualizado'],
                      html.escape(s['ramo'], quote=False), tarefa]
            linhas.append('\t'.join(re.sub(r'[\t\n\x1f]', ' ', c) for c in campos))
        saida = ''.join(linha + '\n' for linha in linhas)
    if formato == 'json' and len(saida.encode('utf-8')) > LIMITE:
        raise ValueError('Resposta excedeu 1 MiB.')
    sys.stdout.write(saida)


if __name__ == '__main__':
    try:
        bruto = sys.stdin.buffer.read(LIMITE + 1)
        if len(bruto) > LIMITE:
            raise ValueError('Lista de sessões vivas excedeu 1 MiB.')
        formato = sys.argv[4]
        nomes = bruto.decode('utf-8', 'strict' if formato == 'json' else 'replace')
        vivas = list(dict.fromkeys(s for s in nomes.splitlines() if s))
        horas = int(sys.argv[2])
        horas_interrompido = int(sys.argv[3])
        if horas < 0 or horas_interrompido < 0:
            raise ValueError('Retenção inválida.')
        emitir(selecionar(sys.argv[1], vivas, horas, horas_interrompido, formato == 'json'), formato)
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError) as erro:
        sys.stderr.write('Não foi possível consultar sessões: ' + str(erro) + '\n')
        sys.exit(1)
