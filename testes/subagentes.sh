#!/usr/bin/env bash
# Testa os papéis de subagente (agentes/claude/agents e agentes/agy/agents) e
# a instalação deles num HOME temporário.
#
# Uso: testes/subagentes.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }
# jq -e em silêncio: redirecionar a linha do conferir calaria o ok e a FALHA.
jqok() { jq "$@" >/dev/null; }
designer_com_referencias() {
  grep -q 'Não crie, edite, mova nem apague arquivos' "$1" && grep -q 'caminho:linha' "$1"
}
designer_sem_comandos() { ! grep -qx '  - run_command' "$1"; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

papeis=(explorador leitor pesquisador verificador auditor arquiteto otimizador redator supervisor)

# Frontmatter e corpo de um agent.md: o corpo começa depois do segundo "---".
cabeca() { awk 'NR > 1 && /^---$/ { exit } NR > 1' "$1"; }
corpo() { awk 'f; /^---$/ && ++n == 2 { f = 1 }' "$1"; }
campo() { cabeca "$1" | sed -n "s/^$2: //p"; }

# O catálogo instalado só lê; a escrita existe apenas no papel privado do controlador.
impl=agentes/agy/agents/implementador/agent.md
conferir "implementador global: subagente leitor Flash sem MCP" \
  [ "$(campo "$impl" subagent),$(campo "$impl" model),$(campo "$impl" inheritMcp)" = true,flash,false ]
conferir "implementador global: somente ferramenta de leitura" \
  [ "$(cabeca "$impl" | sed -n 's/^  - //p' | paste -sd,)" = view_file ]
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo_jangada" >"$tmp/implementador.md" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + '/delegacao')
from implementacao import PAPEL_PRIVADO
print(PAPEL_PRIVADO)
PY
conferir "implementador privado: executor Flash sem MCP" \
  [ "$(campo "$tmp/implementador.md" subagent),$(campo "$tmp/implementador.md" model),$(campo "$tmp/implementador.md" inheritMcp)" = false,flash,false ]
conferir "implementador privado: somente ferramentas de arquivo, sem comandos ou subagentes" \
  [ "$(cabeca "$tmp/implementador.md" | sed -n 's/^  - //p' | sort | paste -sd,)" = multi_replace_file_content,replace_file_content,view_file,write_to_file ]

# Papéis: mesmos nomes e mesmo texto nos dois agentes; só o frontmatter muda.
declare -A modelo_claude=([explorador]=haiku [leitor]=haiku [pesquisador]=haiku [verificador]=sonnet [auditor]=sonnet [arquiteto]=sonnet [otimizador]=sonnet [redator]=haiku [supervisor]=haiku)
for p in "${papeis[@]}"; do
  c="agentes/claude/agents/$p.md"
  a="agentes/agy/agents/$p/agent.md"
  conferir "$p: existe nos dois agentes" test -r "$c" -a -r "$a"
  conferir "$p: mesmo nome nos dois" [ "$(campo "$c" name) $(campo "$a" name)" = "$p $p" ]
  conferir "$p: mesmo texto nos dois" [ "$(corpo "$c")" = "$(corpo "$a")" ]
  conferir "$p: corpo começa por título H1" bash -c '[[ "$(sed -n "/./{p;q}" <<<"$1")" == "# "* ]]' _ "$(corpo "$a")"
  conferir "$p: modelo do Claude" [ "$(campo "$c" model)" = "${modelo_claude[$p]}" ]
  # O agy descarta em silêncio o agente com model fora de flash, pro ou
  # inherit; o esforço (low, medium, high) vai na chamada.
  conferir "$p: modelo do agy é flash" [ "$(campo "$a" model)" = flash ]
  conferir "$p: subagente no agy" [ "$(campo "$a" subagent)" = true ]
  conferir "$p: nenhuma ferramenta de escrita no Claude" \
    bash -c '! grep -qE "^tools:.*\b(Edit|Write|NotebookEdit|Agent)\b" "$1"' _ "$c"
  conferir "$p: nenhuma ferramenta de escrita no agy" \
    bash -c '! grep -qE "^  - (write_to_file|replace_file_content|multi_replace_file_content|notebook_edit|invoke_subagent|define_subagent)$" "$1"' _ "$a"
  conferir "$p: exige citar a origem" grep -qE 'caminho:linha|URL|p\. N' "$c"
  conferir "$p: não edita" grep -q 'Não crie, edite, mova nem apague arquivos' "$c"
done
designer_agy=agentes/agy/agents/designer/agent.md
conferir "designer: existe somente no agy" test -r "$designer_agy" -a ! -e agentes/claude/agents/designer.md
conferir "designer: nome e modelo do agy" \
  [ "$(campo "$designer_agy" name),$(campo "$designer_agy" model),$(campo "$designer_agy" subagent)" = designer,flash,true ]
conferir "designer: ferramentas exatas de leitura no agy" \
  [ "$(cabeca "$designer_agy" | sed -n 's/^  - //p' | sort | paste -sd,)" = find_by_name,grep_search,list_dir,view_file ]
conferir "designer: não usa run_command no agy" designer_sem_comandos "$designer_agy"
conferir "designer: não edita e exige referências" designer_com_referencias "$designer_agy"
conferir "só o pesquisador busca na web (Claude)" \
  [ "$(grep -l '^tools:.*WebSearch' agentes/claude/agents/*.md | xargs -n1 basename)" = pesquisador.md ]
conferir "pesquisador agy: busca, abertura e leitura do corpo baixado" \
  [ "$(cabeca agentes/agy/agents/pesquisador/agent.md | sed -n 's/^  - //p' | sort | paste -sd,)" = read_url_content,search_web,view_file ]
# O agy roda comandos com run_command quando o Claude do mesmo papel tem Bash.
for p in "${papeis[@]}"; do
  bash_claude=0; cmd_agy=0
  grep -qE '^tools:.*\bBash\b' "agentes/claude/agents/$p.md" && bash_claude=1
  grep -qx '  - run_command' "agentes/agy/agents/$p/agent.md" && cmd_agy=1
  conferir "$p: run_command no agy se e só se Bash no Claude" [ "$bash_claude" = "$cmd_agy" ]
done

# O leitor lê documentos de fora; o Bash dele passa pelo jangada-hook-leitor,
# que só deixa comandos de leitura. O verificador roda os testes do projeto e
# fica com o Bash livre.
conferir "leitor: hook PreToolUse no Bash" \
  bash -c 'sed -n "/^hooks:/,/^---$/p" "$1" | grep -qx "          command: jangada-hook-leitor || exit 2"' _ agentes/claude/agents/leitor.md
conferir "papel com Bash sem hook: só o verificador" [ "$(for p in "${papeis[@]}"; do
    f="agentes/claude/agents/$p.md"
    grep -qE '^tools:.*\bBash\b' "$f" && ! grep -q 'jangada-hook-leitor' "$f" && echo "$p"
  done)" = verificador ]
hook_leitor() { jq -cn --arg c "$1" '{tool_name: "Bash", tool_input: {command: $c}}' | bin/jangada-hook-leitor 2>/dev/null; }
export -f hook_leitor
for c in "pdftotext -layout -f 2 -l 3 'Relatório final.pdf' - | grep -n 'Total' | head -40" \
         "grep -c 'fim\$' notas.txt" "ls -la docs" "pdfinfo a.pdf" "tail -n 5 a.csv | cut -d, -f2"; do
  conferir "hook do leitor libera: $c" hook_leitor "$c"
done
for c in "pdftotext a.pdf saida.txt" "cat a.pdf > b" "grep x a; rm -rf ~" "echo \$(id)" "head \`id\`" \
         "rm a" "python3 -c 1" "head a && touch b" "grep x a &" "A=1 grep x a" "grep x \$HOME/.ssh/id" \
         "cat a | sh" "tee b" $'head a\ntouch b' "grep 'x" "grep x a |" "cat <a"; do
  conferir "hook do leitor recusa: ${c//$'\n'/\\n}" bash -c '! hook_leitor "$1"' _ "$c"
done
conferir "hook do leitor: recusa sai com 2" bash -c 'hook_leitor "rm a"; [ $? = 2 ]'
conferir "hook do leitor: outra ferramenta passa" \
  bash -c 'jq -cn "{tool_name: \"Read\", tool_input: {file_path: \"a\"}}" | bin/jangada-hook-leitor'
conferir "hook do leitor: evento ilegível recusa" bash -c '! echo x | bin/jangada-hook-leitor 2>/dev/null'

# No agy o hook é global (~/.gemini/config/hooks.json) e responde em JSON:
# "deny" para o comando recusado do leitor, "ask" no resto, que segue as
# permissões do agy. O leitor vem do JANGADA_AGY_PAPEL (jangada-delegar) ou do
# json do subagente na pasta brain da conversa-mãe.
leitor_id=0b7c2f4e-1111-4222-8333-444455556666
outro_id=0b7c2f4e-1111-4222-8333-777788889999
mkdir -p "$tmp/agy/brain/mae/.system_generated/subagents"
echo '{"subagentDescriptor": {"typeName": "leitor"}}' >"$tmp/agy/brain/mae/.system_generated/subagents/$leitor_id.json"
echo '{"subagentDescriptor": {"typeName": "explorador"}}' >"$tmp/agy/brain/mae/.system_generated/subagents/$outro_id.json"
hook_agy() { # conversa, comando; demais argumentos vão para o env
  local conv="$1" cmd="$2"; shift 2
  jq -cn --arg i "$conv" --arg c "$cmd" '{conversationId: $i, toolCall: {name: "run_command", args: {CommandLine: $c}}}' \
    | env -u JANGADA_AGY_PAPEL JANGADA_AGY_DIR="$tmp/agy" "$@" bin/jangada-hook-leitor --agy
}
decisao() { hook_agy "$@" | jq -r .decision; }
export -f hook_agy decisao
export tmp
conferir "hook do agy: leitor pelo papel, comando que grava recusado" \
  [ "$(decisao x "cp a b" JANGADA_AGY_PAPEL=leitor)" = deny ]
conferir "hook do agy: a recusa traz o motivo" \
  bash -c 'hook_agy x "cat a > b" JANGADA_AGY_PAPEL=leitor | jq -e ".reason | test(\"não é permitido\")" >/dev/null'
conferir "hook do agy: leitor pelo papel, leitura segue as permissões" \
  [ "$(decisao x "head a.txt" JANGADA_AGY_PAPEL=leitor)" = ask ]
conferir "hook do agy: subagente leitor pelo json da conversa" [ "$(decisao "$leitor_id" "rm a")" = deny ]
conferir "hook do agy: outro subagente não é limitado" [ "$(decisao "$outro_id" "rm a")" = ask ]
conferir "hook do agy: agente principal não é limitado" \
  [ "$(decisao 0b7c2f4e-1111-4222-8333-000000000000 "rm a")" = ask ]
conferir "hook do agy: conversa fora do formato não vira caminho" \
  [ "$(decisao "../../mae/.system_generated/subagents/$leitor_id" "rm a")" = ask ]
conferir "hook do agy: JANGADA_HOOK_DESLIGADO não solta o leitor" \
  [ "$(decisao x "rm a" JANGADA_AGY_PAPEL=leitor JANGADA_HOOK_DESLIGADO=1)" = deny ]
conferir "hook do agy: evento ilegível do leitor recusa" \
  [ "$(echo x | JANGADA_AGY_PAPEL=leitor bin/jangada-hook-leitor --agy | jq -r .decision)" = deny ]
conferir "hook do agy: evento ilegível de outro agente segue as permissões" \
  [ "$(echo x | env -u JANGADA_AGY_PAPEL bin/jangada-hook-leitor --agy | jq -r .decision)" = ask ]
mkdir -p "$tmp/pyquebrado"
printf '#!/bin/sh\nexit 1\n' >"$tmp/pyquebrado/python3"
chmod +x "$tmp/pyquebrado/python3"
conferir "hook do agy: falha do Python recusa" \
  [ "$(decisao x "head a" PATH="$tmp/pyquebrado:$PATH")" = deny ]
conferir "hook do agy: PreToolUse do run_command no hooks.json do jangada" \
  jqok -e '.jangada.PreToolUse | any(.matcher == "run_command" and any(.hooks[]; .command == "@JANGADA_CORE_PATH@/bin/jangada-hook-leitor --agy"))' agentes/agy/hooks.json

# O revisor do jangada-validar lê a entrega, conteúdo não confiável: no agy
# roda só com ferramentas de leitura e não aparece como subagente.
rev=agentes/agy/agents/revisor/agent.md
conferir "revisor do agy existe" test -r "$rev"
conferir "revisor do agy não é subagente" [ "$(campo "$rev" subagent)" = false ]
conferir "revisor do agy só lê" [ "$(sed -n '/^tools:/,/^[a-z]/p' "$rev" | grep '^  - ' | sort | tr -d ' -' | paste -sd,)" = find_by_name,grep_search,list_dir,view_file ]

# Instalação num HOME temporário.
instalar() {
  env HOME="$tmp/home" JANGADA_CORE_PATH="$repo_jangada" JANGADA_SIMULAR="${SIMULAR:-0}" \
    bash -c 'source install/lib.sh; ligar_agentes_claude; mesclar_agentes_agy' >"$tmp/saida.log" 2>&1
}
mkdir -p "$tmp/home"
SIMULAR=1 instalar
conferir "simulação não cria nada" [ -z "$(find "$tmp/home" -mindepth 1 -print -quit)" ]

mkdir -p "$tmp/home/.gemini/config" "$tmp/home/.claude/agents"
echo '{"entries":[{"path":"/outro/agents"},{"path":"/velho/jangada/agentes/agy/agents"}],"inherits":[]}' \
  >"$tmp/home/.gemini/config/agents.json"
echo "alheio" >"$tmp/home/.claude/agents/leitor.md"
instalar
agentes_json="$tmp/home/.gemini/config/agents.json"
conferir "agents.json aponta para a pasta do jangada" \
  jqok -e --arg p "$repo_jangada/agentes/agy/agents" '[.entries[].path] == ["/outro/agents", $p]' "$agentes_json"
conferir "agents.json mantém as outras chaves" jqok -e 'has("inherits")' "$agentes_json"
conferir "agents.json ganhou cópia de segurança" \
  bash -c 'ls "$1"/agents.json.jangada-*.bak >/dev/null 2>&1' _ "$tmp/home/.gemini/config"
conferir "subagente do Claude ligado ao repositório" \
  [ "$(readlink "$tmp/home/.claude/agents/explorador.md")" = "$repo_jangada/agentes/claude/agents/explorador.md" ]
conferir "arquivo alheio com o mesmo nome fica" [ "$(cat "$tmp/home/.claude/agents/leitor.md")" = alheio ]
antes="$(cat "$agentes_json")"
n_bak="$(find "$tmp/home/.gemini/config" -name '*.bak' | wc -l)"
instalar
conferir "rodar de novo não muda nada" \
  bash -c '[ "$1" = "$(cat "$2")" ] && [ "$3" = "$(find "$4" -name "*.bak" | wc -l)" ] && grep -q "já registrados" "$5"' \
  _ "$antes" "$agentes_json" "$n_bak" "$tmp/home/.gemini/config" "$tmp/saida.log"

# Links do layout antigo (default/) são trocados; links alheios ficam.
mkdir -p "$HOME/.cache"
th="$(mktemp -d "$HOME/.cache/teste-links.XXXX")"
mkdir -p "$th/.claude/skills" "$th/.claude/agents" "$th/.gemini/config"
ln -s /x/.local/share/jangada/default/claude/skills/jangada "$th/.claude/skills/jangada"
ln -s /outro/lugar/relatorio-tecnico "$th/.claude/skills/relatorio-tecnico"
ln -s /x/.local/share/jangada/default/claude/agents/explorador.md "$th/.claude/agents/explorador.md"
ln -s /outro/lugar/leitor.md "$th/.claude/agents/leitor.md"
echo '{"entries":[{"path":"/x/.local/share/jangada/default/agy/agents"},{"path":"/outro/agents"}]}' >"$th/.gemini/config/agents.json"
env HOME="$th" JANGADA_CORE_PATH="$repo_jangada" \
  bash -c 'source install/lib.sh; ligar_skill_claude; ligar_agentes_claude; mesclar_agentes_agy' >"$th/saida.log" 2>&1
conferir "link antigo default/claude/skills é trocado" \
  [ "$(readlink "$th/.claude/skills/jangada")" = "$repo_jangada/agentes/claude/skills/jangada" ]
conferir "link antigo default/claude/agents é trocado" \
  [ "$(readlink "$th/.claude/agents/explorador.md")" = "$repo_jangada/agentes/claude/agents/explorador.md" ]
conferir "link de skill alheio fica" [ "$(readlink "$th/.claude/skills/relatorio-tecnico")" = /outro/lugar/relatorio-tecnico ]
conferir "link de subagente alheio fica" [ "$(readlink "$th/.claude/agents/leitor.md")" = /outro/lugar/leitor.md ]
conferir "entrada default/agy/agents some e a nova entra" \
  jqok -e --arg p "$repo_jangada/agentes/agy/agents" '[.entries[].path] == ["/outro/agents", $p]' "$th/.gemini/config/agents.json"
rm -rf "$th"

echo
if ((falhas)); then
  echo "$falhas teste(s) falharam"
  exit 1
fi
echo "todos os testes de subagentes passaram"
