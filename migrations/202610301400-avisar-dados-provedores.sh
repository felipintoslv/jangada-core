#!/usr/bin/env bash
# Avisa, uma vez, dos dados por sessão do Claude e do agy, de 30/10/2026.
#
# Conversas, histórico e memória de cada sessão de agente passaram a ficar em
# $JANGADA_ESTADO/provedores. Uma sessão registrada antes recebe, na primeira
# abertura, a cópia só da própria conversa; o histórico global não é copiado e
# as conversas antigas ficam onde estão. A migração não grava nada. Pode rodar
# de novo, e em simulação faz o mesmo que fora dela.
set -euo pipefail
JANGADA_CORE_PATH="${JANGADA_CORE_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=install/lib.sh
source "$JANGADA_CORE_PATH/install/lib.sh"
# shellcheck source=bin/jangada-config
source "$JANGADA_CORE_PATH/bin/jangada-config"

info "jangada-isolar: conversas e memória do Claude e do agy passam a ser por sessão (docs/isolamento.md, seção Dados por sessão dos provedores)"
aviso "o histórico global não é copiado; uma sessão antiga traz só a própria conversa na primeira abertura, e as conversas antigas ficam onde estão"
for v in ANTIGRAVITY_GEMINI_DIR ANTIGRAVITY_APP_DATA_DIR ANTIGRAVITY_CONFIG_REL_DIR \
         ANTIGRAVITY_EXECUTABLE_DATA_DIR GEMINI_DIR; do
  [[ -z "${!v+x}" ]] || aviso "$v está definida: o isolamento recusa abrir o agy enquanto ela existir"
done
