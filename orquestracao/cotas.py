"""Cota restante por provedor e conta, gravada em $JANGADA_ESTADO/cotas.json.

O arquivo é derivado: nasce dos caches e das observações que já existem e não
é lido por quem decide a delegação. Número só entra com origem e data; sem
medição o percentual é null com o motivo. Nesse caso o grupo pode trazer
`ultimo`, a última medida conhecida, só para exibição. Por grupo vale uma só
medida, a mais recente entre o cache local, o arquivo anterior e a consulta
desta execução; só depois se aplica a validade dela.
"""

import datetime
import json
import math
import os
import pathlib
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

from cota_codex import consultar, janelas as janelas_codex, percentual as percentual_codex
from nucleo.consultas import banco_leitura

VERSAO = 1
MOTIVOS = ('sem_cache', 'cache_vencido', 'consulta_falhou', 'conta_sem_confianca',
           'nao_medido_por_este_provedor')
ORIGEM_AGY = 'agy -p /usage'
ORIGEM_CODEX = 'codex app-server account/rateLimits/read'
ORIGEM_CODEX_ESTADO = 'estado dos provedores'
ORIGENS = (ORIGEM_AGY, ORIGEM_CODEX, ORIGEM_CODEX_ESTADO)
RANK_CACHE, RANK_ANTERIOR, RANK_ATUALIZADO = 0, 1, 2
LIMITE_LEITURA = 1024 * 1024
LIMITE_BANCO = 64 * 1024 * 1024
CACHE_PADRAO = 5
CACHE_TETO = 365 * 24 * 60
GRUPO = re.compile(r'[a-z0-9-]+')
BALDE = re.compile(r'(.+)-(5h|weekly)')
NOME_CONTA = re.compile(r'[A-Za-z0-9_-]+')
DATA = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d')

# Sai uma linha "nome<TAB>argon<TAB>confia" por conta, com as mesmas funções que o
# jangada-delegar usa para listar contas e conferir a confiança da pasta.
LISTAR_CONTAS = r'''
source "$1" || exit 1
contas="$(jangada_contas_agy)" || exit 3
pasta="$(git -c core.fsmonitor=false -c core.hooksPath=/dev/null rev-parse --show-toplevel 2>/dev/null || pwd)"
catalogo=0
[[ ! -f "$JANGADA_ESTADO/contas/agy.json" ]] || catalogo=1
while IFS=$'\t' read -r n p a; do
  [[ -n "$n" ]] || continue
  [[ "${JANGADA_AGY_CONTA_MONTADA:-}" != "$n" ]] || p="$HOME/.gemini/antigravity-cli"
  confia=0
  (
    export JANGADA_AGY_CONTA="$n"
    ((catalogo)) && export JANGADA_AGY_SETTINGS="$p/settings.json"
    jangada_agy_confia "$pasta"
  ) >/dev/null 2>&1 && confia=1
  printf '%s\t%s\t%s\t%s\n' "$n" "$a" "$confia" "$pasta"
done <<<"$contas"
'''


# Todo instante que vem de fora (reset_time, resetsAt, SQLite, mtime) passa só por
# estas três funções: valor fora do alcance de datetime vira None, nunca exceção.
FALHAS_DE_DATA = (ValueError, OverflowError, OSError, TypeError)


def iso(segundos):
    """Segundos desde a época como ISO-8601 em UTC, ou None se não representável.

    Sempre UTC: o fuso local pode ter deslocamento com segundos (antes de 1914), que
    DATA recusa.
    """
    try:
        data = datetime.datetime.fromtimestamp(float(segundos), datetime.timezone.utc)
        return data.isoformat(timespec='seconds')
    except FALHAS_DE_DATA:
        return None


def instante(texto):
    """ISO-8601 com fuso como segundos desde a época, ou None."""
    try:
        data = datetime.datetime.fromisoformat(texto)
        return None if data.tzinfo is None else data.timestamp()
    except FALHAS_DE_DATA:
        return None


def numero(valor, minimo=None, maximo=None):
    """Número vindo de fora: int ou float finito (bool não) dentro de [minimo, maximo], ou None."""
    try:
        if type(valor) not in (int, float) or not math.isfinite(valor):
            return None
        if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
            return None
    except (OverflowError, ValueError, TypeError):
        return None
    return valor


def arredondar(valor):
    """Meio para longe do zero, como o round do jq em cota_do_grupo."""
    inteiro = math.floor(valor)
    return inteiro + 1 if valor - inteiro >= 0.5 else inteiro


def renovacao(texto):
    """ISO-8601 em UTC, ou None se o texto não for uma data com fuso representável."""
    segundos = instante(texto)
    return None if segundos is None else iso(segundos)


def validade_cache():
    try:
        minutos = int(os.environ.get('JANGADA_DELEGAR_CACHE', str(CACHE_PADRAO)))
    except ValueError:
        minutos = CACHE_PADRAO
    # Acima do teto a soma com a data não caberia em datetime: vale o padrão.
    minutos = numero(minutos, None, CACHE_TETO)
    return max(CACHE_PADRAO if minutos is None else minutos, 0) * 60


def grupo_do_modelo(modelo):
    if modelo.startswith('gemini-4-argon-'):
        return 'gemini-argon-wtu'
    if modelo.startswith('gemini-'):
        return 'gemini'
    if modelo.startswith(('claude-', 'gpt-')):
        return '3p'
    return None


def grupos_esperados(argon):
    modelos = os.environ.get('JANGADA_DELEGAR_MODELOS',
                             'gemini-3.8-flash-high claude-sonnet-5-5-high gpt-oss-120b-medium').split()
    resultado = []
    for modelo in modelos:
        grupo = grupo_do_modelo(modelo)
        if grupo and (argon or grupo != 'gemini-argon-wtu') and grupo not in resultado:
            resultado.append(grupo)
    return resultado


def grupo_nulo(grupo, motivo, origem=None, medido_em=None, valido_ate=None):
    return {'grupo': grupo, 'percentual': None, 'janelas': [], 'origem': origem,
            'medido_em': medido_em, 'valido_ate': valido_ate, 'motivo': motivo}


def grupo_medido(grupo, percentual, janelas, origem, medido_em, valido_ate):
    return {'grupo': grupo, 'percentual': percentual, 'janelas': janelas, 'origem': origem,
            'medido_em': medido_em, 'valido_ate': valido_ate, 'motivo': None}


def lembrar(candidatas, chave, percentual, medido, valido, origem, janelas, rank, agora):
    """Guarda, por (provedor, conta, grupo), a medida mais recente entre as candidatas.

    Compara pelo segundo; no mesmo segundo vence o rank maior (cache local, arquivo anterior,
    atualização). Data futura não entra. `valido` None é a medida sem validade, só para `ultimo`.
    Na mesma medição (mesmo segundo) vale a menor validade, de quem quer que vença o desempate.
    """
    percentual, medido = numero(percentual, 0, 100), numero(medido)
    if percentual is None or medido is None or medido > agora:
        return
    ordem = (math.floor(medido), rank, medido)
    atual = candidatas.get(chave)
    if atual is not None and atual['ordem'][0] == ordem[0] and None not in (valido, atual['valido']):
        valido = atual['valido'] = min(valido, atual['valido'])
    if atual is None or ordem > atual['ordem']:
        candidatas[chave] = {'ordem': ordem, 'percentual': percentual, 'medido': medido, 'valido': valido,
                             'origem': origem, 'janelas': janelas}


def lembrar_cache_agy(candidatas, conta, lido, validade, agora):
    """Medidas do cache do agy, vencidas ou não: valem a data de modificação mais a validade de hoje."""
    if lido is None:
        return
    conteudo, mtime = lido
    try:
        dados = json.loads(conteudo)
    except (ValueError, RecursionError):
        return
    for grupo in grupos_agy(dados, [], ORIGEM_AGY, None, None):
        lembrar(candidatas, ('agy', conta, grupo['grupo']), grupo['percentual'], mtime, mtime + validade,
                ORIGEM_AGY, grupo['janelas'], RANK_CACHE, agora)


def janelas_anteriores(lista):
    janelas = []
    for janela in lista if isinstance(lista, list) else []:
        if not isinstance(janela, dict) or not isinstance(janela.get('id'), str) or not GRUPO.fullmatch(janela['id']) \
                or numero(janela.get('percentual'), 0, 100) is None:
            continue
        renova = janela.get('renova_em')
        if renova is not None:
            renova = renovacao(renova) if isinstance(renova, str) and DATA.fullmatch(renova) else False
        if renova is not False:
            janelas.append({'id': janela['id'], 'percentual': janela['percentual'], 'renova_em': renova})
    return janelas


def lembrar_anterior(candidatas, arquivo, validade, agora):
    """Medidas do cotas.json anterior: grupo com percentual numérico ou só com `ultimo`.

    A validade do grupo numérico só encurta: vale o menor entre o valido_ate dele e a data da
    medida mais a validade de hoje.
    """
    try:
        lido = ler_regular(arquivo)
        documento = json.loads(lido[0]) if lido else None
    except (OSError, ValueError, RecursionError):
        return
    provedores = documento.get('provedores') if isinstance(documento, dict) else None
    for provedor in provedores if isinstance(provedores, list) else []:
        if not isinstance(provedor, dict):
            continue
        nome, conta = provedor.get('provedor'), provedor.get('conta')
        if nome not in ('agy', 'codex') or not (conta is None or (isinstance(conta, str) and NOME_CONTA.fullmatch(conta))):
            continue
        lista = provedor.get('grupos')
        for grupo in lista if isinstance(lista, list) else []:
            if not isinstance(grupo, dict) or not isinstance(grupo.get('grupo'), str) or not GRUPO.fullmatch(grupo['grupo']):
                continue
            chave = (nome, conta, grupo['grupo'])
            if grupo.get('percentual') is not None:
                medida, origem, janelas = grupo, grupo.get('origem'), janelas_anteriores(grupo.get('janelas'))
                datas = (grupo.get('medido_em'), grupo.get('valido_ate'))
            else:
                medida, origem, janelas = grupo.get('ultimo'), None, []
                datas = (medida.get('medido_em') if isinstance(medida, dict) else None, None)
            if not isinstance(medida, dict) or not isinstance(datas[0], str) or not DATA.fullmatch(datas[0]):
                continue
            medido, valido = instante(datas[0]), None
            if medido is None:
                continue
            if origem in ORIGENS and isinstance(datas[1], str) and DATA.fullmatch(datas[1]):
                valido = instante(datas[1])
            if valido is None:
                origem, janelas = None, []
            else:
                valido = min(valido, medido + validade)
            lembrar(candidatas, chave, medida.get('percentual'), medido, valido, origem, janelas, RANK_ANTERIOR, agora)


def lembrar_medidos(candidatas, documento, rank_agy, rank_codex, agora):
    """Medidas que o documento já traz (cache lido ou consulta desta execução), antes de vencerem."""
    for provedor in documento['provedores']:
        for grupo in provedor['grupos']:
            if grupo['percentual'] is not None:
                lembrar(candidatas, (provedor['provedor'], provedor['conta'], grupo['grupo']), grupo['percentual'],
                        instante(grupo['medido_em']), instante(grupo['valido_ate']), grupo['origem'], grupo['janelas'],
                        rank_agy if provedor['provedor'] == 'agy' else rank_codex, agora)


def resolver(documento, candidatas, agora):
    """Publica, por grupo, só a medida mais recente: dentro da validade como número, vencida como `ultimo`."""
    for provedor in documento['provedores']:
        for indice, grupo in enumerate(provedor['grupos']):
            escolhida = candidatas.get((provedor['provedor'], provedor['conta'], grupo['grupo']))
            if escolhida is None or grupo['motivo'] == 'conta_sem_confianca':
                continue
            medido_em = iso(escolhida['medido'])
            if medido_em is None:
                continue
            valido = escolhida['valido']
            valido_ate = iso(valido) if valido is not None else None
            # Compara o que é publicado: valido_ate sai truncado ao segundo.
            if valido_ate is not None and instante(valido_ate) > agora:
                provedor['grupos'][indice] = grupo_medido(grupo['grupo'], escolhida['percentual'], escolhida['janelas'],
                                                          escolhida['origem'], medido_em, valido_ate)
                continue
            if grupo['percentual'] is not None or grupo['motivo'] == 'cache_vencido':
                grupo = provedor['grupos'][indice] = grupo_nulo(grupo['grupo'], 'cache_vencido', escolhida['origem'],
                                                                medido_em, valido_ate)
            grupo['ultimo'] = {'percentual': escolhida['percentual'], 'medido_em': medido_em}


def baldes_agy(dados):
    """Grupo -> (janelas ativas, válido). Só números, ids filtrados e datas entram."""
    grupos = {}
    try:
        lista = dados['command']['data']['groups']
    except (KeyError, TypeError):
        return grupos
    if not isinstance(lista, list):
        return grupos
    for item in lista:
        baldes = item.get('buckets') if isinstance(item, dict) else None
        for balde in baldes if isinstance(baldes, list) else []:
            identificador = balde.get('id') if isinstance(balde, dict) else None
            partes = BALDE.fullmatch(identificador) if isinstance(identificador, str) else None
            if not partes or not GRUPO.fullmatch(partes[1]) or balde.get('disabled') is True:
                continue
            fracao = numero(balde.get('remaining_fraction'), 0, 1)
            valido = fracao is not None
            entrada = grupos.setdefault(partes[1], {'janelas': [], 'valido': True})
            reset = balde.get('reset_time')
            fim = renovacao(reset)
            valido = valido and (reset is None or fim is not None)
            entrada['valido'] = entrada['valido'] and valido
            if valido:
                entrada['janelas'].append((identificador, fracao, fim))
    return grupos


def grupos_agy(dados, esperados, origem, medido_em, valido_ate):
    encontrados = baldes_agy(dados)
    resultado = []
    for grupo in esperados + sorted(set(encontrados) - set(esperados)):
        entrada = encontrados.get(grupo)
        if not entrada or not entrada['valido'] or not entrada['janelas']:
            resultado.append(grupo_nulo(grupo, 'consulta_falhou'))
            continue
        minimo = min(fracao for _, fracao, _ in entrada['janelas'])
        janelas = [{'id': identificador, 'percentual': arredondar(fracao * 10000) / 100, 'renova_em': fim}
                   for identificador, fracao, fim in entrada['janelas']]
        resultado.append(grupo_medido(grupo, arredondar(minimo * 10000) / 100, janelas,
                                      origem, medido_em, valido_ate))
    return resultado


def grupos_agy_em(dados, esperados, medido, valido):
    medido_em, valido_ate = iso(medido), iso(valido)
    if medido_em is None or valido_ate is None:
        return [grupo_nulo(g, 'consulta_falhou', ORIGEM_AGY) for g in esperados]
    return grupos_agy(dados, esperados, ORIGEM_AGY, medido_em, valido_ate)


def ler_regular(caminho):
    """(conteúdo, mtime) de um arquivo regular sem seguir link, ou None se ausente."""
    try:
        fd = os.open(caminho, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as arquivo:
        info = os.fstat(arquivo.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('cache não é arquivo regular')
        conteudo = arquivo.read(LIMITE_LEITURA + 1)
    if len(conteudo) > LIMITE_LEITURA:
        raise ValueError('cache excede o limite')
    return conteudo, info.st_mtime


def contas_agy(core):
    resposta = subprocess.run(['bash', '-c', LISTAR_CONTAS, 'jangada-cotas', str(core / 'bin/jangada-config')],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30, check=False)
    if resposta.returncode != 0:
        raise ValueError('catálogo de contas do agy inválido')
    contas = []
    for linha in resposta.stdout.splitlines():
        partes = linha.split('\t')
        if len(partes) != 4 or not NOME_CONTA.fullmatch(partes[0]) or partes[1] not in ('true', 'false'):
            raise ValueError('lista de contas do agy inválida')
        contas.append({'nome': partes[0], 'argon': partes[1] == 'true', 'confia': partes[2] == '1', 'pasta': partes[3]})
    if not contas:
        raise ValueError('lista de contas do agy vazia')
    return contas


def consultar_agy(core, conta, catalogo):
    ambiente = {chave: valor for chave, valor in os.environ.items() if chave != 'JANGADA_SESSAO'}
    ambiente['JANGADA_HOOK_DESLIGADO'] = '1'
    comando = ['agy', '-p', '/usage', '--output-format', 'json', '--print-timeout', '60s']
    if catalogo:
        ambiente['JANGADA_ISOLAR_PERFIL'] = 'agente'
        comando = [str(core / 'bin/jangada-isolar'), '--conta', conta['nome'], '--'] + comando
    resposta = subprocess.run(comando, cwd=conta['pasta'], env=ambiente, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=75, check=False)
    if resposta.returncode != 0 or len(resposta.stdout) > LIMITE_LEITURA:
        raise ValueError('consulta do /usage falhou')
    return json.loads(resposta.stdout)


def medir_agy(core, conta, catalogo, atualizar, cache, agora, candidatas):
    esperados = grupos_esperados(conta['argon'])
    if not conta['confia']:
        return [grupo_nulo(g, 'conta_sem_confianca') for g in esperados]
    validade = validade_cache()
    arquivo = cache / ('agy-usage-%s.json' % conta['nome'] if catalogo else 'agy-usage.json')
    try:
        lido, ilegivel = ler_regular(arquivo), False
    except (OSError, ValueError):
        lido, ilegivel = None, True
    lembrar_cache_agy(candidatas, conta['nome'], lido, validade, agora)
    if atualizar:
        try:
            dados = consultar_agy(core, conta, catalogo)
        except (OSError, ValueError, TypeError, RecursionError, subprocess.SubprocessError):
            return [grupo_nulo(g, 'consulta_falhou', ORIGEM_AGY) for g in esperados]
        medido = time.time()
        return grupos_agy_em(dados, esperados, medido, medido + validade)
    if ilegivel:
        return [grupo_nulo(g, 'consulta_falhou', ORIGEM_AGY) for g in esperados]
    if lido is None or not lido[0].strip():
        return [grupo_nulo(g, 'sem_cache') for g in esperados]
    conteudo, mtime = lido
    if mtime > agora or agora - mtime >= validade:
        passado = mtime <= agora
        return [grupo_nulo(g, 'cache_vencido', ORIGEM_AGY, iso(mtime) if passado else None,
                           iso(mtime + validade) if passado else None) for g in esperados]
    try:
        dados = json.loads(conteudo)
    except (ValueError, RecursionError):
        return [grupo_nulo(g, 'consulta_falhou', ORIGEM_AGY) for g in esperados]
    return grupos_agy_em(dados, esperados, mtime, mtime + validade)


def entradas_agy(core, raiz_estado, atualizar, agora, candidatas):
    catalogo = (raiz_estado / 'contas/agy.json').is_file()
    cache = pathlib.Path(os.environ.get('XDG_CACHE_HOME') or pathlib.Path.home() / '.cache') / 'jangada'
    try:
        contas = contas_agy(core)
    except (OSError, ValueError, subprocess.SubprocessError):
        return [{'provedor': 'agy', 'conta': None, 'grupos': [], 'motivo': 'consulta_falhou'}]
    return [{'provedor': 'agy', 'conta': conta['nome'],
             'grupos': medir_agy(core, conta, catalogo, atualizar, cache, agora, candidatas), 'motivo': None}
            for conta in contas]


def estado_codex(raiz_estado, agora, candidatas):
    banco = raiz_estado / 'agentes/runtime/tarefas.sqlite'
    if not banco.is_file():
        return grupo_nulo('codex', 'sem_cache')
    try:
        with banco_leitura(banco, LIMITE_BANCO) as db:
            linha = db.execute("SELECT cota, atualizado, valido_ate FROM provedores WHERE id='codex'").fetchone()
    except (OSError, ValueError, sqlite3.Error):
        return grupo_nulo('codex', 'consulta_falhou', ORIGEM_CODEX_ESTADO)
    if linha is None or linha['cota'] is None:
        return grupo_nulo('codex', 'sem_cache')
    cota, medido, valido = numero(linha['cota'], 0, 100), numero(linha['atualizado']), numero(linha['valido_ate'])
    if cota is None or medido is None or valido is None:
        return grupo_nulo('codex', 'consulta_falhou', ORIGEM_CODEX_ESTADO)
    lembrar(candidatas, ('codex', None, 'codex'), round(cota, 2), medido, valido, ORIGEM_CODEX_ESTADO, [], RANK_CACHE, agora)
    medido_em, valido_ate = iso(medido), iso(valido)
    if medido_em is None or valido_ate is None:
        return grupo_nulo('codex', 'consulta_falhou', ORIGEM_CODEX_ESTADO)
    if valido <= agora or medido > agora:
        return grupo_nulo('codex', 'cache_vencido', ORIGEM_CODEX_ESTADO, medido_em, valido_ate)
    return grupo_medido('codex', round(cota, 2), [], ORIGEM_CODEX_ESTADO, medido_em, valido_ate)


def consulta_codex(raiz_estado, agora):
    pasta = raiz_estado / 'agentes/runtime'
    try:
        pasta.mkdir(mode=0o700, parents=True, exist_ok=True)
        dados = consultar(pasta)
        medido = time.time()
        cota, validade = percentual_codex(dados, medido)
        confirmadas, _ = janelas_codex(dados, medido)
        janelas = [{'id': 'codex-' + nome, 'percentual': round(restante, 2), 'renova_em': iso(fim)}
                   for nome, restante, fim in confirmadas]
        medido_em, valido_ate = iso(medido), iso(medido + validade)
        if medido_em is None or valido_ate is None or any(j['renova_em'] is None for j in janelas):
            return grupo_nulo('codex', 'consulta_falhou', ORIGEM_CODEX)
        return grupo_medido('codex', round(cota, 2), janelas, ORIGEM_CODEX, medido_em, valido_ate)
    except (OSError, OverflowError, ValueError, TypeError, RecursionError, subprocess.SubprocessError):
        return grupo_nulo('codex', 'consulta_falhou', ORIGEM_CODEX)


def entrada_codex(raiz_estado, atualizar, permitir_remoto, agora, candidatas):
    grupo = estado_codex(raiz_estado, agora, candidatas)
    if atualizar and permitir_remoto:
        grupo = consulta_codex(raiz_estado, agora)
    return {'provedor': 'codex', 'conta': None, 'grupos': [grupo], 'motivo': None}


def vencer(documento, agora):
    """Troca por null o número cuja validade acabou durante as consultas."""
    for provedor in documento['provedores']:
        for indice, grupo in enumerate(provedor['grupos']):
            if grupo['percentual'] is None:
                continue
            limite = instante(grupo['valido_ate'])
            if limite is None:
                provedor['grupos'][indice] = grupo_nulo(grupo['grupo'], 'consulta_falhou', grupo['origem'])
            elif limite <= agora:
                provedor['grupos'][indice] = grupo_nulo(grupo['grupo'], 'cache_vencido', grupo['origem'],
                                                        grupo['medido_em'], grupo['valido_ate'])


def montar(raiz_estado, core, atualizar=False, permitir_remoto=False, agora=None):
    agora = time.time() if agora is None else agora
    # Sem --permitir-remoto nada sai da máquina, nem a consulta ao agy.
    consultar_rede = atualizar and permitir_remoto
    candidatas = {}
    lembrar_anterior(candidatas, raiz_estado / 'cotas.json', validade_cache(), agora)
    documento = {'versao': VERSAO, 'gerado': iso(agora),
                 'provedores': entradas_agy(core, raiz_estado, consultar_rede, agora, candidatas)
                 + [entrada_codex(raiz_estado, atualizar, permitir_remoto, agora, candidatas),
                    {'provedor': 'claude', 'conta': None, 'grupos': [], 'motivo': 'nao_medido_por_este_provedor'}]}
    # A validade é conferida no instante da entrega, não no da partida.
    agora = max(agora, time.time())
    lembrar_medidos(candidatas, documento, RANK_ATUALIZADO if consultar_rede else RANK_CACHE,
                    RANK_ATUALIZADO if consultar_rede else RANK_CACHE, agora)
    vencer(documento, agora)
    resolver(documento, candidatas, agora)
    documento['gerado'] = iso(agora)
    validar(documento, agora)
    return documento


def validar_ultimo(grupo, agora):
    ultimo = grupo['ultimo']
    if grupo.get('percentual') is not None or grupo.get('motivo') == 'conta_sem_confianca':
        raise ValueError('ultimo só cabe em grupo sem número e com conta confiável')
    if not isinstance(ultimo, dict) or set(ultimo) != {'percentual', 'medido_em'}:
        raise ValueError('ultimo inválido')
    if numero(ultimo['percentual'], 0, 100) is None or not DATA.fullmatch(str(ultimo['medido_em'])):
        raise ValueError('ultimo sem número de 0 a 100 ou sem data')
    medido = instante(ultimo['medido_em'])
    if medido is None or medido > agora:
        raise ValueError('ultimo com data impossível ou futura')


def validar(documento, agora):
    """Recusa número sem origem e data, e número com validade vencida."""
    if not isinstance(documento, dict) or documento.get('versao') != VERSAO or not DATA.fullmatch(str(documento.get('gerado'))):
        raise ValueError('cabeçalho de cotas inválido')
    if not isinstance(documento.get('provedores'), list):
        raise ValueError('lista de provedores inválida')
    for provedor in documento['provedores']:
        if provedor.get('motivo') is not None and provedor['motivo'] not in MOTIVOS:
            raise ValueError('motivo inválido')
        for grupo in provedor.get('grupos', []):
            if not GRUPO.fullmatch(str(grupo.get('grupo'))):
                raise ValueError('id de grupo inválido')
            percentual = grupo.get('percentual')
            if 'ultimo' in grupo:
                validar_ultimo(grupo, agora)
            if percentual is None:
                if grupo.get('motivo') not in MOTIVOS:
                    raise ValueError('percentual nulo exige motivo')
                continue
            if numero(percentual, 0, 100) is None:
                raise ValueError('percentual fora de 0 a 100')
            if not isinstance(grupo.get('origem'), str) or not grupo['origem']:
                raise ValueError('percentual sem origem')
            if not DATA.fullmatch(str(grupo.get('medido_em'))) or not DATA.fullmatch(str(grupo.get('valido_ate'))):
                raise ValueError('percentual sem data de medição e validade')
            limite = instante(grupo['valido_ate'])
            if limite is None or limite <= agora:
                raise ValueError('percentual com validade vencida')


def gravar(destino, documento):
    """Troca o arquivo inteiro de uma vez; nunca deixa JSON truncado em destino."""
    destino = pathlib.Path(destino)
    destino.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, prefix='.cotas-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as arquivo:
            os.fchmod(arquivo.fileno(), 0o600)
            arquivo.write(json.dumps(documento, ensure_ascii=False, indent=2) + '\n')
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except BaseException:
        try:
            os.unlink(temporario)
        except FileNotFoundError:
            pass
        raise


def executar(raiz_estado, atualizar=False, permitir_remoto=False, core=None):
    """Imprime o JSON e o grava no estado; devolve 0, ou 1 se a gravação falhou."""
    raiz_estado = pathlib.Path(raiz_estado)
    core = pathlib.Path(core or pathlib.Path(__file__).resolve().parent.parent)
    documento = montar(raiz_estado, core, atualizar, permitir_remoto)
    print(json.dumps(documento, ensure_ascii=False))
    try:
        gravar(raiz_estado / 'cotas.json', documento)
    except OSError as erro:
        print('jangada-router: cotas.json não gravado (%s)' % erro.strerror, file=sys.stderr)
        return 1
    return 0
