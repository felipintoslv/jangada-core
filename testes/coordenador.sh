#!/usr/bin/env bash
# jangada-coordenador: abertura, registro pelos hooks, consulta e fim, num
# servidor tmux próprio do teste (TMUX_TMPDIR temporário), nunca o servidor
# real do jangada.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
repo_jangada="$PWD"
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
  env -u JANGADA_SESSAO -u JANGADA_ISOLADO -u JANGADA_COORDENADOR -u TMUX -u WAYLAND_DISPLAY \
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
hook() { rodar env "${@:3}" "$repo_jangada/bin/jangada-hook-claude" "$1" <<<"$2"; }

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
saida="$(rodar env JANGADA_AUTOR_MODELO=haiku JANGADA_VALIDAR_MODELO=haiku CREDENCIAL_TESTE_ALHEIA=nao-repassar JANGADA_SESSAO=alheia--tarefa "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto/sub" 2>&1)"
conferir "a abertura cria a sessão PROJETO--coordenador" [ "$saida" = projeto--coordenador ]
conferir "a sessão existe no servidor do teste" tm has-session -t =projeto--coordenador
conferir "o socket é o do teste" test -S "$sock/tmux-$(id -u)/jangada"
conferir "a pasta dos registros tem modo 700" [ "$(stat -c %a "$reg")" = 700 ]
conferir "o registro nasce com projeto, provedor e estado iniciado" \
  [ "$(campo '[.projeto, .provedor, .estado] | join(" ")')" = "$tmp/projeto claude iniciado" ]
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
  date mv rm rmdir stat sleep head python3; do
  ln -s "$(command -v "$c")" "$sem_flock/$c"
done
for c in tmux claude codex hyprctl jangada-terminal; do
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
for provedor in claude codex; do
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
  "$repo_jangada/bin/jangada-hook-codex" aguardando
conferir "o hook do Codex também grava" [ "$(campo .estado)" = aguardando ]
hook concluido '{"last_assistant_message":"pronto"}' JANGADA_COORDENADOR=projeto--coordenador

# Consulta com uma tarefa ligada ao coordenador, viva no servidor do teste.
mkdir -p "$estado/revisoes"
printf '{"sessao":"projeto--tarefa","coordenador_sessao":"projeto--coordenador"}' \
  >"$estado/revisoes/projeto--tarefa.json"
printf '{"sessao":"projeto--solta","coordenador":"dono"}' >"$estado/revisoes/projeto--solta.json"
tm new-session -d -s projeto--tarefa
consulta="$(rodar "$repo_jangada/bin/jangada-agentes" --coordenadores-json)"
conferir "a consulta lista o coordenador com a tarefa" [ "$(jq -c '.coordenadores' <<<"$consulta")" = \
  "$(jq -cn --arg p "$tmp/projeto" --arg a "$(campo .atualizado)" '[{sessao:"projeto--coordenador", projeto:$p,
     provedor:"claude", estado:"concluido", ultima_linha:"pronto", atualizado:$a, viva:true,
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

# Saída voluntária do cliente falso, com registro antigo ainda no disco.
rm -f "$tmp/claude.pronto"
rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" >/dev/null 2>&1
conferir "o cliente anterior está pronto para sair" esperar test -f "$tmp/claude.pronto"
tm send-keys -t =projeto--coordenador: C-d
conferir "a saída voluntária termina a sessão anterior" esperar bash -c '! "$@" has-session -t =projeto--coordenador 2>/dev/null' _ \
  env TMUX_TMPDIR="$sock" tmux -L jangada
conferir "registro antigo sozinho não torna a sessão viva" test -f "$reg/projeto--coordenador.json"
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

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "todos os testes do coordenador passaram"
