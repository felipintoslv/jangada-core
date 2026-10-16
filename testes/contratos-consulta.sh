#!/usr/bin/env bash
# Testa o contrato K4 (docs/modularizacao-3.0/03-contratos.md): as consultas
# jangada-agentes --lista, --lista-atualizada e --waybar não gravam nada no
# estado, e só --limpar-orfaos remove as sessões órfãs, com o mesmo critério
# de antes.
#
# Uso: testes/contratos-consulta.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
estado="$tmp/state/jangada/agentes"
mkdir -p "$estado" "$tmp/bin" "$tmp/home" "$tmp/config" "$tmp/pasta"

# O tmux falso só conhece a sessão "viva".
printf '#!/bin/sh\n[ "$*" != "${*#*list-sessions}" ] && echo viva\nexit 0\n' >"$tmp/bin/tmux"
chmod +x "$tmp/bin/tmux"

agora="$(date -Iseconds)"
morto="$(sh -c 'echo $$')"
jq -n --arg a "$agora" '{estado:"trabalhando", atualizado:$a}' >"$estado/viva.json"
jq -n --arg a "$agora" '{estado:"concluido", atualizado:$a}' >"$estado/concluida.json"
jq -n --arg a "$agora" --argjson p "$morto" '{estado:"trabalhando", pid:$p, atualizado:$a}' >"$estado/orfa.json"
jq -n '{estado:"concluido", atualizado:"2000-01-01T00:00:00+00:00"}' >"$estado/vencida.json"
jq -n --arg a "$agora" --arg d "$tmp/pasta" '{estado:"trabalhando", agente:"codex", dir:$d, atualizado:$a}' >"$estado/caida.json"

agentes() {
  env -u TMUX -u JANGADA_ISOLADO -u JANGADA_AGENTES_GUARDAR PATH="$tmp/bin:$PATH" HOME="$tmp/home" \
    XDG_STATE_HOME="$tmp/state" XDG_CONFIG_HOME="$tmp/config" JANGADA_CORE_PATH="$repo_jangada" \
    "$repo_jangada/bin/jangada-agentes" "$@"
}

retrato() {
  (cd "$tmp/state" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum && find . | sort)
}

consultas=(--lista --lista-atualizada --waybar)
for opcao in "${consultas[@]}"; do
  antes="$(retrato)"
  agentes "$opcao" >"$tmp/antes$opcao" 2>&1
  conferir "$opcao sai com 0" [ "$?" -eq 0 ]
  conferir "$opcao não grava no estado" [ "$antes" == "$(retrato)" ]
done
conferir "a órfã continua no estado depois das consultas" test -e "$estado/orfa.json"
conferir "--lista mostra a sessão viva" grep -q $'^trabalhando\tviva\t' "$tmp/antes--lista"
conferir "--lista mostra a concluída dentro do prazo" grep -q $'^concluido\tconcluida\t' "$tmp/antes--lista"
conferir "--lista mostra a sessão que dá para restaurar" grep -q $'^interrompido\tcaida\t' "$tmp/antes--lista"
conferir "--lista tem só as três sessões" [ "$(cut -f2 "$tmp/antes--lista" | sort | tr '\n' ' ')" == "caida concluida viva " ]
conferir "--waybar conta as três sessões" \
  jq -e '.text == "󰚩 3  󰑮 1  󰄬 1  󰜺 1" and .class == "trabalhando" and (.tooltip | type) == "string"' "$tmp/antes--waybar" >/dev/null

conferir "--limpar-orfaos sai com 0" agentes --limpar-orfaos
conferir "--limpar-orfaos remove a órfã" test ! -e "$estado/orfa.json"
conferir "--limpar-orfaos remove a concluída vencida" test ! -e "$estado/vencida.json"
conferir "--limpar-orfaos mantém a sessão viva" test -e "$estado/viva.json"
conferir "--limpar-orfaos mantém a concluída dentro do prazo" test -e "$estado/concluida.json"
conferir "--limpar-orfaos marca como interrompida a sessão que dá para restaurar" \
  jq -e '.estado == "interrompido"' "$estado/caida.json" >/dev/null

# A órfã já não aparecia na consulta; sem ela no disco, a saída é a mesma. A
# marcação de interrompida regrava "atualizado", quarto campo da lista.
for opcao in "${consultas[@]}"; do
  agentes "$opcao" >"$tmp/depois$opcao" 2>&1
  conferir "$opcao sai com 0 depois da limpeza" [ "$?" -eq 0 ]
  conferir "$opcao igual antes e depois da limpeza" \
    cmp -s <(cut -f1-3,5- "$tmp/antes$opcao") <(cut -f1-3,5- "$tmp/depois$opcao")
done

python3 - "$repo_jangada" "$tmp" <<'PYTEST' || falhas=$((falhas + 1))
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

repo, tmp = map(Path, sys.argv[1:])
origem = tmp / 'json-state'
pasta = origem / 'jangada/agentes'
ambiente = dict(os.environ, PATH=str(tmp / 'bin') + ':' + os.environ['PATH'],
                HOME=str(tmp / 'home'), XDG_CONFIG_HOME=str(tmp / 'config'),
                XDG_STATE_HOME=str(origem), JANGADA_CORE_PATH=str(repo))
for nome in ('JANGADA_ISOLADO', 'TMUX', 'JANGADA_AGENTES_GUARDAR'):
    ambiente.pop(nome, None)


def consultar(opcao='--lista-json'):
    return subprocess.run([str(repo / 'bin/jangada-agentes'), opcao],
                          capture_output=True, env=ambiente, timeout=5)


def retrato():
    return [(str(p.relative_to(origem)), p.lstat().st_mode,
             hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else '')
            for p in sorted(origem.rglob('*')) if not p.is_fifo()]


# Estado ausente não recebe diretórios, inclusive nas consultas antigas.
for opcao in ('--lista-json', '--lista', '--lista-atualizada', '--waybar'):
    r = consultar(opcao)
    assert r.returncode == 0, r.stderr
    assert not origem.exists()
assert json.loads(consultar().stdout)['sessoes'][0]['nome'] == 'viva'
tmux = tmp / 'bin/tmux'
original_tmux = tmux.read_text()
tmux.write_text('#!/bin/sh\nexit 0\n')
assert json.loads(consultar().stdout) == {'versao': 1, 'sessoes': []}
assert not origem.exists()
tmux.write_text("#!/bin/sh\nprintf '%s\\n' viva 'meu trabalho' 'ação' '../../fora'\n")
for opcao in ('--lista-json', '--lista', '--lista-atualizada', '--waybar'):
    r = consultar(opcao)
    assert r.returncode == 0 and r.stderr and not origem.exists()
    if opcao == '--lista-json':
        assert [s['nome'] for s in json.loads(r.stdout)['sessoes']] == ['viva']
    elif opcao == '--waybar':
        assert json.loads(r.stdout)['text'] == '󰚩 1'
    else:
        assert [l.split('\t')[1] for l in r.stdout.decode().splitlines()] == ['viva']
tmux.write_text('#!/bin/sh\necho ../../fora\n')
for opcao in ('--lista', '--lista-atualizada', '--waybar'):
    r = consultar(opcao)
    assert r.returncode == 0 and r.stderr
    assert not origem.exists()
    if opcao == '--waybar':
        assert json.loads(r.stdout)['class'] == 'vazio'
tmux.write_text(original_tmux)
pasta.mkdir(parents=True)
agora = subprocess.check_output(['date', '-Iseconds'], text=True).strip()
texto = 'ação\nlinha dois\t雪 &lt;b&gt; <b>literal</b>'
viva = dict(estado='aguardando', dir=str(tmp / 'pasta'), atualizado=agora,
            ramo='agente/<ramo>&lt;', tarefa=texto, agente='codex', raiz='/projeto/raiz',
            mensagem=texto, desde=agora, inicio='a' * 40, coordenador='claude',
            revisor='claude', comando='segredo que não sai', conversa='privada')
(pasta / 'viva.json').write_text(json.dumps(viva))
(pasta / 'retida.json').write_text(json.dumps(dict(estado='concluido', atualizado=agora)))
(pasta / 'interrompida.json').write_text(json.dumps(dict(estado='interrompido', atualizado=agora)))
(pasta / 'restauravel.json').write_text(json.dumps(dict(agente='codex', dir=str(tmp / 'pasta'))))
(pasta / 'expirada.json').write_text(json.dumps(dict(estado='concluido', atualizado='2000-01-01')))
(pasta / 'pid.json').write_text(json.dumps(dict(estado='ativo', pid=os.getpid())))
# Contextos e pareceres não são abertos, mesmo quando não são arquivos regulares.
(pasta / 'revisao-um-r1.json').write_text('não é JSON')
os.mkfifo(pasta / 'validacao-um-r1.contexto.json')
(pasta / 'delegacao-exemplo.json').write_text('não é sessão')
tmux.write_text("#!/bin/sh\nprintf '%s\\n' viva revisao-um-r1 validacao-um-r1.contexto delegacao-exemplo\n")
antes = retrato()
for opcao in ('--lista-json', '--lista', '--lista-atualizada'):
    r = consultar(opcao)
    assert r.returncode == 0, r.stderr
    if opcao == '--lista-json':
        reservadas = {s['nome']: s for s in json.loads(r.stdout)['sessoes']}
        for nome in ('revisao-um-r1', 'validacao-um-r1.contexto', 'delegacao-exemplo'):
            assert reservadas[nome]['estado'] == 'ativo'
            assert reservadas[nome]['mensagem'] == reservadas[nome]['tarefa'] == ''
    assert retrato() == antes
tmux.write_text(original_tmux)
antes = retrato()
r = consultar()
assert r.returncode == 0, r.stderr
resultado = json.loads(r.stdout)
assert resultado['versao'] == 1
sessoes = {s['nome']: s for s in resultado['sessoes']}
assert set(sessoes) == {'viva', 'retida', 'interrompida', 'restauravel', 'pid'}
assert sessoes['restauravel']['estado'] == 'interrompido'
assert sessoes['viva']['tarefa'] == texto == sessoes['viva']['mensagem']
assert sessoes['viva']['desde'] == agora
assert sessoes['viva']['projeto'] == 'raiz'
assert not {'inicio', 'comando', 'conversa', 'pid'} & sessoes['viva'].keys()
assert retrato() == antes
for opcao in ('--lista', '--lista-atualizada'):
    r = consultar(opcao)
    assert r.returncode == 0, r.stderr
    linha = next(l for l in r.stdout.decode().splitlines() if l.split('\t')[1] == 'viva')
    assert linha == '\t'.join(('aguardando', 'viva', str(tmp / 'pasta'), agora,
                               'agente/&lt;ramo&gt;&amp;lt;', 'ação'))
    assert retrato() == antes

# Todo erro recusa a resposta integral; nunca publica uma lista parcial.
ruim = pasta / 'ruim.json'
for conteudo in ('{', '[]', json.dumps(dict(mensagem=[])),
                 json.dumps(dict(tarefa='x' * 16001)), json.dumps(dict(pid=True)),
                 'x' * (1024 * 1024 + 1)):
    ruim.write_text(conteudo)
    antes = retrato()
    r = consultar()
    assert r.returncode == 1 and not r.stdout and r.stderr, (conteudo[:30], r)
    assert retrato() == antes
ruim.unlink()
for tipo in ('link', 'fifo', 'diretorio'):
    if tipo == 'link':
        ruim.symlink_to(pasta / 'viva.json')
    elif tipo == 'fifo':
        os.mkfifo(ruim)
    else:
        ruim.mkdir()
    r = consultar()
    assert r.returncode == 1 and not r.stdout and r.stderr, tipo
    ruim.rmdir() if tipo == 'diretorio' else ruim.unlink()
(pasta / 'nome inválido.json').write_text('{}')
assert consultar().returncode == 1
(pasta / 'nome inválido.json').unlink()
# A pasta de sessões também não pode ser link.
pasta.rename(pasta.with_name('originais'))
pasta.symlink_to(pasta.with_name('originais'), target_is_directory=True)
assert consultar().returncode == 1
antes = retrato()
for opcao in ('--lista', '--lista-atualizada', '--waybar'):
    r = consultar(opcao)
    assert r.returncode == 0 and r.stderr, r
    if opcao == '--waybar':
        assert json.loads(r.stdout)['text'] == '󰚩 1'
    else:
        assert r.stdout.decode().split('\t')[:2] == ['ativo', 'viva']
    assert retrato() == antes
pasta.unlink()
pasta.with_name('originais').rename(pasta)
# Um arquivo no lugar da pasta também não aborta as consultas TSV.
pasta.rename(pasta.with_name('originais'))
pasta.write_text('não é diretório')
assert consultar().returncode == 1
for opcao in ('--lista', '--waybar'):
    r = consultar(opcao)
    assert r.returncode == 0 and r.stderr
pasta.unlink()
pasta.with_name('originais').rename(pasta)
if os.geteuid() != 0:
    antes = retrato()
    modo = pasta.stat().st_mode & 0o7777
    pasta.chmod(0)
    try:
        assert consultar().returncode == 1
        for opcao in ('--lista', '--waybar'):
            r = consultar(opcao)
            assert r.returncode == 0 and r.stderr
    finally:
        pasta.chmod(modo)
    assert retrato() == antes
# Resposta agregada limitada, mesmo com cada registro dentro do limite.
for i in range(80):
    (pasta / f'grande-{i}.json').write_text(json.dumps(dict(estado='concluido', atualizado=agora, tarefa='x' * 16000)))
r = consultar()
assert r.returncode == 1 and not r.stdout and b'1 MiB' in r.stderr
for p in pasta.glob('grande-*.json'):
    p.unlink()
# Core e fachada funcionam sem pastas Shell e Monitor.
minimo = tmp / 'core-sem-interface'
(minimo / 'bin').mkdir(parents=True)
(minimo / 'nucleo').mkdir(parents=True)
for nome, fonte in (('bin/jangada-config', 'bin/jangada-config'),
                    ('bin/jangada-agentes', 'bin/jangada-agentes'),
                    ('nucleo/sessoes.py', 'nucleo/sessoes.py')):
    shutil.copy2(repo / fonte, minimo / nome)
ambiente['JANGADA_CORE_PATH'] = str(minimo)
r = subprocess.run([str(minimo / 'bin/jangada-agentes'), '--lista-json'],
                   env=ambiente, capture_output=True, timeout=5)
assert r.returncode == 0, r.stderr
assert json.loads(r.stdout) == resultado
# Retenção recebe ambos os prazos e funciona sem date, ou com date que recusa.
from datetime import datetime, timedelta
retencao = tmp / 'retencao'
retencao.mkdir()
(retencao / 'antiga.json').write_text(json.dumps(dict(estado='interrompido',
    atualizado=(datetime.now().astimezone() - timedelta(hours=1)).isoformat())))
sem_data = tmp / 'sem-data'
sem_data.mkdir()
for date_disponivel in (False, True):
    if date_disponivel:
        (sem_data / 'date').write_text('#!/bin/sh\nexit 1\n')
        (sem_data / 'date').chmod(0o700)
    for prazo, esperado in (('168', ['antiga']), ('0', [])):
        r = subprocess.run([sys.executable, str(repo / 'nucleo/sessoes.py'),
                            str(retencao), '24', prazo, 'json'], input='', text=True,
                           capture_output=True, env=dict(ambiente, PATH=str(sem_data)), timeout=5)
        assert r.returncode == 0, r.stderr
        assert [s['nome'] for s in json.loads(r.stdout)['sessoes']] == esperado

(sem_data / 'date').write_text('#!' + sys.executable + '\nimport time\ntime.sleep(3)\n')
(sem_data / 'date').chmod(0o700)
r = subprocess.run([sys.executable, str(repo / 'nucleo/sessoes.py'),
                    str(retencao), '24', '168', 'json'], input='', text=True,
                   capture_output=True, env=dict(ambiente, PATH=str(sem_data)), timeout=5)
assert r.returncode == 0 and json.loads(r.stdout)['sessoes'][0]['nome'] == 'antiga', r.stderr

# Falhas de varredura e de execução da data não dependem de permissões do usuário de teste.
import importlib.util
from unittest.mock import patch
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('sessoes', repo / 'nucleo/sessoes.py')
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)
abrir_original = modulo.os.open
def abrir_sessao(caminho, *args, **kwargs):
    assert str(caminho) not in ('revisao-um-r1.json', 'validacao-um-r1.contexto.json',
                              'delegacao-exemplo.json'), caminho
    return abrir_original(caminho, *args, **kwargs)
with patch.object(modulo.os, 'open', side_effect=abrir_sessao):
    for estrito in (True, False):
        selecionadas = modulo.selecionar(pasta, ['revisao-um-r1',
            'validacao-um-r1.contexto', 'delegacao-exemplo'], 24, 168, estrito)
        assert [s['nome'] for s in selecionadas[:3]] == [
            'revisao-um-r1', 'validacao-um-r1.contexto', 'delegacao-exemplo']
with patch.object(modulo.os, 'scandir', side_effect=OSError('varredura indisponível')):
    legado = modulo.selecionar(pasta, ['viva'], 24, 168, False)
    assert [s['nome'] for s in legado] == ['viva']
    try:
        modulo.selecionar(pasta, ['viva'], 24, 168, True)
    except OSError:
        pass
    else:
        raise AssertionError('JSON deveria recusar varredura indisponível')
with patch.object(modulo.subprocess, 'run', side_effect=OSError('date indisponível')):
    assert modulo.selecionar(retencao, [], 24, 168, True)[0]['nome'] == 'antiga'

# O TSV não valida metadados que não apresenta nem limita a tarefa antes do resumo.
ambiente['JANGADA_CORE_PATH'] = str(repo)
for chave in ('WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'DISPLAY'):
    ambiente.pop(chave, None)
viva['mensagem'] = []
viva['tarefa'] = 'x' * 16001
(pasta / 'viva.json').write_text(json.dumps(viva))
assert consultar().returncode == 1
r = consultar('--lista')
assert r.returncode == 0, r.stderr
linha = next(l for l in r.stdout.decode().splitlines() if l.split('\t')[1] == 'viva')
assert linha.split('\t')[-1] == 'x' * 47 + '...'
r = consultar('--waybar')
assert r.returncode == 0 and json.loads(r.stdout)['class'] == 'aguardando', r.stderr
ruim.write_text('{')
r = consultar('--waybar')
assert r.returncode == 0 and json.loads(r.stdout)['class'] == 'aguardando', r.stderr
assert r.stderr
r = consultar('--proximo')
assert r.returncode == 0, r.stderr
viva['mensagem'] = 'texto'
viva['tarefa'] = '\ud800'
(pasta / 'viva.json').write_text(json.dumps(viva))
assert consultar().returncode == 1
r = consultar('--lista')
assert r.returncode == 0 and r.stderr and r.stdout
r = consultar('--waybar')
assert r.returncode == 0 and r.stderr and json.loads(r.stdout)

# A consulta pública de observação descobre caminhos no Core sem gravar estado.
observacao_xdg = tmp / 'observacao-xdg'
observacao_xdg.mkdir()
ambiente['XDG_STATE_HOME'] = str(observacao_xdg)
origem = observacao_xdg
antes = retrato()
r = consultar('--observacao-json')
assert r.returncode == 0 and not r.stderr, r.stderr
assert json.loads(r.stdout) == {'versao': 1, 'caminhos': [str(observacao_xdg)]}
assert not (observacao_xdg / 'jangada').exists()
assert retrato() == antes
estado_pai_link = tmp / 'observacao-xdg-link'
estado_pai_link.symlink_to(observacao_xdg, target_is_directory=True)
ambiente['XDG_STATE_HOME'] = str(estado_pai_link)
r = consultar('--observacao-json')
assert r.returncode == 0 and json.loads(r.stdout) == {
    'versao': 1, 'caminhos': [str(observacao_xdg)]}
assert not (observacao_xdg / 'jangada').exists()
ambiente['XDG_STATE_HOME'] = str(observacao_xdg)

estado_observacao = observacao_xdg / 'jangada'
(estado_observacao / 'agentes/projetos/um').mkdir(parents=True)
(estado_observacao / 'revisoes').mkdir()
(estado_observacao / 'agentes/sessao.json').write_text('{}')
(estado_observacao / 'agentes/x\n.json').write_text('{}')
(estado_observacao / 'revisoes/validacao-s-r1.json').write_text('{}')
(estado_observacao / 'agentes/projetos/um/tarefas.sqlite').write_bytes(b'')
(estado_observacao / 'agentes/projetos/um/tarefas.sqlite-wal').write_bytes(b'')
(estado_observacao / 'agentes/projetos/atalho').symlink_to(tmp, target_is_directory=True)
(estado_observacao / 'agentes/link.json').symlink_to(estado_observacao / 'agentes/sessao.json')
antes = retrato()
r = consultar('--observacao-json')
assert r.returncode == 0 and not r.stderr, r.stderr
observacao = json.loads(r.stdout)
assert observacao['versao'] == 1
assert set(observacao['caminhos']) == {
    str(estado_observacao / 'agentes'), str(estado_observacao / 'agentes/sessao.json'),
    str(estado_observacao / 'revisoes'), str(estado_observacao / 'revisoes/validacao-s-r1.json'),
    str(estado_observacao / 'agentes/projetos'), str(estado_observacao / 'agentes/projetos/um'),
    str(estado_observacao / 'agentes/projetos/um/tarefas.sqlite'),
    str(estado_observacao / 'agentes/projetos/um/tarefas.sqlite-wal')}
assert str(estado_observacao / 'agentes/x\n.json') not in observacao['caminhos']
# Um componente intermediário simbólico não abre a árvore apontada.
agentes = estado_observacao / 'agentes'
agentes.rename(agentes.with_name('agentes-originais'))
fora_agentes = tmp / 'fora-agentes'
fora_agentes.mkdir()
(fora_agentes / 'segredo.json').write_text('{}')
agentes.symlink_to(fora_agentes, target_is_directory=True)
r = consultar('--observacao-json')
assert r.returncode == 0, r.stderr
assert str(fora_agentes / 'segredo.json') not in json.loads(r.stdout)['caminhos']
agentes.unlink()
agentes.with_name('agentes-originais').rename(agentes)
# Bases ausentes são representadas pelo antepassado existente mais próximo.
agentes.rename(agentes.with_name('agentes-originais'))
r = consultar('--observacao-json')
assert r.returncode == 0, r.stderr
assert set(json.loads(r.stdout)['caminhos']) == {
    str(estado_observacao), str(estado_observacao / 'revisoes'),
    str(estado_observacao / 'revisoes/validacao-s-r1.json')}
agentes.with_name('agentes-originais').rename(agentes)
projetos_ausentes = agentes / 'projetos'
projetos_ausentes.rename(projetos_ausentes.with_name('projetos-originais'))
r = consultar('--observacao-json')
assert r.returncode == 0, r.stderr
assert str(agentes) in json.loads(r.stdout)['caminhos']
assert str(projetos_ausentes) not in json.loads(r.stdout)['caminhos']
projetos_ausentes.with_name('projetos-originais').rename(projetos_ausentes)
# Área vinculada nunca é percorrida; a consulta observa seu antepassado.
projetos = estado_observacao / 'agentes/projetos'
projetos.rename(projetos.with_name('projetos-originais'))
externo = tmp / 'fora-da-origem'
externo.mkdir()
(externo / 'segredo.json').write_text('{}')
projetos.symlink_to(externo, target_is_directory=True)
r = consultar('--observacao-json')
assert r.returncode == 0, r.stderr
assert str(externo / 'segredo.json') not in json.loads(r.stdout)['caminhos']
projetos.unlink()
projetos.with_name('projetos-originais').rename(projetos)

# Projetos removidos ou inacessíveis durante a leitura são omitidos; falha de base é explícita.
spec_observacao = importlib.util.spec_from_file_location('observacao', repo / 'nucleo/observacao.py')
modulo_observacao = importlib.util.module_from_spec(spec_observacao)
spec_observacao.loader.exec_module(modulo_observacao)
scandir_original = modulo_observacao.os.scandir
projeto_um = projetos / 'um'
def scandir_projeto_com_falha(caminho):
    if str(caminho) == str(projeto_um):
        raise FileNotFoundError('projeto removido')
    return scandir_original(caminho)
with patch.object(modulo_observacao.os, 'scandir', side_effect=scandir_projeto_com_falha):
    parcial = json.loads(modulo_observacao.observar(estado_observacao))
assert str(projeto_um) not in parcial['caminhos']
assert str(projeto_um / 'tarefas.sqlite') not in parcial['caminhos']
def scandir_projeto_sem_permissao(caminho):
    if str(caminho) == str(projeto_um):
        raise PermissionError('projeto sem permissão')
    return scandir_original(caminho)
with patch.object(modulo_observacao.os, 'scandir', side_effect=scandir_projeto_sem_permissao):
    parcial = json.loads(modulo_observacao.observar(estado_observacao))
assert str(projeto_um) not in parcial['caminhos']
assert str(projeto_um / 'tarefas.sqlite-wal') not in parcial['caminhos']
def scandir_base_com_falha(caminho):
    if str(caminho) == str(estado_observacao / 'revisoes'):
        raise PermissionError('base sem permissão')
    return scandir_original(caminho)
with patch.object(modulo_observacao.os, 'scandir', side_effect=scandir_base_com_falha):
    try:
        modulo_observacao.observar(estado_observacao)
    except PermissionError:
        pass
    else:
        raise AssertionError('falha de leitura da base deveria recusar a consulta')
assert not modulo_observacao.adicionar(set(), Path('/' + 'x' * 4096))
with patch.object(modulo_observacao, 'LIMITE_ENTRADAS', 1):
    try:
        modulo_observacao.observar(estado_observacao)
    except ValueError as erro:
        assert 'limite de entradas' in str(erro)
    else:
        raise AssertionError('volume de entradas deveria recusar a consulta')

# O limite exato de caminhos é aceito e o próximo caminho recusa a lista inteira.
volume = estado_observacao / 'revisoes'
for indice in range(4088):
    (volume / f'volume-{indice}.json').touch()
r = consultar('--observacao-json')
assert r.returncode == 0 and len(json.loads(r.stdout)['caminhos']) == 4096, r.stderr
(volume / 'volume-extra.json').touch()
r = consultar('--observacao-json')
assert r.returncode == 1 and not r.stdout and r.stderr
for arquivo in volume.glob('volume-*.json'):
    arquivo.unlink()

if os.geteuid() != 0:
    revisoes = estado_observacao / 'revisoes'
    modo = revisoes.stat().st_mode & 0o7777
    revisoes.chmod(0)
    try:
        r = consultar('--observacao-json')
        assert r.returncode == 1 and not r.stdout and r.stderr
    finally:
        revisoes.chmod(modo)
assert retrato() == antes
print('observação JSON: antepassado, caminhos limitados e sem efeitos passaram')
print('consulta JSON: seleção, TSV, limites, recusas e Core sem interface passaram')
PYTEST

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "todos os testes do contrato de consulta passaram"
