#!/usr/bin/env bash
# Testa a instalação das skills (agentes/claude/skills) num HOME temporário:
# Claude Code com todas, agy sem a coordenador e Codex só com a coordenador;
# e a migração que reaplica hooks e skills do Claude Code numa instalação antiga.
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

for s in conferir-citacao conferir-referencias fichamento; do
  conferir "$s: SKILL.md com name igual à pasta" grep -qx "name: $s" "$origem/$s/SKILL.md"
  conferir "$s: description diz quando não usar" grep -q 'Não use' "$origem/$s/SKILL.md"
  conferir "$s: revisao-academica diz onde entra" grep -q "\`$s\`" "$origem/revisao-academica/SKILL.md"
done

conferir "coordenador: no máximo 130 linhas" [ "$(wc -l <"$origem/coordenador/SKILL.md")" -le 130 ]
conferir "coordenador: o comando de abertura declara quem coordena" \
  grep -q '^jangada-agente --janela --coordenador VOCE ' "$origem/coordenador/SKILL.md"
conferir "coordenador: o nome declarado é claude ou codex" \
  grep -q '`VOCE` é `claude` ou `codex`' "$origem/coordenador/SKILL.md"
for trecho in '.jangada/regras-do-dono.md' '.jangada/estado.md' '.jangada/armadilhas.md' \
  'diário' 'sessões reais, ramos e worktrees' 'resumo antes de abrir tarefas' \
  'Autorizações registradas ainda válidas' 'ausentes não autorizam inventar decisões' \
  'passagem está pronta' 'Shell antigo' 'opus' 'gpt-6-astra' \
  'aprovação do dono' 'Sem memória entre conversas' 'no limite de rodadas'; do
  conferir "coordenador: passagem orienta $trecho" grep -Fq "$trecho" "$origem/coordenador/SKILL.md"
done
for trecho in 'Atuação aberta persiste' 'mesma identidade' 'Retomar da Central' \
  'jangada-coordenador --finalizar SESSAO' 'limpe imediatamente' 'tarefas herdadas' \
  'vínculo real com o projeto' 'registro protegido' 'parecer da cabeça exigido' \
  'integração e árvore limpa' 'git branch -d RAMO' 'preservando evidências' \
  'não prova conclusão' 'Preserve e relate' 'não apague ramo não integrado'; do
  conferir "coordenador: persistência e limpeza orientam $trecho" grep -Fq "$trecho" "$origem/coordenador/SKILL.md"
done
conferir "coordenador: remove a proibição de limpar tarefas herdadas" \
  bash -c '! grep -Fq "Não apague ramos nem pastas de trabalho que você não abriu" "$1"' _ "$origem/coordenador/SKILL.md"
conferir "coordenador: mantém proibição geral para qualquer agente" \
  grep -Fq 'Nunca aprove execução fora da proteção, envio ao remoto, instalação, exclusão ou `--forcar`.' "$origem/coordenador/SKILL.md"
conferir "coordenador: restringe exceção à exclusão na limpeza autorizada de aceita" \
  grep -Fq 'Para exclusão, exceção só à limpeza autorizada de tarefa aceita do projeto, conforme Encerrar.' "$origem/coordenador/SKILL.md"
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

# Migração que reaplica hooks e skills do Claude Code, num HOME falso à parte.
migracao="$(find migrations -maxdepth 1 -name '*-ligar-hooks-e-skills-do-claude.sh' | head -n 1)"
casa2="$tmp/home2"
bin2="$tmp/bin2"
mkdir -p "$bin2" "$casa2/.claude/skills/conferir-citacao"
for c in bash dirname readlink realpath ln mkdir date cp jq sed mktemp cat chmod mv rm; do
  ln -s "$(command -v "$c")" "$bin2/$c"
done
echo alheia >"$casa2/.claude/skills/conferir-citacao/SKILL.md"
ln -s /outra/origem/fichamento "$casa2/.claude/skills/fichamento"
echo '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "/alheio/meu-hook"}]}]}}' >"$casa2/.claude/settings.json"
migrar() { # [VAR=valor ...]
  env -u CODEX_HOME HOME="$casa2" PATH="$bin2" JANGADA_CORE_PATH="$repo_jangada" JANGADA_SIMULAR=0 \
    "$@" bash "$migracao" >"$tmp/migracao.log" 2>&1
}
retrato() { find "$1" -printf '%p %y %l\n' | sort; find "$1" -type f -exec cat {} + | md5sum; }
conferir "migração: existe em migrations/" [ -n "$migracao" ]
antes="$(retrato "$casa2")"
migrar JANGADA_SIMULAR=1
conferir "migração: simulação sai com 0" [ "$?" = 0 ]
conferir "migração: simulação não altera nada" [ "$(retrato "$casa2")" = "$antes" ]
migrar
conferir "migração: sai com 0" [ "$?" = 0 ]
conferir "migração: liga a skill que falta" \
  [ "$(readlink "$casa2/.claude/skills/conferir-referencias")" = "$origem/conferir-referencias" ]
conferir "migração: pasta alheia com o mesmo nome fica" [ "$(cat "$casa2/.claude/skills/conferir-citacao/SKILL.md")" = alheia ]
conferir "migração: link alheio fica" [ "$(readlink "$casa2/.claude/skills/fichamento")" = /outra/origem/fichamento ]
conferir "migração: mescla os hooks do jangada-hook-regras" \
  grep -q "$repo_jangada/bin/jangada-hook-regras gravacao" "$casa2/.claude/settings.json"
conferir "migração: hook alheio fica" grep -q /alheio/meu-hook "$casa2/.claude/settings.json"
conferir "migração: guarda cópia do settings.json" \
  [ -n "$(find "$casa2/.claude" -maxdepth 1 -name 'settings.json.jangada-*.bak' -print -quit)" ]
depois="$(retrato "$casa2")"
migrar
conferir "migração: rodar de novo não altera nada" [ "$(retrato "$casa2")" = "$depois" ]
rm -rf "$casa2" && mkdir -p "$casa2"
migrar
conferir "migração: sem Claude Code não cria nada" [ -z "$(find "$casa2" -mindepth 1 -print -quit)" ]

if ((falhas)); then
  echo "$falhas teste(s) das skills falharam"
  exit 1
fi
echo "todos os testes das skills passaram"
