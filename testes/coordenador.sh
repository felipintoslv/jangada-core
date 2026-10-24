#!/usr/bin/env bash
# jangada-coordenador: abertura, registro pelos hooks, consulta e fim, num
# servidor tmux próprio do teste (TMUX_TMPDIR temporário), nunca o servidor
# real do jangada.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
repo_jangada="$PWD"
python3 - "$repo_jangada" <<'PYTEST' || exit 1
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(sys.argv[1]) / 'nucleo'))
from coordenadores import arquivar, gravar, ler_registro

with tempfile.TemporaryDirectory(prefix='jangada-registros-') as tmp:
    pasta = Path(tmp)
    fd = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY)
    try:
        gravar(fd, 'registro.json', dict(ciclo='aberta', estado='iniciado'))
        gravar(fd, 'registro.json', dict(ciclo='aberta', estado='concluido'))
        assert json.loads((pasta / 'registro.json').read_text()) == dict(ciclo='aberta', estado='concluido')
        assert (pasta / 'registro.json').stat().st_mode & 0o777 == 0o600
        assert not list(pasta.glob('.reg.*'))
        gravar(fd, 'exclusivo.json', dict(versao=1), novo=True)
        antes = (pasta / 'exclusivo.json').read_bytes()
        try:
            gravar(fd, 'exclusivo.json', dict(versao=2), novo=True)
        except FileExistsError:
            pass
        else:
            raise AssertionError('Arquivo exclusivo existente foi substituído.')
        assert (pasta / 'exclusivo.json').read_bytes() == antes
        assert (pasta / 'exclusivo.json').stat().st_nlink == 1
        (pasta / 'link.json').symlink_to(pasta / 'exclusivo.json')
        try:
            gravar(fd, 'link.json', dict(versao=2), novo=True)
        except FileExistsError:
            pass
        else:
            raise AssertionError('Arquivo exclusivo simbólico foi substituído.')
        assert (pasta / 'link.json').is_symlink()
        assert (pasta / 'exclusivo.json').read_bytes() == antes
        dados = dict(sessao='projeto--coordenador', atuacao_id='a' * 32, ciclo='encerrada')
        revisoes = pasta / 'revisoes'
        revisoes.mkdir()
        (revisoes / 'projeto--tarefa.json').write_text(json.dumps(dict(coordenador_sessao=dados['sessao'])))
        assert arquivar(fd, dados, pasta) == 1
        historico = pasta / 'historico' / ('a' * 32 + '.json')
        antes = historico.read_bytes()
        (revisoes / 'alheia--tarefa.json').write_text('{')
        assert arquivar(fd, dados, pasta) == 1
        assert historico.read_bytes() == antes
        assert historico.stat().st_nlink == 1
        original = dict(sessao='seguro--coordenador', atuacao_id='d' * 32, ciclo='aberta')
        encerrado = dict(original, ciclo='encerrada', encerrado='2026-10-18T12:00:00+00:00')
        gravar(fd, 'seguro--coordenador.json', original)
        intacto = (pasta / 'seguro--coordenador.json').read_bytes()
        historico_seguro = pasta / 'historico' / ('d' * 32 + '.json')
        for invalido in ('{', '[]', json.dumps(dict(versao=1, registro=encerrado,
                                                   pendencias=[dict(sessao='../fora', origem='../fora.json')]))):
            historico_seguro.write_text(invalido)
            try:
                arquivar(fd, encerrado, pasta, original)
            except ValueError:
                pass
            else:
                raise AssertionError('Histórico inválido aceito.')
            assert (pasta / 'seguro--coordenador.json').read_bytes() == intacto
            assert historico_seguro.read_text() == invalido
        historico_seguro.unlink()
        alheia = revisoes / 'alheia--tarefa.json'
        fonte = pasta / 'fonte-protegida.json'
        fonte.write_text(json.dumps(dict(coordenador_sessao='alheio--coordenador')))
        for caso in ('json', 'lista', 'link', 'ligacao', 'fifo', 'diretorio'):
            if alheia.exists() or alheia.is_symlink():
                alheia.unlink()
            if caso == 'json':
                alheia.write_text('{')
            elif caso == 'lista':
                alheia.write_text('[]')
            elif caso == 'link':
                alheia.symlink_to(fonte)
            elif caso == 'ligacao':
                os.link(fonte, alheia)
            elif caso == 'fifo':
                os.mkfifo(alheia)
            else:
                alheia.mkdir()
            try:
                arquivar(fd, encerrado, pasta, original)
            except (OSError, ValueError):
                pass
            else:
                raise AssertionError('Pendência inválida aceita: ' + caso)
            assert (pasta / 'seguro--coordenador.json').read_bytes() == intacto
            assert not historico_seguro.exists()
            if caso == 'diretorio':
                alheia.rmdir()
            else:
                alheia.unlink()
        assert arquivar(fd, encerrado, pasta, original) == 0
        assert json.loads((pasta / 'seguro--coordenador.json').read_text()) == encerrado
        assert not list(pasta.rglob('.reg.*'))
        for provedor, modelo in (('claude', 'opus'), ('codex', 'gpt-6-astra'),
                                 ('agy', 'gemini-4-argon-high')):
            valido = dict(sessao='modelo--coordenador', projeto=str(pasta), provedor=provedor)
            for valor in (None, modelo, 'modelo-invalido'):
                dados = dict(valido, modelo=valor) if valor is not None else valido
                gravar(fd, 'modelo--coordenador.json', dados)
                esperado = valor == modelo or (valor is None and provedor != 'agy')
                try:
                    lido = ler_registro(fd, 'modelo--coordenador')
                except ValueError:
                    assert not esperado, (provedor, valor)
                else:
                    assert esperado and lido == dados, (provedor, valor)
    finally:
        os.close(fd)
print('ok    gravação, substituição, exclusividade e histórico em estado sintético')
PYTEST
if [[ -n "${JANGADA_ISOLADO:-}" ]]; then
  pulado_no_isolamento "fluxo do coordenador exige abertura fora do isolamento; sinalizadores preservados, pendente na suíte externa"
  exit 0
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux ausente; teste do coordenador ignorado"
  exit 0
fi
tmp="$(mktemp -d)"
erros_dos_pulados "$tmp"
falhas=0
conferir() {
  local nome="$1"; shift
  if "$@"; then printf 'ok    %s\n' "$nome"
  elif ! pulado_se_recusado "${tmp:-}" "$nome"; then printf 'FALHA %s\n' "$nome"; falhas=$((falhas + 1)); fi
}
path_chamador="$tmp/bin:$tmp/atalho com espaço; literal:$PATH"
path_servidor="$tmp/servidor-sem-clientes"
mkdir -p "$path_servidor" "$tmp/bin" "$tmp/home" "$tmp/config" "$tmp/state" "$tmp/projeto/sub" "$tmp/outro" "$tmp/codex"
# O caminho do soquete do tmux tem limite de cerca de 100 bytes: com um TMPDIR
# longo, ele fica numa pasta curta no /tmp.
sock="$(mktemp -d /tmp/jangada-sock.XXXXXX)"
estado="$tmp/state/jangada"
reg="$estado/coordenadores"

# Claude falso: grava os bytes recebidos sem interpretar nada.
cat >"$tmp/bin/claude" <<'EOF'
#!/usr/bin/env python3
import os, sys, tty
if os.path.isfile('.falhar-cliente'):
    print('falha sintética na partida do Claude', file=sys.stderr)
    sys.exit(42)
with open(os.environ['FALSO_DIR'] + '/claude.args', 'wb') as args:
    args.write(b'\0'.join(a.encode() for a in sys.argv[1:]) + b'\0')
tty.setraw(0)
caminho = os.environ['FALSO_DIR'] + '/claude.bytes'
open(caminho, 'wb').close()
open(os.environ['FALSO_DIR'] + '/claude.pronto', 'w').close()
with open(caminho, 'ab', buffering=0) as log:
    while True:
        dados = os.read(0, 4096)
        if not dados:
            break
        if dados == b'\x04':
            break
        log.write(dados)
EOF
# Codex falso: o app-server responde pelo falso-codex-hooks.py; a chamada
# principal grava os argumentos e espera.
cat >"$tmp/bin/codex" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
  [[ "$arg" == app-server ]] && exec python3 "$JANGADA_CORE_PATH/testes/falso-codex-hooks.py" "$@"
done
if [[ -f .falhar-cliente ]]; then
  echo 'falha sintética na partida do Codex' >&2
  exit 42
fi
printf '%s\0' "$@" >"$FALSO_DIR/codex.args"
exec python3 -c 'import os, tty; tty.setraw(0); os.read(0, 1)'
EOF
cat >"$tmp/bin/agy" <<'EOF'
#!/usr/bin/env python3
import json, os, sys, tty
from pathlib import Path
pasta = Path(os.environ['FALSO_DIR'])
if sys.argv[1:] == ['models']:
    print((pasta / 'argon.catalogo').read_text() if (pasta / 'argon.catalogo').exists() else 'gemini-4-argon-high')
    sys.exit(0)
if '-p' in sys.argv:
    assert sys.argv[sys.argv.index('-p') + 1] == '/usage'
    if (pasta / 'argon.uso').exists():
        print((pasta / 'argon.uso').read_text())
        sys.exit(0)
    cota = float((pasta / 'argon.cota').read_text()) if (pasta / 'argon.cota').exists() else 1
    print(json.dumps({'command': {'data': {'groups': [{'buckets': [
        {'id': 'gemini-argon-wtu-weekly', 'remaining_fraction': cota},
        {'id': 'gemini-wtu-weekly', 'remaining_fraction': 0}]}]}}}))
    sys.exit(0)
if Path('.falhar-cliente').exists():
    print('modelo indisponível na partida do agy', file=sys.stderr)
    sys.exit(42)
(pasta / 'agy.args').write_bytes(b'\0'.join(a.encode() for a in sys.argv[1:]) + b'\0')
tty.setraw(0)
os.read(0, 1)
EOF
tmux_real="$(command -v tmux)"
cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FALSO_DIR/tmux.chamadas"
exec "$TMUX_REAL" "$@"
EOF
for c in notify-send pkill hyprctl; do
  printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/$c"
done
cat >"$tmp/bin/hyprctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FALSO_DIR/foco.chamadas"
[[ "$1" != clients ]] || printf '[{"title":"projeto--coordenador","address":"0x1"}]\n'
EOF
cat >"$tmp/bin/jangada-terminal" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FALSO_DIR/foco.chamadas"
EOF
chmod +x "$tmp/bin/"*

rodar() {
  env -u JANGADA_SESSAO -u JANGADA_COORDENADOR -u JANGADA_ATUACAO_ID -u JANGADA_COORDENADOR_PROVEDOR -u TMUX -u WAYLAND_DISPLAY \
    -u HYPRLAND_INSTANCE_SIGNATURE -u DISPLAY \
    PATH="$path_chamador" HOME="$tmp/home" SHELL=/bin/sh TMUX_TMPDIR="$sock" FALSO_DIR="$tmp" \
    TMUX_REAL="$tmux_real" CODEX_HOME="$tmp/codex" JANGADA_CORE_PATH="$repo_jangada" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$tmp/state" "$@"
}
tm() { rodar tmux -L jangada "$@"; }
trap 'tm kill-server >/dev/null 2>&1; if [[ -n "${MANTER:-}" ]]; then echo "$tmp"; else rm -rf "$tmp"; fi; rm -rf "$sock"' EXIT
esperar() {
  local i
  for ((i = 0; i < 50; i++)); do "$@" && return 0; sleep 0.1; done
  return 1
}
mensagem_no_painel() {
  tm capture-pane -p -S - -t "=$1:" | grep -Fq "$2"
}
ambiente_do_painel() {
  local pid
  pid="$(tm display-message -p -t "=$1:" '#{pane_pid}')" || return 1
  python3 - "$pid" "$path_chamador" <<'PYTEST'
import sys
from pathlib import Path
ambiente = Path('/proc', sys.argv[1], 'environ').read_bytes().split(b'\0')
assert b'PATH=' + sys.argv[2].encode() in ambiente
assert not any(v.startswith(b'CREDENCIAL_TESTE_ALHEIA=') for v in ambiente)
PYTEST
}
campo() { jq -r "$1 // \"\" | tostring" "$reg/projeto--coordenador.json" 2>/dev/null; }
hook() { rodar env JANGADA_ATUACAO_ID="$(campo .atuacao_id)" "${@:3}" "$repo_jangada/bin/jangada-hook-claude" "$1" <<<"$2"; }

git init -q -b main "$tmp/projeto"
git -C "$tmp/projeto" -c user.name=t -c user.email=t@t commit -q --allow-empty -m inicio

# Abertura, a partir de uma subpasta: o coordenador fica na raiz do projeto.
# Quem chama é uma tarefa, com JANGADA_SESSAO no processo e no ambiente
# global do servidor: o coordenador não a herda.
# O servidor nasce sem clientes no PATH; cada processo novo usa o do chamador.
rodar env PATH="$path_servidor" "$tmux_real" -L jangada -f "$repo_jangada/agentes/tmux/agentes.conf" new-session -d -s base
conferir "o servidor nasce sem o caminho dos clientes falsos" \
  test "$(tm show-environment -g PATH)" = "PATH=$path_servidor"
opcao_global="$(tm show-options -gwv remain-on-exit)"
opcao_base="$(tm show-options -wv -t =base: remain-on-exit)"
tm set-environment -g JANGADA_SESSAO alheia--tarefa
saida="$(rodar env JANGADA_AUTOR_MODELO=haiku JANGADA_VALIDAR_MODELO=haiku CREDENCIAL_TESTE_ALHEIA=nao-repassar JANGADA_SESSAO=alheia--tarefa "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto/sub" 2>&1)"; rc=$?
conferir "a abertura cria a sessão PROJETO--coordenador" [ "$rc:$saida" = 0:projeto--coordenador ]
if [[ "$rc:$saida" != 0:projeto--coordenador ]]; then
  printf 'primeira abertura: código %s; saída: %s\n' "$rc" "$saida" >&2
  exit 1
fi
conferir "a sessão existe no servidor do teste" tm has-session -t =projeto--coordenador
conferir "o socket é o do teste" test -S "$sock/tmux-$(id -u)/jangada"
conferir "a pasta dos registros tem modo 700" [ "$(stat -c %a "$reg")" = 700 ]
conferir "o registro nasce com projeto, provedor e estado iniciado" \
  [ "$(campo '[.projeto, .provedor, .estado] | join(" ")')" = "$tmp/projeto claude iniciado" ]
atuacao_original="$(campo .atuacao_id)"
desde_original="$(campo .desde)"
conferir "a criação dá identidade segura e ciclo aberto" \
  jq -e '.ciclo == "aberta" and (.atuacao_id | test("^[A-Za-z0-9_-]{16,128}$"))' "$reg/projeto--coordenador.json"
conferir "o processo recebe a identidade para os hooks" \
  test "$(tm show-environment -t =projeto--coordenador JANGADA_ATUACAO_ID)" = "JANGADA_ATUACAO_ID=$atuacao_original"
antes="$(cat "$reg/projeto--coordenador.json")"
painel="$(tm display-message -p -t =projeto--coordenador: '#{pane_pid}')"
saida="$(rodar "$repo_jangada/bin/jangada-coordenador" --finalizar projeto--coordenador 2>&1)"; rc=$?
conferir "finalizar vivo recusa com orientação de estado, diário e saída" \
  bash -c '[[ "$1" = 2 && "$2" == *"estado e o diário"* && "$2" == *"saia voluntariamente"* ]]' _ "$rc" "$saida"
conferir "finalizar vivo não muda registro nem processo" \
  test "$(cat "$reg/projeto--coordenador.json"):$(tm display-message -p -t =projeto--coordenador: '#{pane_pid}')" = "$antes:$painel"
conferir "a sessão recebe JANGADA_COORDENADOR" \
  [ "$(tm show-environment -t =projeto--coordenador JANGADA_COORDENADOR 2>/dev/null)" = JANGADA_COORDENADOR=projeto--coordenador ]
conferir "a sessão não recebe JANGADA_SESSAO" \
  [ "$( (tm show-environment -t =projeto--coordenador; tm show-environment -g) | grep -c '^JANGADA_SESSAO=')" = 0 ]
conferir "o processo da sessão não recebe JANGADA_SESSAO" \
  bash -c '! tr "\\0" "\\n" <"/proc/$1/environ" | grep -q "^JANGADA_SESSAO="' _ \
  "$(tm display-message -p -t =projeto--coordenador: '#{pane_pid}')"
conferir "a retenção de falhas não altera a opção global" \
  test "$(tm show-options -gwv remain-on-exit)" = "$opcao_global"
conferir "a retenção de falhas não altera outra sessão" \
  test "$(tm show-options -wv -t =base: remain-on-exit)" = "$opcao_base"
conferir "só a janela nova retém falhas" \
  test "$(tm show-options -wv -t =projeto--coordenador: remain-on-exit)" = failed
tm kill-session -t =base
conferir "a sessão roda na raiz do projeto" \
  [ "$(tm display-message -p -t =projeto--coordenador: '#{pane_start_path}')" = "$tmp/projeto" ]
conferir "o Claude falso abre na sessão" esperar test -f "$tmp/claude.pronto"
conferir "Claude recebe o PATH literal do chamador sem outras credenciais" \
  ambiente_do_painel projeto--coordenador
conferir "a abertura Claude não muda o PATH global do servidor" \
  test "$(tm show-environment -g PATH)" = "PATH=$path_servidor"

args_claude="$(tr '\0' '\n' <"$tmp/claude.args")"
conferir "Claude recebe opus apesar do modelo econômico da tarefa" \
  [ "$(head -n 2 <<<"$args_claude" | paste -sd ' ')" = '--model opus' ]
prompt_inicial="$(tail -n 1 <<<"$args_claude")"
conferir "o texto inicial é um único argumento após o modelo" \
  [ "$(tr -cd '\0' <"$tmp/claude.args" | wc -c)" = 3 ]
for trecho in 'coordenador deste projeto' '.jangada/regras-do-dono.md' '.jangada/estado.md' \
  '.jangada/armadilhas.md' 'diário' '.jangada/coordenacao.md' 'sessões reais' 'ramos' 'worktrees' \
  'antes de abrir tarefas' 'permissões de tarefa que permanecem válidas' 'não autorizam inventar decisões'; do
  conferir "o argumento inicial orienta: $trecho" grep -Fq "$trecho" <<<"$prompt_inicial"
done
conferir "a abertura não usa send-keys nem buffers" \
  bash -c '! grep -Eq "send-keys|load-buffer|paste-buffer" "$1"' _ "$tmp/tmux.chamadas"

# Segundo pedido para o mesmo projeto: avisa e não abre outra.
antes="$(cat "$reg/projeto--coordenador.json")"
: >"$tmp/foco.chamadas"
saida="$(rodar env PATH="$tmp/outro-path:$path_chamador" HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" 2>&1)"; rc=$?
conferir "o segundo pedido sai com 0 e avisa" [ "$rc" = 0 ]
conferir "o aviso diz que já está aberto" grep -q "já está aberto" <<<"$saida"
conferir "mesmo provedor não altera o PATH do processo existente" \
  ambiente_do_painel projeto--coordenador
conferir "mesmo provedor mantém o registro" test "$(cat "$reg/projeto--coordenador.json")" = "$antes"
conferir "mesmo provedor foca a sessão correta" grep -q 'dispatch.*0x1' "$tmp/foco.chamadas"
conferir "continua uma sessão só" [ "$(tm list-sessions -F '#S' | grep -c coordenador)" = 1 ]

# Outro provedor preserva o registro, a sessão e o ambiente, sem focar.
: >"$tmp/foco.chamadas"
antes="$(cat "$reg/projeto--coordenador.json")"
painel="$(tm display-message -p -t =projeto--coordenador: '#{pane_id} #{pane_pid}')"
tm set-environment -g JANGADA_SESSAO marcador
tm set-environment -g CLAUDE_CODE_TESTE preservar
: >"$tmp/tmux.chamadas"
saida="$(rodar env HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" --provedor codex 2>&1)"; rc=$?
conferir "provedor divergente sai com 2" [ "$rc" = 2 ]
conferir "a recusa informa o provedor vivo e a saída voluntária" \
  grep -q 'aberto com claude.*encerrar voluntariamente.*codex' <<<"$saida"
conferir "a divergência não consulta nem altera o foco" test ! -s "$tmp/foco.chamadas"
conferir "a divergência preserva o registro" [ "$(cat "$reg/projeto--coordenador.json")" = "$antes" ]
conferir "a divergência preserva o processo" \
  [ "$(tm display-message -p -t =projeto--coordenador: '#{pane_id} #{pane_pid}')" = "$painel" ]
conferir "a divergência não foca, cria ou envia entrada" \
  bash -c '! grep -Eq "select-|attach|new-session|send-keys|buffer|set-environment" "$1"' _ "$tmp/tmux.chamadas"
conferir "a divergência não limpa o ambiente de outra sessão" \
  [ "$(tm show-environment -g CLAUDE_CODE_TESTE)" = CLAUDE_CODE_TESTE=preservar ]
tm set-environment -g -u JANGADA_SESSAO
tm set-environment -g -u CLAUDE_CODE_TESTE

# Registro inválido nunca é substituído enquanto o tmux está vivo.
cp "$reg/projeto--coordenador.json" "$tmp/registro.valido"
for caso in ausente link json lista multiplos sem-projeto tipo-projeto relativo sem-provedor desconhecido tipo-provedor sessao; do
  rm -f "$reg/projeto--coordenador.json"
  case "$caso" in
    ausente) ;;
    link) ln -s "$tmp/registro.valido" "$reg/projeto--coordenador.json" ;;
    json) printf '{' >"$reg/projeto--coordenador.json" ;;
    lista) printf '[]' >"$reg/projeto--coordenador.json" ;;
    multiplos) cat "$tmp/registro.valido" "$tmp/registro.valido" >"$reg/projeto--coordenador.json" ;;
    *)
      case "$caso" in
        sem-projeto) filtro='del(.projeto)' ;;
        tipo-projeto) filtro='.projeto = 12' ;;
        relativo) filtro='.projeto = "projeto"' ;;
        sem-provedor) filtro='del(.provedor)' ;;
        desconhecido) filtro='.provedor = "agy"' ;;
        tipo-provedor) filtro='.provedor = ["claude"]' ;;
        sessao) filtro='.sessao = "outra"' ;;
      esac
      jq "$filtro" "$tmp/registro.valido" >"$reg/projeto--coordenador.json" ;;
  esac
  antes="$(cat "$reg/projeto--coordenador.json" 2>/dev/null)"
  : >"$tmp/tmux.chamadas"
  : >"$tmp/foco.chamadas"
  saida="$(rodar env HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" 2>&1)"; rc=$?
  conferir "registro $caso: recusa por inconsistência" \
    test "$rc" = 2
  conferir "registro $caso: explica a preservação" grep -q 'registro inconsistente.*sessão preservada' <<<"$saida"
  conferir "registro $caso: não foca" test ! -s "$tmp/foco.chamadas"
  conferir "registro $caso: preserva dados" [ "$(cat "$reg/projeto--coordenador.json" 2>/dev/null)" = "$antes" ]
  conferir "registro $caso: sem foco, criação ou entrada" \
    bash -c '! grep -Eq "select-|attach|new-session|send-keys|buffer|set-environment" "$1"' _ "$tmp/tmux.chamadas"
  conferir "registro $caso: mantém o processo vivo" \
    [ "$(tm display-message -p -t =projeto--coordenador: '#{pane_id} #{pane_pid}')" = "$painel" ]
  if [[ "$caso" = ausente ]]; then conferir "não recria registro ausente" test ! -e "$reg/projeto--coordenador.json"; fi
  if [[ "$caso" = link ]]; then conferir "não substitui registro com link" test -L "$reg/projeto--coordenador.json"; fi
done
rm -f "$reg/projeto--coordenador.json"
cp "$tmp/registro.valido" "$reg/projeto--coordenador.json"

# Outra pasta com o mesmo nome: recusa, sem focar nem mexer no coordenador
# que existe.
git init -q -b main "$tmp/a/projeto"
antes="$(cat "$reg/projeto--coordenador.json")"
: >"$tmp/foco.chamadas"
saida="$(rodar env HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/a/projeto" 2>&1)"; rc=$?
conferir "pasta de mesmo nome sai com 2" [ "$rc" = 2 ]
conferir "a recusa nomeia a pasta do coordenador existente" grep -q "coordenador de $tmp/projeto, não de $tmp/a/projeto" <<<"$saida"
conferir "a recusa não foca a janela" test ! -s "$tmp/foco.chamadas"
conferir "o registro do outro fica intacto" [ "$(cat "$reg/projeto--coordenador.json")" = "$antes" ]
conferir "nenhuma sessão nova" [ "$(tm list-sessions -F '#S' | grep -c coordenador)" = 1 ]

# PATH fechado sem flock: exercita a trava por pasta sem simular a função.
sem_flock="$tmp/sem-flock"
mkdir -p "$sem_flock" "$tmp/sem-cliente"
for c in bash dirname sed realpath git basename iconv tr jq mkdir chmod mktemp \
  date mv rm rmdir stat sleep head python3 timeout grep env; do
  ln -s "$(command -v "$c")" "$sem_flock/$c"
done
for c in tmux claude codex agy hyprctl jangada-terminal; do
  ln -s "$tmp/bin/$c" "$sem_flock/$c"
done
conferir "o PATH alternativo não oferece flock" \
  rodar env PATH="$sem_flock" bash -c '! command -v flock'
cp "$reg/projeto--coordenador.json" "$tmp/antes-sem-flock"
for caso in provedor homonimo registro; do
  alvo="$tmp/projeto"; provedor=codex
  case "$caso" in
    homonimo) alvo="$tmp/a/projeto"; provedor=claude ;;
    registro) printf '{}' >"$reg/projeto--coordenador.json"; provedor=claude ;;
  esac
  antes="$(cat "$reg/projeto--coordenador.json")"
  : >"$tmp/foco.chamadas"
  : >"$tmp/tmux.chamadas"
  for tentativa in 1 2; do
    saida="$(rodar env PATH="$sem_flock" HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste \
      "$repo_jangada/bin/jangada-coordenador" --projeto "$alvo" --provedor "$provedor" 2>&1)"; rc=$?
    conferir "sem flock, $caso: recusa $tentativa sai com 2" test "$rc" = 2
    conferir "sem flock, $caso: recusa $tentativa libera a trava" test ! -d "$reg/.trava.d"
  done
  conferir "sem flock, $caso: preserva registro" test "$(cat "$reg/projeto--coordenador.json")" = "$antes"
  conferir "sem flock, $caso: preserva foco" test ! -s "$tmp/foco.chamadas"
  conferir "sem flock, $caso: não cria sessão nem envia entrada" \
    bash -c '! grep -Eq "new-session|send-keys|buffer|set-environment" "$1"' _ "$tmp/tmux.chamadas"
  cp "$tmp/antes-sem-flock" "$reg/projeto--coordenador.json"
done

# Cliente ausente tem um único diagnóstico e preserva o registro antigo.
rm "$sem_flock/claude"
printf '{"estado":"encerrado"}' >"$reg/sem-cliente--coordenador.json"
for modo in sem-flock com-flock; do
  if [[ "$modo" = com-flock ]]; then ln -s "$(command -v flock)" "$sem_flock/flock"; fi
  antes="$(cat "$reg/sem-cliente--coordenador.json")"
  : >"$tmp/foco.chamadas"
  saida="$(rodar env PATH="$sem_flock" HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste \
    "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/sem-cliente" 2>&1)"; rc=$?
  conferir "$modo, cliente ausente: sai com 1" test "$rc" = 1
  conferir "$modo, cliente ausente: diagnóstico único" \
    test "$saida" = 'jangada-coordenador: claude não instalado; nenhuma sessão criada'
  conferir "$modo, cliente ausente: preserva registro e foco" \
    test "$(cat "$reg/sem-cliente--coordenador.json"):$(cat "$tmp/foco.chamadas")" = "$antes:"
  conferir "$modo, cliente ausente: não deixa trava presa" test ! -d "$reg/.trava.d"
done
rm "$sem_flock/flock"
ln -s "$tmp/bin/claude" "$sem_flock/claude"
antes="$(cat "$reg/sem-cliente--coordenador.json")"
rodar env PATH="$sem_flock" "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/sem-cliente" >"$tmp/saida" 2>&1
conferir "registro inválido sem sessão também é preservado" \
  test "$?:$(cat "$reg/sem-cliente--coordenador.json")" = "2:$antes"
jq -n --arg p "$tmp/sem-cliente" \
  '{sessao:"sem-cliente--coordenador",projeto:$p,provedor:"claude",estado:"encerrado"}' \
  >"$reg/sem-cliente--coordenador.json"
saida="$(rodar env PATH="$sem_flock" "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/sem-cliente" 2>&1)"; rc=$?
conferir "sem flock, o pedido seguinte cria a sessão" test "$rc:$saida" = '0:sem-cliente--coordenador'
conferir "sem flock, a criação também libera a trava" test ! -d "$reg/.trava.d"
rodar env PATH="$sem_flock" "$repo_jangada/bin/jangada-coordenador" --fim sem-cliente--coordenador >"$tmp/saida" 2>&1
conferir "sem flock, --fim continua encerrando" test "$?" = 0
conferir "sem flock, --fim também libera a trava" test ! -d "$reg/.trava.d"
rm "$reg/sem-cliente--coordenador.json"

# Codex: os hooks do jangada vão na chamada, com a aprovação no estado.
saida="$(rodar env JANGADA_AUTOR_MODELO=gpt-6.1-sol JANGADA_VALIDAR_MODELO=gpt-6.1-sol CREDENCIAL_TESTE_ALHEIA=nao-repassar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/outro" --provedor codex 2>&1)"
conferir "a abertura com Codex cria a sessão" [ "$saida" = outro--coordenador ]
conferir "o Codex abre com os hooks do coordenador" esperar test -s "$tmp/codex.args"
conferir "Codex recebe o PATH literal do chamador sem outras credenciais" \
  ambiente_do_painel outro--coordenador
conferir "a abertura Codex não muda o PATH global do servidor" \
  test "$(tm show-environment -g PATH)" = "PATH=$path_servidor"
args_codex="$(tr '\0' '\n' <"$tmp/codex.args" 2>/dev/null)"
conferir "Codex recebe o modelo forte e o mesmo texto inicial" \
  python3 - "$tmp/codex.args" "$prompt_inicial" <<'PYTEST'
import sys
from pathlib import Path
args = Path(sys.argv[1]).read_bytes().decode().split('\0')[:-1]
assert args[-3:] == ['--model', 'gpt-6-astra', sys.argv[2]], args
PYTEST
conferir "o Stop do Codex chama o jangada-hook-codex" grep -q "^hooks.Stop=.*jangada-hook-codex' concluido" <<<"$args_codex"
conferir "a aprovação dos hooks vai na chamada" grep -q "^hooks.state=" <<<"$args_codex"
conferir "a aprovação fica na pasta dos coordenadores" test -f "$reg/codex-hooks-confianca.json"
conferir "o registro do Codex diz o provedor" [ "$(jq -r .provedor "$reg/outro--coordenador.json")" = codex ]
tm kill-session -t =outro--coordenador
rm -f "$reg/outro--coordenador.json"

# Falha imediata preserva a mensagem num painel morto, só na janela nova.
for provedor in claude codex agy; do
  mkdir -p "$tmp/falha-$provedor"
  touch "$tmp/falha-$provedor/.falhar-cliente"
  sessao_falha="falha-$provedor--coordenador"
  saida="$(rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/falha-$provedor" --provedor "$provedor" 2>&1)"; rc=$?
  conferir "$provedor com falha imediata: abertura mantém o contrato" test "$rc:$saida" = "0:$sessao_falha"
  conferir "$provedor com falha imediata: tmux conserva o painel" \
    esperar bash -c '[[ "$("$@" display-message -p -t "=$0:" "#{pane_dead} #{pane_dead_status}")" = "1 42" ]]' \
    "$sessao_falha" env TMUX_TMPDIR="$sock" tmux -L jangada
  conferir "$provedor com falha imediata: mensagem continua visível" \
    esperar mensagem_no_painel "$sessao_falha" 'na partida do'
  conferir "$provedor com falha imediata: opção global intacta" \
    test "$(tm show-options -gwv remain-on-exit)" = "$opcao_global"
  antes="$(cat "$reg/$sessao_falha.json")"
  if [[ "$provedor" = claude ]]; then sucessor=codex; else sucessor=claude; fi
  saida="$(rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/falha-$provedor" --provedor "$sucessor" 2>&1)"; rc=$?
  conferir "$provedor com painel morto: não abre outro provedor" test "$rc" = 2
  conferir "$provedor com painel morto: preserva registro" test "$(cat "$reg/$sessao_falha.json")" = "$antes"
  rodar "$repo_jangada/bin/jangada-coordenador" --fim "$sessao_falha" >/dev/null 2>&1
  conferir "$provedor com painel morto: --fim preserva sua semântica" \
    test "$?:$(jq -r .estado "$reg/$sessao_falha.json")" = '0:encerrado'
  rm "$reg/$sessao_falha.json"
done

# Hooks: sem JANGADA_COORDENADOR nada muda; com ele, estado e última linha.
antes="$(cat "$reg/projeto--coordenador.json")"
hook trabalhando '{"prompt":"sem variável"}'
conferir "sem JANGADA_COORDENADOR o hook não grava" [ "$(cat "$reg/projeto--coordenador.json")" = "$antes" ]
hook trabalhando '{"prompt":"sem variável"}' JANGADA_COORDENADOR=projeto--coordenador JANGADA_ISOLADO=1
conferir "isolado o hook não grava" [ "$(cat "$reg/projeto--coordenador.json")" = "$antes" ]
hook aguardando '{"message":"Claude precisa\u200b de permissão\u001b[31m\u202e para\u0007 Bash","notification_type":"permission_prompt"}' \
  JANGADA_COORDENADOR=projeto--coordenador
conferir "o hook grava aguardando" [ "$(campo .estado)" = aguardando ]
conferir "a última linha sai sem ANSI, controles nem invisíveis" \
  [ "$(campo .ultima_linha)" = "Claude precisa  de permissão  para  Bash" ]
conferir "o hook grava atualizado" [ -n "$(campo .atualizado)" ]
longa="$(printf 'x%.0s' {1..300})"
hook concluido "{\"last_assistant_message\":\"$longa\"}" JANGADA_COORDENADOR=projeto--coordenador
conferir "a última linha não passa de 200 caracteres" [ "$(campo '.ultima_linha | length')" -le 200 ]
hook aguardando '{"message":"Claude is waiting for your input","notification_type":"idle_prompt"}' \
  JANGADA_COORDENADOR=projeto--coordenador
conferir "o lembrete de inatividade vira concluido sem trocar a linha" \
  [ "$(campo .estado)" = concluido -a "$(campo '.ultima_linha | startswith("xxx")')" = true ]
hook inicio '{"source":"clear"}' JANGADA_COORDENADOR=projeto--coordenador
conferir "o /clear não muda o estado" [ "$(campo .estado)" = concluido ]
printf '{"estado":"x"}' >"$tmp/outro.json"
ln -s "$tmp/outro.json" "$reg/link--coordenador.json"
hook trabalhando '{"prompt":"p"}' JANGADA_COORDENADOR=link--coordenador
conferir "o hook não segue link no registro" [ "$(cat "$tmp/outro.json")" = '{"estado":"x"}' ]
rm -f "$reg/link--coordenador.json"
printf '{"cwd":"/x"}' | rodar env JANGADA_COORDENADOR=projeto--coordenador \
  JANGADA_ATUACAO_ID="$atuacao_original" \
  "$repo_jangada/bin/jangada-hook-codex" aguardando
conferir "o hook do Codex também grava" [ "$(campo .estado)" = aguardando ]
hook concluido '{"last_assistant_message":"pronto"}' JANGADA_COORDENADOR=projeto--coordenador
for provedor_hook in claude codex agy; do
  for evento in concluido fim; do
    printf '{"last_assistant_message":"fim de resposta","reason":"prompt_input_exit"}' \
      | rodar env JANGADA_COORDENADOR=projeto--coordenador JANGADA_ATUACAO_ID="$atuacao_original" \
        "$repo_jangada/bin/jangada-hook-$provedor_hook" "$evento"
    conferir "$provedor_hook $evento mantém ciclo, identidade e data original" \
      test "$(campo '[.ciclo,.atuacao_id,.desde,.encerrado // ""] | join(" ")')" = "aberta $atuacao_original $desde_original "
  done
done
hook concluido '{"last_assistant_message":"pronto"}' JANGADA_COORDENADOR=projeto--coordenador

antes_outro_provedor="$(cat "$reg/projeto--coordenador.json")"
for evento in trabalhando concluido; do
  printf '{"fullyIdle":true,"prompt":"evento alheio"}' \
    | rodar env JANGADA_COORDENADOR=projeto--coordenador JANGADA_ATUACAO_ID="$atuacao_original" \
      JANGADA_COORDENADOR_PROVEDOR=claude "$repo_jangada/bin/jangada-hook-agy" "$evento"
  conferir "agy $evento não altera registro Claude com identidade correta" \
    test "$(cat "$reg/projeto--coordenador.json")" = "$antes_outro_provedor"
done

# Consulta com uma tarefa ligada ao coordenador, viva no servidor do teste.
mkdir -p "$estado/revisoes"
printf '{"sessao":"projeto--tarefa","coordenador_sessao":"projeto--coordenador"}' \
  >"$estado/revisoes/projeto--tarefa.json"
printf '{"sessao":"projeto--solta","coordenador":"dono"}' >"$estado/revisoes/projeto--solta.json"
tm new-session -d -s projeto--tarefa
consulta="$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json)"
conferir "a consulta lista o coordenador com a tarefa" [ "$(jq -c '.coordenadores' <<<"$consulta")" = \
  "$(jq -cn --arg p "$tmp/projeto" --arg a "$(campo .atualizado)" --arg id "$atuacao_original" '[{sessao:"projeto--coordenador", projeto:$p,
     provedor:"claude", estado:"concluido", ultima_linha:"pronto", atualizado:$a, viva:true,
     ciclo:"aberta", atuacao_id:$id, retomavel:false,
     tarefas:[{sessao:"projeto--tarefa", viva:true}]}]')" ]
conferir "a consulta é a versão 1" [ "$(jq .versao <<<"$consulta")" = 1 ]
printf '{"sessao":"vazio--coordenador"}' >"$reg/vazio--coordenador.json"
conferir "campo ausente sai nulo, nunca \"None\"" [ "$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json \
  | jq -c '.coordenadores[] | select(.sessao == "vazio--coordenador") | [.projeto, .estado, .ultima_linha, .atualizado, .viva]')" \
  = '[null,null,null,null,false]' ]
rm -f "$reg/vazio--coordenador.json"
ln -s "$tmp/outro.json" "$reg/link--coordenador.json"
rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json >"$tmp/saida" 2>/dev/null
conferir "registro de coordenador com link faz a consulta sair com 1" [ "$?" = 1 ]
conferir "a consulta recusada não escreve nada no stdout" [ ! -s "$tmp/saida" ]
rm -f "$reg/link--coordenador.json"

# O envio de mensagem saiu: --mensagem é opção desconhecida e nada chega à
# sessão.
printf 'texto da Central\n' >"$tmp/msg"
: >"$tmp/claude.bytes"
rodar "$repo_jangada/bin/jangada-coordenador" --mensagem projeto--coordenador --arquivo "$tmp/msg" >"$tmp/saida" 2>&1
conferir "--mensagem sai com 2" [ "$?" = 2 ]
sleep 0.2
conferir "--mensagem não deixa buffer no tmux" [ -z "$(tm list-buffers 2>/dev/null)" ]
conferir "--mensagem não cola o texto no painel" \
  bash -c '! grep -q "texto da Central" <<<"$1"' _ "$(tm capture-pane -p -t =projeto--coordenador: 2>/dev/null)"
conferir "nada chega ao Claude" [ ! -s "$tmp/claude.bytes" ]

# Fim: a sessão some, o registro fica marcado e a tarefa continua.
rodar "$repo_jangada/bin/jangada-coordenador" --fim projeto--coordenador >/dev/null 2>&1
conferir "o --fim sai com 0" [ "$?" = 0 ]
conferir "o --fim encerra a sessão" esperar bash -c '! "$@" has-session -t =projeto--coordenador 2>/dev/null' _ \
  env TMUX_TMPDIR="$sock" tmux -L jangada
conferir "o registro fica encerrado, com data" [ "$(campo .estado)" = encerrado -a -n "$(campo .encerrado)" ]
conferir "a tarefa e a cópia dela continuam" tm has-session -t =projeto--tarefa
conferir "a cópia da tarefa continua" test -f "$estado/revisoes/projeto--tarefa.json"
hook trabalhando '{"prompt":"tarde"}' JANGADA_COORDENADOR=projeto--coordenador
conferir "hook depois do --fim não reabre o registro" [ "$(campo .estado)" = encerrado ]
conferir "a consulta mostra o coordenador encerrado e morto" [ "$(rodar "$repo_jangada/bin/jangada-agentes" \
  --coordenadores-json | jq -c '.coordenadores[0] | [.estado, .viva]')" = '["encerrado",false]' ]
conferir "--fim também encerra explicitamente o ciclo e arquiva" \
  jq -e --arg id "$atuacao_original" '.registro.atuacao_id == $id and .registro.ciclo == "encerrada" and (.pendencias | length) == 1' \
    "$reg/historico/$atuacao_original.json"
historico_original="$(cat "$reg/historico/$atuacao_original.json")"

# Saída voluntária do cliente falso, com registro antigo ainda no disco.
rm -f "$tmp/claude.pronto"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" >/dev/null 2>&1
atuacao_atual="$(campo .atuacao_id)"
conferir "após encerramento nasce outra identidade com histórico preservado" \
  test "$atuacao_atual:$(cat "$reg/historico/$atuacao_original.json")" != "$atuacao_original:$historico_original"
conferir "o arquivo histórico anterior permanece idêntico" \
  test "$(cat "$reg/historico/$atuacao_original.json")" = "$historico_original"
desde_atual="$(campo .desde)"
conferir "o cliente anterior está pronto para sair" esperar test -f "$tmp/claude.pronto"
tm send-keys -t =projeto--coordenador: C-d
conferir "a saída voluntária termina a sessão anterior" esperar bash -c '! "$@" has-session -t =projeto--coordenador 2>/dev/null' _ \
  env TMUX_TMPDIR="$sock" tmux -L jangada
conferir "registro antigo sozinho não torna a sessão viva" test -f "$reg/projeto--coordenador.json"
consulta="$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json)"
conferir "saída voluntária mantém atuação aberta e retomável" \
  jq -e --arg id "$atuacao_atual" '.coordenadores[] | select(.sessao == "projeto--coordenador") | .ciclo == "aberta" and .atuacao_id == $id and .retomavel and (.viva | not) and (.tarefas | length) == 1' <<<"$consulta"
rm -f "$tmp/codex.args"
: >"$tmp/tmux.chamadas"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" --provedor codex >"$tmp/concorrente1" 2>&1 &
pid1=$!
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" --provedor codex >"$tmp/concorrente2" 2>&1 &
pid2=$!
wait "$pid1"; rc1=$?
wait "$pid2"; rc2=$?
conferir "pedidos simultâneos compatíveis passam" test "$rc1:$rc2" = 0:0
conferir "a trava permite uma única criação" [ "$(grep -c 'new-session' "$tmp/tmux.chamadas")" = 1 ]
conferir "a passagem cria o processo Codex" esperar test -s "$tmp/codex.args"
conferir "o sucessor mantém a raiz e atualiza o provedor" \
  [ "$(campo '[.projeto, .provedor, .estado] | join(" ")')" = "$tmp/projeto codex iniciado" ]
conferir "a troca voluntária retoma identidade, data e tarefa protegida" \
  test "$(campo '[.atuacao_id,.desde] | join(" ")'):$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json | jq -r '.coordenadores[] | select(.sessao == "projeto--coordenador") | .tarefas[0].sessao')" = "$atuacao_atual $desde_atual:projeto--tarefa"
conferir "a sessão sucessora nasce na pasta do projeto" \
  [ "$(tm display-message -p -t =projeto--coordenador: '#{pane_start_path}')" = "$tmp/projeto" ]
: >"$tmp/foco.chamadas"
antes="$(cat "$reg/projeto--coordenador.json")"
saida="$(rodar env HYPRLAND_INSTANCE_SIGNATURE=teste WAYLAND_DISPLAY=teste "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" --provedor claude 2>&1)"; rc=$?
conferir "Codex vivo também recusa Claude" test "$rc" = 2
conferir "a recusa identifica Codex e a saída voluntária" grep -q 'aberto com codex.*encerrar voluntariamente.*claude' <<<"$saida"
conferir "a recusa inversa preserva o registro e o foco" \
  test "$(cat "$reg/projeto--coordenador.json"):$(cat "$tmp/foco.chamadas")" = "$antes:"
tm send-keys -t =projeto--coordenador: C-d
esperar bash -c '! "$@" has-session -t =projeto--coordenador 2>/dev/null' _ env TMUX_TMPDIR="$sock" tmux -L jangada
rm -f "$tmp/claude.pronto"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" >/dev/null 2>&1
conferir "a passagem de volta abre Claude" esperar test -f "$tmp/claude.pronto"
conferir "a passagem de volta registra Claude" test "$(campo .provedor)" = claude

# Provedores divergentes disputando a criação: um só ganha sob a trava.
mkdir -p "$tmp/disputa"
: >"$tmp/tmux.chamadas"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/disputa" --provedor claude >"$tmp/disputa1" 2>&1 &
pid1=$!
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/disputa" --provedor codex >"$tmp/disputa2" 2>&1 &
pid2=$!
wait "$pid1"; rc1=$?
wait "$pid2"; rc2=$?
conferir "concorrência divergente admite somente um provedor" \
  bash -c '[[ "$1:$2" = 0:2 || "$1:$2" = 2:0 ]]' _ "$rc1" "$rc2"
conferir "concorrência divergente cria uma única sessão" [ "$(grep -c 'new-session' "$tmp/tmux.chamadas")" = 1 ]
conferir "concorrência divergente informa a saída voluntária" \
  grep -q 'encerrar voluntariamente' "$tmp/disputa1" "$tmp/disputa2"
if ((rc1 == 0)); then vencedor=claude; else vencedor=codex; fi
conferir "o registro mantém o provedor vencedor" \
  test "$(jq -r .provedor "$reg/disputa--coordenador.json")" = "$vencedor"
tm kill-session -t =disputa--coordenador

# --fim espera a trava da abertura antes de fechar a sessão.
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" >/dev/null 2>&1
esperar tm has-session -t =projeto--coordenador
flock "$reg" sleep 1 &
segura=$!
sleep 0.2
rodar "$repo_jangada/bin/jangada-coordenador" --fim projeto--coordenador >/dev/null 2>&1 &
fim_pid=$!
sleep 0.4
conferir "com a trava ocupada o --fim não fecha a sessão" tm has-session -t =projeto--coordenador
wait "$segura"; wait "$fim_pid"
conferir "solta a trava, o --fim encerra" [ "$?" = 0 -a "$(campo .estado)" = encerrado ]

# --projeto junto com --fim: sessão e registro concordam no fim.
coerente() {
  local estado_viva
  estado_viva="$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json \
    | jq -c '.coordenadores[] | select(.sessao == "projeto--coordenador") | [.estado == "encerrado", .viva]')"
  if tm has-session -t =projeto--coordenador 2>/dev/null; then
    [ "$estado_viva" = '[false,true]' ]
  else
    [ "$estado_viva" = '[true,false]' ]
  fi
}
incoerentes=0
for _ in 1 2 3 4 5; do
  rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" >/dev/null 2>&1
  rodar "$repo_jangada/bin/jangada-coordenador" --fim projeto--coordenador >/dev/null 2>&1 &
  rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" >/dev/null 2>&1 &
  wait
  coerente || incoerentes=$((incoerentes + 1))
done
conferir "--projeto junto com --fim nunca deixa sessão viva com registro encerrado" [ "$incoerentes" = 0 ]

# Persistência real, com clientes sintéticos e o servidor privado deste teste.
mkdir -p "$tmp/persistencia/.jangada"
printf 'decisão salva; $(touch NUNCA_EXECUTAR)\n' >"$tmp/persistencia/.jangada/estado.md"
cp "$tmp/persistencia/.jangada/estado.md" "$tmp/estado.salvo"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" >/dev/null 2>&1
persistente="$reg/persistencia--coordenador.json"
jq '.decisoes=["continuar"] | .autorizacoes=["testar"]' "$persistente" >"$tmp/novo"
mv "$tmp/novo" "$persistente"
id_persistente="$(jq -r .atuacao_id "$persistente")"
desde_persistente="$(jq -r .desde "$persistente")"
printf '{"sessao":"persistencia--pendente","coordenador_sessao":"persistencia--coordenador","estado":"concluido"}' \
  >"$estado/revisoes/persistencia--pendente.json"
for modo_trava in flock fallback; do
  if [[ "$modo_trava" = fallback ]]; then caminho_teste="$sem_flock"; else caminho_teste="$path_chamador"; fi
  tm kill-session -t =persistencia--coordenador
  conferir "$modo_trava: interrupção não encerra a atuação" \
    jq -e --arg id "$id_persistente" '.ciclo == "aberta" and .atuacao_id == $id and (has("encerrado") | not)' "$persistente"
  for provedor_retomada in agy codex claude; do
    rodar env PATH="$caminho_teste" "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" --provedor "$provedor_retomada" >"$tmp/saida" 2>&1
    conferir "$modo_trava, $provedor_retomada: retoma identidade, decisões e autorizações" \
      jq -e --arg id "$id_persistente" --arg desde "$desde_persistente" --arg p "$provedor_retomada" \
        '.atuacao_id == $id and .desde == $desde and .decisoes == ["continuar"] and .autorizacoes == ["testar"] and .provedor == $p' "$persistente"
    tm kill-session -t =persistencia--coordenador
  done
  rodar env PATH="$caminho_teste" "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" --provedor codex >"$tmp/saida" 2>&1
done
tm kill-session -t =persistencia--coordenador
rodar "$repo_jangada/bin/jangada-coordenador" --finalizar persistencia--coordenador >"$tmp/finalizacao" 2>&1
conferir "finaliza sem sessão e informa a pendência preservada" \
  bash -c '[[ "$1" = 0 ]] && grep -q "pendências preservadas: 1" "$2"' _ "$?" "$tmp/finalizacao"
conferir "checkpoint conserva o registro e só referencia as pendências" \
  python3 - "$persistente" "$reg/historico/$id_persistente.json" <<'PYTEST'
import json, sys
from pathlib import Path
registro, historico = [json.loads(Path(p).read_text()) for p in sys.argv[1:]]
assert historico == dict(versao=1, registro=registro, pendencias=[dict(
    sessao='persistencia--pendente', origem='revisoes/persistencia--pendente.json')])
assert registro['ciclo'] == 'encerrada' and registro['encerrado']
PYTEST
antes="$(cat "$persistente")"
checkpoint="$(cat "$reg/historico/$id_persistente.json")"
rodar "$repo_jangada/bin/jangada-coordenador" --finalizar persistencia--coordenador >/dev/null 2>&1
conferir "finalização repetida é idempotente" \
  test "$?:$(cat "$persistente"):$(cat "$reg/historico/$id_persistente.json")" = "0:$antes:$checkpoint"
conferir "finalizar não grava estado ou diário no projeto nem executa texto" \
  bash -c 'cmp -s "$1" "$2/.jangada/estado.md" && [[ "$(find "$2/.jangada" -type f | wc -l)" = 1 && ! -e "$2/NUNCA_EXECUTAR" ]]' _ "$tmp/estado.salvo" "$tmp/persistencia"
for provedor_hook in claude codex agy; do
  printf '{"prompt":"atrasado"}' | rodar env JANGADA_COORDENADOR=persistencia--coordenador \
    JANGADA_ATUACAO_ID="$id_persistente" "$repo_jangada/bin/jangada-hook-$provedor_hook" trabalhando
  conferir "$provedor_hook: hook atrasado não altera atuação encerrada" test "$(cat "$persistente")" = "$antes"
done
cp "$reg/historico/$id_persistente.json" "$tmp/checkpoint.valido"
for caso in json link ligacao; do
  rm "$reg/historico/$id_persistente.json"
  case "$caso" in
    json) printf '{' >"$reg/historico/$id_persistente.json" ;;
    link) ln -s "$tmp/checkpoint.valido" "$reg/historico/$id_persistente.json" ;;
    ligacao) ln "$tmp/checkpoint.valido" "$reg/historico/$id_persistente.json" ;;
  esac
  anterior="$(cat "$reg/historico/$id_persistente.json")"
  rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" >"$tmp/saida" 2>&1
  conferir "histórico $caso: impede substituição da atuação e preserva arquivos" \
    test "$?:$(cat "$persistente"):$(cat "$reg/historico/$id_persistente.json")" = "2:$antes:$anterior"
done
rm "$reg/historico/$id_persistente.json"
cp "$tmp/checkpoint.valido" "$reg/historico/$id_persistente.json"
mv "$reg/historico" "$tmp/historico.real"
ln -s "$tmp/historico.real" "$reg/historico"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" >"$tmp/saida" 2>&1
conferir "pasta histórica simbólica impede nova atuação" test "$?:$(cat "$persistente")" = "2:$antes"
rm "$reg/historico"
mv "$tmp/historico.real" "$reg/historico"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" >/dev/null 2>&1
conferir "a nova atuação mantém o histórico encerrado" test "$(cat "$reg/historico/$id_persistente.json")" = "$checkpoint"
conferir "a identidade da nova atuação difere" test "$(jq -r .atuacao_id "$persistente")" != "$id_persistente"
antes="$(cat "$persistente")"
for provedor_hook in claude codex agy; do
  for id_velho in "$id_persistente" ''; do
    printf '{"prompt":"atrasado"}' | rodar env JANGADA_COORDENADOR=persistencia--coordenador \
      JANGADA_ATUACAO_ID="$id_velho" "$repo_jangada/bin/jangada-hook-$provedor_hook" trabalhando
    conferir "$provedor_hook: identidade antiga ou ausente não altera nova atuação" test "$(cat "$persistente")" = "$antes"
  done
done

tm kill-session -t =persistencia--coordenador
antes="$(cat "$persistente")"
mv "$estado/revisoes/persistencia--pendente.json" "$tmp/pendente.protegida"
ln -s "$tmp/pendente.protegida" "$estado/revisoes/persistencia--pendente.json"
rodar "$repo_jangada/bin/jangada-coordenador" --finalizar persistencia--coordenador >"$tmp/saida" 2>&1
conferir "pendência protegida com link impede finalização sem perder o estado" \
  test "$?:$(cat "$persistente")" = "1:$antes"
rm "$estado/revisoes/persistencia--pendente.json"
mv "$tmp/pendente.protegida" "$estado/revisoes/persistencia--pendente.json"

# Migração acontece ao abrir; consulta não migra nem confunde hook com ciclo.
for legado in aberto encerrado; do
  mkdir -p "$tmp/legado-$legado"
  sessao_legado="legado-$legado--coordenador"
  legado_arq="$reg/$sessao_legado.json"
  jq -n --arg s "$sessao_legado" --arg p "$tmp/legado-$legado" \
    '{sessao:$s,projeto:$p,provedor:"claude",estado:"encerrado",desde:"2020-01-01T00:00:00+00:00"}' >"$legado_arq"
  if [[ "$legado" = encerrado ]]; then
    jq '.encerrado="2020-01-02T00:00:00+00:00"' "$legado_arq" >"$tmp/novo"
    mv "$tmp/novo" "$legado_arq"
  fi
  antes="$(cat "$legado_arq")"
  consulta="$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json)"
  conferir "legado $legado: consulta não grava nem gera identidade" \
    test "$(cat "$legado_arq"):$(jq -r --arg s "$sessao_legado" '.coordenadores[] | select(.sessao == $s) | .atuacao_id' <<<"$consulta")" = "$antes:null"
  rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/legado-$legado" >/dev/null 2>&1
  conferir "legado $legado: abertura migra para atuação com identidade" jq -e '.ciclo == "aberta" and (.atuacao_id | length) >= 16' "$legado_arq"
  if [[ "$legado" = aberto ]]; then
    conferir "legado aberto: conserva data original apesar do estado do hook" \
      test "$(jq -r .desde "$legado_arq")" = '2020-01-01T00:00:00+00:00'
  else
    conferir "legado encerrado: registro antigo fica no histórico" \
      python3 - "$reg/historico" "$sessao_legado" <<'PYTEST'
import json, sys
from pathlib import Path
registros = [json.loads(p.read_text())['registro'] for p in Path(sys.argv[1]).glob('*.json')]
assert any(r['sessao'] == sys.argv[2] and r['desde'] == '2020-01-01T00:00:00+00:00'
           and r['encerrado'] == '2020-01-02T00:00:00+00:00' for r in registros)
PYTEST
  fi
  tm kill-session -t "=$sessao_legado"
done

# Sem sessão viva, registros suspeitos continuam sendo dados preservados.
mkdir -p "$tmp/guardado" "$tmp/homonimo/guardado"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/guardado" >/dev/null 2>&1
tm kill-session -t =guardado--coordenador
cp "$reg/guardado--coordenador.json" "$tmp/guardado.valido"
for caso in json vazio lista multiplos duplicado link ligacao identidade data ciclo homonimo; do
  rm -f "$reg/guardado--coordenador.json"
  cp "$tmp/guardado.valido" "$reg/guardado--coordenador.json"
  alvo="$tmp/guardado"
  case "$caso" in
    json) printf '{' >"$reg/guardado--coordenador.json" ;;
    vazio) : >"$reg/guardado--coordenador.json" ;;
    lista) printf '[]' >"$reg/guardado--coordenador.json" ;;
    multiplos) cat "$tmp/guardado.valido" >>"$reg/guardado--coordenador.json" ;;
    duplicado) sed 's/"sessao":/"sessao":"intruso","sessao":/' "$tmp/guardado.valido" >"$reg/guardado--coordenador.json" ;;
    link|ligacao)
      rm "$reg/guardado--coordenador.json"
      if [[ "$caso" = link ]]; then ln -s "$tmp/guardado.valido" "$reg/guardado--coordenador.json"
      else ln "$tmp/guardado.valido" "$reg/guardado--coordenador.json"; fi ;;
    identidade) jq '.atuacao_id="../escapar"' "$tmp/guardado.valido" >"$reg/guardado--coordenador.json" ;;
    data) jq '.encerrado="inválida"' "$tmp/guardado.valido" >"$reg/guardado--coordenador.json" ;;
    ciclo) jq '.ciclo="outro"' "$tmp/guardado.valido" >"$reg/guardado--coordenador.json" ;;
    homonimo) alvo="$tmp/homonimo/guardado" ;;
  esac
  antes="$(cat "$reg/guardado--coordenador.json")"
  rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$alvo" >"$tmp/saida" 2>&1; rc=$?
  conferir "$caso sem sessão: abertura recusa e preserva" test "$rc:$(cat "$reg/guardado--coordenador.json")" = "2:$antes"
  if [[ "$caso" != homonimo ]]; then
    rodar "$repo_jangada/bin/jangada-coordenador" --finalizar guardado--coordenador >"$tmp/saida" 2>&1
    conferir "$caso sem sessão: finalização recusa e preserva" test "$?:$(cat "$reg/guardado--coordenador.json")" = "1:$antes"
  fi
done
rm "$reg/guardado--coordenador.json"
cp "$tmp/guardado.valido" "$reg/guardado--coordenador.json"

# Recusas devem acontecer antes de --fim alterar registro ou matar processo.
fonte_falha="$tmp/fonte-falha.json"
printf '{"coordenador_sessao":"alheio--coordenador"}' >"$fonte_falha"
entrada_falha="$estado/revisoes/alheia--falha.json"
preparar_falha() {
  case "$1" in
    pendencia-json) printf '{' >"$entrada_falha" ;;
    pendencia-lista) printf '[]' >"$entrada_falha" ;;
    pendencia-link) ln -s "$fonte_falha" "$entrada_falha" ;;
    pendencia-ligacao) ln "$fonte_falha" "$entrada_falha" ;;
    pendencia-fifo) mkfifo "$entrada_falha" ;;
    pendencia-diretorio) mkdir "$entrada_falha" ;;
    raiz-revisoes)
      mv "$estado/revisoes" "$tmp/revisoes-salvas"
      ln -s "$tmp/revisoes-salvas" "$estado/revisoes" ;;
    historico-json) printf '{' >"$historico_falha" ;;
    historico-lista) printf '[]' >"$historico_falha" ;;
    historico-link) ln -s "$fonte_falha" "$historico_falha" ;;
    historico-ligacao) ln "$fonte_falha" "$historico_falha" ;;
    historico-divergente) printf '{"versao":1,"registro":{},"pendencias":[]}' >"$historico_falha" ;;
    raiz-historico)
      mv "$reg/historico" "$tmp/historico-salvo"
      ln -s "$tmp/historico-salvo" "$reg/historico" ;;
  esac
}
restaurar_falha() {
  case "$1" in
    pendencia-diretorio) rmdir "$entrada_falha" ;;
    pendencia-*) rm "$entrada_falha" ;;
    historico-*) rm "$historico_falha" ;;
    raiz-revisoes)
      rm "$estado/revisoes"
      mv "$tmp/revisoes-salvas" "$estado/revisoes" ;;
    raiz-historico)
      rm "$reg/historico"
      mv "$tmp/historico-salvo" "$reg/historico" ;;
  esac
}
mkdir -p "$tmp/seguro"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/seguro" >/dev/null 2>&1
seguro="$reg/seguro--coordenador.json"
historico_falha="$reg/historico/$(jq -r .atuacao_id "$seguro").json"
for modo_trava in flock fallback; do
  if [[ "$modo_trava" = fallback ]]; then caminho_teste="$sem_flock"; else caminho_teste="$path_chamador"; fi
  for caso in pendencia-json pendencia-lista pendencia-link pendencia-ligacao pendencia-fifo \
    pendencia-diretorio raiz-revisoes historico-json historico-lista historico-link \
    historico-ligacao historico-divergente raiz-historico; do
    antes="$(cat "$seguro")"
    painel="$(tm display-message -p -t =seguro--coordenador: '#{pane_pid}')"
    preparar_falha "$caso"
    : >"$tmp/tmux.chamadas"
    rodar env PATH="$caminho_teste" "$repo_jangada/bin/jangada-coordenador" --fim seguro--coordenador >"$tmp/saida" 2>&1; rc=$?
    conferir "$modo_trava, $caso: --fim recusa sem alterar registro" test "$rc:$(cat "$seguro")" = "1:$antes"
    conferir "$modo_trava, $caso: --fim não manda matar sessão" \
      bash -c '! grep -q kill-session "$1"' _ "$tmp/tmux.chamadas"
    conferir "$modo_trava, $caso: processo original continua vivo" \
      test "$(tm display-message -p -t =seguro--coordenador: '#{pane_pid}')" = "$painel"
    conferir "$modo_trava, $caso: recusa libera a trava" test ! -d "$reg/.trava.d"
    restaurar_falha "$caso"
  done
done
rodar "$repo_jangada/bin/jangada-coordenador" --fim seguro--coordenador >"$tmp/saida" 2>&1
conferir "--fim com dados íntegros encerra após todas as recusas" \
  test "$?:$(jq -r .ciclo "$seguro")" = '0:encerrada'
conferir "--fim com dados íntegros mantém compatibilidade de matar sessão" \
  bash -c '! "$@" has-session -t =seguro--coordenador 2>/dev/null' _ env TMUX_TMPDIR="$sock" tmux -L jangada

# Checkpoint válido dispensa varredura de pendências ao repetir ou abrir.
mkdir -p "$tmp/reusar"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/reusar" >/dev/null 2>&1
rodar "$repo_jangada/bin/jangada-coordenador" --fim reusar--coordenador >/dev/null 2>&1
reusar="$reg/reusar--coordenador.json"
for caso in pendencia-json pendencia-lista pendencia-link pendencia-ligacao pendencia-fifo \
  pendencia-diretorio raiz-revisoes; do
  antes="$(cat "$reusar")"
  id_reusar="$(jq -r .atuacao_id "$reusar")"
  checkpoint="$(cat "$reg/historico/$id_reusar.json")"
  preparar_falha "$caso"
  rodar "$repo_jangada/bin/jangada-coordenador" --finalizar reusar--coordenador >"$tmp/saida" 2>&1
  conferir "$caso: repetir finalização reaproveita checkpoint sem varrer cópias" \
    test "$?:$(cat "$reusar")" = "0:$antes"
  rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/reusar" >"$tmp/saida" 2>&1; rc=$?
  conferir "$caso: nova abertura usa checkpoint válido apesar da cópia alheia" \
    test "$rc:$(jq -r .ciclo "$reusar")" = '0:aberta'
  conferir "$caso: nova atuação e histórico preservados" \
    bash -c '[[ "$1" != "$2" && "$3" = "$4" ]]' _ "$(jq -r .atuacao_id "$reusar")" "$id_reusar" "$(cat "$reg/historico/$id_reusar.json")" "$checkpoint"
  conferir "$caso: abertura realmente cria sessão" tm has-session -t =reusar--coordenador
  restaurar_falha "$caso"
  tm kill-session -t =reusar--coordenador
  rodar "$repo_jangada/bin/jangada-coordenador" --finalizar reusar--coordenador >/dev/null 2>&1
done

# A mesma trava também serializa abrir/finalizar; nenhuma chamada mata a outra.
for modo_trava in flock fallback; do
  if [[ "$modo_trava" = fallback ]]; then caminho_teste="$sem_flock"; else caminho_teste="$path_chamador"; fi
  for _ in 1 2 3; do
    tm kill-session -t =persistencia--coordenador 2>/dev/null || true
    rodar env PATH="$caminho_teste" "$repo_jangada/bin/jangada-coordenador" --finalizar persistencia--coordenador >"$tmp/finalizar-corrida" 2>&1 &
    pid1=$!
    rodar env PATH="$caminho_teste" "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/persistencia" >"$tmp/abrir-corrida" 2>&1 &
    pid2=$!
    wait "$pid1"; rc1=$?
    wait "$pid2"; rc2=$?
    conferir "$modo_trava: corrida termina com abertura ou recusa por sessão viva" \
      bash -c '[[ "$1:$2" = 0:0 || "$1:$2" = 2:0 ]]' _ "$rc1" "$rc2"
    conferir "$modo_trava: corrida mantém ciclo aberto e sessão viva" \
      jq -e '.ciclo == "aberta" and (has("encerrado") | not)' "$persistente"
    conferir "$modo_trava: corrida não mata o coordenador aberto" tm has-session -t =persistencia--coordenador
    conferir "$modo_trava: corrida mantém associação da tarefa protegida" \
      test "$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json | jq -r '.coordenadores[] | select(.sessao == "persistencia--coordenador") | .tarefas[0].sessao')" = persistencia--pendente
    conferir "$modo_trava: libera a trava ao terminar" test ! -d "$reg/.trava.d"
  done
done

mkdir -p "$tmp/vazia"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/vazia" >/dev/null 2>&1
tm kill-session -t =vazia--coordenador
rodar "$repo_jangada/bin/jangada-coordenador" --finalizar vazia--coordenador >"$tmp/saida" 2>&1
conferir "finalização sem tarefas informa zero e não cria documentos no projeto" \
  bash -c '[[ "$1" = 0 && "$(cat "$2")" == *"pendências preservadas: 0"* && -z "$(find "$3" -mindepth 1 -print -quit)" ]]' _ "$?" "$tmp/saida" "$tmp/vazia"

# Argon usa o mesmo contexto e mantém a atuação após interrupção.
mkdir -p "$tmp/argon"
cmd_argon=("$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/argon" --provedor agy)
rodar "${cmd_argon[@]}" --modelo invalido >"$tmp/saida" 2>&1
conferir "Argon: modelo diferente é recusado antes de criar sessão" test "$?" = 2
conferir "Argon: recusa não cria registro" test ! -e "$reg/argon--coordenador.json"
printf 'gemini-4-argon-medium' >"$tmp/argon.catalogo"
rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
conferir "Argon: modelo indisponível recusa sem tentar outro" test "$?" = 1
conferir "Argon: modelo ausente não cria registro" test ! -e "$reg/argon--coordenador.json"
rm "$tmp/argon.catalogo"
for cota_invalida in 0.19 -1 1.1 nan; do
  printf '%s' "$cota_invalida" >"$tmp/argon.cota"
  rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
  conferir "Argon: cota $cota_invalida recusa" test "$?" = 1
  conferir "Argon: cota $cota_invalida não cria registro" test ! -e "$reg/argon--coordenador.json"
done
for uso_invalido in '{' '{}' '{"command":{"data":{"groups":[{"buckets":[{"id":"gemini-wtu-weekly","remaining_fraction":1}]}]}}}'; do
  printf '%s' "$uso_invalido" >"$tmp/argon.uso"
  rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
  conferir "Argon: cota desconhecida não usa grupo Flash" test "$?" = 1
done
rm "$tmp/argon.uso"
printf '0' >"$tmp/argon.cota"
rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
conferir "Argon: cota zero recusa antes de criar registro" test "$?" = 1
conferir "Argon: cota zero não abre sessão" bash -c '! "$@" has-session -t =argon--coordenador 2>/dev/null' _ env TMUX_TMPDIR="$sock" tmux -L jangada
conferir "Argon: cota zero explica bloqueio sem alternativa" grep -q 'cota.*gemini-4-argon-high' "$tmp/saida"
printf '1' >"$tmp/argon.cota"
rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
conferir "Argon: abertura com cliente falso" test "$?" = 0
conferir "Argon: cliente recebeu argumentos" esperar test -s "$tmp/agy.args"
conferir "Argon: modelo exato, mesmo contexto e permissões do cliente" \
  python3 - "$tmp/agy.args" "$prompt_inicial" <<'PYTEST'
import sys
from pathlib import Path
assert Path(sys.argv[1]).read_bytes().split(b'\0')[:-1] == [
    b'--model', b'gemini-4-argon-high', b'--prompt-interactive', sys.argv[2].encode()]
PYTEST
argon_reg="$reg/argon--coordenador.json"
argon_id="$(jq -r .atuacao_id "$argon_reg")"
argon_antes="$(cat "$argon_reg")"
rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
conferir "Argon: repetição preserva registro vivo" test "$?:$(cat "$argon_reg")" = "0:$argon_antes"
hook_argon() {
  printf '%s' "$2" | rodar env JANGADA_COORDENADOR=argon--coordenador JANGADA_ATUACAO_ID="$argon_id" "${@:3}" "$repo_jangada/bin/jangada-hook-agy" "$1"
}
for origem in claude codex; do
  printf '{"prompt":"evento alheio"}' \
    | rodar env JANGADA_COORDENADOR=argon--coordenador JANGADA_ATUACAO_ID="$argon_id" \
      JANGADA_COORDENADOR_PROVEDOR="$origem" "$repo_jangada/bin/jangada-hook-$origem" trabalhando
  conferir "$origem com origem explícita não altera registro Argon" \
    test "$(cat "$argon_reg")" = "$argon_antes"
done
hook_argon inicio '{"modelName":"gemini-4-argon-high"}' >/dev/null
conferir "Argon: SessionStart conserva identidade e ciclo aberto" \
  jq -e --arg id "$argon_id" '.estado == "iniciado" and .atuacao_id == $id and .ciclo == "aberta"' "$argon_reg"
hook_argon trabalhando '{"modelName":"gemini-4-argon-high"}' >/dev/null
conferir "Argon: PreInvocation registra trabalhando" test "$(jq -r .estado "$argon_reg")" = trabalhando
argon_antes="$(cat "$argon_reg")"
for payload in '{"fullyIdle":false}' '{}' '{"fullyIdle":null}' '{"fullyIdle":"true"}' '{"fullyIdle":1}'; do
  hook_argon concluido "$payload" >/dev/null
  conferir "Argon: Stop sem ociosidade comprovada ($payload) preserva registro" test "$(cat "$argon_reg")" = "$argon_antes"
done
for extra in JANGADA_HOOK_DESLIGADO=1 JANGADA_ISOLADO=1 JANGADA_AGY_PAPEL=arquiteto JANGADA_ATUACAO_ID=velha; do
  hook_argon concluido '{"fullyIdle":true}' "$extra" >/dev/null
  conferir "Argon: $extra não altera o pai" test "$(cat "$argon_reg")" = "$argon_antes"
done
hook_argon concluido '{"fullyIdle":true,"terminationReason":"NO_TOOL_CALL"}' >/dev/null
conferir "Argon: resposta pronta mantém atuação aberta" \
  jq -e --arg id "$argon_id" '.estado == "concluido" and .ciclo == "aberta" and .atuacao_id == $id and .ultima_linha == "turno concluído"' "$argon_reg"
hook_argon trabalhando '{}' >/dev/null
hook_argon concluido '{"fullyIdle":true,"terminationReason":"ERROR","error":"falha sintética"}' >/dev/null
conferir "Argon: erro permanece visível sem encerrar atuação" \
  jq -e '.estado == "concluido" and .ciclo == "aberta" and .ultima_linha == "erro: falha sintética"' "$argon_reg"
hook_argon trabalhando '{}' >/dev/null
hook_argon concluido '{"fullyIdle":true,"terminationReason":"USER_CANCELED"}' >/dev/null
conferir "Argon: interrupção do turno conserva ciclo e identidade" \
  jq -e --arg id "$argon_id" '.estado == "concluido" and .ciclo == "aberta" and .atuacao_id == $id and .ultima_linha == "turno interrompido"' "$argon_reg"
# A trava da delegação pode estar ocupada; abertura não espera por ela nem a retém.
exec 8>"$estado/agentes/.agy-execucao.lock"
flock -n 8
conferir "Argon: saída voluntária termina o processo" tm send-keys -t =argon--coordenador: x
conferir "Argon: sessão termina sem fechar ciclo" esperar bash -c '! "$@" has-session -t =argon--coordenador 2>/dev/null' _ env TMUX_TMPDIR="$sock" tmux -L jangada
rodar "${cmd_argon[@]}" >"$tmp/saida" 2>&1
conferir "Argon: retoma sem disputar trava de filho" test "$?" = 0
exec 8>&-
conferir "Argon: processo retomado iniciou" esperar test -s "$tmp/agy.args"
conferir "Argon: retomada conserva identidade" test "$(jq -r .atuacao_id "$argon_reg")" = "$argon_id"
rodar "$repo_jangada/bin/jangada-coordenador" --finalizar argon--coordenador >"$tmp/saida" 2>&1
conferir "Argon: finalizar vivo recusa" test "$?" = 2
tm send-keys -t =argon--coordenador: x
esperar bash -c '! "$@" has-session -t =argon--coordenador 2>/dev/null' _ env TMUX_TMPDIR="$sock" tmux -L jangada
rodar "$repo_jangada/bin/jangada-coordenador" --finalizar argon--coordenador >"$tmp/saida" 2>&1
conferir "Argon: finalização voluntária arquiva atuação" test "$?:$(jq -r .ciclo "$argon_reg")" = 0:encerrada
argon_antes="$(cat "$argon_reg")"
hook_argon trabalhando '{}' >/dev/null
conferir "Argon: hook atrasado não reabre ciclo" test "$(cat "$argon_reg")" = "$argon_antes"
rm "$tmp/argon.cota"

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "todos os testes do coordenador passaram"
