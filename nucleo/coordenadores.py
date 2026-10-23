"""Consulta pública e persistência interna das atuações do coordenador."""

from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

sys.dont_write_bytecode = True

from contexto import ler, objeto, pasta_leitura  # noqa: E402
from sessoes import LIMITE, eh_sessao, nome_valido  # noqa: E402

REGISTROS_MAX = 4096
LINHA_MAX = 200
ESTADOS = ('iniciado', 'trabalhando', 'aguardando', 'concluido', 'encerrado')
MODELOS = {'claude': 'opus', 'codex': 'gpt-6-astra', 'agy': 'gemini-4-argon-high'}
PROVEDORES = tuple(MODELOS)
ANSI = re.compile('\x1b\\[[0-?]*[ -/]*[@-~]')
CONTROLE = re.compile('[\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]')
IDENTIDADE = re.compile(r'[A-Za-z0-9_-]{16,128}')


def identidade(dados):
    valor = dados.get('atuacao_id')
    return valor if isinstance(valor, str) and IDENTIDADE.fullmatch(valor) else None


def ciclo(dados):
    # Hooks antigos escreviam estado=encerrado sem encerrar a atuação.
    return 'encerrada' if data(dados, 'encerrado') or dados.get('ciclo') == 'encerrada' else 'aberta'


def texto(dados, nome, limite=4096):
    valor = dados.get(nome)
    if not isinstance(valor, str) or len(valor) > limite or CONTROLE.search(valor):
        return None
    return valor


def data(dados, nome):
    valor = texto(dados, nome, 64)
    try:
        datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    return valor


def ultima_linha(dados):
    valor = dados.get('ultima_linha')
    if not isinstance(valor, str):
        return None
    return CONTROLE.sub(' ', ANSI.sub('', valor)).strip()[:LINHA_MAX]


def arquivos(fd, sufixo='.json', recusar_link=False, estrito=False):
    """Nomes SESSAO.json de arquivos regulares, sem seguir links. Com
    recusar_link, link recusa a consulta; estrito recusa qualquer candidato irregular."""
    nomes = []
    with os.scandir(fd) as entradas:
        for entrada in entradas:
            nome = entrada.name
            if not nome.endswith(sufixo) or not eh_sessao(nome) or not nome_valido(nome[:-5]):
                continue
            try:
                info = os.stat(nome, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                nomes.append(nome)
            elif estrito:
                raise ValueError('registro %s não é arquivo regular' % nome)
            elif recusar_link and stat.S_ISLNK(info.st_mode):
                raise ValueError('registro %s é link simbólico' % nome)
            if len(nomes) > REGISTROS_MAX:
                raise ValueError('Consulta excedeu %d registros.' % REGISTROS_MAX)
    return sorted(nomes)


def tarefas_por_coordenador(estado, vivas, estrito=False):
    """Tarefas lidas das cópias em revisoes/, que o agente isolado não grava.
    Cópia ilegível fica de fora na consulta; encerramento estrito recusa."""
    tarefas = {}
    with pasta_leitura(Path(estado) / 'revisoes') as fd:
        if fd is None:
            return tarefas
        for nome in arquivos(fd, recusar_link=estrito, estrito=estrito):
            try:
                dados = objeto(fd, nome)
            except (OSError, ValueError):
                if estrito:
                    raise ValueError('Cópia protegida ilegível: revisoes/' + nome)
                continue
            coordenador = dados.get('coordenador_sessao')
            if isinstance(coordenador, str) and nome_valido(coordenador):
                sessao = nome[:-5]
                tarefas.setdefault(coordenador, []).append({'sessao': sessao, 'viva': sessao in vivas})
    return tarefas


def coordenadores(estado, vivas):
    tarefas = tarefas_por_coordenador(estado, vivas)
    lista = []
    with pasta_leitura(Path(estado) / 'coordenadores') as fd:
        if fd is not None:
            # A pasta guarda também a aprovação dos hooks do Codex.
            for nome in arquivos(fd, '--coordenador.json', recusar_link=True):
                try:
                    dados = objeto(fd, nome)
                except FileNotFoundError:
                    continue
                sessao = nome[:-5]
                estado_atual = dados.get('estado') if dados.get('estado') in ESTADOS else None
                provedor = dados.get('provedor') if dados.get('provedor') in PROVEDORES else None
                encerrado = ciclo(dados) == 'encerrada'
                projeto = texto(dados, 'projeto')
                lista.append({
                    'sessao': sessao,
                    'projeto': projeto if projeto and projeto.startswith('/') else None,
                    'provedor': provedor,
                    'estado': estado_atual,
                    'ultima_linha': ultima_linha(dados),
                    'atualizado': data(dados, 'atualizado'),
                    'viva': sessao in vivas and not encerrado,
                    'ciclo': ciclo(dados),
                    'atuacao_id': identidade(dados),
                    'retomavel': not encerrado and sessao not in vivas,
                    'tarefas': tarefas.get(sessao, []),
                })
    return {'versao': 1, 'coordenadores': lista}


def pares_unicos(pares):
    dados = {}
    for chave, valor in pares:
        if chave in dados:
            raise ValueError('Chave repetida no registro: ' + chave)
        dados[chave] = valor
    return dados


def ler_registro(fd, sessao):
    dados = json.loads(ler(fd, sessao + '.json'), object_pairs_hook=pares_unicos)
    if (not isinstance(dados, dict) or dados.get('sessao') != sessao
            or not (texto(dados, 'projeto') or '').startswith('/')
            or dados.get('provedor') not in PROVEDORES
            or ('modelo' in dados and dados['modelo'] != MODELOS.get(dados.get('provedor')))
            or (dados.get('provedor') == 'agy' and dados.get('modelo') != MODELOS['agy'])
            or (dados.get('atuacao_id') is not None and not identidade(dados))
            or ('ciclo' in dados and dados['ciclo'] not in ('aberta', 'encerrada'))
            or ('estado' in dados and dados['estado'] not in ESTADOS)
            or ('ultima_linha' in dados and not isinstance(dados['ultima_linha'], str))
            or any(dados.get(chave) not in (None, '') and not data(dados, chave)
                   for chave in ('desde', 'atualizado', 'encerrado'))
            or (dados.get('ciclo') == 'aberta' and data(dados, 'encerrado'))
            or (dados.get('ciclo') == 'encerrada' and not data(dados, 'encerrado'))):
        raise ValueError('Registro inconsistente de ' + sessao)
    # Recusa NaN e Infinity também nos campos que não são modificados.
    json.dumps(dados, allow_nan=False)
    return dados


def gravar(fd, nome, dados, novo=False):
    bruto = (json.dumps(dados, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if len(bruto) > LIMITE:
        raise ValueError('Registro excedeu 1 MiB.')
    temporario = '.reg.' + secrets.token_hex(16)
    arquivo = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
    try:
        with os.fdopen(arquivo, 'wb') as saida:
            saida.write(bruto)
            saida.flush()
            os.fsync(saida.fileno())
        if novo:
            # Publica sem substituir um arquivo ou link já existente.
            os.link(temporario, nome, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        else:
            os.replace(temporario, nome, src_dir_fd=fd, dst_dir_fd=fd)
    finally:
        try:
            os.unlink(temporario, dir_fd=fd)
        except FileNotFoundError:
            pass
        os.fsync(fd)


def arquivar(fd, dados, estado, original=None):
    """Confere histórico e pendências antes de publicar o encerramento."""
    try:
        os.mkdir('historico', 0o700, dir_fd=fd)
        os.fsync(fd)
    except FileExistsError:
        pass
    historico = os.open('historico', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        nome = dados['atuacao_id'] + '.json'
        novo = False
        try:
            salvo = objeto(historico, nome)
        except FileNotFoundError:
            tarefas = tarefas_por_coordenador(estado, set(), estrito=True).get(dados['sessao'], [])
            pendencias = [dict(sessao=t['sessao'], origem='revisoes/' + t['sessao'] + '.json')
                          for t in tarefas]
            salvo = dict(versao=1, registro=dados, pendencias=pendencias)
            novo = True
        referencias = salvo.get('pendencias')
        if (salvo.get('versao') != 1 or salvo.get('registro') != dados
                or not isinstance(referencias, list)
                or any(not isinstance(t, dict) or set(t) != {'sessao', 'origem'}
                       or not isinstance(t['sessao'], str) or not nome_valido(t['sessao'])
                       or t['origem'] != 'revisoes/' + t['sessao'] + '.json'
                       for t in referencias)):
            raise ValueError('Histórico existente não corresponde à atuação.')
        # O registro encerrado permite repetir o arquivo caso sua publicação falhe.
        if original is not None and dados != original:
            gravar(fd, dados['sessao'] + '.json', dados)
        if novo:
            gravar(historico, nome, salvo, novo=True)
        return len(salvo['pendencias'])
    finally:
        os.close(historico)


def persistir(estado, modo, sessao, argumentos):
    """Uso interno, sempre sob a trava do lançador; não executa texto salvo."""
    if (os.environ.get('JANGADA_ISOLADO') or not nome_valido(sessao)
            or not sessao.endswith('--coordenador')):
        raise ValueError('Persistência exige coordenador fora do isolamento e sessão válida.')
    with pasta_leitura(Path(estado) / 'coordenadores') as fd:
        if fd is None:
            raise ValueError('Pasta de coordenadores ausente.')
        try:
            dados = ler_registro(fd, sessao)
        except FileNotFoundError:
            if modo != 'abrir':
                raise
            dados = None
        if modo == 'conferir':
            if ciclo(dados) != 'aberta':
                raise ValueError('Sessão viva com ciclo encerrado; sessão preservada.')
            return dados
        if modo == 'ler':
            return dados
        original = dados.copy() if dados is not None else None
        agora = datetime.now().astimezone().isoformat(timespec='seconds')
        if modo == 'registrar':
            esperado, situacao, linha, *provedor_hook = argumentos
            if (ciclo(dados) == 'encerrada' or (identidade(dados) or '') != esperado
                    or (provedor_hook and provedor_hook[0] and provedor_hook[0] != dados['provedor'])):
                return None
            if situacao not in ESTADOS + ('',):
                raise ValueError('Estado de hook inválido.')
            linha = CONTROLE.sub(' ', ANSI.sub('', linha)).strip()[:LINHA_MAX]
            if situacao:
                dados['estado'] = situacao
            if linha:
                dados['ultima_linha'] = linha
            dados['atualizado'] = agora
        elif modo in ('abrir', 'finalizar'):
            if modo == 'abrir':
                projeto, provedor = argumentos
                if dados and dados['projeto'] != projeto:
                    raise ValueError('Registro pertence ao coordenador de %s, não de %s; preservado'
                                     % (dados['projeto'], projeto))
                if provedor not in PROVEDORES:
                    raise ValueError('Provedor inválido.')
            if dados:
                if not identidade(dados):
                    dados['atuacao_id'] = secrets.token_hex(16)
                dados.setdefault('desde', agora)
            if modo == 'finalizar' or (dados and ciclo(dados) == 'encerrada'):
                if ciclo(dados) == 'aberta':
                    dados.update(ciclo='encerrada', estado='encerrado', encerrado=agora, atualizado=agora)
                else:
                    dados['ciclo'] = 'encerrada'
                restantes = arquivar(fd, dados, estado, original)
                if modo == 'finalizar':
                    return dict(pendencias=restantes, atuacao_id=dados['atuacao_id'])
                dados = None
            if dados is None:
                dados = dict(sessao=sessao, projeto=projeto, desde=agora,
                             atuacao_id=secrets.token_hex(16))
            dados.update(provedor=provedor, modelo=MODELOS[provedor],
                         ciclo='aberta', estado='iniciado', atualizado=agora)
            dados.setdefault('ultima_linha', '')
        else:
            raise ValueError('Operação interna desconhecida.')
        gravar(fd, sessao + '.json', dados)
        return dados


if __name__ == '__main__':
    try:
        if len(sys.argv) >= 5 and sys.argv[1] == '--persistir':
            resultado = persistir(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
            if resultado is not None:
                print(json.dumps(resultado, ensure_ascii=False, allow_nan=False))
            sys.exit(0)
        if len(sys.argv) != 2:
            raise ValueError('Uso: coordenadores.py ESTADO')
        bruto = sys.stdin.buffer.read(LIMITE + 1)
        if len(bruto) > LIMITE:
            raise ValueError('Lista de sessões vivas excedeu 1 MiB.')
        vivas = {s for s in bruto.decode('utf-8').splitlines() if s}
        resposta = json.dumps(coordenadores(sys.argv[1], vivas), ensure_ascii=False, allow_nan=False) + '\n'
        if len(resposta.encode('utf-8')) > LIMITE:
            raise ValueError('Resposta excedeu 1 MiB.')
        sys.stdout.write(resposta)
    except (OSError, ValueError, RecursionError) as erro:
        sys.stderr.write('Não foi possível acessar os coordenadores: ' + str(erro) + '\n')
        sys.exit(1)
