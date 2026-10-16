#!/usr/bin/env bash
# Instalação do jangada-core. Executa as etapas de install/ em ordem numérica.
#
# Uso:
#   ./install.sh                  instala tudo
#   ./install.sh 10 50            executa só as etapas que começam com 10 e 50
#   JANGADA_SIMULAR=1 ./install.sh   mostra o que seria feito, sem executar
set -euo pipefail

JANGADA_CORE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export JANGADA_CORE_PATH
# shellcheck source=install/lib.sh
source "$JANGADA_CORE_PATH/install/lib.sh"

[[ $EUID -ne 0 ]] || morrer "execute como usuário comum; o script pede sudo quando precisa"

# A pasta de onde o install.sh roda vira o JANGADA_CORE_PATH dos hooks e da sessão.
# A cópia de trabalho e os worktrees dos agentes são graváveis de dentro do
# isolamento, então instalar dali faria rodar fora dele o código que o agente
# muda. A simulação não executa nada e continua liberada, para testar a
# instalação na cópia de trabalho.
# shellcheck source=bin/jangada-config
source "$JANGADA_CORE_PATH/bin/jangada-config"
_aqui="$(cd "$JANGADA_CORE_PATH" && pwd -P)"
_motivo=""
if [[ -f "$JANGADA_CORE_PATH/.git" ]]; then
  _motivo="$_aqui é um worktree"
elif [[ -n "$JANGADA_REPO" && -d "$JANGADA_REPO" && "$(cd "$JANGADA_REPO" && pwd -P)" == "$_aqui" ]]; then
  _motivo="$_aqui é a cópia de trabalho (JANGADA_REPO)"
elif [[ -d "$JANGADA_WORKTREES" && "$_aqui/" == "$(cd "$JANGADA_WORKTREES" && pwd -P)/"* ]]; then
  _motivo="$_aqui fica em JANGADA_WORKTREES"
fi
if [[ -n "$_motivo" ]]; then
  simulando || morrer "$_motivo, gravável pelos agentes; instale de um clone em ~/.local/share/jangada-core (git clone $_aqui ~/.local/share/jangada-core)"
  aviso "$_motivo; só a simulação roda daqui"
fi
unset _aqui _motivo

simulando && aviso "modo simulação: nenhum comando será executado"

etapas=("$JANGADA_CORE_PATH"/install/[0-9][0-9]-*.sh)

deve_rodar() {
  local nome="$1" filtro
  (($# > 1)) || return 0
  shift
  for filtro in "$@"; do
    [[ "$nome" == "$filtro"-* ]] && return 0
  done
  return 1
}

for etapa in "${etapas[@]}"; do
  nome="$(basename "$etapa")"
  deve_rodar "$nome" "$@" || continue
  info "etapa $nome"
  # shellcheck disable=SC1090
  source "$etapa"
done

ok "instalação concluída"
info "rode testes/verificar.sh para conferir a instalação"
