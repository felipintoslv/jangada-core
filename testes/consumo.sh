#!/usr/bin/env bash
# Testa o jangada-consumo com registros de conversa sintéticos, e a dica da
# barra do jangada-agentes --waybar que o mostra. Sem rede.
#
# Uso: testes/consumo.sh
set -uo pipefail
export LC_ALL=C.UTF-8
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@" >/dev/null; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
unset JANGADA_ISOLADO TMUX
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/home/.config" XDG_STATE_HOME="$tmp/home/.local/state" \
  XDG_CACHE_HOME="$tmp/home/.cache" JANGADA_CORE_PATH="$repo_jangada"
mkdir -p "$HOME/.claude/projects/p"
consumo="$repo_jangada/bin/jangada-consumo"

# tmux falso sem sessões: as da máquina não entram na barra.
mkdir -p "$tmp/falsos"
printf '#!/bin/sh\nexit 0\n' >"$tmp/falsos/tmux"
chmod +x "$tmp/falsos/tmux"
export PATH="$tmp/falsos:$PATH"

"$consumo" --curto >"$tmp/saida" 2>&1; rc=$?
conferir "sem registros: sai com 0 ($rc)" test "$rc" -eq 0
conferir "sem registros: nenhum bloco em andamento" grep -q 'nenhum bloco de 5h' "$tmp/saida"
barra="$("$repo_jangada/bin/jangada-agentes" --waybar 2>&1)"
conferir "sem registros: a barra sai como vazia" jq -e '.class == "vazio"' <<<"$barra"

# Duas respostas de 10 e 20 tokens de saída, uma repetida (conta uma vez só).
agora="$(date -u -d '-30 minutes' +%Y-%m-%dT%H:%M:%SZ)"
linha() { printf '{"timestamp":"%s","requestId":"%s","message":{"id":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}\n' "$agora" "$1" "$1" "$2" "$3"; }
{ linha r1 100 10; linha r1 100 10; linha r2 200 20; } >"$HOME/.claude/projects/p/c.jsonl"
rm -f "$XDG_CACHE_HOME/jangada/consumo.json"
"$consumo" --json >"$tmp/saida" 2>&1; rc=$?
conferir "com registros: sai com 0 ($rc)" test "$rc" -eq 0
conferir "com registros: bloco ativo, 2 respostas, 330 tokens" \
  jq -e '.ativo == true and .mensagens == 2 and .entrada == 300 and .saida == 30 and .total == 330' "$tmp/saida"
"$consumo" --curto >"$tmp/saida" 2>&1
conferir "com registros: linha curta" grep -q '^Claude, bloco de 5h: 330 tokens (30 de saída, 2 respostas), renova às' "$tmp/saida"
"$consumo" >"$tmp/saida" 2>&1
conferir "com registros: texto" grep -q '^total:        330' "$tmp/saida"
barra="$("$repo_jangada/bin/jangada-agentes" --waybar 2>&1)"
conferir "com registros: a dica da barra traz o consumo" jq -e '.tooltip | contains("Claude, bloco de 5h: 330 tokens")' <<<"$barra"

"$consumo" --nada >/dev/null 2>&1; rc=$?
conferir "opção desconhecida é recusada" test "$rc" -ne 0

if ((falhas)); then echo "$falhas falha(s)"; exit 1; fi
echo "tudo certo"
