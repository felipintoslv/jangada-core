#!/usr/bin/env bash
# jangada-coordenador: abertura, registro pelos hooks, consulta, mensagem e
# fim, num servidor tmux próprio do teste (TMUX_TMPDIR temporário), nunca o
# servidor real do jangada.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux ausente; teste do coordenador ignorado"
  exit 0
fi
tmp="$(mktemp -d)"
falhas=0
conferir() {
  local nome="$1"; shift
  if "$@"; then printf 'ok    %s\n' "$nome"; else printf 'FALHA %s\n' "$nome"; falhas=$((falhas + 1)); fi
}
mkdir -p "$tmp/bin" "$tmp/home" "$tmp/config" "$tmp/state" "$tmp/sock" "$tmp/projeto/sub" "$tmp/outro" "$tmp/codex"
estado="$tmp/state/jangada"
reg="$estado/coordenadores"

# Claude falso: liga a colagem entre marcas, como o Claude Code, e grava os
# bytes recebidos sem interpretar nada.
cat >"$tmp/bin/claude" <<'EOF'
#!/usr/bin/env python3
import os, sys, tty
tty.setraw(0)
sys.stdout.write('\x1b[?2004h')
sys.stdout.flush()
caminho = os.environ['FALSO_DIR'] + '/claude.bytes'
open(caminho, 'wb').close()
open(os.environ['FALSO_DIR'] + '/claude.pronto', 'w').close()
with open(caminho, 'ab', buffering=0) as log:
    while True:
        dados = os.read(0, 4096)
        if not dados:
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
printf '%s\0' "$@" >"$FALSO_DIR/codex.args"
exec cat >/dev/null
EOF
for c in notify-send pkill hyprctl; do
  printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/$c"
done
chmod +x "$tmp/bin/"*

rodar() {
  env -u JANGADA_SESSAO -u JANGADA_ISOLADO -u JANGADA_COORDENADOR -u TMUX -u WAYLAND_DISPLAY \
    -u HYPRLAND_INSTANCE_SIGNATURE -u DISPLAY \
    PATH="$tmp/bin:$PATH" HOME="$tmp/home" SHELL=/bin/sh TMUX_TMPDIR="$tmp/sock" FALSO_DIR="$tmp" \
    CODEX_HOME="$tmp/codex" JANGADA_CORE_PATH="$repo_jangada" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$tmp/state" "$@"
}
tm() { rodar tmux -L jangada "$@"; }
trap 'tm kill-server >/dev/null 2>&1; if [[ -n "${MANTER:-}" ]]; then echo "$tmp"; else rm -rf "$tmp"; fi' EXIT
esperar() {
  local i
  for ((i = 0; i < 50; i++)); do "$@" && return 0; sleep 0.1; done
  return 1
}
campo() { jq -r "$1 // \"\" | tostring" "$reg/projeto--coordenador.json" 2>/dev/null; }
bytes() { od -An -c "$tmp/claude.bytes" 2>/dev/null | tr -s ' \n' ' '; }
hook() { rodar env "${@:3}" "$repo_jangada/bin/jangada-hook-claude" "$1" <<<"$2"; }

git init -q -b main "$tmp/projeto"
git -C "$tmp/projeto" -c user.name=t -c user.email=t@t commit -q --allow-empty -m inicio

# Abertura, a partir de uma subpasta: o coordenador fica na raiz do projeto.
saida="$(rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto/sub" 2>&1)"
conferir "a abertura cria a sessão PROJETO--coordenador" [ "$saida" = projeto--coordenador ]
conferir "a sessão existe no servidor do teste" tm has-session -t =projeto--coordenador
conferir "o socket é o do teste" test -S "$tmp/sock/tmux-$(id -u)/jangada"
conferir "a pasta dos registros tem modo 700" [ "$(stat -c %a "$reg")" = 700 ]
conferir "o registro nasce com projeto, provedor e estado iniciado" \
  [ "$(campo '[.projeto, .provedor, .estado] | join(" ")')" = "$tmp/projeto claude iniciado" ]
conferir "a sessão recebe JANGADA_COORDENADOR" \
  [ "$(tm show-environment -t =projeto--coordenador JANGADA_COORDENADOR 2>/dev/null)" = JANGADA_COORDENADOR=projeto--coordenador ]
conferir "a sessão não recebe JANGADA_SESSAO" \
  [ "$( (tm show-environment -t =projeto--coordenador; tm show-environment -g) | grep -c '^JANGADA_SESSAO=')" = 0 ]
conferir "a sessão roda na raiz do projeto" \
  [ "$(tm display-message -p -t =projeto--coordenador: '#{pane_start_path}')" = "$tmp/projeto" ]
conferir "o Claude falso abre na sessão" esperar test -f "$tmp/claude.pronto"

# Segundo pedido para o mesmo projeto: avisa e não abre outra.
saida="$(rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/projeto" 2>&1)"; rc=$?
conferir "o segundo pedido sai com 0 e avisa" [ "$rc" = 0 ]
conferir "o aviso diz que já está aberto" grep -q "já está aberto" <<<"$saida"
conferir "continua uma sessão só" [ "$(tm list-sessions -F '#S' | grep -c coordenador)" = 1 ]

# Codex: os hooks do jangada vão na chamada, com a aprovação no estado.
saida="$(rodar "$repo_jangada/bin/jangada-coordenador" --projeto "$tmp/outro" --provedor codex 2>&1)"
conferir "a abertura com Codex cria a sessão" [ "$saida" = outro--coordenador ]
conferir "o Codex abre com os hooks do coordenador" esperar test -s "$tmp/codex.args"
args_codex="$(tr '\0' '\n' <"$tmp/codex.args" 2>/dev/null)"
conferir "o Stop do Codex chama o jangada-hook-codex" grep -q "^hooks.Stop=.*jangada-hook-codex' concluido" <<<"$args_codex"
conferir "a aprovação dos hooks vai na chamada" grep -q "^hooks.state=" <<<"$args_codex"
conferir "a aprovação fica na pasta dos coordenadores" test -f "$reg/codex-hooks-confianca.json"
conferir "o registro do Codex diz o provedor" [ "$(jq -r .provedor "$reg/outro--coordenador.json")" = codex ]
tm kill-session -t =outro--coordenador
rm -f "$reg/outro--coordenador.json"

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

# Mensagem: só com concluido; o texto vai entre as marcas de colagem e um
# Enter fecha.
printf 'primeira linha\nsegunda linha\n\n' >"$tmp/msg"
rodar env JANGADA_COORDENADOR_PAUSA=0.2 "$repo_jangada/bin/jangada-coordenador" \
  --mensagem projeto--coordenador --arquivo "$tmp/msg" >"$tmp/saida" 2>&1
conferir "a mensagem com concluido sai com 0" [ "$?" = 0 ]
esperada="$(printf '\033[200~primeira linha\nsegunda linha\033[201~\r' | od -An -c | tr -s ' \n' ' ')"
conferir "o Claude recebe só o texto colado e um Enter" esperar [ "$(bytes)" = "$esperada" ]
conferir "o buffer da mensagem é apagado" [ -z "$(tm list-buffers 2>/dev/null)" ]
: >"$tmp/claude.bytes"
for e in aguardando trabalhando; do
  hook "$e" '{"prompt":"p"}' JANGADA_COORDENADOR=projeto--coordenador
  rodar "$repo_jangada/bin/jangada-coordenador" --mensagem projeto--coordenador --arquivo "$tmp/msg" >"$tmp/saida" 2>&1
  conferir "a mensagem com $e sai com 3" [ "$?" = 3 ]
  conferir "a recusa com $e diz o motivo" grep -q "mensagem recusada" "$tmp/saida"
done
sleep 0.2
conferir "nada chega ao Claude nas recusas" [ ! -s "$tmp/claude.bytes" ]
hook concluido '{"last_assistant_message":"pronto"}' JANGADA_COORDENADOR=projeto--coordenador
printf 'texto\033[31m com escape\n' >"$tmp/msg-controle"
printf 'linha\r\n' >"$tmp/msg-cr"
head -c 9000 /dev/zero | tr '\0' a >"$tmp/msg-grande"
for m in msg-controle msg-cr msg-grande; do
  rodar "$repo_jangada/bin/jangada-coordenador" --mensagem projeto--coordenador --arquivo "$tmp/$m" >"$tmp/saida" 2>&1
  conferir "texto inválido ($m) sai com 2" [ "$?" = 2 ]
done
sleep 0.2
conferir "texto inválido não chega ao Claude" [ ! -s "$tmp/claude.bytes" ]
rodar "$repo_jangada/bin/jangada-coordenador" --mensagem projeto--tarefa --arquivo "$tmp/msg" >/dev/null 2>&1
conferir "mensagem para sessão que não é coordenador sai com 2" [ "$?" = 2 ]
rodar env JANGADA_ISOLADO=1 "$repo_jangada/bin/jangada-coordenador" \
  --mensagem projeto--coordenador --arquivo "$tmp/msg" >/dev/null 2>&1
conferir "isolado, a mensagem é recusada" [ "$?" = 3 ]

# Fim: a sessão some, o registro fica marcado e a tarefa continua.
rodar "$repo_jangada/bin/jangada-coordenador" --fim projeto--coordenador >/dev/null 2>&1
conferir "o --fim sai com 0" [ "$?" = 0 ]
conferir "o --fim encerra a sessão" esperar bash -c '! "$@" has-session -t =projeto--coordenador 2>/dev/null' _ \
  env TMUX_TMPDIR="$tmp/sock" tmux -L jangada
conferir "o registro fica encerrado, com data" [ "$(campo .estado)" = encerrado -a -n "$(campo .encerrado)" ]
conferir "a tarefa e a cópia dela continuam" tm has-session -t =projeto--tarefa
conferir "a cópia da tarefa continua" test -f "$estado/revisoes/projeto--tarefa.json"
hook trabalhando '{"prompt":"tarde"}' JANGADA_COORDENADOR=projeto--coordenador
conferir "hook depois do --fim não reabre o registro" [ "$(campo .estado)" = encerrado ]
rodar "$repo_jangada/bin/jangada-coordenador" --mensagem projeto--coordenador --arquivo "$tmp/msg" >/dev/null 2>&1
conferir "mensagem depois do --fim sai com 3" [ "$?" = 3 ]
conferir "a consulta mostra o coordenador encerrado e morto" [ "$(rodar "$repo_jangada/bin/jangada-agentes" \
  --coordenadores-json | jq -c '.coordenadores[0] | [.estado, .viva]')" = '["encerrado",false]' ]

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "todos os testes do coordenador passaram"
