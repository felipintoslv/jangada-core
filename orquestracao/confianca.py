"""Autoridade do controlador e registros protegidos, sem serviço permanente.

A proteção contra o executor vem das montagens, não de segredo ou de chmod.
Um usuário com controle da conta continua sendo autoridade sobre estes arquivos.
"""

import base64
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

MARCA = '/tmp/.jangada-sem-autoridade'
ENTREGAS = ('fotos', 'integracoes')


def isolado():
    return bool(os.environ.get('JANGADA_ISOLADO')) or any(
        linha.split()[4] == MARCA for linha in Path('/proc/self/mountinfo').read_text().splitlines())


def exigir_controlador():
    if isolado():
        # stderr fica no registro do processo; não se oferece um canal de escrita
        # autoritativo ao executor nem se confia em seu próprio log.
        print('AUTORIZACAO_RECUSADA: executor isolado não possui autoridade', file=sys.stderr)
        raise ValueError('operação exige controlador fora do isolamento')


def codificar(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


# Um registro guardado é relido inteiro para conferência; o limite vale para
# o JSON serializado, com o conteúdo em base64.
LIMITE_REGISTRO = 64 * 1024 * 1024


def ler_regular(caminho):
    caminho = Path(caminho)
    if caminho.parent.resolve() != caminho.parent.absolute():
        raise ValueError('evidência não pode atravessar ligação simbólica')
    fd = os.open(caminho, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as arquivo:
        antes = os.fstat(arquivo.fileno())
        if not stat.S_ISREG(antes.st_mode) or antes.st_nlink != 1:
            raise ValueError('evidência exige arquivo regular sem ligações adicionais')
        if antes.st_size > LIMITE_REGISTRO:
            raise ValueError('evidência excede 64 MiB; preservar originais e arquivar sob supervisão')
        conteudo = arquivo.read(LIMITE_REGISTRO + 1)
        depois = os.fstat(arquivo.fileno())
    if (antes.st_size, antes.st_mtime_ns, antes.st_ctime_ns) != (
            depois.st_size, depois.st_mtime_ns, depois.st_ctime_ns):
        raise ValueError('evidência mudou durante leitura')
    atual = caminho.lstat()
    if (atual.st_ino, atual.st_dev, atual.st_ctime_ns) != (depois.st_ino, depois.st_dev, depois.st_ctime_ns):
        raise ValueError('evidência substituída durante leitura')
    return conteudo


def guardar(pasta, documento):
    exigir_controlador()
    pasta = Path(pasta)
    if pasta.absolute() != pasta.resolve():
        raise ValueError('registro protegido não pode atravessar ligação simbólica')
    pasta.mkdir(mode=0o700, parents=True, exist_ok=True)
    if pasta.resolve() != pasta.absolute():
        raise ValueError('arquivo protegido não pode atravessar ligação simbólica')
    conteudo = codificar(documento)
    if len(conteudo) > LIMITE_REGISTRO:
        raise ValueError('registro excede 64 MiB; preservar originais e arquivar sob supervisão')
    resumo = hashlib.sha256(conteudo).hexdigest()
    destino = pasta / (resumo + '.json')
    if destino.exists() or destino.is_symlink():
        if ler_regular(destino) != conteudo:
            raise ValueError('registro histórico adulterado')
        sincronizar_diretorio(pasta)
        return destino
    fd, temporario = tempfile.mkstemp(prefix='.registro-', dir=pasta)
    try:
        with os.fdopen(fd, 'wb') as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        # link publica sem sobrescrever um registro concorrente.
        try:
            os.link(temporario, destino)
        except FileExistsError:
            pass
        Path(temporario).unlink()
        if ler_regular(destino) != conteudo:
            raise ValueError('registro publicado não confere')
        sincronizar_diretorio(pasta)
    finally:
        Path(temporario).unlink(missing_ok=True)
    return destino


def sincronizar_diretorio(pasta):
    diretorio = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(diretorio)
    finally:
        os.close(diretorio)


def autorizar_conclusao(pasta, linha):
    # O recibo corresponde à linha inteira, incluindo tentativa, política da
    # tarefa, versão do artefato e instante da decisão. SQLite sozinho não basta.
    return guardar(Path(pasta) / 'decisoes', {'versao': 1, 'tarefa': dict(linha)})


def auditar_recusa(funcao):
    @functools.wraps(funcao)
    def executar(self, *args, **kwargs):
        try:
            return funcao(self, *args, **kwargs)
        except ValueError as erro:
            if not isolado():
                guardar(self.pasta / 'recusas', {'evento': 'operacao_recusada', 'operacao': funcao.__name__,
                    'tarefa': args[0] if args else None, 'motivo': str(erro), 'data_ns': time.time_ns()})
            raise
    return executar


def conferir_conclusao(pasta, item):
    if item['status'] != 'COMPLETED':
        return item
    documento = {'versao': 1, 'tarefa': dict(item)}
    resumo = hashlib.sha256(codificar(documento)).hexdigest()
    try:
        if ler_regular(Path(pasta) / 'decisoes' / (resumo + '.json')) != codificar(documento):
            raise ValueError('decisão não confere')
        objeto = ler_regular(Path(pasta) / 'artefatos' / (item['hash_artefato'] + '.txt'))
        if hashlib.sha256(objeto).hexdigest() != item['hash_artefato']:
            raise ValueError('artefato não confere')
    except (OSError, ValueError, TypeError):
        item = dict(item, status='REVIEW_REQUIRED', motivo='AUTORIZACAO_RECUSADA: conclusão sem decisão íntegra ou artefato adulterado; reconferir entrega')
    return item


def pasta_entrega(estado, nome):
    """Pasta privada do estado para árvores entregues pelo agente.

    O conteúdo não é conferido: uma entrega traz links versionados. Por isso
    estas pastas ficam fora de revisoes/ e o isolamento as oculta inteiras.
    Quem chama já decidiu que roda fora do isolamento, como o mktemp que esta
    função substitui; dentro dele, a pasta é a vazia que o isolamento monta.
    """
    if nome not in ENTREGAS:
        raise ValueError('pasta de entregas desconhecida')
    pasta = Path(estado) / nome
    if pasta.absolute() != pasta.resolve():
        raise ValueError('estado protegido não pode atravessar ligação simbólica')
    pasta.mkdir(mode=0o700, parents=True, exist_ok=True)
    if pasta.absolute() != pasta.resolve():
        raise ValueError('estado protegido não pode atravessar ligação simbólica')
    if pasta.lstat().st_uid != os.getuid():
        raise ValueError('pasta de entregas pertence a outro usuário')
    pasta.chmod(0o700)
    return pasta


def preparar_isolamento(estado):
    exigir_controlador()
    estado = Path(estado)
    protegidos = [estado / 'agentes/projetos', estado / 'revisoes', estado / 'painel-chave']
    for pasta in protegidos:
        if pasta.absolute() != pasta.resolve():
            raise ValueError('estado protegido não pode atravessar ligação simbólica')
        pasta.mkdir(mode=0o700, parents=True, exist_ok=True)
        if pasta.absolute() != pasta.resolve():
            raise ValueError('estado protegido não pode atravessar ligação simbólica')
        for caminho in pasta.rglob('*'):
            info = caminho.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError('estado protegido contém ligação ou canal de comunicação')
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError('estado protegido contém arquivo com ligação adicional')
    protegidos += [pasta_entrega(estado, nome) for nome in ENTREGAS]
    # O lançador fecha descritores adicionais. Os três padrões sobrevivem:
    # não podem dar acesso a arquivo protegido nem a socket de um controlador.
    for numero in range(3):
        try:
            info = os.fstat(numero)
            destino = Path(os.readlink(f'/proc/self/fd/{numero}'))
        except OSError:
            continue
        if stat.S_ISSOCK(info.st_mode) or any(destino.is_relative_to(p) for p in protegidos):
            raise ValueError('descritor padrão expõe estado protegido ou socket')


def registrar_inicio(estado, sessao):
    exigir_controlador()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', sessao) or sessao in ('.', '..'):
        raise ValueError('sessão inválida')
    estado = Path(estado)
    documentos = {}
    for pasta, nomes in (('agentes', [f'prompt-{sessao}.md', f'protocolo-{sessao}.md']),
                          ('revisoes', [f'{sessao}.json'])):
        for nome in nomes:
            origem = estado / pasta / nome
            if origem.exists() or origem.is_symlink():
                conteudo = ler_regular(origem)
                documentos[pasta + '/' + nome] = {
                    'sha256': hashlib.sha256(conteudo).hexdigest(),
                    'conteudo_base64': base64.b64encode(conteudo).decode('ascii')}
    return guardar(estado / 'revisoes/inicios' / sessao, {
        'sessao': sessao, 'origem': 'controlador antes de iniciar ou retomar agente',
        'documentos': documentos, 'revisao_executada': False})


def arquivar(estado, sessao):
    exigir_controlador()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', sessao) or sessao in ('.', '..'):
        raise ValueError('sessão inválida')
    estado = Path(estado)
    documentos = {}
    tamanho = 0
    for nome in ('agentes', 'revisoes'):
        pasta = estado / nome
        fixos = [pasta / (sessao + '.json'), pasta / ('validacao-' + sessao + '.aprovado')]
        if nome == 'agentes':
            fixos += [pasta / ('prompt-' + sessao + '.md'), pasta / ('protocolo-' + sessao + '.md')]
        rodadas = [p for p in pasta.glob('validacao-' + sessao + '-r*') if re.fullmatch(
            r'validacao-' + re.escape(sessao) + r'-r[0-9]+\..+', p.name)]
        for caminho in sorted(set(fixos + rodadas)):
            if not caminho.exists() and not caminho.is_symlink():
                continue
            conteudo = ler_regular(caminho)
            tamanho += 4 * ((len(conteudo) + 2) // 3)
            if tamanho > LIMITE_REGISTRO:
                raise ValueError('sessão excede 64 MiB em base64; preservar originais e arquivar sob supervisão')
            documentos[str(caminho.relative_to(estado))] = {
                'sha256': hashlib.sha256(conteudo).hexdigest(),
                'conteudo_base64': base64.b64encode(conteudo).decode('ascii'),
                'confianca': 'controlador' if nome == 'revisoes' else 'declarado_pelo_executor',
            }
    if not documentos:
        raise ValueError('não há documentos para arquivar')
    metadados = {}
    meta = 'revisoes/' + sessao + '.json'
    if meta in documentos:
        metadados = json.loads(base64.b64decode(documentos[meta]['conteudo_base64']))
    historico = {'versao': 1, 'sessao': sessao, 'execucao': metadados.get('execucao'),
                 'atividade': metadados.get('atividade'), 'tarefa': metadados.get('tarefa_id'),
                 'metadados_protegidos': metadados, 'documentos': documentos,
                 'auditabilidade': 'conteudos_preservados; identidades e versões conforme documentos, sem inferir revisão ausente'}
    historico['registros_inicio'] = {}
    for caminho in sorted((estado / 'revisoes/inicios' / sessao).glob('*.json')):
        conteudo = ler_regular(caminho)
        if hashlib.sha256(conteudo).hexdigest() != caminho.stem:
            raise ValueError('registro de início adulterado')
        historico['registros_inicio'][caminho.stem] = json.loads(conteudo)
    marca = 'revisoes/validacao-' + sessao + '.aprovado'
    problemas = []
    if marca in documentos:
        aprovacao = json.loads(base64.b64decode(documentos[marca]['conteudo_base64']))
        rodada = aprovacao.get('num')
        contexto = f'revisoes/validacao-{sessao}-r{rodada}.contexto.json'
        parecer = f'revisoes/validacao-{sessao}-r{rodada}.md'
        if contexto not in documentos or parecer not in documentos or not metadados:
            problemas.append('aprovação sem contexto, parecer integral ou autoria protegida')
        else:
            dados = json.loads(base64.b64decode(documentos[contexto]['conteudo_base64']))
            for chave in ('candidate_sha', 'candidate_tree', 'base_sha'):
                if not aprovacao.get(chave) or aprovacao[chave] != dados.get(chave):
                    problemas.append('aprovação não corresponde à versão registrada na rodada')
    historico['pendencias'] = problemas
    destino = guardar(estado / 'revisoes/arquivo', historico)
    if problemas:
        raise ValueError('arquivo preservado, mas encerramento exige reconferência: ' + '; '.join(problemas))
    return destino


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'preparar-isolamento':
            preparar_isolamento(sys.argv[2])
        elif sys.argv[1] == 'pasta-entrega':
            print(pasta_entrega(sys.argv[2], sys.argv[3]))
        elif sys.argv[1] == 'arquivar':
            print(arquivar(sys.argv[2], sys.argv[3]))
        elif sys.argv[1] == 'registrar-falha':
            guardar(Path(sys.argv[2]) / 'revisoes/falhas-isolamento', {
                'evento': 'execucao_isolada_falhou', 'codigo': int(sys.argv[3]),
                'sessao': os.environ.get('JANGADA_SESSAO'), 'data_ns': time.time_ns()})
        elif sys.argv[1] == 'registrar-inicio':
            registrar_inicio(sys.argv[2], sys.argv[3])
        else:
            raise ValueError('operação desconhecida')
    except (OSError, ValueError, TypeError) as erro:
        print('AUTORIZACAO_RECUSADA ou falha de preservação: ' + str(erro), file=sys.stderr)
        sys.exit(1)
