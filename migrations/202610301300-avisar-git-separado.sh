#!/usr/bin/env bash
# Avisa, uma vez, da troca do worktree pelo clone de sessão, de 30/10/2026.
#
# Sessão nova passou a ser um clone com .git próprio, que lê os objetos da
# raiz pelo alternates: um agente não move o ramo de outro nem grava objeto
# na raiz. As sessões abertas antes seguem em worktree até o
# jangada-agente-fim, sem conversão, porque converter uma sessão ativa
# trocaria o .git debaixo do agente. Enquanto alguma delas existir, os objetos
# e as refs agente/ da raiz continuam graváveis de dentro dela. A migração só
# lista essas sessões; não grava nada. Pode rodar de novo, e em simulação
# faz o mesmo que fora dela.
set -euo pipefail
JANGADA_CORE_PATH="${JANGADA_CORE_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=install/lib.sh
source "$JANGADA_CORE_PATH/install/lib.sh"
# shellcheck source=bin/jangada-config
source "$JANGADA_CORE_PATH/bin/jangada-config"

info "jangada-agente: sessões novas viram clone próprio (docs/atualizacao-e-migracoes.md, seção Git separado)"
antigas=()
for p in "$JANGADA_WORKTREES"/*/*; do
  [[ -f "$p/.git" && ! -L "$p/.git" ]] && antigas+=("$p")
done
if ((${#antigas[@]})); then
  aviso "${#antigas[@]} sessão(ões) antiga(s) em worktree seguem como estão até o jangada-agente-fim; enquanto existirem, a raiz delas continua gravável de dentro:"
  for p in "${antigas[@]}"; do aviso "  $p"; done
fi
