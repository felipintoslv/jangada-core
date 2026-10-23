#!/usr/bin/env python3
"""Testa o contrato K7 (docs/modularizacao-3.0/03-contratos.md): o formato dos
registros das seções 1, 2, 4, 8 e 9 de docs/registros.md.

Os registros são gerados pelos comandos do jangada numa pasta temporária, com
HOME, XDG_* e PATH próprios e um tmux falso; nada vem do estado da instalação
nem do tmux da máquina. Cada registro é conferido contra a tabela
testes/contratos/registros.json (nome, tipo e obrigatoriedade de cada campo,
e dos campos internos de objetos e de listas de objetos), e cada campo da
tabela precisa estar citado na seção do documento.

O jangada-projeto é trocado por um falso: registrar a execução da sessão exige
controlador fora do isolamento, e o teste precisa dar o mesmo resultado dentro
e fora dele. Pelo mesmo motivo o código de saída do jangada-agente não é
conferido: o SESSAO.json já está gravado quando a preservação do pedido, que
vem depois, recusa dentro do isolamento.

Uso: testes/contratos-registros.py
"""

import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
TABELA = RAIZ / 'testes/contratos/registros.json'
DOCUMENTO = RAIZ / 'docs/registros.md'
SESSAO = 'projeto--tarefa'
MARCA = '/tmp/.jangada-isolado'
# Dentro do jangada-isolar, esta marca faz o Core recusar o que exige o
# controlador de fora; o jangada-validar não chega ao revisor. Ali os casos
# que dependem dele são pulados, e fora nenhum é (testes/isolamento.sh).
SEM_AUTORIDADE = '/tmp/.jangada-sem-autoridade'
DATA = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')
TIPOS = {
    'texto': lambda v: isinstance(v, str),
    'data': lambda v: isinstance(v, str) and bool(DATA.match(v)),
    'inteiro': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'numero': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'booleano': lambda v: isinstance(v, bool),
    'objeto': lambda v: isinstance(v, dict),
    'lista': lambda v: isinstance(v, list),
    'nulo': lambda v: v is None,
}
# Um campo renomeado em cada ponto do código que grava: (arquivo, de, para,
# registro, campo que some, campo que aparece). Campo interno vai pelo caminho.
TROCAS = [
    ('bin/jangada-validar', 'itens: $itens,', 'apontamentos: $itens,',
     'validar.jsonl', 'itens', 'apontamentos'),
    ('bin/jangada-validar', 'candidate_sha: $candidato,', 'candidato: $candidato,',
     'validacao-SESSAO.aprovado', 'candidate_sha', 'candidato'),
    ('bin/jangada-agente', 'desde:$agora,', 'criado:$agora,', 'SESSAO.json', 'desde', 'criado'),
    ('bin/jangada-config', 'estado: $e,', 'situacao: $e,', 'eventos-agentes.jsonl', 'estado', 'situacao'),
    ('bin/jangada-delegar', 'papel: $papel,', 'funcao: $papel,', 'delegacoes.jsonl', 'papel', 'funcao'),
    ('bin/jangada-delegar', 'chamadas: $total_chamadas}', 'quantas: $total_chamadas}',
     'delegacoes.jsonl', 'tentativas.chamadas', 'tentativas.quantas'),
    ('bin/jangada-delegar', 'codigo_transporte: $codigo,', 'transporte: $codigo,',
     'delegacoes.jsonl', 'chamadas_local.codigo_transporte', 'chamadas_local.transporte'),
]

FALSOS = {
    # Só conhece a sessão que o new-session criou.
    'tmux': '''#!/bin/sh
case " $* " in
  *" new-session "*) : >"$FALSO_DIR/tmux.sessao" ;;
  *" has-session "*) [ -e "$FALSO_DIR/tmux.sessao" ] || exit 1 ;;
esac
exit 0
''',
    # Responde à lista de agentes, à cota e ao pedido (revisão ou delegação).
    'agy': '''#!/usr/bin/env bash
if [[ "$1" == agents ]]; then
  printf '%s\\n' explorador leitor pesquisador verificador auditor arquiteto designer otimizador redator revisor
  exit 0
fi
if [[ "$2" == /usage ]]; then
  printf '{"status":"SUCCESS","response":"","command":{"name":"usage","data":{"groups":[{"name":"Gemini Models","buckets":[{"id":"gemini-weekly","remaining_fraction":0.9},{"id":"gemini-5h","remaining_fraction":%s}]}]}}}\\n' "$FALSO_COTA"
  exit 0
fi
jq -n --arg r "$(printf '%b' "$FALSO_RESPOSTA")" \\
  '{conversation_id: "c1", status: "SUCCESS", response: $r, denied_actions: []}'
''',
    # Ollama: o modelo pedido, nenhum outro carregado e uma resposta com medidas.
    'curl': '''#!/bin/sh
case "$*" in
  */api/tags*) echo '{"models":[{"name":"qwen3:4b"}]}' ;;
  */api/ps*) echo '{"models":[]}' ;;
  */api/chat*) echo '{"message":{"content":"resumo em doc.txt:1"},"prompt_eval_count":20,"eval_count":5,"total_duration":1000000}' ;;
esac
''',
    'jangada-projeto': '''#!/bin/sh
case " $* " in *" sessao-iniciar "*) echo '{"execucao":"exe-0123456789abcdef"}' ;; esac
exit 0
''',
}

falhas = 0
pulados = 0


def sem_autoridade():
    return any(linha.split()[4] == SEM_AUTORIDADE
               for linha in pathlib.Path('/proc/self/mountinfo').read_text().splitlines())


def conferir(descricao, certo, detalhe=(), controlador=False):
    """Com controlador=True, o caso depende do jangada-validar de fora e é
    pulado dentro do isolamento."""
    global falhas, pulados
    if controlador and sem_autoridade():
        pulados += 1
        print(f'pulado no isolamento: {descricao} (o jangada-validar exige o controlador de fora)')
        if os.environ.get('JANGADA_TESTES_PULADOS'):
            with open(os.environ['JANGADA_TESTES_PULADOS'], 'a', encoding='utf-8') as arquivo:
                arquivo.write(descricao + '\n')
        return
    print(('ok    ' if certo else 'FALHA ') + descricao)
    if not certo:
        falhas += 1
        for linha in detalhe:
            print('      ' + str(linha))


def problemas(nome, registro, campos, caminho=''):
    """Um problema por linha; lista vazia quando o registro cumpre a tabela.
    Desce nos objetos com "campos" e nos itens das listas com "itens"."""
    if not isinstance(registro, dict):
        return [f'{nome}: {caminho or "o registro"} não é um objeto JSON']
    achados = []
    for campo, regra in campos.items():
        nome_campo = caminho + campo
        if campo not in registro:
            if regra['obrigatorio']:
                achados.append(f'{nome}: falta o campo obrigatório {nome_campo}')
            continue
        valor = registro[campo]
        if not any(TIPOS[t](valor) for t in regra['tipo']):
            achados.append(f'{nome}: {nome_campo} devia ser {" ou ".join(regra["tipo"])}, '
                           f'veio {json.dumps(valor, ensure_ascii=False)[:60]}')
        elif 'campos' in regra and isinstance(valor, dict):
            achados += problemas(nome, valor, regra['campos'], nome_campo + '.')
        elif 'itens' in regra and isinstance(valor, list):
            for item in valor:
                achados += problemas(nome, item, regra['itens'], nome_campo + '.')
    achados += [f'{nome}: campo fora da tabela: {caminho}{campo}' for campo in registro if campo not in campos]
    return achados


def caminhos(campos, caminho=''):
    """Os caminhos de todos os campos da tabela, internos inclusive."""
    for campo, regra in campos.items():
        yield caminho + campo
        yield from caminhos(regra.get('campos') or regra.get('itens') or {}, caminho + campo + '.')


def presentes(registro, campos, caminho=''):
    """Os caminhos da tabela que aparecem no registro."""
    if not isinstance(registro, dict):
        return
    for campo, regra in campos.items():
        if campo not in registro:
            continue
        yield caminho + campo
        valor = registro[campo]
        internos = regra.get('campos') or regra.get('itens') or {}
        for item in (valor if 'itens' in regra and isinstance(valor, list) else [valor]):
            yield from presentes(item, internos, caminho + campo + '.')


def secao_do_documento(numero):
    texto = DOCUMENTO.read_text(encoding='utf-8')
    achado = re.search(rf'^## {re.escape(numero)}\. .*?(?=^## |\Z)', texto, re.M | re.S)
    return achado.group(0) if achado else ''


def executavel(caminho, conteudo):
    caminho.write_text(conteudo, encoding='utf-8')
    caminho.chmod(0o755)


class Gerador:
    """Gera os registros numa pasta temporária, com o código de RAIZ ou com
    cópias alteradas dos arquivos de `trocas`."""

    def __init__(self, tmp, trocas=()):
        self.tmp = tmp
        self.arvore = tmp / 'jangada'
        self.falso = tmp / 'falso'
        self.casa = tmp / 'casa'
        self.projeto = tmp / 'projeto'
        self.estado = tmp / 'estado/jangada'
        self.worktree = tmp / 'worktrees/projeto/tarefa'
        for pasta in (self.arvore / 'bin', self.falso, self.projeto, self.estado, tmp / 'bin',
                      tmp / 'config/jangada', tmp / 'cache', tmp / 'run',
                      self.casa / '.gemini/antigravity-cli/log', self.casa / '.gemini/config'):
            pasta.mkdir(parents=True)
        for origem in RAIZ.iterdir():
            if origem.name != 'bin' and not origem.name.startswith('.'):
                (self.arvore / origem.name).symlink_to(origem)
        for origem in (RAIZ / 'bin').iterdir():
            if origem.name != 'jangada-projeto':
                (self.arvore / 'bin' / origem.name).symlink_to(origem)
        for arquivo, de, para in trocas:
            destino = self.arvore / arquivo
            texto = destino.read_text(encoding='utf-8')
            if de not in texto:
                raise SystemExit(f'{arquivo} não tem mais o trecho "{de}"; atualize TROCAS')
            destino.unlink()
            executavel(destino, texto.replace(de, para))
        executavel(self.arvore / 'bin/jangada-projeto', FALSOS['jangada-projeto'])
        for nome in ('tmux', 'agy', 'curl'):
            executavel(tmp / 'bin' / nome, FALSOS[nome])
        for nome in ('claude', 'notify-send', 'setsid', 'pkill'):
            executavel(tmp / 'bin' / nome, '#!/bin/sh\nexit 0\n')
        # Nenhum jogo aberto e memória de vídeo de sobra, qualquer que seja a
        # máquina: com o nvidia-smi real, outra carga na placa fazia a
        # delegação local sair com 4.
        executavel(tmp / 'bin/pgrep', '#!/bin/sh\nexit 1\n')
        executavel(tmp / 'bin/nvidia-smi', '#!/bin/sh\necho 24000\n')
        (tmp / 'config/jangada/jangada.conf').write_text(f'JANGADA_WORKTREES={tmp}/worktrees\n')
        (self.casa / '.gemini/antigravity-cli/settings.json').write_text(
            json.dumps({'trustedWorkspaces': [str(self.projeto.resolve())]}))
        hooks = (RAIZ / 'agentes/agy/hooks.json').read_text(encoding='utf-8')
        (self.casa / '.gemini/config/hooks.json').write_text(hooks.replace('@JANGADA_CORE_PATH@', str(self.arvore)))
        # Ambiente montado do zero: nenhuma variável JANGADA_*, TMUX ou XDG_* da
        # sessão que roda o teste chega aos comandos.
        self.ambiente = {
            'PATH': f'{tmp}/bin:/usr/local/sbin:/usr/local/bin:/usr/bin:/bin',
            'HOME': str(self.casa), 'LANG': 'C.UTF-8',
            'XDG_STATE_HOME': str(tmp / 'estado'), 'XDG_CONFIG_HOME': str(tmp / 'config'),
            'XDG_CACHE_HOME': str(tmp / 'cache'), 'XDG_RUNTIME_DIR': str(tmp / 'run'),
            'TMUX_TMPDIR': str(tmp / 'run'), 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
            'JANGADA_CORE_PATH': str(self.arvore), 'FALSO_DIR': str(self.falso),
            'JANGADA_ISOLAR_ESCRITA': str(self.falso), 'FALSO_COTA': '0.9', 'FALSO_RESPOSTA': '',
        }
        if 'TMPDIR' in os.environ:
            self.ambiente['TMPDIR'] = os.environ['TMPDIR']
        if not shutil.which('gitleaks', path=self.ambiente['PATH']):
            self.ambiente['JANGADA_VALIDAR_SEM_GITLEAKS'] = '1'
        self.git('init', '-q', '-b', 'main', pasta=self.projeto)
        self.git('commit', '-q', '--allow-empty', '-m', 'inicio', pasta=self.projeto)

    def rodar(self, *comando, pasta=None, entrada=None, **variaveis):
        return subprocess.run([str(c) for c in comando], cwd=pasta or self.tmp, env={**self.ambiente, **variaveis},
                              input=entrada, stdin=None if entrada is not None else subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=300)

    def como_agente(self, *comando, **argumentos):
        """Roda como o agente chama: com JANGADA_ISOLADO e a marca do isolamento
        montada. Dentro de uma sessão a marca já existe; fora, o bwrap monta só
        ela, como faz o testes/validar.sh."""
        prefixo, variaveis = [], {'JANGADA_ISOLADO': '1', 'JANGADA_SESSAO': SESSAO}
        montagens = pathlib.Path('/proc/self/mountinfo').read_text().splitlines()
        if not any(linha.split()[4] == MARCA for linha in montagens):
            marca = self.tmp / 'marca'
            marca.touch()
            prefixo = ['bwrap', '--dev-bind', '/', '/', '--ro-bind', '/dev/null', marca, '--']
            variaveis['JANGADA_MARCA_ISOLADO'] = str(marca)
        return self.rodar(*prefixo, *comando, **variaveis, **argumentos)

    def git(self, *argumentos, pasta):
        feito = self.rodar('git', '-c', 'user.name=t', '-c', 'user.email=t@t', *argumentos, pasta=pasta)
        if feito.returncode:
            raise SystemExit(f'git {" ".join(argumentos)}: {feito.stderr}')

    def comando(self, nome):
        return self.arvore / 'bin' / nome

    def linhas(self, nome):
        arquivo = self.estado / nome
        if not arquivo.is_file():
            return []
        return [json.loads(linha) for linha in arquivo.read_text(encoding='utf-8').splitlines() if linha]

    def sessao(self):
        arquivo = self.estado / 'agentes' / f'{SESSAO}.json'
        return json.loads(arquivo.read_text(encoding='utf-8')) if arquivo.is_file() else None

    def abrir_sessao(self):
        """SESSAO.json criado pelo jangada-agente (seção 4)."""
        self.rodar(self.comando('jangada-agente'), '--agente', 'claude', '--revisor', 'agy',
                   '--perfil', 'claude-codex', '--atividade', 'atv-1', '--tarefa-id', 'tarefa-1',
                   '--coordenador', 'claude',
                   '--projeto', self.projeto, '--nome', 'tarefa', '--prompt', 'tarefa de teste')
        return self.sessao()

    def registro_de(self, nome, **variaveis):
        """SESSAO.json e cópia em revisoes/ de uma sessão aberta sem a opção --coordenador."""
        # Pasta própria para o tmux falso, que só conhece uma sessão por pasta.
        falso = self.tmp / f'falso-{nome}'
        falso.mkdir()
        self.rodar(self.comando('jangada-agente'), '--agente', 'claude', '--projeto', self.projeto,
                   '--nome', nome, '--prompt', 'tarefa de teste', FALSO_DIR=str(falso), **variaveis)
        lidos = []
        for pasta in ('agentes', 'revisoes'):
            arquivo = self.estado / pasta / f'projeto--{nome}.json'
            lidos.append(json.loads(arquivo.read_text(encoding='utf-8')) if arquivo.is_file() else {})
        return lidos

    def coordenador_de(self, nome, **variaveis):
        """Coordenador gravado numa sessão aberta sem a opção --coordenador."""
        return self.registro_de(nome, **variaveis)[0].get('coordenador')

    def hooks(self):
        """eventos-agentes.jsonl (seção 8) e os campos que os hooks põem no SESSAO.json."""
        eventos = [
            ('inicio', {'session_id': '11111111-2222-3333-4444-555555555555', 'cwd': str(self.worktree)}),
            ('trabalhando', {'prompt': 'faça'}),
            ('subagente-inicio', {'session_id': 'c1', 'agent_id': 'a1', 'agent_type': 'explorador'}),
            ('subagente-fim', {'session_id': 'c1', 'agent_id': 'a1', 'agent_type': 'explorador'}),
            ('aguardando', {'message': 'permissão', 'notification_type': 'permission_prompt'}),
        ]
        for evento, dados in eventos:
            self.rodar(self.comando('jangada-hook-claude'), evento, entrada=json.dumps(dados), JANGADA_SESSAO=SESSAO)
        self.rodar(self.comando('jangada-agentes'), '--focar', SESSAO)
        return self.linhas('eventos-agentes.jsonl')

    def validar(self):
        """validar.jsonl (seção 1), pareceres e marca de aprovação (seção 2): uma
        rodada REVISAR e outra APROVADO, com o agy falso de revisor. Roda fora do
        isolamento, como o atendente do jangada-isolar a roda; testes/atendente.sh
        cobre o pedido de dentro."""
        (self.worktree / 'arquivo.txt').write_text('linha 1\n')
        self.git('add', 'arquivo.txt', pasta=self.worktree)
        self.git('commit', '-q', '-m', 'commit 1', pasta=self.worktree)
        codigos = []
        for resposta, extra in (('STATUS: REVISAR\\n1. arquivo.txt:1: problema', []),
                                ('STATUS: APROVADO\\ntudo certo', ['--resposta', '1 rejeitado: motivo'])):
            feito = self.rodar(self.comando('jangada-validar'), *extra, self.worktree,
                               JANGADA_SESSAO=SESSAO, FALSO_RESPOSTA=resposta)
            codigos.append(feito.returncode)
        return codigos

    def delegar(self):
        """delegacoes.jsonl (seção 9): uma delegação ao agy atendida, outra recusada
        por cota e uma ao modelo local, que grava as medidas de cada chamada."""
        codigos = []
        for cota in ('0.9', '0.1'):
            feito = self.como_agente(self.comando('jangada-delegar'), 'explorador', 'mapeie', '--permitir-remoto', pasta=self.projeto,
                                     FALSO_COTA=cota, FALSO_RESPOSTA='relatorio em a.sh:1',
                                     JANGADA_DELEGAR_CACHE='0')
            codigos.append(feito.returncode)
        (self.projeto / 'doc.txt').write_text('texto do documento\n')
        feito = self.como_agente(self.comando('jangada-delegar'), 'leitor', 'resuma', '--destino', 'local',
                                 '--arquivos', 'doc.txt', pasta=self.projeto, JANGADA_LOCAL_IGNORAR_VRAM='1')
        codigos.append(feito.returncode)
        return codigos

    def atuacoes(self):
        """Persistência comum aos três provedores, sem abrir cliente remoto."""
        pasta = self.estado / 'coordenadores'
        pasta.mkdir(mode=0o700, exist_ok=True)
        registros = []
        for provedor in ('claude', 'codex', 'agy'):
            sessao = provedor + '--coordenador'
            for modo, argumentos in (('abrir', [str(self.projeto), provedor]),
                                     ('finalizar', [])):
                feito = self.rodar('python3', self.arvore / 'nucleo/coordenadores.py',
                                   '--persistir', self.estado, modo, sessao, *argumentos)
                if feito.returncode:
                    raise AssertionError(feito.stderr)
                dados = json.loads((pasta / (sessao + '.json')).read_text())
                registros.append((provedor + '/' + modo, dados))
        return registros

    def tudo(self):
        """Todos os registros, por nome da tabela: lista de (rótulo, registro)."""
        registros = {nome: [] for nome in ('validar.jsonl', 'validacao-SESSAO.aprovado', 'SESSAO.json',
                                           'eventos-agentes.jsonl', 'delegacoes.jsonl')}
        pareceres = self.estado / 'revisoes'
        momentos = [('criado', self.abrir_sessao())]
        registros['eventos-agentes.jsonl'] = list(enumerate(self.hooks(), 1))
        momentos.append(('depois dos hooks', self.sessao()))
        self.codigos_validar = self.validar()
        momentos.append(('depois do validar', self.sessao()))
        registros['SESSAO.json'] = momentos
        registros['validar.jsonl'] = list(enumerate(self.linhas('revisoes/validar.jsonl'), 1))
        marca = pareceres / f'validacao-{SESSAO}.aprovado'
        if marca.is_file():
            registros['validacao-SESSAO.aprovado'] = [('marca', json.loads(marca.read_text(encoding='utf-8')))]
        self.pareceres = sorted(pareceres.glob(f'validacao-{SESSAO}-r*.md'))
        self.codigos_delegar = self.delegar()
        registros['delegacoes.jsonl'] = list(enumerate(self.linhas('delegacoes.jsonl'), 1))
        registros['coordenadores/SESSAO.json'] = self.atuacoes()
        return registros


def achados_de(tabela, registros):
    return {nome: [p for rotulo, registro in registros[nome]
                   for p in problemas(f'{nome} ({rotulo})', registro, tabela[nome]['campos'])]
            for nome in registros}


def main():
    tabela = json.loads(TABELA.read_text(encoding='utf-8'))
    parecer = tabela.pop('validacao-SESSAO-rN.md')

    # Todo campo da tabela está no documento, entre crases no texto ou entre
    # aspas num exemplo.
    for nome, descricao in {**tabela, 'validacao-SESSAO-rN.md': parecer}.items():
        secao = secao_do_documento(descricao['secao'])
        conferir(f'{nome}: a seção {descricao["secao"]} existe em docs/registros.md', bool(secao))
        faltam = [campo for campo in caminhos(descricao.get('campos', {}))
                  if f'`{campo.rsplit(".", 1)[-1]}`' not in secao and f'"{campo}"' not in secao]
        conferir(f'{nome}: todo campo da tabela está citado na seção {descricao["secao"]}', not faltam,
                 [f'sem citação: {campo}' for campo in faltam])

    with tempfile.TemporaryDirectory() as pasta:
        gerador = Gerador(pathlib.Path(pasta).resolve())
        registros = gerador.tudo()
        achados = achados_de(tabela, registros)

        conferir('o jangada-agente grava o SESSAO.json', registros['SESSAO.json'][0][1] is not None)
        conferir('o SESSAO.json leva o perfil e os vínculos dados ao jangada-agente',
                 {campo: (registros['SESSAO.json'][0][1] or {}).get(campo)
                  for campo in ('perfil', 'atividade', 'tarefa_id')}
                 == {'perfil': 'claude-codex', 'atividade': 'atv-1', 'tarefa_id': 'tarefa-1'})
        conferir('o --coordenador fica no SESSAO.json e sobrevive aos hooks e ao jangada-validar',
                 [(registro or {}).get('coordenador') for _, registro in registros['SESSAO.json']] == ['claude'] * 3)
        conferir('sem --coordenador, o SESSAO.json diz "dono"', gerador.coordenador_de('sem-opcao') == 'dono')
        conferir('JANGADA_COORDENADOR vale como a opção',
                 gerador.coordenador_de('pela-variavel', JANGADA_COORDENADOR='codex') == 'codex')
        sem_registro = gerador.registro_de('sem-registro', JANGADA_COORDENADOR='outro--coordenador')
        conferir('sem registro do coordenador, a tarefa não ganha coordenador_sessao',
                 all('coordenador_sessao' not in r for r in sem_registro), sem_registro)
        coordenadores = gerador.estado / 'coordenadores'
        coordenadores.mkdir(mode=0o700, exist_ok=True)
        (coordenadores / 'projeto--coordenador.json').write_text('{"sessao": "projeto--coordenador"}')
        de_dentro = gerador.registro_de('de-dentro', JANGADA_COORDENADOR='projeto--coordenador')
        conferir('a tarefa aberta de dentro do coordenador grava coordenador_sessao no SESSAO.json e na cópia',
                 [r.get('coordenador_sessao') for r in de_dentro] == ['projeto--coordenador'] * 2
                 and de_dentro[0].get('coordenador') == 'projeto--coordenador', de_dentro)
        conferir('os hooks e a troca de foco gravam seis eventos',
                 [e.get('estado') for _, e in registros['eventos-agentes.jsonl']]
                 == ['inicio', 'trabalhando', 'subagente-inicio', 'subagente-fim', 'aguardando', 'foco'],
                 [e for _, e in registros['eventos-agentes.jsonl']])
        conferir('o hook grava estado, mensagem e conversa no SESSAO.json',
                 all(campo in (registros['SESSAO.json'][1][1] or {}) for campo in ('conversa', 'mensagem'))
                 and (registros['SESSAO.json'][1][1] or {}).get('estado') == 'aguardando')
        conferir('o jangada-validar sai com 3 no REVISAR e 0 no APROVADO', gerador.codigos_validar == [3, 0],
                 [gerador.codigos_validar], controlador=True)
        conferir('o jangada-validar grava a validação no SESSAO.json',
                 (registros['SESSAO.json'][2][1] or {}).get('validacao') == 'r2: APROVADO (agy)', controlador=True)
        conferir('o validar.jsonl tem uma linha por rodada',
                 [(r.get('rodada'), r.get('resultado')) for _, r in registros['validar.jsonl']]
                 == [(1, 'revisar'), (2, 'aprovado')], controlador=True)
        conferir('cada rodada grava um parecer validacao-SESSAO-rN.md',
                 [p.name for p in gerador.pareceres] == [f'validacao-{SESSAO}-r{n}.md' for n in (1, 2)], controlador=True)
        primeiras = [next((linha for linha in p.read_text(encoding='utf-8').splitlines() if linha.strip()), '')
                     for p in gerador.pareceres]
        conferir('a primeira linha com texto de cada parecer é o STATUS',
                 bool(primeiras) and all(re.match(parecer['primeira_linha'], linha) for linha in primeiras),
                 primeiras, controlador=True)
        conferir('o APROVADO grava a marca validacao-SESSAO.aprovado', bool(registros['validacao-SESSAO.aprovado']),
                 controlador=True)
        conferir('o jangada-delegar sai com 0 nas delegações atendidas e 4 na recusada',
                 gerador.codigos_delegar == [0, 4, 0], [gerador.codigos_delegar])
        conferir('o delegacoes.jsonl tem a delegação ao agy, a recusada e a local',
                 [(d.get('destino'), d.get('recusa')) for _, d in registros['delegacoes.jsonl']]
                 == [('agy', False), ('agy', True), ('local', False)])
        for nome in tabela:
            conferir(f'{nome}: campos e tipos conforme a tabela', not achados[nome], achados[nome])
            vistos = {c for _, registro in registros[nome] for c in presentes(registro, tabela[nome]['campos'])}
            ausentes = sorted(set(caminhos(tabela[nome]['campos'])) - vistos
                              - set(tabela[nome].get('sem_exemplo', [])))
            conferir(f'{nome}: todo campo da tabela aparece em algum registro gerado, salvo os de "sem_exemplo"',
                     not ausentes, [f'ausentes: {ausentes}'],
                     controlador=nome in ('validar.jsonl', 'validacao-SESSAO.aprovado', 'SESSAO.json'))

        # O teste precisa falhar quando um campo muda de nome. Primeiro numa
        # cópia do registro, depois numa cópia do código que grava.
        for nome in tabela:
            campo = next(c for c, regra in tabela[nome]['campos'].items() if regra['obrigatorio'])
            alterado = copy.deepcopy(registros[nome][-1][1]) if registros[nome] else {}
            if isinstance(alterado, dict):
                alterado[f'{campo}_novo'] = alterado.pop(campo, None)
            achado = problemas(nome, alterado, tabela[nome]['campos'])
            conferir(f'{nome}: campo {campo} renomeado numa cópia do registro é apontado',
                     f'{nome}: falta o campo obrigatório {campo}' in achado
                     and f'{nome}: campo fora da tabela: {campo}_novo' in achado, achado)
        # Os campos subagentes.* do validar.jsonl vêm de comando opcional, fora do Core por ora
        # (jangada-subagentes) e ficam em "sem_exemplo".
        internos = [('delegacoes.jsonl', ['tentativas', 0], 'chamadas', 'tentativas.chamadas'),
                    ('delegacoes.jsonl', ['chamadas_local', 0, 'tempos_ms'], 'total', 'chamadas_local.tempos_ms.total')]
        for nome, rota, campo, caminho in internos:
            alterado = copy.deepcopy(registros[nome][-1][1]) if registros[nome] else {}
            try:
                objeto = alterado
                for passo in rota:
                    objeto = objeto[passo]
                objeto[f'{campo}_novo'] = objeto.pop(campo)
            except (KeyError, IndexError, TypeError):
                pass
            achado = problemas(nome, alterado, tabela[nome]['campos'])
            conferir(f'{nome}: campo interno {caminho} renomeado numa cópia do registro é apontado',
                     f'{nome}: falta o campo obrigatório {caminho}' in achado
                     and f'{nome}: campo fora da tabela: {caminho}_novo' in achado, achado)
        errado = copy.deepcopy(registros['validar.jsonl'][-1][1]) if registros['validar.jsonl'] else {}
        errado['rodada'] = '2'
        conferir('validar.jsonl: campo com o tipo trocado numa cópia do registro é apontado',
                 any('rodada devia ser inteiro' in p for p in problemas('validar.jsonl', errado,
                                                                        tabela['validar.jsonl']['campos'])))

    with tempfile.TemporaryDirectory() as pasta:
        gerador = Gerador(pathlib.Path(pasta).resolve(), [troca[:3] for troca in TROCAS])
        achados = achados_de(tabela, gerador.tudo())
        for arquivo, _, _, nome, some, aparece in TROCAS:
            texto = '\n'.join(achados[nome])
            conferir(f'{nome}: {some} renomeado numa cópia de {arquivo} é apontado',
                     f'falta o campo obrigatório {some}' in texto and f'campo fora da tabela: {aparece}' in texto,
                     achados[nome], controlador=arquivo == 'bin/jangada-validar')

    if pulados:
        print(f'{pulados} caso(s) pulado(s) no isolamento')
    if falhas:
        print(f'{falhas} falha(s)')
        return 1
    print('todos os testes do contrato de registros passaram')
    return 0


if __name__ == '__main__':
    sys.exit(main())
