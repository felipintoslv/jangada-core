#!/usr/bin/env bash
# Avisa, uma vez, da mudança de padrão do jangada-isolar de 30/10/2026.
#
# A casa mínima, o ambiente mínimo, o keyring fechado sem item e o login só
# dos provedores concedidos passaram a ser o padrão. Quem dependia do modo
# antigo vê aqui o que muda na própria configuração e qual variável o traz de
# volta. A migração não grava nada: religar o modo antigo por conta própria
# desfaria a proteção sem o dono decidir. Pode rodar de novo, e em simulação
# faz o mesmo que fora dela.
set -euo pipefail
JANGADA_CORE_PATH="${JANGADA_CORE_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=install/lib.sh
source "$JANGADA_CORE_PATH/install/lib.sh"
# shellcheck source=bin/jangada-config
source "$JANGADA_CORE_PATH/bin/jangada-config"

conf="$JANGADA_CONFIG/jangada.conf"
info "jangada-isolar: novos padrões de proteção de credenciais (docs/isolamento.md, seção Modos e transição)"
if [[ -z "${JANGADA_ISOLAR_CASA:-}" ]]; then
  aviso "a pasta pessoal agora começa vazia no agente; para algo dela, JANGADA_ISOLAR_CASA_LER em $conf (modo antigo: JANGADA_ISOLAR_CASA=inteira)"
fi
if [[ -z "${JANGADA_ISOLAR_AMBIENTE:-}" ]]; then
  aviso "o agente agora recebe só a lista base de variáveis; para outra, JANGADA_ISOLAR_AMBIENTE_MANTER em $conf (modo antigo: JANGADA_ISOLAR_AMBIENTE=herdado)"
fi
if [[ -z "${JANGADA_ISOLAR_KEYRING_ITEM:-}" && -z "${JANGADA_ISOLAR_KEYRING:-}" ]] && tem_comando agy; then
  aviso "sem JANGADA_ISOLAR_KEYRING_ITEM, o keyring fica fechado ao agy (modo antigo: JANGADA_ISOLAR_KEYRING=servico)"
fi
if [[ -z "${JANGADA_ISOLAR_PROVEDORES:-}" ]]; then
  aviso "cada sessão recebe só o login do próprio provedor e do destino da delegação; para outro, JANGADA_ISOLAR_PROVEDORES em $conf"
fi
