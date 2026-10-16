#!/usr/bin/env bash
# Testa a instalação das skills (agentes/claude/skills) num HOME temporário:
# Claude Code com todas, agy sem a coordenador e Codex só com a coordenador.
#
# Uso: testes/skills.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

origem="$repo_jangada/agentes/claude/skills"
casa="$tmp/home"
# PATH sem claude, agy nem codex: só as pastas do HOME decidem o que é ligado.
limpo="$tmp/bin"
mkdir -p "$limpo" "$casa"
for c in bash dirname readlink ln mkdir date cp; do
  ln -s "$(command -v "$c")" "$limpo/$c"
done

# Uso: instalar [VAR=valor ...] -- comando do lib.sh.
instalar() {
  local amb=()
  while [[ "$1" != -- ]]; do amb+=("$1"); shift; done
  shift
  env -u CODEX_HOME HOME="$casa" PATH="$limpo" JANGADA_CORE_PATH="$repo_jangada" JANGADA_SIMULAR=0 \
    "${amb[@]}" bash -c "source install/lib.sh; $1" >"$tmp/saida.log" 2>&1
}
nomes() { find "$1" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | sort | paste -sd,; }
todas="$(find "$origem/" -mindepth 2 -maxdepth 2 -name SKILL.md -printf '%h\n' | sed 's#.*/##' | sort | paste -sd,)"

conferir "coordenador: no máximo 130 linhas" [ "$(wc -l <"$origem/coordenador/SKILL.md")" -le 130 ]
conferir "coordenador: o comando de abertura declara quem coordena" \
  grep -q '^jangada-agente --janela --coordenador VOCE ' "$origem/coordenador/SKILL.md"
conferir "coordenador: o nome declarado é claude ou codex" \
  grep -q '`VOCE` é `claude` ou `codex`' "$origem/coordenador/SKILL.md"
conferir "coordenador: sem arquivo auxiliar" [ "$(nomes "$origem/coordenador")" = SKILL.md ]

instalar JANGADA_SIMULAR=1 -- 'ligar_skill_claude; ligar_skill_agy; ligar_skill_codex'
conferir "simulação não cria nada" [ -z "$(find "$casa" -mindepth 1 -print -quit)" ]

instalar -- ligar_skill_claude
conferir "Claude Code: todas as skills ligadas" [ "$(nomes "$casa/.claude/skills")" = "$todas" ]
conferir "Claude Code: coordenador aponta para o repositório" \
  [ "$(readlink "$casa/.claude/skills/coordenador")" = "$origem/coordenador" ]

instalar -- ligar_skill_agy
conferir "agy: todas menos a coordenador" \
  [ "$(nomes "$casa/.gemini/config/skills")" = "$(tr ',' '\n' <<<"$todas" | grep -vx coordenador | paste -sd,)" ]

instalar -- ligar_skill_codex
conferir "Codex: só a coordenador" [ "$(nomes "$casa/.codex/skills")" = coordenador ]
conferir "Codex: coordenador aponta para o repositório" \
  [ "$(readlink "$casa/.codex/skills/coordenador")" = "$origem/coordenador" ]
instalar -- ligar_skill_codex
conferir "Codex: rodar de novo avisa que já está ligada" grep -q 'skill coordenador do Codex já ligada' "$tmp/saida.log"

ln -sfn /velho/jangada/agentes/claude/skills/coordenador "$casa/.codex/skills/coordenador"
instalar -- ligar_skill_codex
conferir "Codex: link antigo do jangada é trocado" \
  [ "$(readlink "$casa/.codex/skills/coordenador")" = "$origem/coordenador" ]

ln -sfn /outra/origem/coordenador "$casa/.codex/skills/coordenador"
instalar -- ligar_skill_codex
conferir "Codex: link de outra origem fica" [ "$(readlink "$casa/.codex/skills/coordenador")" = /outra/origem/coordenador ]
conferir "Codex: link de outra origem gera aviso" grep -q 'não é do jangada; mantido' "$tmp/saida.log"

rm "$casa/.codex/skills/coordenador"
mkdir "$casa/.codex/skills/coordenador"
echo alheio >"$casa/.codex/skills/coordenador/SKILL.md"
instalar -- ligar_skill_codex
conferir "Codex: pasta alheia com o mesmo nome fica" [ "$(cat "$casa/.codex/skills/coordenador/SKILL.md")" = alheio ]

instalar CODEX_HOME="$tmp/codex" -- ligar_skill_codex
conferir "Codex: CODEX_HOME muda a pasta" [ "$(readlink "$tmp/codex/skills/coordenador")" = "$origem/coordenador" ]

if ((falhas)); then
  echo "$falhas teste(s) das skills falharam"
  exit 1
fi
echo "todos os testes das skills passaram"
