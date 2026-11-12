"""Retenção dos dados de sessões encerradas: lista e, confirmado, apaga.

Entram só os dados que o encerramento deixa para trás e que não têm uso depois
dele ou já estão copiados em revisoes/arquivo. A prova de encerramento vem de
registros que o agente isolado não alcança: o arquivo da sessão em
revisoes/arquivo, a data `fim` da linha dela em consumo-tarefas.jsonl e a
ausência da cópia revisoes/SESSAO.json. Nada é seguido por link, nada fora de
JANGADA_ESTADO é aberto para escrita e nenhuma remoção atravessa montagem.

Uso: retencao.py ESTADO PROVEDORES [--dias N] [--aplicar] -- COMANDO_TMUX...
"""

from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True

from sessoes import nome_valido

MARCA = '/tmp/.jangada-sem-autoridade'
LIMITE = 64 * 1024 * 1024
DIAS = 30
DIAS_MAX = 36500
CONFIRMACAO = 'apagar'
PREFIXO_REVISOR = 'revisao-codex-'
SUFIXOS = ('.md', '.md.log', '.md.tmp', '.md.cobertura', '.md.incompleto',
           '.contexto.json', '.contexto.json.tmp', '.verificacoes.tsv')
SUFIXO = '(?:' + '|'.join(re.escape(s) for s in SUFIXOS) + ')'
RODADA = re.compile(r'validacao-(.+)-r[0-9]{1,9}' + SUFIXO)
FIM_LOG = re.compile(r'fim-(.+)\.log')
ARQUIVO = re.compile(r'[0-9a-f]{64}\.json')
PROVEDOR = re.compile(r'claude|agy-[A-Za-z0-9_-]+')
# O agente parado e o próprio encerramento ainda gravam depois da data `fim`
# do consumo; alteração além desta folga indica uso da pasta depois do fim.
FOLGA = 3600
ESPERA_TRAVA = 5
PROFUNDIDADE = 256
PASTA = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

MOTIVOS = (('sem_prova', 'sem prova de encerramento'),
           ('aberta', 'sessão viva ou aberta'),
           ('recente', 'encerrada há menos de {dias} dias'),
           ('alterada', 'alterada depois do encerramento'))


class Recusa(Exception):
    """Entrada que não pode ser medida nem apagada com segurança."""


def isolado(mountinfo='/proc/self/mountinfo'):
    if os.environ.get('JANGADA_ISOLADO'):
        return True
    try:
        with open(mountinfo, encoding='utf-8', errors='surrogateescape') as arquivo:
            return any(linha.split()[4] == MARCA for linha in arquivo)
    except (OSError, IndexError):
        return True


def montagens():
    """Pontos de montagem do processo, decodificados do mountinfo."""
    pontos = []
    with open('/proc/self/mountinfo', encoding='utf-8', errors='surrogateescape') as arquivo:
        for linha in arquivo:
            ponto = linha.split(' ')[4]
            pontos.append(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), ponto))
    return pontos


def cruza_montagem(caminho, pontos):
    return any(p == caminho or p.startswith(caminho + '/') for p in pontos)


def real(fd):
    return os.readlink(f'/proc/self/fd/{fd}')


def abrir_pasta(base, partes):
    """Abre cada componente sem seguir link. None quando a pasta não existe."""
    atual = os.dup(base)
    try:
        for parte in partes:
            try:
                proximo = os.open(parte, PASTA, dir_fd=atual)
            except FileNotFoundError:
                return None
            os.close(atual)
            atual = proximo
        resultado, atual = atual, None
        return resultado
    finally:
        if atual is not None:
            os.close(atual)


def ler(fd, nome):
    arquivo_fd = os.open(nome, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(arquivo_fd, 'rb') as arquivo:
        info = os.fstat(arquivo.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMITE:
            raise ValueError(f'{nome} deve ser arquivo regular, sem ligações, de até 64 MiB')
        bruto = arquivo.read(LIMITE + 1)
    if len(bruto) > LIMITE:
        raise ValueError(f'{nome} excedeu 64 MiB')
    return bruto


def data(texto):
    if not isinstance(texto, str) or len(texto) > 64:
        return None
    try:
        valor = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return valor if valor.tzinfo is not None else None


def tamanho(n):
    for unidade, fator in (('GB', 1024 ** 3), ('MB', 1024 ** 2), ('KB', 1024)):
        if n >= fator:
            return f'{n / fator:.1f} {unidade}'.replace('.', ',')
    return f'{n} B'


def plural(n, um, varios):
    return f'{n} {um if n == 1 else varios}'


class Estado:
    """Provas e áreas de dados de uma pasta de estado do jangada."""

    def __init__(self, raiz, provedores, dias, tmux):
        self.raiz = os.path.realpath(raiz)
        self.fd = os.open(self.raiz, os.O_RDONLY | os.O_DIRECTORY)
        self.provedores = provedores
        self.dias = dias
        self.tmux = tmux
        self.agora = datetime.now().astimezone()
        self.limite = self.agora - timedelta(days=dias)
        self.avisos = []
        self.atualizar()

    def fechar(self):
        os.close(self.fd)

    def atualizar(self):
        self.vivas = self.sessoes_vivas()
        self.arquivados = self.ler_arquivos()
        self.fins = self.ler_consumo()

    def avisar(self, texto):
        if texto not in self.avisos:
            self.avisos.append(texto)

    def sessoes_vivas(self):
        if not self.tmux:
            return set()
        try:
            feito = subprocess.run([*self.tmux, 'list-sessions', '-F', '#S'], capture_output=True,
                                   stdin=subprocess.DEVNULL, timeout=10, check=False)
        except FileNotFoundError:
            return set()
        except (OSError, subprocess.SubprocessError) as erro:
            raise Recusa(f'não foi possível listar as sessões do tmux: {erro}') from erro
        return set(feito.stdout.decode('utf-8', 'replace').splitlines()) if feito.returncode == 0 else set()

    def ler_arquivos(self):
        """Sessão -> nomes dos arquivos íntegros e sem pendência em revisoes/arquivo."""
        arquivados = {}
        fd = abrir_pasta(self.fd, ('revisoes', 'arquivo'))
        if fd is None:
            return arquivados
        try:
            with os.scandir(fd) as entradas:
                nomes = [e.name for e in entradas if ARQUIVO.fullmatch(e.name)]
            for nome in nomes:
                sessao = self.conferir_arquivo(fd, nome)
                if sessao:
                    arquivados.setdefault(sessao, []).append(nome)
        finally:
            os.close(fd)
        return arquivados

    def conferir_arquivo(self, fd, nome):
        try:
            conteudo = ler(fd, nome)
            if hashlib.sha256(conteudo).hexdigest() != nome[:-5]:
                raise ValueError('conteúdo não confere com o nome')
            documento = json.loads(conteudo)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RecursionError):
            self.avisar('arquivo de revisoes/arquivo ilegível ou adulterado não conta como prova')
            return None
        if not isinstance(documento, dict) or documento.get('versao') != 1:
            return None
        sessao = documento.get('sessao')
        if not isinstance(sessao, str) or not nome_valido(sessao) or documento.get('pendencias', []) != []:
            return None
        return sessao

    def ler_consumo(self):
        """Sessão -> data `fim` mais recente do consumo-tarefas.jsonl."""
        fins = {}
        try:
            bruto = ler(self.fd, 'consumo-tarefas.jsonl')
        except FileNotFoundError:
            return fins
        except (OSError, ValueError):
            self.avisar('consumo-tarefas.jsonl ilegível; nenhuma sessão tem prova de encerramento')
            return fins
        for linha in bruto.decode('utf-8', 'replace').splitlines():
            try:
                registro = json.loads(linha)
            except (ValueError, RecursionError):
                continue
            if not isinstance(registro, dict):
                continue
            sessao, fim = registro.get('sessao'), data(registro.get('fim'))
            if isinstance(sessao, str) and nome_valido(sessao) and fim is not None:
                if sessao not in fins or fim > fins[sessao]:
                    fins[sessao] = fim
        return fins

    def existe(self, partes, nome):
        """Presença sem seguir link. Na dúvida, diz que existe."""
        try:
            fd = abrir_pasta(self.fd, partes)
        except OSError:
            return True
        if fd is None:
            return False
        try:
            os.stat(nome, dir_fd=fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return True
        finally:
            os.close(fd)

    def situacao(self, sessao):
        """(motivo, fim): motivo 'elegivel', 'aberta', 'sem_prova' ou 'recente'."""
        if sessao in self.vivas:
            return 'aberta', None
        if self.existe(('agentes',), sessao + '.json') or self.existe(('revisoes',), sessao + '.json'):
            return 'aberta', None
        fim = self.fins.get(sessao)
        if sessao not in self.arquivados or fim is None:
            return 'sem_prova', None
        if fim > self.limite:
            return 'recente', fim
        return 'elegivel', fim

    def conhecida(self, sessao):
        return sessao in self.arquivados or sessao in self.fins or self.situacao(sessao)[0] == 'aberta'

    def decidir(self, donos):
        """Todos os donos elegíveis, salvo nome sem rastro de sessão.

        Devolve (motivo, sessão, tipo, fim, nomes das sessões elegíveis)."""
        elegiveis, motivos = [], []
        for sessao, tipo in donos:
            motivo, fim = self.situacao(sessao)
            if motivo == 'elegivel':
                elegiveis.append((sessao, tipo, fim))
            elif motivo != 'sem_prova' or self.conhecida(sessao):
                motivos.append(motivo)
        for motivo in ('aberta', 'recente', 'sem_prova'):
            if motivo in motivos:
                return motivo, donos[0][0], donos[0][1], None, ()
        if not elegiveis:
            return 'sem_prova', donos[0][0], donos[0][1], None, ()
        sessao, tipo, _ = elegiveis[0]
        return 'elegivel', sessao, tipo, max(f for _, _, f in elegiveis), tuple(s for s, _, _ in elegiveis)

    def areas(self):
        """(partes da pasta, tipo, espera pasta, dono do nome) de cada área com dados."""
        proprio = lambda nome: [(nome, None)]
        return ([(('codex',), None, True, self.donos_codex)]
                + [(('provedores', p), 'provedor ' + p, True, proprio) for p in self.provedores]
                + [(('revisoes', 'inicios'), 'inicios', True, proprio),
                   (('agentes',), 'rodadas em agentes', False, self.dono_rodada),
                   (('revisoes',), 'rodadas em revisoes', False, self.dono_rodada),
                   (('agentes',), 'registro do fim', False, self.dono_fim)])

    @staticmethod
    def donos_codex(nome):
        donos = [(nome, 'codex')]
        revisada = nome[len(PREFIXO_REVISOR):]
        if nome.startswith(PREFIXO_REVISOR) and nome_valido(revisada):
            donos.append((revisada, 'codex do revisor'))
        return donos

    @staticmethod
    def dono_rodada(nome):
        achado = RODADA.fullmatch(nome)
        if not achado:
            return []
        sessao = achado[1]
        # O nome exato da sessão, nunca prefixo: tarefa não leva os de tarefa-2.
        if not nome_valido(sessao) or not re.fullmatch(
                'validacao-' + re.escape(sessao) + r'-r[0-9]{1,9}' + SUFIXO, nome):
            return []
        return [(sessao, None)]

    @staticmethod
    def dono_fim(nome):
        achado = FIM_LOG.fullmatch(nome)
        return [(achado[1], None)] if achado and nome_valido(achado[1]) else []

    def unidades(self):
        """Cada entrada das áreas, medida e decidida."""
        pontos = montagens()
        for area, (partes, tipo, espera_pasta, dono) in enumerate(self.areas()):
            try:
                fd, base = self.abrir_area(partes)
            except (Recusa, OSError):
                self.avisar('/'.join(partes) + '/ é link, não abre ou está fora do caminho esperado; '
                            'fica fora da limpeza')
                continue
            if fd is None:
                continue
            try:
                with os.scandir(fd) as entradas:
                    nomes = sorted(e.name for e in entradas)
                for nome in nomes:
                    if not nome_valido(nome):
                        if espera_pasta:
                            yield dict(motivo='recusada', partes=partes, nome=nome)
                        continue
                    donos = dono(nome)
                    if not donos:
                        continue
                    yield dict(self.unidade(fd, base, partes, nome, tipo, espera_pasta, donos, pontos), area=area)
            finally:
                os.close(fd)

    def abrir_area(self, partes):
        """(fd, caminho real) da área, ou (None, None) quando ela não existe."""
        fd = abrir_pasta(self.fd, partes)
        if fd is None:
            return None, None
        base = real(fd)
        if base != os.path.join(self.raiz, *partes):
            os.close(fd)
            raise Recusa('área fora do caminho esperado')
        return fd, base

    def remedir(self, unidade):
        """A mesma unidade medida e decidida com o estado lido agora."""
        partes, tipo, espera_pasta, dono = self.areas()[unidade['area']]
        fd, base = self.abrir_area(partes)
        if fd is None:
            return dict(motivo='sumiu')
        try:
            return self.unidade(fd, base, partes, unidade['nome'], tipo, espera_pasta, dono(unidade['nome']),
                                montagens())
        finally:
            os.close(fd)

    def reler_provas(self, sessoes):
        """Lê de novo o tmux, o consumo e os arquivos que provam o encerramento destas sessões."""
        self.vivas = self.sessoes_vivas()
        self.fins = self.ler_consumo()
        fd = abrir_pasta(self.fd, ('revisoes', 'arquivo'))
        try:
            for sessao in sessoes:
                nomes = [n for n in self.arquivados.pop(sessao, ())
                         if fd is not None and self.conferir_arquivo(fd, n) == sessao]
                if nomes:
                    self.arquivados[sessao] = nomes
        finally:
            if fd is not None:
                os.close(fd)

    def unidade(self, fd, base, partes, nome, tipo, espera_pasta, donos, pontos):
        unidade = dict(partes=partes, nome=nome)
        try:
            unidade['bytes'], maior = medir(fd, base, nome, espera_pasta, pontos)
        except FileNotFoundError:
            unidade['motivo'] = 'sumiu'
            return unidade
        except (Recusa, OSError):
            unidade['motivo'] = 'recusada'
            return unidade
        motivo, sessao, tipo_dono, fim, travas = self.decidir(donos)
        unidade.update(motivo=motivo, sessao=sessao, tipo=tipo or tipo_dono, fim=fim, travas=travas,
                       provedor=partes[1] if partes[0] == 'provedores' else None)
        if motivo == 'elegivel' and maior / 1e9 > fim.timestamp() + FOLGA:
            unidade['motivo'] = 'alterada'
        return unidade


def medir(fd, base, nome, espera_pasta, pontos):
    """(bytes ocupados, maior mtime em ns) sem seguir link nem atravessar montagem."""
    caminho = os.path.join(base, nome)
    info = os.stat(nome, dir_fd=fd, follow_symlinks=False)
    if os.path.realpath(caminho) != caminho or os.path.dirname(caminho) != base:
        raise Recusa('fora da pasta esperada')
    if espera_pasta:
        if not stat.S_ISDIR(info.st_mode):
            raise Recusa('esperada pasta')
        if cruza_montagem(caminho, pontos):
            raise Recusa('ponto de montagem')
        filho = os.open(nome, PASTA, dir_fd=fd)
        try:
            conferir_mesma(filho, info)
            total, maior = percorrer(filho, info.st_dev, 0)
        finally:
            os.close(filho)
        return total + info.st_blocks * 512, max(maior, info.st_mtime_ns)
    if not stat.S_ISREG(info.st_mode):
        raise Recusa('esperado arquivo regular')
    return info.st_blocks * 512, info.st_mtime_ns


def conferir_mesma(fd, info):
    aberto = os.fstat(fd)
    if (aberto.st_dev, aberto.st_ino) != (info.st_dev, info.st_ino):
        raise Recusa('entrada trocada durante a leitura')


def percorrer(fd, dispositivo, profundidade):
    if profundidade > PROFUNDIDADE:
        raise Recusa('profundidade excedida')
    total = maior = 0
    with os.scandir(fd) as entradas:
        for entrada in entradas:
            info = entrada.stat(follow_symlinks=False)
            total += info.st_blocks * 512
            maior = max(maior, info.st_mtime_ns)
            if stat.S_ISDIR(info.st_mode):
                if info.st_dev != dispositivo:
                    raise Recusa('ponto de montagem')
                filho = os.open(entrada.name, PASTA, dir_fd=fd)
                try:
                    conferir_mesma(filho, info)
                    parcial, mtime = percorrer(filho, dispositivo, profundidade + 1)
                finally:
                    os.close(filho)
                total += parcial
                maior = max(maior, mtime)
    return total, maior


def apagar_arvore(fd, dispositivo, profundidade):
    if profundidade > PROFUNDIDADE:
        raise Recusa('profundidade excedida')
    with os.scandir(fd) as entradas:
        filhos = [(e.name, e.stat(follow_symlinks=False)) for e in entradas]
    for nome, info in filhos:
        if stat.S_ISDIR(info.st_mode):
            if info.st_dev != dispositivo:
                raise Recusa('ponto de montagem')
            filho = os.open(nome, PASTA, dir_fd=fd)
            try:
                conferir_mesma(filho, info)
                apagar_arvore(filho, dispositivo, profundidade + 1)
            finally:
                os.close(filho)
            os.rmdir(nome, dir_fd=fd)
        else:
            # Link é apagado como entrada; o destino não é aberto.
            os.unlink(nome, dir_fd=fd)


def apagar(estado, partes, nome):
    """Apaga uma entrada direta da área, conferida de novo pelo caminho real."""
    fd = abrir_pasta(estado.fd, partes)
    if fd is None:
        raise FileNotFoundError(nome)
    try:
        base = real(fd)
        if base != os.path.join(estado.raiz, *partes):
            raise Recusa('área fora do caminho esperado')
        caminho = os.path.join(base, nome)
        if os.path.realpath(caminho) != caminho:
            raise Recusa('fora da pasta esperada')
        info = os.stat(nome, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            if not stat.S_ISREG(info.st_mode):
                raise Recusa('esperado arquivo regular')
            os.unlink(nome, dir_fd=fd)
            return
        if cruza_montagem(caminho, montagens()):
            raise Recusa('ponto de montagem')
        filho = os.open(nome, PASTA, dir_fd=fd)
        try:
            conferir_mesma(filho, info)
            apagar_arvore(filho, info.st_dev, 0)
        finally:
            os.close(filho)
        os.rmdir(nome, dir_fd=fd)
    finally:
        os.close(fd)


def pasta_filha(fd, nome):
    try:
        os.mkdir(nome, 0o700, dir_fd=fd)
    except FileExistsError:
        pass
    return os.open(nome, PASTA, dir_fd=fd)


def esperar_trava(fd, descricao):
    prazo = time.monotonic() + ESPERA_TRAVA
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= prazo:
                raise Recusa(descricao + ' em uso')
            time.sleep(0.1)


def travar_revisao(estado, sessao):
    """revisoes/travas/SESSAO, a mesma do jangada-agente-fim e do jangada-validar."""
    revisoes = abrir_pasta(estado.fd, ('revisoes',))
    if revisoes is None:
        revisoes = pasta_filha(estado.fd, 'revisoes')
    try:
        travas = pasta_filha(revisoes, 'travas')
    finally:
        os.close(revisoes)
    try:
        fd = pasta_filha(travas, sessao)
    finally:
        os.close(travas)
    try:
        esperar_trava(fd, 'revisão da sessão')
    except BaseException:
        os.close(fd)
        raise
    return fd


def travar_provedor(estado, provedor, sessao):
    """provedores/.travas/PROVEDOR/SESSAO, a mesma do jangada-isolar."""
    raiz = abrir_pasta(estado.fd, ('provedores',))
    if raiz is None:
        raise FileNotFoundError('provedores')
    try:
        travas = pasta_filha(raiz, '.travas')
    finally:
        os.close(raiz)
    try:
        pasta = pasta_filha(travas, provedor)
    finally:
        os.close(travas)
    try:
        fd = os.open(sessao, os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=pasta)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Recusa('trava do provedor não é arquivo regular')
            esperar_trava(fd, 'dados do provedor')
            # Uma limpeza do isolar pode ter trocado o arquivo durante a espera.
            conferir_mesma(fd, os.stat(sessao, dir_fd=pasta, follow_symlinks=False))
        except BaseException:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(pasta)


def medir_todas(estado):
    """As unidades das áreas. Dado alterado depois do fim mantém a sessão inteira."""
    unidades = list(estado.unidades())
    alteradas = {s for u in unidades if u.get('motivo') == 'alterada' for s in u['travas']}
    for unidade in unidades:
        if unidade.get('motivo') == 'elegivel' and set(unidade['travas']) & alteradas:
            unidade['motivo'] = 'alterada'
    return unidades


def agrupar(unidades):
    grupos = {}
    for unidade in unidades:
        if unidade.get('motivo') != 'elegivel':
            continue
        chave = (unidade['sessao'], unidade['tipo'], unidade['partes'])
        grupo = grupos.setdefault(chave, dict(sessao=unidade['sessao'], tipo=unidade['tipo'],
                                              partes=unidade['partes'], fim=unidade['fim'],
                                              unidades=[], bytes=0))
        grupo['unidades'].append(unidade)
        grupo['bytes'] += unidade['bytes']
        grupo['fim'] = max(grupo['fim'], unidade['fim'])
    return sorted(grupos.values(), key=lambda g: (g['sessao'], g['tipo'], g['partes']))


def listar(estado, unidades, saida):
    grupos = agrupar(unidades)
    escrever = saida.write
    if grupos:
        escrever(f'Dados de sessões encerradas há mais de {estado.dias} dias, com prova de encerramento:\n')
        largura = max(len(g['sessao']) for g in grupos)
        largura_tipo = max(len(g['tipo']) for g in grupos)
        escrever(f'  {"SESSÃO":<{largura}}  {"TIPO":<{largura_tipo}}  {"TAMANHO":>9}  ENCERRADA EM\n')
        for g in grupos:
            escrever(f'  {g["sessao"]:<{largura}}  {g["tipo"]:<{largura_tipo}}  {tamanho(g["bytes"]):>9}  '
                     f'{g["fim"].strftime("%d/%m/%Y")}\n')
        sessoes = len({g['sessao'] for g in grupos})
        escrever(f'Total: {plural(len(grupos), "item", "itens")} de {plural(sessoes, "sessão", "sessões")}, '
                 f'{tamanho(sum(g["bytes"] for g in grupos))}.\n')
    else:
        escrever(f'Nenhum dado de sessão encerrada há mais de {estado.dias} dias com prova de encerramento.\n')
    escrever('\nMantidos, só para informação:\n')
    for motivo, texto in MOTIVOS:
        lista = [u for u in unidades if u.get('motivo') == motivo]
        if lista or motivo == 'sem_prova':
            escrever(f'  {texto.format(dias=estado.dias)}: {plural(len(lista), "item", "itens")}, '
                     f'{tamanho(sum(u["bytes"] for u in lista))}\n')
    recusadas = sum(1 for u in unidades if u.get('motivo') == 'recusada')
    if recusadas:
        escrever(f'  recusados (link, montagem, tipo ou nome fora do padrão): {plural(recusadas, "item", "itens")}\n')
    return grupos


def abrir_registro(estado):
    fd = os.open('limpezas.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                 0o600, dir_fd=estado.fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise Recusa('limpezas.jsonl deve ser arquivo regular sem ligações')
    return fd


def registrar(fd, linha):
    texto = json.dumps(linha, ensure_ascii=False, separators=(',', ':')) + '\n'
    esperar_trava(fd, 'limpezas.jsonl')
    try:
        os.write(fd, texto.encode('utf-8'))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)


def reconferir(estado, grupo):
    """Unidades do grupo que continuam elegíveis com o estado lido agora."""
    areas = estado.areas()
    estado.reler_provas({s for u in grupo['unidades'] for s, _ in areas[u['area']][3](u['nome'])})
    validas, mantidas = [], []
    for unidade in grupo['unidades']:
        try:
            atual = estado.remedir(unidade)
        except (Recusa, OSError):
            atual = dict(motivo='recusada')
        if (atual.get('motivo') == 'elegivel' and atual['sessao'] == grupo['sessao']
                and atual['tipo'] == grupo['tipo']):
            validas.append(dict(atual, area=unidade['area']))
        else:
            mantidas.append((unidade, atual['motivo']))
    return validas, mantidas


def aplicar(estado, grupos, registro, erro=sys.stderr):
    """Apaga cada grupo sob as travas da sessão, depois de reconferir tudo."""
    apagados = falhas = 0
    textos = dict(MOTIVOS, sumiu='não existe mais', recusada='link, montagem, tipo ou nome fora do padrão')
    for grupo in grupos:
        travas = []
        rotulo = f'{grupo["sessao"]} ({grupo["tipo"]})'
        try:
            for sessao in sorted({s for u in grupo['unidades'] for s in u['travas']}):
                travas.append(travar_revisao(estado, sessao))
                for provedor in sorted({u['provedor'] for u in grupo['unidades'] if u['provedor']}):
                    travas.append(travar_provedor(estado, provedor, sessao))
            validas, mantidas = reconferir(estado, grupo)
            for unidade, motivo in mantidas:
                caminho = '/'.join(unidade['partes'] + (unidade['nome'],))
                erro.write(f'aviso: {caminho} mantido na reconferência: '
                           f'{textos.get(motivo, motivo).format(dias=estado.dias)}\n')
            removidos, total, resultado = [], 0, 'removido'
            for unidade in validas:
                caminho = '/'.join(unidade['partes'] + (unidade['nome'],))
                try:
                    apagar(estado, unidade['partes'], unidade['nome'])
                except FileNotFoundError:
                    continue
                except (Recusa, OSError) as falha:
                    erro.write(f'erro: {caminho} não foi apagado por inteiro: {falha}\n')
                    resultado = 'parcial'
                    falhas += 1
                removidos.append(caminho)
                total += unidade['bytes']
            if removidos:
                registrar(registro, {'sessao': grupo['sessao'], 'tipo': grupo['tipo'], 'caminhos': removidos,
                                     'bytes': total, 'encerrada': grupo['fim'].isoformat(timespec='seconds'),
                                     'quando': datetime.now().astimezone().isoformat(timespec='seconds'),
                                     'resultado': resultado})
                apagados += 1
        except (Recusa, OSError) as falha:
            erro.write(f'aviso: {rotulo} mantido: {falha}\n')
            falhas += 1
        finally:
            for fd in travas:
                os.close(fd)
    return apagados, falhas


def opcoes(argumentos):
    if '--' not in argumentos:
        raise ValueError('falta o comando do tmux depois de --')
    corte = argumentos.index('--')
    proprios, tmux = argumentos[:corte], argumentos[corte + 1:]
    if len(proprios) < 2:
        raise ValueError('informe a pasta de estado e os provedores')
    raiz, provedores, resto = proprios[0], proprios[1].split(), proprios[2:]
    if not os.path.isabs(raiz):
        raise ValueError('a pasta de estado deve ser caminho absoluto')
    if any(not PROVEDOR.fullmatch(p) for p in provedores):
        raise ValueError('provedor fora da lista fixa')
    dias, aplica = DIAS, False
    while resto:
        opcao = resto.pop(0)
        if opcao == '--aplicar':
            aplica = True
        elif opcao == '--dias':
            valor = resto.pop(0) if resto else ''
            if not re.fullmatch(r'[0-9]{1,5}', valor) or not 1 <= int(valor) <= DIAS_MAX:
                raise ValueError(f'--dias aceita inteiro de 1 a {DIAS_MAX}')
            dias = int(valor)
        else:
            raise ValueError('opção desconhecida: ' + opcao)
    return raiz, sorted(set(provedores)), dias, aplica, tmux


def main(argumentos):
    try:
        raiz, provedores, dias, aplica, tmux = opcoes(argumentos)
    except ValueError as erro:
        sys.stderr.write(f'jangada-agentes --limpar-antigos: {erro}\n'
                         'uso: jangada-agentes --limpar-antigos [--dias N] [--aplicar]\n')
        return 2
    simular = aplica and os.environ.get('JANGADA_SIMULAR') == '1'
    if aplica and not simular:
        if isolado():
            sys.stderr.write('AUTORIZACAO_RECUSADA: executor isolado não possui autoridade; '
                             '--aplicar exige controlador fora do isolamento\n')
            return 1
        if not os.isatty(0):
            sys.stderr.write('--aplicar exige terminal para a confirmação; nada foi apagado\n')
            return 1
    try:
        estado = Estado(raiz, provedores, dias, tmux)
    except FileNotFoundError:
        print(f'Nenhum estado em {raiz}; nada a limpar.')
        return 0
    except (Recusa, OSError) as erro:
        sys.stderr.write(f'jangada-agentes --limpar-antigos: {erro}\n')
        return 1
    try:
        unidades = medir_todas(estado)
        grupos = listar(estado, unidades, sys.stdout)
        for aviso in estado.avisos:
            sys.stderr.write(f'aviso: {aviso}\n')
        if not aplica or simular:
            if simular:
                print('JANGADA_SIMULAR=1: --aplicar só lista; nada foi apagado.')
            else:
                opcao = '' if dias == DIAS else f' --dias {dias}'
                print(f'Nada foi apagado. Para apagar, rode jangada-agentes --limpar-antigos{opcao} --aplicar.')
            return 0
        if not grupos:
            print('Nada a apagar.')
            return 0
        total = tamanho(sum(g['bytes'] for g in grupos))
        sys.stdout.write(f'\nPara apagar {plural(len(grupos), "item", "itens")} ({total}) '
                         f'sem cópia de segurança, digite {CONFIRMACAO}: ')
        sys.stdout.flush()
        if sys.stdin.readline().strip() != CONFIRMACAO:
            print('Nada foi apagado.')
            return 0
        # Aberto antes da primeira remoção: sem registro, nada é apagado.
        registro = abrir_registro(estado)
        try:
            apagados, falhas = aplicar(estado, grupos, registro)
        finally:
            os.close(registro)
        print(f'Apagados: {plural(apagados, "item", "itens")}; registro em {raiz}/limpezas.jsonl.')
        return 1 if falhas else 0
    except (Recusa, OSError) as erro:
        sys.stderr.write(f'jangada-agentes --limpar-antigos: {erro}\n')
        return 1
    finally:
        estado.fechar()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
