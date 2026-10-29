#!/usr/bin/env bash
# Suíte do jangada-core. Não instala nem executa nada do jangada.
# Requer: shellcheck, jq, python3, git.
set -uo pipefail
export LC_ALL=C.UTF-8
unset JANGADA_ISOLADO JANGADA_DELEGAR JANGADA_VALIDAR_REVISOR
cd "$(dirname "$0")/.." || exit 1
falhas=0
# Cada teste acrescenta aqui uma linha por caso pulado dentro do isolamento
# (testes/isolamento.sh e testes/isolamento.py).
JANGADA_TESTES_PULADOS="$(mktemp)"
export JANGADA_TESTES_PULADOS
trap 'rm -f "$JANGADA_TESTES_PULADOS"' EXIT
passo() { printf '\n== %s\n' "$*"; }
falha() { printf 'XX %s\n' "$*"; falhas=$((falhas + 1)); }

passo "capacidades da máquina"
testes/capacidades.sh || falha "falta capacidade exigida em JANGADA_TESTES_EXIGIR"

passo "sintaxe bash"
for f in install.sh install/*.sh migrations/*.sh bin/* testes/*.sh; do
  [[ -f "$f" ]] || continue
  bash -n "$f" || falha "bash -n: $f"
done

passo "shellcheck"
if command -v shellcheck >/dev/null; then
  shellcheck -x -S warning install.sh install/*.sh migrations/*.sh bin/* testes/*.sh || falha "shellcheck"
else
  echo "shellcheck ausente; etapa ignorada"
fi

passo "JSON"
jq empty agentes/claude/hooks.json || falha "hooks.json"
jq empty agentes/agy/hooks.json || falha "agy/hooks.json"
jq empty delegacao/roteamento.json || falha "delegacao/roteamento.json"

passo "py_compile dos pacotes"
for d in nucleo orquestracao delegacao provedores validacao agentes; do
  while IFS= read -r f; do
    python3 -B -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$f" \
      || falha "py_compile: $f"
  done < <(find "$d" -name '*.py')
done

passo "skills do Claude Code"
# O Claude Code ignora a skill sem frontmatter ou com name diferente da pasta.
for d in agentes/claude/skills/*/; do
  d="${d%/}"
  cab="$(awk 'NR == 1 && $0 != "---" {exit} NR > 1 && $0 == "---" {exit} NR > 1' "$d/SKILL.md" 2>/dev/null)"
  grep -qx "name: ${d##*/}" <<<"$cab" || falha "skill ${d##*/}: sem name igual à pasta"
  grep -q '^description:' <<<"$cab" || falha "skill ${d##*/}: sem description"
done
testes/skills.sh || falha "testes/skills.sh"

# O tema de gráficos tem um arquivo por linguagem; as cores não podem divergir.
cores_do_tema() { grep -o '^ *"\?[a-z]\+"\? *[=:] *"#[0-9A-Fa-f]\{6\}"' "$1" | tr -d ' "' | tr '=' ':' | sort; }
diff <(cores_do_tema agentes/claude/skills/graficos/tema_dv.R) <(cores_do_tema agentes/claude/skills/graficos/tema_dv.py) \
  || falha "skill graficos: tintas ou paleta diferem entre tema_dv.R e tema_dv.py"
[[ "$(cores_do_tema agentes/claude/skills/graficos/tema_dv.R | wc -l)" -eq 11 ]] \
  || falha "skill graficos: esperadas 5 tintas e 6 cores em tema_dv.R"

passo "escritas fora das pastas do jangada estão nas exceções da regra 1"
testes/regra1.sh || falha "testes/regra1.sh"

passo "contratos entre módulos"
for t in testes/contratos-*; do
  case "$t" in
    *.py) python3 "$t" ;;
    *) "$t" ;;
  esac || falha "$t"
done

passo "ajudantes dos testes dentro do isolamento"
testes/isolamento-ajudantes.sh || falha "testes/isolamento-ajudantes.sh"
python3 testes/isolamento-ajudantes.py || falha "testes/isolamento-ajudantes.py"

passo "comandos citados nos protocolos dos agentes existem em bin/"
for c in $(grep -ho '`jangada-[a-z-]*' agentes/perfis/protocolo*.md | tr -d '`' | sort -u); do
  [[ -x "bin/$c" ]] || falha "bin/$c citado no protocolo mas ausente"
done

passo "diagnóstico do ambiente"
python3 -B testes/doctor.py || falha "testes/doctor.py"

passo "registro de provedores"
if command -v jq >/dev/null; then
  testes/provedores.sh || falha "testes/provedores.sh"
else
  echo "  jq ausente, etapa ignorada"
fi

passo "jangada-validar com claude e agy falsos"
python3 testes/agente-seletor.py || falha "testes/agente-seletor.py"
if command -v git >/dev/null && command -v jq >/dev/null; then
  testes/validar.sh || falha "testes/validar.sh"
  testes/atendente.sh || falha "testes/atendente.sh"
  testes/core-independente.sh
  rc_core=$?
  if ((rc_core == 77)); then
    echo "pulado: R com lintr ausente"
  elif ((rc_core != 0)); then
    falha "testes/core-independente.sh"
  fi
else
  echo "git ou jq ausente; etapa ignorada"
fi

passo "baseline: preservação, aprovação e recuperação sintética"
python3 testes/baseline.py || falha "testes/baseline.py"
python3 testes/contexto-revisao.py || falha "testes/contexto-revisao.py"

passo "isolamento dos agentes"
testes/isolar.sh || falha "testes/isolar.sh"
testes/restaurar.sh || falha "testes/restaurar.sh"
testes/fim.sh || falha "testes/fim.sh"

passo "histórico de estados dos agentes"
testes/eventos.sh || falha "testes/eventos.sh"
testes/codex.sh || falha "testes/codex.sh"
testes/coordenador.sh || falha "testes/coordenador.sh"

passo "subagentes"
testes/subagentes.sh || falha "testes/subagentes.sh"
testes/delegar.sh || falha "testes/delegar.sh"
testes/confianca-agy-fluxo.sh || falha "testes/confianca-agy-fluxo.sh"
testes/conta-agy-saldo.sh || falha "testes/conta-agy-saldo.sh"
python3 testes/delegacao.py || falha "testes/delegacao.py"
python3 testes/modelos-tarefa.py || falha "testes/modelos-tarefa.py"
python3 testes/implementacao-agy.py || falha "testes/implementacao-agy.py"
python3 testes/avaliar-ollama.py || falha "testes/avaliar-ollama.py"
python3 testes/extracao.py || falha "testes/extracao.py"
python3 testes/orquestracao.py || falha "testes/orquestracao.py"
python3 testes/executor.py || falha "testes/executor.py"
python3 testes/recuperacao.py || falha "testes/recuperacao.py"
python3 testes/operacional.py || falha "testes/operacional.py"
python3 testes/confianca-p0.py || falha "testes/confianca-p0.py"
python3 testes/supervisao.py || falha "testes/supervisao.py"
python3 testes/acompanhamento.py || falha "testes/acompanhamento.py"
python3 testes/deterministico.py || falha "testes/deterministico.py"
python3 testes/metricas-projeto.py || falha "testes/metricas-projeto.py"
python3 testes/indicadores.py || falha "testes/indicadores.py"
python3 testes/rodadas.py || falha "testes/rodadas.py"
python3 testes/tokens-revisor.py || falha "testes/tokens-revisor.py"
python3 testes/saude.py || falha "testes/saude.py"
python3 testes/consultas-modulos.py || falha "testes/consultas-modulos.py"
python3 testes/cota-codex.py || falha "testes/cota-codex.py"
python3 testes/cotas.py || falha "testes/cotas.py"
python3 testes/codex-economico.py || falha "testes/codex-economico.py"

passo "atualização do código e migrações"
testes/update.sh || falha "testes/update.sh"
python3 testes/update-codigo.py || falha "testes/update-codigo.py"

passo "consumo do Claude"
testes/consumo.sh || falha "testes/consumo.sh"

passo "trava do install.sh contra pastas gravadas pelos agentes"
testes/install-trava.sh || falha "testes/install-trava.sh"

passo "comandos instalados em ~/.local/bin"
testes/comandos-instalados.sh || falha "testes/comandos-instalados.sh"

passo "versões"
testes/versao.sh || falha "testes/versao.sh"

passo "hooks com a configuração vazia ou inválida"
testes/hooks.sh || falha "testes/hooks.sh"

printf '\n'
pulados="$(wc -l <"$JANGADA_TESTES_PULADOS")"
((pulados == 0)) || echo "$((pulados)) caso(s) pulado(s) no isolamento"
((falhas == 0)) && echo "tudo certo" || echo "$falhas falha(s)"
exit $((falhas > 0))
