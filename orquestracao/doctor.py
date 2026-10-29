"""Diagnóstico sem inicializar clientes, bancos persistentes ou configuração."""

import argparse
import base64
import contextlib
import datetime
import http.client
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import time
import urllib.parse

RAIZ = Path(__file__).resolve().parents[1]
LIMITE = 1024 * 1024
ESTADOS = ('ok', 'aviso', 'falha', 'nao_verificavel')


class ConsultaRecusada(ValueError):
    def __init__(self, erro, codigo=None):
        super().__init__('consulta recusada')
        self.erro = erro
        self.codigo = codigo


def ler(caminho, limite=LIMITE):
    # O_NONBLOCK impede que um FIFO no lugar de uma configuração trave o relatório.
    fd = os.open(caminho, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as arquivo:
        if not stat.S_ISREG(os.fstat(arquivo.fileno()).st_mode):
            raise ValueError('arquivo não regular')
        dados = arquivo.read(limite + 1)
    if len(dados) > limite:
        raise ValueError('arquivo excede o limite de leitura')
    return dados


def objeto(caminho):
    dados = json.loads(ler(caminho))
    if not isinstance(dados, dict):
        raise ValueError('objeto esperado')
    return dados


def numero(valor, minimo=0, maximo=math.inf):
    return type(valor) in (int, float) and math.isfinite(valor) and minimo <= valor <= maximo


def executar(args, prazo=3, capturar=False, ambiente=None, capturar_erro=False):
    processo = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE if capturar else subprocess.DEVNULL,
                                stderr=subprocess.PIPE if capturar_erro else subprocess.DEVNULL,
                                env=ambiente, start_new_session=True)
    try:
        saida, erro = processo.communicate(timeout=prazo)
        if processo.returncode:
            raise ConsultaRecusada(erro or b'', processo.returncode)
        saida = (saida or b'').decode('utf-8')
        return (saida, erro or b'') if capturar_erro else saida
    finally:
        if processo.poll() is None:
            try:
                # O Git remove seus temporários ao tratar TERM, inclusive no prazo vencido.
                os.killpg(processo.pid, signal.SIGTERM)
                processo.wait(timeout=.5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
        try:
            os.killpg(processo.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        processo.wait()
        for fluxo in (processo.stdout, processo.stderr):
            if fluxo is not None:
                fluxo.close()


class Doctor:
    def __init__(self):
        self.itens = []
        self.casa = Path.home()
        self.config = Path(os.environ.get('XDG_CONFIG_HOME', self.casa / '.config')) / 'jangada'
        self.estado = Path(os.environ.get('XDG_STATE_HOME', self.casa / '.local/state')) / 'jangada'
        self.cache = Path(os.environ.get('XDG_CACHE_HOME', self.casa / '.cache')) / 'jangada'
        self.codex = Path(os.environ.get('CODEX_HOME', self.casa / '.codex'))
        padroes = {'JANGADA_CORE_PATH': str(RAIZ), 'JANGADA_CANAL': 'main',
                   'JANGADA_LOCAL_MODELO': 'qwen3:4b', 'JANGADA_OLLAMA_URL': 'http://localhost:11434',
                   'JANGADA_DELEGAR_MODELOS': 'gemini-3.8-flash-high claude-sonnet-5-5-high gpt-oss-120b-medium',
                   'JANGADA_CODEX_COTA_MIN': '25', 'JANGADA_DELEGAR_COTA_MIN': '20',
                   'JANGADA_DELEGAR_CACHE': '5'}
        self.valores = {k: os.environ.get(k, v) for k, v in padroes.items()}
        # O arquivo prevalece como no jangada-config, sem source nem expansão de shell.
        try:
            for linha in ler(self.config / 'jangada.conf').decode('utf-8').splitlines():
                chave, separador, valor = linha.rstrip().partition('=')
                if separador and chave in padroes:
                    for prefixo in ('$HOME', '~'):
                        if valor.startswith(prefixo):
                            valor = str(self.casa) + valor[len(prefixo):]
                            break
                    self.valores[chave] = valor
        except FileNotFoundError:
            pass
        except (OSError, ValueError, UnicodeError):
            self.adicionar('configuracao', 'nao_verificavel', 'Configuração ilegível ou inválida; usados valores do ambiente e padrões.')
        self.core = Path(self.valores['JANGADA_CORE_PATH'])

    def adicionar(self, ident, estado, detalhe):
        self.itens.append(dict(id=ident, categoria=ident.split('.')[0], estado=estado, detalhe=detalhe))

    def conferir(self, ident, consulta):
        try:
            estado, detalhe = consulta()
        except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError,
                subprocess.SubprocessError, sqlite3.Error, http.client.HTTPException):
            estado, detalhe = 'nao_verificavel', 'Consulta indisponível, inválida ou sem resposta no prazo; nenhum ajuste realizado.'
        self.adicionar(ident, estado, detalhe)

    def programas(self):
        obrigatorios = ('bash', 'python3', 'sqlite3', 'bwrap', 'tmux', 'git', 'jq')
        opcionais = {'claude': 'sessões e revisão Claude', 'codex': 'sessões e revisão Codex',
                     'agy': 'delegação e revisão agy', 'ollama': 'cliente local',
                     'curl': 'delegação local', 'xdg-dbus-proxy': 'login do agy no isolamento',
                     'gdbus': 'keyring por item', 'Rscript': 'verificação de R com lintr',
                     'shellcheck': 'verificação de shell', 'ssh-keygen': 'conferência de assinaturas SSH',
                     'notify-send': 'notificações', 'inotifywait': 'observação das sessões',
                     'timeout': 'prazos da delegação', 'flock': 'travas entre processos'}
        for nome in obrigatorios:
            tem = bool(shutil.which(nome))
            self.adicionar('programa.' + nome, 'ok' if tem else 'falha',
                           'Programa obrigatório encontrado no PATH.' if tem else 'Programa obrigatório ausente no PATH.')
        for nome, uso in opcionais.items():
            tem = bool(shutil.which(nome))
            self.adicionar('programa.' + nome, 'ok' if tem else 'aviso',
                           ('Programa opcional presente: ' if tem else 'Programa opcional ausente: ') + uso + '.')

    def userns(self):
        bwrap = shutil.which('bwrap')
        if not bwrap:
            return 'falha', 'Bubblewrap ausente; impossível abrir o isolamento.'
        try:
            executar([bwrap, '--unshare-user', '--unshare-pid', '--unshare-net',
                      '--ro-bind', '/', '/', '--die-with-parent', '--new-session', '--', '/usr/bin/true'])
        except ValueError:
            return 'falha', 'Bubblewrap recusou o teste mínimo de namespaces; confira as restrições do kernel ou deste ambiente.'
        return 'ok', 'Teste mínimo real de namespaces passou em até 3 segundos; não verifica as montagens dos provedores.'

    def autenticacao(self, provedor):
        if provedor == 'agy':
            return 'nao_verificavel', 'Login guardado no keyring; o diagnóstico não consulta segredos nem inicia o cliente.'
        caminho = (self.casa / '.claude/.credentials.json' if provedor == 'claude' else self.codex / 'auth.json')
        if not caminho.exists():
            return 'aviso', 'Credencial em arquivo ausente; outros mecanismos de login não foram consultados.'
        dados = objeto(caminho)
        if provedor == 'claude':
            oauth = dados['claudeAiOauth']
            token, fim = oauth.get('accessToken'), oauth.get('expiresAt')
            if not isinstance(token, str) or not token or not numero(fim):
                raise ValueError('credencial inválida')
            if fim / 1000 <= time.time():
                return 'aviso', 'Credencial local vencida; não houve renovação nem consulta ao servidor.'
        else:
            tokens = dados.get('tokens')
            if dados.get('auth_mode') == 'apikey' or dados.get('OPENAI_API_KEY'):
                return 'aviso', 'Configuração indica chave de API; o Core exige login por assinatura.'
            if not isinstance(tokens, dict) or any(not isinstance(tokens.get(k), str) or not tokens[k]
                                                   for k in ('access_token', 'id_token')):
                raise ValueError('credencial inválida')
            partes = tokens['access_token'].split('.')
            if len(partes) != 3:
                return 'nao_verificavel', 'Credencial local presente; prazo de validade não observável sem iniciar o cliente.'
            payload = json.loads(base64.urlsafe_b64decode(partes[1] + '=' * (-len(partes[1]) % 4)))
            fim = payload.get('exp')
            if not numero(fim):
                raise ValueError('prazo inválido')
            if fim <= time.time():
                return 'aviso', 'Credencial local vencida; não houve renovação nem consulta ao servidor.'
        return 'ok', 'Credencial local presente no formato esperado; validade no servidor não foi consultada.'

    def cota_agy(self):
        caminho = self.cache / 'agy-usage.json'
        validade = float(self.valores['JANGADA_DELEGAR_CACHE']) * 60
        idade = time.time() - caminho.stat().st_mtime
        if not numero(validade, 1) or not 0 <= idade < validade:
            return 'nao_verificavel', 'Registro de cota ausente ou vencido; não houve atualização pela rede.'
        grupos = objeto(caminho)['command']['data']['groups']
        if not isinstance(grupos, list) or any(not isinstance(g, dict) for g in grupos):
            raise ValueError('grupos inválidos')
        usados = {'gemini' if m.startswith('gemini-') else '3p'
                  for m in self.valores['JANGADA_DELEGAR_MODELOS'].split()}
        if not usados:
            return 'nao_verificavel', 'Nenhum modelo agy configurado para observar a cota; sem consulta remota.'
        cotas = {}
        for grupo in grupos:
            baldes = grupo.get('buckets', [])
            if not isinstance(baldes, list) or any(not isinstance(b, dict) for b in baldes):
                raise ValueError('baldes inválidos')
            for balde in baldes:
                ident = balde.get('id')
                if not isinstance(ident, str) or balde.get('disabled') is True:
                    continue
                for prefixo in usados:
                    if ident.startswith(prefixo + '-'):
                        cotas.setdefault(prefixo, []).append(balde.get('remaining_fraction'))
        saldos = {g: min(valores) * 100 for g, valores in cotas.items()
                  if all(numero(v, 0, 1) for v in valores)}
        ausentes = usados - cotas.keys()
        invalidos = cotas.keys() - saldos.keys()
        minimo = float(self.valores['JANGADA_DELEGAR_COTA_MIN'])
        if not numero(minimo, 0, 100):
            raise ValueError('reserva inválida')
        abaixo = {g for g, saldo in saldos.items() if saldo == 0 or saldo < minimo}
        detalhes = []
        if saldos:
            detalhes.append('Saldos observados: ' + ', '.join(f'{g}: {saldos[g]:.2f}%' for g in sorted(saldos)))
        if ausentes:
            detalhes.append('grupos ausentes: ' + ', '.join(sorted(ausentes)))
        if invalidos:
            detalhes.append('grupos inválidos: ' + ', '.join(sorted(invalidos)))
        if abaixo:
            detalhes.append('grupos abaixo da reserva: ' + ', '.join(sorted(abaixo)))
        if not saldos:
            return 'aviso', 'Nenhum saldo válido de grupo configurado; ' + '; '.join(detalhes) + '; sem atualização pela rede.'
        return ('aviso' if ausentes or invalidos or abaixo else 'ok',
                '; '.join(detalhes) + '; registro local ainda no prazo, sem consulta remota.')

    def cota_codex(self):
        caminho = self.estado / 'agentes/runtime/tarefas.sqlite'
        # Não abra a origem com SQLite: até mode=ro pode criar SHM. Sem WAL,
        # uma cópia em memória basta; com WAL não afirmamos conhecer a última cota.
        if Path(str(caminho) + '-wal').exists():
            return 'nao_verificavel', 'Banco de observações usa WAL; a cota não é consultada para evitar arquivos auxiliares na origem.'
        info = caminho.stat()
        dados = ler(caminho, 16 * LIMITE)
        depois = caminho.stat()
        if ((info.st_mtime_ns, info.st_size) != (depois.st_mtime_ns, depois.st_size)
                or Path(str(caminho) + '-wal').exists()):
            raise ValueError('banco mudou durante a leitura')
        if not dados.startswith(b'SQLite format 3\0') or len(dados) < 100:
            raise ValueError('banco inválido')
        # deserialize não abre bancos em formato WAL. Sem WAL pendente, os
        # bytes 18 e 19 habilitam o diário tradicional apenas na cópia em memória.
        dados = dados[:18] + b'\x01\x01' + dados[20:]
        with contextlib.closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(dados)
            prazo = time.monotonic() + .2
            db.set_progress_handler(lambda: time.monotonic() >= prazo, 1000)
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA temp_store=MEMORY')
            db.execute('PRAGMA query_only=ON')
            linha = db.execute("SELECT cota, atualizado, valido_ate FROM provedores WHERE id='codex'").fetchone()
        agora = time.time()
        if (not linha or not numero(linha[0], 0, 100) or not numero(linha[1])
                or not numero(linha[2]) or not linha[1] <= agora < linha[2]):
            return 'nao_verificavel', 'Cota do Codex ausente, inválida ou vencida; não houve atualização pela rede.'
        minimo = float(self.valores['JANGADA_CODEX_COTA_MIN'])
        if not numero(minimo, 0, 100):
            raise ValueError('reserva inválida')
        return ('aviso' if linha[0] < minimo or linha[0] == 0 else 'ok',
                f'Saldo observado: {linha[0]:.2f}%; observação local ainda no prazo, sem consulta remota.')

    def isolamento(self, provedor):
        if not os.access(self.core / 'bin/jangada-isolar', os.X_OK) or not shutil.which('bwrap'):
            return 'falha', 'Falta o comando de isolamento ou bubblewrap.'
        if provedor == 'agy':
            if not (shutil.which('xdg-dbus-proxy') and os.environ.get('DBUS_SESSION_BUS_ADDRESS')
                    and os.environ.get('XDG_RUNTIME_DIR') and Path(os.environ['XDG_RUNTIME_DIR']).is_dir()):
                return 'aviso', 'Falta proxy, endereço D-Bus ou pasta de execução; o agy pode não alcançar o login.'
            return 'nao_verificavel', 'Pré-requisitos do proxy presentes; keyring e acesso real dentro do isolamento não foram testados.'
        if provedor == 'codex' and (not self.codex.is_absolute() or not self.codex.is_dir()):
            return 'aviso', 'O Codex exige pasta de login existente e absoluta antes de abrir a sessão.'
        return 'nao_verificavel', 'Pré-requisitos básicos presentes; montagens, dados próprios da sessão e proteção das configurações não foram testados.'

    def local(self):
        modelo = self.valores['JANGADA_LOCAL_MODELO']
        if not re.fullmatch(r'[A-Za-z0-9_./:-]{1,160}', modelo):
            return 'aviso', 'Nome do modelo local configurado inválido; valor omitido.'
        url = urllib.parse.urlsplit(self.valores['JANGADA_OLLAMA_URL'])
        if (url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'}
                or url.username or url.password or url.query or url.fragment):
            return 'nao_verificavel', 'Endereço Ollama fora do HTTP local permitido; nenhuma requisição enviada.'
        conexao = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=2)
        try:
            conexao.request('GET', url.path.rstrip('/') + '/api/tags')
            resposta = conexao.getresponse()
            if resposta.status != 200:
                raise ValueError('consulta indisponível')
            corpo = resposta.read(LIMITE + 1)
            if len(corpo) > LIMITE:
                raise ValueError('resposta grande')
            dados = json.loads(corpo)
            modelos = dados['models']
            if not isinstance(modelos, list) or any(not isinstance(m, dict) or not isinstance(m.get('name'), str) for m in modelos):
                raise ValueError('modelos inválidos')
            presente = modelo in {m['name'] for m in modelos}
            return ('ok' if presente else 'aviso',
                    f'Modelo configurado {modelo}: ' + ('presente no serviço local; geração e memória não foram testadas.' if presente else 'ausente no serviço local.'))
        finally:
            conexao.close()

    def pasta(self, nome):
        caminho = self.estado / nome
        if any(p.is_symlink() for p in (caminho, *caminho.parents) if p == self.estado or self.estado in p.parents):
            return 'falha', 'Há link simbólico no caminho dentro da pasta de estado.'
        try:
            info = caminho.lstat()
        except FileNotFoundError:
            return 'aviso', 'Pasta ausente; não foi criada. Algumas pastas surgem apenas ao usar a função correspondente.'
        modo = stat.S_IMODE(info.st_mode)
        if not stat.S_ISDIR(info.st_mode):
            return 'falha', 'Esperada uma pasta real, sem link simbólico.'
        if info.st_uid != os.getuid():
            return 'falha', f'Dono diferente do usuário atual (UID {info.st_uid}); modo {modo:04o}.'
        privados = {'revisoes', 'coordenadores', 'codex', 'fotos', 'integracoes', 'agentes/runtime'}
        if modo & 0o022 or (nome in privados and modo & 0o077):
            return 'aviso', f'UID {info.st_uid}, modo {modo:04o}; permissões mais abertas que o esperado para esta pasta.'
        if modo & 0o700 != 0o700:
            return 'aviso', f'UID {info.st_uid}, modo {modo:04o}; faltam permissões do dono.'
        return 'ok', f'Pasta existente, UID {info.st_uid}, modo {modo:04o}.'

    def migracoes(self):
        pasta = self.core / 'migrations'
        if not pasta.is_dir():
            raise ValueError('migrações indisponíveis')
        scripts = [p for p in pasta.iterdir() if p.suffix == '.sh' and p.is_file()]
        pendentes = sum(not (self.estado / 'migracoes' / p.name).exists() for p in scripts)
        return ('aviso' if pendentes else 'ok',
                f'{pendentes} migrações pendentes entre {len(scripts)} scripts; nenhum script executado.')

    def temporario_git(self):
        if not self.estado.is_absolute() or any(p.is_symlink() for p in (self.estado, *self.estado.parents)):
            return 'Pasta de estado relativa ou com link simbólico; cópia temporária não permitida.'
        try:
            info = self.estado.stat()
        except FileNotFoundError:
            return 'Pasta de estado ausente; nenhuma pasta foi criada para a cópia temporária.'
        except OSError:
            return 'Pasta de estado não acessível; cópia temporária não permitida.'
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o022):
            return 'Pasta de estado insegura: exige pasta real do usuário, sem escrita de grupo ou outros.'
        try:
            for ancestral in self.estado.parents:
                info_ancestral = ancestral.stat()
                if ((info_ancestral.st_uid not in {0, os.getuid()}
                     and not os.statvfs(ancestral).f_flag & os.ST_RDONLY)
                        or (info_ancestral.st_mode & 0o022 and not info_ancestral.st_mode & stat.S_ISVTX)):
                    return 'Pasta de estado com ancestral inseguro para a cópia temporária.'
        except OSError:
            return 'Não foi possível conferir os ancestrais da pasta de estado; cópia temporária não permitida.'
        if stat.S_IMODE(info.st_mode) & 0o300 != 0o300 or not os.access(self.estado, os.W_OK | os.X_OK):
            return 'Pasta de estado sem acesso de escrita ou travessia para a cópia temporária.'
        return None

    def git(self, *args, verificador=None, temporario=None, aparar=True):
        # Configuração do repositório não pode escolher executáveis nem gravar índice.
        ambiente = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        ambiente.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0',
                        GIT_NO_LAZY_FETCH='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
        if temporario is not None:
            ambiente.update(TMPDIR=str(temporario), LC_ALL='C')
        fixos = ['core.fsmonitor=false', 'core.hooksPath=/dev/null', 'core.pager=cat',
                 'core.untrackedCache=false', 'gpg.program=/usr/bin/false',
                 'gpg.x509.program=/usr/bin/false', 'gpg.ssh.program=' + (verificador or '/usr/bin/false'),
                 'gpg.ssh.allowedSignersFile=' + str(self.config / 'allowed_signers'),
                 'gpg.ssh.revocationFile=/dev/null']
        comando = ['git', '--no-pager', '--no-optional-locks', '-C', str(self.core)]
        for fixo in fixos:
            comando += ['-c', fixo]
        saida = executar(comando + list(args), prazo=5, capturar=True, ambiente=ambiente,
                         capturar_erro=temporario is not None)
        if temporario is not None:
            saida, erro = saida
            return (saida.strip() if aparar else saida), erro
        return saida.strip() if aparar else saida

    def versao(self):
        canal = self.valores['JANGADA_CANAL']
        if canal not in {'main', 'estavel'}:
            raise ValueError('canal inválido')
        atual = self.git('rev-parse', '--verify', 'HEAD^{commit}')
        destino = self.git('rev-parse', '--verify', f'refs/remotes/origin/{canal}^{{commit}}')
        if not all(re.fullmatch('[0-9a-f]{40,64}', sha) for sha in (atual, destino)):
            raise ValueError('referência inválida')
        tag = self.git('describe', '--tags', '--match', 'v[0-9]*', '--always', atual)
        if not re.fullmatch(r'[v0-9a-z.\-]{1,80}', tag):
            tag = atual[:12]
        if not (self.config / 'allowed_signers').is_file():
            return 'nao_verificavel', f'Cópia em {tag}; falta allowed_signers para conferir a origem local, sem buscar atualizações.'
        verificador = shutil.which('ssh-keygen')
        if not verificador:
            return 'nao_verificavel', f'Cópia em {tag}; ssh-keygen ausente no PATH, assinatura não conferida.'
        motivo = self.temporario_git()
        if motivo:
            return 'nao_verificavel', motivo
        commits = self.git('rev-list', '--max-count=513', atual + '..' + destino).splitlines()
        if len(commits) > 512:
            return 'nao_verificavel', 'Comparação excede 512 commits; nenhuma busca ou atualização realizada.'
        if (len(set(commits)) != len(commits) or any(not re.fullmatch('[0-9a-f]{40,64}', c) for c in commits)
                or (commits and (destino not in commits or atual in commits))):
            return 'nao_verificavel', 'Lista de commits inválida; assinatura não conferida.'
        conferir = commits or [destino]
        try:
            saida, erro = self.git('log', '--no-walk=unsorted', '--no-show-signature', '--no-notes',
                                   '--no-decorate', '--no-patch', '--no-color', '--format=%G?',
                                   '--end-of-options', *conferir, verificador=verificador,
                                   temporario=self.estado, aparar=False)
        except ConsultaRecusada as consulta:
            saida, erro = None, consulta.erro
        except ValueError:
            return 'nao_verificavel', 'Não foi possível conferir a assinatura pelo Git; nenhum ajuste realizado.'
        # O Git pode devolver N e código zero quando falha ao preparar a assinatura SSH.
        if any(m in erro for m in (b'could not create temporary file', b'failed writing detached signature')):
            return 'nao_verificavel', 'O Git não conseguiu criar ou gravar a cópia temporária na pasta de estado; assinatura não conferida.'
        if saida is None:
            return 'nao_verificavel', 'O Git não confirmou a assinatura; consulta recusada ou indisponível, sem afirmar que a assinatura é inválida.'
        resultados = saida.splitlines(keepends=True)
        if (len(resultados) != len(conferir)
                or any(r not in {'G\n', 'N\n', 'B\n', 'U\n', 'X\n', 'Y\n', 'R\n', 'E\n'} for r in resultados)):
            return 'nao_verificavel', 'Resultado da conferência Git ausente, incompleto ou inválido; nenhum ajuste realizado.'
        if 'E\n' in resultados:
            return 'nao_verificavel', 'Git retornou E: houve conferência indeterminada ou falha operacional; nenhum ajuste realizado.'
        recusados = sum(r != 'G\n' for r in resultados)
        if recusados:
            return 'aviso', f'{recusados} commits sem assinatura válida por allowed_signers; o jangada-update recusaria aplicá-los.'
        if atual == destino:
            return 'ok', f'Cópia em {tag}, igual à referência local assinada da origem; atualidade remota não consultada.'
        try:
            self.git('merge-base', '--is-ancestor', atual, destino)
        except ConsultaRecusada as erro:
            if erro.codigo == 1:
                return 'aviso', f'Cópia em {tag} diverge ou está à frente da referência local assinada; sem consulta remota.'
            return 'nao_verificavel', 'Falha operacional ao comparar a ancestralidade das referências locais; nenhum ajuste realizado.'
        return 'aviso', f'Cópia em {tag}, com {len(commits)} commits pendentes da referência local assinada; sem consulta remota.'

    def hooks(self, provedor):
        if provedor == 'codex':
            candidatos = [('pasta Codex', self.codex / 'jangada-hooks-confianca.json'),
                          ('coordenadores', self.estado / 'coordenadores/codex-hooks-confianca.json')]
            sessao = os.environ.get('JANGADA_SESSAO', '')
            if re.fullmatch('[A-Za-z0-9_.-]+', sessao) and sessao not in {'.', '..'}:
                candidatos.insert(0, ('sessão atual', self.estado / 'codex' / sessao / 'jangada-hooks-confianca.json'))
            vistos, registros = set(), []
            tem_desabilitado = False
            for contexto, caminho in candidatos:
                if not caminho.exists():
                    continue
                info = caminho.stat()
                identidade = (info.st_dev, info.st_ino)
                if identidade in vistos:
                    continue
                vistos.add(identidade)
                dados = objeto(caminho)
                desabilitados = 0
                for entrada in dados.values():
                    if (not isinstance(entrada, dict) or not isinstance(entrada.get('trusted_hash'), str)
                            or not entrada['trusted_hash'] or type(entrada.get('enabled', True)) is not bool):
                        raise ValueError('registro de confiança inválido')
                    desabilitados += entrada.get('enabled') is False
                registros.append(f'{contexto}: {len(dados)} entradas, {desabilitados} desabilitadas')
                tem_desabilitado |= bool(desabilitados)
            if not registros:
                return 'nao_verificavel', 'Sem registro local de confiança no contexto consultado. Hooks do Codex são fornecidos por argumentos e aprovados por sessão; cliente não iniciado.'
            return ('aviso' if tem_desabilitado else 'nao_verificavel',
                    'Registros locais de confiança por contexto: ' + '; '.join(registros)
                    + '. Não comprovam o fornecimento dos hooks na execução; cliente não iniciado.')
        caminho = (self.casa / '.claude/settings.json' if provedor == 'claude'
                   else self.casa / '.gemini/config/hooks.json')
        if not caminho.exists():
            return 'aviso', 'Arquivo de hooks ausente; nenhum registro foi criado.'
        dados = objeto(caminho)
        modelo = objeto(RAIZ / 'agentes' / provedor / 'hooks.json')
        def expandir(valor):
            if isinstance(valor, dict):
                return {k: expandir(v) for k, v in valor.items()}
            if isinstance(valor, list):
                return [expandir(v) for v in valor]
            return valor.replace('@JANGADA_CORE_PATH@', str(self.core)) if isinstance(valor, str) else valor

        modelo = expandir(modelo)

        def contem(esperado, atual):
            if isinstance(esperado, dict):
                return isinstance(atual, dict) and all(k in atual and contem(v, atual[k]) for k, v in esperado.items())
            if isinstance(esperado, list):
                return isinstance(atual, list) and all(any(contem(v, a) for a in atual) for v in esperado)
            return esperado == atual

        if dados.get('disableAllHooks') is True or not contem(modelo, dados):
            return 'aviso', 'Hooks esperados ausentes, desabilitados ou diferentes do padrão instalado; conteúdo omitido.'
        return 'ok', 'Hooks esperados registrados no arquivo; execução pelo cliente não foi testada.'

    def registro(self):
        nomes = {'claude', 'codex', 'agy', 'ollama'}
        for origem, pasta in (('instalado', self.core / 'provedores'), ('usuario', self.config / 'provedores')):
            try:
                if pasta.is_dir():
                    nomes.update(p.stem for p in pasta.iterdir() if p.suffix == '.conf' and re.fullmatch('[A-Za-z0-9_-]+', p.stem))
            except OSError:
                self.adicionar('registro.catalogo_' + origem, 'nao_verificavel', 'Pasta do registro de provedores ilegível.')
        tipos = {}
        for nome in sorted(nomes):
            def consultar(n=nome):
                caminho = self.config / 'provedores' / (n + '.conf')
                if not os.access(caminho, os.R_OK):
                    caminho = self.core / 'provedores' / (n + '.conf')
                valores = {}
                for linha in ler(caminho).decode('utf-8').splitlines():
                    k, sep, v = linha.rstrip().partition('=')
                    if sep:
                        valores[k] = v
                tipo, funcoes = valores.get('TIPO'), valores.get('FUNCOES', '')
                if (tipo not in {'cli', 'ollama'} or not re.fullmatch(r'(?:(?:principal|coordenador|revisor|delegacao)(?: |$))+', funcoes)
                        or (tipo != 'cli' and {'principal', 'coordenador'} & set(funcoes.split()))
                        or not re.fullmatch(r'(?:--?[a-z][a-z0-9-]*)?', valores.get('PROTOCOLO_ARG', ''))
                        or not re.fullmatch('[A-Za-z0-9_.:-]*', valores.get('MODELO_REVISOR', ''))
                        or not re.fullmatch('[0-9]*', valores.get('RESERVA', ''))):
                    return 'aviso', 'Registro inválido; o Core ignora este provedor.'
                tipos[n] = tipo
                return 'ok', 'Registro válido, com precedência da configuração do usuário; arquivo não executado.'
            self.conferir('registro.' + nome, consultar)
            if nome not in {'claude', 'codex', 'agy', 'ollama'}:
                if tipos.get(nome) == 'cli':
                    self.adicionar('programa.' + nome, 'ok' if shutil.which(nome) else 'aviso',
                                   'Executável do provedor adicional ' + ('presente.' if shutil.which(nome) else 'ausente.'))
                for categoria in ('autenticacao', 'cota', 'isolamento', 'hooks'):
                    self.adicionar(categoria + '.' + nome, 'nao_verificavel', 'Provedor adicional sem contrato de diagnóstico específico; cliente não iniciado.')

    def relatorio(self):
        self.programas()
        self.registro()
        self.conferir('isolamento.userns', self.userns)
        for provedor in ('claude', 'codex', 'agy'):
            self.conferir('autenticacao.' + provedor, lambda p=provedor: self.autenticacao(p))
            self.conferir('isolamento.' + provedor, lambda p=provedor: self.isolamento(p))
            self.conferir('hooks.' + provedor, lambda p=provedor: self.hooks(p))
        self.adicionar('cota.claude', 'nao_verificavel', 'Não há registro local de saldo com validade documentada; nenhum cliente ou serviço remoto consultado.')
        self.conferir('cota.agy', self.cota_agy)
        self.conferir('cota.codex', self.cota_codex)
        self.conferir('local.modelo', self.local)
        self.conferir('versao.origem', self.versao)
        self.conferir('migracoes.pendentes', self.migracoes)
        for nome in ('', 'agentes', 'agentes/runtime', 'revisoes', 'coordenadores', 'codex', 'fotos', 'integracoes', 'migracoes'):
            self.conferir('pastas.' + (nome.replace('/', '.') or 'estado'), lambda n=nome: self.pasta(n))
        resumo = {estado: sum(i['estado'] == estado for i in self.itens) for estado in ESTADOS}
        return dict(versao=1, gerado_em=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    resumo=resumo, codigo_saida=1 if resumo['falha'] else 0, verificacoes=self.itens)


def texto(dados):
    rotulos = {'ok': 'OK', 'aviso': 'AVISO', 'falha': 'FALHA', 'nao_verificavel': 'NÃO VERIFICÁVEL'}
    linhas = ['=== Diagnóstico do jangada-core (doctor) ===', '']
    for item in dados['verificacoes']:
        linhas.append(f"[{rotulos[item['estado']]}] {item['id']}: {item['detalhe']}")
    r = dados['resumo']
    linhas += ['', f"Resumo: {r['ok']} ok, {r['aviso']} avisos, {r['falha']} falhas, {r['nao_verificavel']} não verificáveis.",
               'Somente leitura. Código de saída: ' + str(dados['codigo_saida']) + '.']
    return '\n'.join(linhas)


def main():
    parser = argparse.ArgumentParser(prog='jangada doctor', add_help=False,
                                     description='Confere o ambiente do Core sem corrigir nem atualizar registros.')
    parser.add_argument('-h', '--help', '--ajuda', action='help', help='Mostra esta ajuda.')
    parser.add_argument('--json', action='store_true', help='Imprime relatório estruturado, versão 1.')
    args = parser.parse_args()
    dados = Doctor().relatorio()
    print(json.dumps(dados, ensure_ascii=False, indent=2) if args.json else texto(dados))
    return dados['codigo_saida']


if __name__ == '__main__':
    raise SystemExit(main())
