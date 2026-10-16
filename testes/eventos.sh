#!/usr/bin/env bash
# Testa o histórico de estados dos agentes (eventos-agentes.jsonl), gravado
# pelos hooks do Claude e do agy e pela troca de foco do jangada-agentes.
#
# Uso: testes/eventos.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
estado="$tmp/state/jangada"
eventos="$estado/eventos-agentes.jsonl"
mkdir -p "$estado/agentes" "$tmp/bin"
# notify-send e setsid falsos: o teste não abre notificação nem terminal.
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/notify-send"
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/setsid"
# tmux falso: toda sessão existe.
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/tmux"
chmod +x "$tmp/bin/"*

rodar() {
  env -u HYPRLAND_INSTANCE_SIGNATURE -u JANGADA_HOOK_DESLIGADO -u JANGADA_SESSAO -u JANGADA_ISOLADO PATH="$tmp/bin:$PATH" \
    XDG_STATE_HOME="$tmp/state" XDG_CONFIG_HOME="$tmp/config" JANGADA_CORE_PATH="$repo_jangada" "$@"
}
claude() { printf '%s' "${2:-{\}}" | rodar JANGADA_SESSAO=proj--tarefa "$repo_jangada/bin/jangada-hook-claude" "$1"; }
agy() { printf '%s' "${2:-{\}}" | rodar JANGADA_SESSAO=outro "$repo_jangada/bin/jangada-hook-agy" "$1" >/dev/null; }
jq_ok() { jq -e -s "$@" >/dev/null; }
estados() { jq -r --arg s "$1" 'select(.sessao == $s) | .estado' "$eventos" | paste -sd' '; }

# Caso 1: Claude. O PostToolUse repete "trabalhando"; só a mudança vira linha.
jq -n '{sessao: "proj--tarefa", dir: "/x/wt/tarefa", raiz: "/x/proj", agente: "claude"}' \
  >"$estado/agentes/proj--tarefa.json"
claude inicio '{"session_id": "c1", "cwd": "/x/wt/tarefa"}'
claude trabalhando '{"prompt": "faça"}'
claude trabalhando '{}'
claude trabalhando '{}'
claude aguardando '{"message": "permissão", "notification_type": "permission_prompt"}'
claude trabalhando '{}'
claude concluido '{}'
claude aguardando '{"notification_type": "idle_prompt"}'
claude fim '{"reason": "clear"}'
claude fim '{"reason": "prompt_input_exit"}'
conferir "caso 1: uma linha por mudança de estado" \
  [ "$(estados proj--tarefa)" = "inicio trabalhando aguardando trabalhando concluido fim" ]
conferir "caso 1: o projeto vem da raiz, não do worktree" \
  [ "$(jq -r 'select(.sessao == "proj--tarefa") | .projeto' "$eventos" | sort -u)" = proj ]
conferir "caso 1: agente e data em toda linha" \
  jq_ok 'all(.[]; .agente == "claude" and (.data | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T")))' "$eventos"

# Caso 2: agy. O Stop com fullyIdle falso não muda o estado.
jq -n '{sessao: "outro", dir: "/y/outro", raiz: "/y/outro", agente: "agy"}' >"$estado/agentes/outro.json"
agy trabalhando '{}'
agy trabalhando '{}'
agy concluido '{"fullyIdle": false}'
agy concluido '{"fullyIdle": true}'
conferir "caso 2: agy grava só a mudança" [ "$(estados outro)" = "trabalhando concluido" ]
conferir "caso 2: agy com agente e projeto" \
  jq_ok '[.[] | select(.sessao == "outro")] | all(.agente == "agy" and .projeto == "outro")' "$eventos"

# Caso 3: fora de uma sessão do jangada, nada é gravado.
antes="$(wc -l <"$eventos")"
printf '{}' | rodar "$repo_jangada/bin/jangada-hook-claude" trabalhando
conferir "caso 3: sem JANGADA_SESSAO, nada muda" [ "$(wc -l <"$eventos")" = "$antes" ]

# Caso 4: troca de foco, com horário.
rodar "$repo_jangada/bin/jangada-agentes" --focar outro >/dev/null 2>&1
conferir "caso 4: foco registrado" \
  jq_ok 'any(.[]; .sessao == "outro" and .estado == "foco" and .agente == "agy")' "$eventos"

# Caso 4b: subagente do Claude. Início e fim viram linha com id e tipo, e o
# estado da sessão fica como estava.
claude trabalhando '{}'
antes_estado="$(jq -c '{estado, mensagem, atualizado}' "$estado/agentes/proj--tarefa.json")"
claude subagente-inicio '{"session_id": "c1", "agent_id": "a1", "agent_type": "explorador"}'
claude subagente-fim '{"session_id": "c1", "agent_id": "a1", "agent_type": "explorador", "last_assistant_message": "relatório"}'
conferir "caso 4b: início e fim do subagente registrados" \
  jq_ok '[.[] | select(.estado | startswith("subagente"))]
    | map(.estado) == ["subagente-inicio", "subagente-fim"]
    and all(.[]; .subagente_id == "a1" and .subagente_tipo == "explorador" and .conversa == "c1"
            and .sessao == "proj--tarefa" and .projeto == "proj" and .agente == "claude")' "$eventos"
conferir "caso 4b: estado da sessão não muda" \
  [ "$(jq -c '{estado, mensagem, atualizado}' "$estado/agentes/proj--tarefa.json")" = "$antes_estado" ]
conferir "caso 4b: linhas antigas sem campos novos" \
  jq_ok 'all(.[] | select(.estado | startswith("subagente") | not); has("subagente_id") | not)' "$eventos"

# Caso 5: o hook não falha nem trava com o histórico sem permissão de escrita.
rm -f "$eventos"; mkdir "$eventos"
claude trabalhando '{}'; rc=$?
conferir "caso 5: histórico ilegível não derruba o hook do Claude" [ "$rc" = 0 ]
printf '{}' | rodar JANGADA_SESSAO=outro "$repo_jangada/bin/jangada-hook-agy" trabalhando >"$tmp/saida"; rc=$?
conferir "caso 5: nem o do agy, que segue respondendo {}" \
  bash -c '[ "$1" = 0 ] && [ "$(cat "$2")" = "{}" ]' _ "$rc" "$tmp/saida"

# Escritas simultâneas de linhas grandes: cada linha tem de sair inteira.
grande="$tmp/grande.json"
printf '{"x": "%s"}\n' "$(head -c 300000 /dev/zero | tr '\0' x)" >"$grande"
: >"$tmp/concorrente.jsonl"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  rodar bash -c 'source "$1/bin/jangada-config"
    for j in 1 2 3 4 5 6 7 8; do jangada_anexar_linha "$2" "$(jq -c --arg i "$3" --arg j "$j" ". + {i: \$i, j: \$j}" "$4")"; done' \
    _ "$repo_jangada" "$tmp/concorrente.jsonl" "$i" "$grande" &
done
wait
conferir "anexação concorrente: 96 linhas inteiras" \
  bash -c '[ "$(jq -c "select((.x | length) == 300000) | [.i, .j]" "$1" 2>/dev/null | sort -u | wc -l)" = 96 ] && [ "$(wc -l <"$1")" = 96 ]' \
  _ "$tmp/concorrente.jsonl"

if ((falhas)); then
  echo "$falhas falha(s); saídas em $tmp (mantido)"
  trap - EXIT
  exit 1
fi
echo "todos os testes do histórico de estados passaram"
