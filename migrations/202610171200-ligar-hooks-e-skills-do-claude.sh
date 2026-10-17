#!/usr/bin/env bash
# Reaplica a ligação de hooks e skills do Claude Code numa instalação existente.
#
# O jangada-update não roda install/50-agentes.sh. Sem esta migração, os hooks
# do jangada-hook-regras (aviso ao gravar, lembrete ao coordenador e regras de
# pesquisa) e as skills conferir-citacao, conferir-referencias e fichamento não
# chegam a quem já tinha instalado. Usa as mesmas funções de install/lib.sh:
# mesclar_hooks_claude acrescenta só os hooks que faltam, com cópia de
# segurança do settings.json, e ligar_skill_claude liga só as skills que
# faltam, sem mexer em link ou pasta alheia. Pode rodar de novo, e com
# JANGADA_SIMULAR=1 só mostra o que faria.
set -euo pipefail
JANGADA_CORE_PATH="${JANGADA_CORE_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=install/lib.sh
source "$JANGADA_CORE_PATH/install/lib.sh"

if tem_comando claude || [[ -d "$HOME/.claude" ]]; then
  mesclar_hooks_claude
  ligar_skill_claude
else
  info "Claude Code não encontrado; hooks e skills não ligados"
fi
