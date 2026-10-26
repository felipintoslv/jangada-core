#!/usr/bin/env bash
# Testa a trava do install.sh: fora da simulação ele recusa rodar de pasta que
# os agentes gravam (worktree, JANGADA_REPO, JANGADA_WORKTREES e JANGADA_PROJETOS,
# onde fica a cópia de trabalho do Core) e aceita um clone fora delas.
#
# Nenhuma etapa de install/ roda: o filtro "99" não casa com etapa alguma, então
# o install.sh só passa pela trava. HOME, XDG_CONFIG_HOME e a configuração são
# temporários.
#
# Uso: testes/install-trava.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }

if [[ $EUID -eq 0 ]]; then
  echo "pulado: o install.sh recusa o usuário root antes da trava"
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home" "$tmp/state" "$tmp/projetos" "$tmp/wt" "$tmp/fora"

# Cópia mínima do que o install.sh lê; nenhuma etapa vai junto.
copiar_core() {
  local destino="$1"
  mkdir -p "$destino/bin" "$destino/install"
  cp "$repo_jangada/install.sh" "$destino/install.sh"
  cp "$repo_jangada/bin/jangada-config" "$destino/bin/jangada-config"
  cp "$repo_jangada/install/lib.sh" "$destino/install/lib.sh"
}

# rodar PASTA SIMULAR [LINHA_DO_CONF...]: roda o install.sh da PASTA com a
# configuração dada. Saída e código ficam em $saida e $rc.
rodar() {
  local pasta="$1" simular="$2"; shift 2
  rm -rf "$tmp/cfg"; mkdir -p "$tmp/cfg/jangada"
  {
    printf 'JANGADA_PROJETOS=%s\n' "$tmp/projetos"
    printf 'JANGADA_WORKTREES=%s\n' "$tmp/wt"
    (($#)) && printf '%s\n' "$@"
  } >"$tmp/cfg/jangada/jangada.conf"
  saida="$(env -i PATH="$PATH" LC_ALL=C.UTF-8 HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/cfg" \
    XDG_STATE_HOME="$tmp/state" JANGADA_SIMULAR="$simular" bash "$pasta/install.sh" 99 2>&1)"
  rc=$?
}

recusa() {
  local d="$1" trecho="$2"
  if ((rc == 1)) && [[ "$saida" == *"gravável pelos agentes"* && "$saida" == *"$trecho"* \
    && "$saida" == *"~/.local/share/jangada-core"* && "$saida" != *"instalação concluída"* ]]; then
    ok "$d"
  else
    falha "$d (código $rc): $saida"
  fi
}

aceita() {
  local d="$1"
  if ((rc == 0)) && [[ "$saida" == *"instalação concluída"* ]]; then
    ok "$d"
  else
    falha "$d (código $rc): $saida"
  fi
}

# Cópia de trabalho do Core dentro de JANGADA_PROJETOS, sem JANGADA_REPO
# apontando para ela (o JANGADA_REPO padrão é a cópia do Shell).
copiar_core "$tmp/projetos/migracao-jangada-core"
git -C "$tmp/projetos/migracao-jangada-core" init -q
rodar "$tmp/projetos/migracao-jangada-core" 0
recusa "recusa a cópia de trabalho do Core dentro de JANGADA_PROJETOS" "fica em JANGADA_PROJETOS"

# Subpasta de JANGADA_PROJETOS também conta.
copiar_core "$tmp/projetos/grupo/core"
rodar "$tmp/projetos/grupo/core" 0
recusa "recusa uma subpasta de JANGADA_PROJETOS" "fica em JANGADA_PROJETOS"

# Link simbólico para fora não esconde a pasta real.
ln -s "$tmp/projetos/migracao-jangada-core" "$tmp/fora/atalho"
rodar "$tmp/fora/atalho" 0
recusa "recusa um link simbólico para JANGADA_PROJETOS" "fica em JANGADA_PROJETOS"

# Os três casos antigos.
copiar_core "$tmp/fora/worktree"
printf 'gitdir: %s\n' "$tmp/fora/gitdir" >"$tmp/fora/worktree/.git"
rodar "$tmp/fora/worktree" 0
recusa "recusa um worktree" "é um worktree"

copiar_core "$tmp/fora/copia"
git -C "$tmp/fora/copia" init -q
rodar "$tmp/fora/copia" 0 "JANGADA_REPO=$tmp/fora/copia"
recusa "recusa a cópia de trabalho apontada por JANGADA_REPO" "(JANGADA_REPO)"

copiar_core "$tmp/wt/proj/tarefa"
rodar "$tmp/wt/proj/tarefa" 0
recusa "recusa uma pasta em JANGADA_WORKTREES" "fica em JANGADA_WORKTREES"

# Clone fora de todas essas pastas.
copiar_core "$tmp/fora/clone"
git -C "$tmp/fora/clone" init -q
rodar "$tmp/fora/clone" 0 "JANGADA_REPO=$tmp/fora/copia"
aceita "aceita um clone fora das pastas gravadas pelos agentes"

# Nome que só começa igual a JANGADA_PROJETOS não é subpasta dele.
copiar_core "$tmp/projetos-outro/core"
git -C "$tmp/projetos-outro/core" init -q
rodar "$tmp/projetos-outro/core" 0
aceita "aceita uma pasta irmã com prefixo igual ao de JANGADA_PROJETOS"

# A simulação continua liberada das pastas recusadas, com aviso.
rodar "$tmp/projetos/migracao-jangada-core" 1
if ((rc == 0)) && [[ "$saida" == *"só a simulação roda daqui"* && "$saida" == *"instalação concluída"* ]]; then
  ok "simulação liberada da cópia de trabalho do Core"
else
  falha "simulação liberada da cópia de trabalho do Core (código $rc): $saida"
fi

((falhas == 0)) && echo "tudo certo" || echo "$falhas falha(s)"
exit $((falhas > 0))
