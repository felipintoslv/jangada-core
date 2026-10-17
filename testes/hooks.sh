#!/usr/bin/env bash
# Testa a instalação e a conferência dos hooks do Claude e do agy com o
# arquivo de configuração vazio ou inválido: a mescla trata o vazio como {} e
# grava os hooks e não mexe no arquivo inválido. A conferência do arquivo
# vazio pelo jangada-verificar é de comando opcional, fora do Core por ora.
#
# Uso: testes/hooks.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$tmp/estado"
export JANGADA_CORE_PATH="$PWD" JANGADA_SIMULAR=0
unset HYPRLAND_INSTANCE_SIGNATURE
claude_cfg="$HOME/.claude/settings.json"
agy_cfg="$HOME/.gemini/config/hooks.json"
mkdir -p "$HOME/.claude" "$HOME/.gemini/config"

mesclar() { # função da lib
  bash -c 'source install/lib.sh && "$1"' _ "$1" >"$tmp/saida" 2>&1
}
eventos_claude() { jq -r '.hooks | keys | join(" ")' agentes/claude/hooks.json; }

echo "== settings.json do Claude vazio"
: >"$claude_cfg"
mesclar mesclar_hooks_claude
conferir "a mescla grava os hooks" \
  [ "$(jq -r '.hooks | keys | join(" ")' "$claude_cfg" 2>/dev/null)" = "$(eventos_claude)" ]
conferir "a mescla não diz que já estavam instalados" bash -c '! grep -q "já instalados" "$1"' _ "$tmp/saida"
conferir "a mescla guarda a cópia do vazio" \
  bash -c 'ls "$1".jangada-*.bak >/dev/null 2>&1' _ "$claude_cfg"
mesclar mesclar_hooks_claude
conferir "rodar de novo não muda nada" grep -q "já instalados" "$tmp/saida"

echo "== settings.json do Claude inválido"
printf '{"hooks": \n' >"$claude_cfg"
mesclar mesclar_hooks_claude
conferir "a mescla avisa e não grava" \
  bash -c 'grep -q "não consegui ler" "$1" && [ "$(cat "$2")" = "{\"hooks\": " ]' _ "$tmp/saida" "$claude_cfg"

echo "== hooks.json do agy vazio"
: >"$agy_cfg"
mesclar mesclar_hooks_agy
conferir "a mescla grava os hooks" bash -c 'jq -e "$1" "$2" >/dev/null' _ '.jangada.PreToolUse and .jangada.Stop' "$agy_cfg"
conferir "a mescla não diz que já estavam instalados" bash -c '! grep -q "já instalados" "$1"' _ "$tmp/saida"
conferir "a mescla guarda a cópia do vazio" \
  bash -c 'ls "$1".jangada-*.bak >/dev/null 2>&1' _ "$agy_cfg"
mesclar mesclar_hooks_agy
conferir "rodar de novo não muda nada" grep -q "já instalados" "$tmp/saida"

echo "== hooks.json do agy inválido"
printf '{"jangada": \n' >"$agy_cfg"
mesclar mesclar_hooks_agy
conferir "a mescla avisa e não grava" \
  bash -c 'grep -q "não consegui ler" "$1" && [ "$(cat "$2")" = "{\"jangada\": " ]' _ "$tmp/saida" "$agy_cfg"

echo "== escrita atômica do settings.json"
# Quem abriu o arquivo antes da mescla continua lendo o conteúdo antigo
# inteiro: a troca é por rename, não por truncar e regravar.
printf '{"antigo": 1}\n' >"$claude_cfg"
chmod 600 "$claude_cfg"
exec 7<"$claude_cfg"
mesclar mesclar_hooks_claude
conferir "leitor aberto antes da mescla vê o arquivo antigo inteiro" \
  bash -c '[ "$(cat <&7)" = "{\"antigo\": 1}" ]'
exec 7<&-
conferir "arquivo novo é JSON com os hooks e o que já havia" jq -e '.antigo == 1 and (.hooks | length > 0)' "$claude_cfg"
conferir "permissões mantidas" bash -c '[ "$(stat -c %a "$1")" = 600 ]' _ "$claude_cfg"
conferir "sem temporário ao lado" bash -c '! ls "$1".jangada-?????? >/dev/null 2>&1' _ "$claude_cfg"

# Interrupção no meio da troca: um mv falso mata a mescla com SIGKILL.
printf '{"antigo": 2}\n' >"$claude_cfg"
mkdir -p "$tmp/mata"
printf '#!/bin/sh\nkill -KILL "$PPID"\n' >"$tmp/mata/mv"
chmod +x "$tmp/mata/mv"
PATH="$tmp/mata:$PATH" bash -c 'source install/lib.sh && mesclar_hooks_claude' >/dev/null 2>&1
conferir "interrompida, a mescla deixa o arquivo antigo inteiro" \
  bash -c '[ "$(cat "$1")" = "{\"antigo\": 2}" ]' _ "$claude_cfg"
rm -f "$claude_cfg".jangada-*

# Arquivo que é link simbólico: o link fica, o alvo é trocado.
mkdir -p "$tmp/dot"
printf '{"antigo": 3}\n' >"$tmp/dot/settings.json"
rm -f "$claude_cfg"
ln -s "$tmp/dot/settings.json" "$claude_cfg"
mesclar mesclar_hooks_claude
conferir "link simbólico preservado e alvo atualizado" \
  bash -c '[ -L "$1" ] && jq -e ".antigo == 3 and (.hooks | length > 0)" "$2" >/dev/null' _ "$claude_cfg" "$tmp/dot/settings.json"

echo "== hook do leitor sem JANGADA_CORE_PATH"
# Árvore mínima: o comando e a conferência, sem JANGADA_CORE_PATH no ambiente.
arvore="$tmp/arvore"
mkdir -p "$arvore/bin" "$arvore/agentes/claude"
cp bin/jangada-hook-leitor "$arvore/bin/"
cp agentes/claude/hook-leitor.py "$arvore/agentes/claude/"
leitor_link() { # comando; demais argumentos vão para o env
  local cmd="$1"; shift
  jq -cn --arg c "$cmd" '{tool_name: "Bash", tool_input: {command: $c}}' \
    | env "$@" "$arvore/bin/jangada-hook-leitor" 2>/dev/null
}
agy_link() { # comando, papel
  jq -cn --arg c "$1" '{conversationId: "x", toolCall: {name: "run_command", args: {CommandLine: $c}}}' \
    | env -u JANGADA_CORE_PATH JANGADA_AGY_DIR="$tmp/agy" JANGADA_AGY_PAPEL="$2" "$arvore/bin/jangada-hook-leitor" --agy | jq -r .decision
}
conferir "com JANGADA_CORE_PATH, leitura liberada" leitor_link "head a.txt" JANGADA_CORE_PATH="$arvore"
conferir "sem JANGADA_CORE_PATH, leitura liberada pela pasta do comando" leitor_link "head a.txt" -u JANGADA_CORE_PATH
leitor_link "rm a" -u JANGADA_CORE_PATH
conferir "sem JANGADA_CORE_PATH, escrita recusada com 2" [ "$?" = 2 ]
conferir "agy: outro agente segue as permissões" [ "$(agy_link "rm a" "")" = ask ]
conferir "agy: leitor que grava é recusado" [ "$(agy_link "rm a" leitor)" = deny ]

echo "== regras ao gravar (jangada-hook-regras gravacao)"
obra="$tmp/obra"
mkdir -p "$obra"
travessao=$'\xe2\x80\x94'
printf 'ver %s/notas\n' "$HOME" >"$obra/pessoal.txt"
printf 'um %s dois\n' "$travessao" >"$obra/texto.md"
printf 'um %s dois\n' "$travessao" >"$obra/texto.txt"
printf '#!/usr/bin/env bash\nrm -rf $PASTA/\n' >"$obra/script"
printf 'def f(:\n' >"$obra/quebrado.py"
printf 'limpo\n' >"$obra/limpo.md"
regras() { # JSON do evento; demais argumentos vão para o env
  local json="$1"; shift
  env "$@" bin/jangada-hook-regras gravacao <<<"$json" 2>/dev/null
}
gravou() { # arquivo
  jq -cn --arg c "$obra" --arg f "$obra/$1" \
    '{hook_event_name: "PostToolUse", cwd: $c, tool_name: "Write", tool_input: {file_path: $f}}'
}
json_ok() { jq -e "$@" >/dev/null; }
contexto() { jq -r '.hookSpecificOutput | select(.hookEventName == "PostToolUse") | .additionalContext'; }
conferir "caminho pessoal avisa" bash -c 'grep -q "pessoal.txt: caminho pessoal" <<<"$1"' _ \
  "$(regras "$(gravou pessoal.txt)" JANGADA_SESSAO=t | contexto)"
conferir "travessão em .md avisa" bash -c 'grep -q "texto.md: travessão na linha 1" <<<"$1"' _ \
  "$(regras "$(gravou texto.md)" JANGADA_SESSAO=t | contexto)"
conferir "travessão fora de .md não avisa" [ -z "$(regras "$(gravou texto.txt)" JANGADA_SESSAO=t)" ]
if command -v shellcheck >/dev/null 2>&1; then
  conferir "shellcheck em script de bash avisa" bash -c 'grep -q "SC2115" <<<"$1"' _ \
    "$(regras "$(gravou script)" JANGADA_SESSAO=t | contexto)"
else
  echo "pulado: shellcheck ausente"
fi
conferir "sintaxe Python avisa" bash -c 'grep -q "quebrado.py: erro de sintaxe Python" <<<"$1"' _ \
  "$(regras "$(gravou quebrado.py)" JANGADA_SESSAO=t | contexto)"
conferir "sintaxe Python não grava __pycache__" test ! -e "$obra/__pycache__"
conferir "arquivo limpo não avisa" [ -z "$(regras "$(gravou limpo.md)" JANGADA_SESSAO=t)" ]
conferir "sem JANGADA_SESSAO não faz nada" [ -z "$(regras "$(gravou pessoal.txt)" -u JANGADA_SESSAO)" ]
conferir "JANGADA_HOOK_DESLIGADO não faz nada" \
  [ -z "$(regras "$(gravou pessoal.txt)" JANGADA_SESSAO=t JANGADA_HOOK_DESLIGADO=1)" ]
conferir "entrada inválida sai com 0 e em silêncio" \
  bash -c '[ -z "$(JANGADA_SESSAO=t bin/jangada-hook-regras gravacao <<<"não é json")" ]'
patch="$(printf '*** Begin Patch\n*** Update File: texto.md\n@@\n*** Add File: quebrado.py\n+x\n*** End Patch')"
evento_codex() { # evento
  jq -cn --arg c "$obra" --arg p "$patch" --arg e "$1" \
    '{hook_event_name: $e, cwd: $c, tool_name: "apply_patch", tool_input: {command: $p}}'
}
export -f contexto
saida_codex="$(env JANGADA_SESSAO=t bin/jangada-hook-codex trabalhando <<<"$(evento_codex PostToolUse)" 2>/dev/null)"
conferir "Codex: apply_patch avisa pelos dois arquivos" \
  bash -c 'c="$(contexto <<<"$1")"; grep -q "texto.md: travessão" <<<"$c" && grep -q "quebrado.py: erro" <<<"$c"' _ "$saida_codex"
conferir "Codex: outro evento não escreve na saída" \
  [ -z "$(env JANGADA_SESSAO=t bin/jangada-hook-codex trabalhando <<<"$(evento_codex PreToolUse)" 2>/dev/null)" ]
conferir "Codex: sem JANGADA_SESSAO não faz nada" \
  [ -z "$(env -u JANGADA_SESSAO bin/jangada-hook-codex trabalhando <<<"$(evento_codex PostToolUse)" 2>/dev/null)" ]
conferir "hooks.json: regras só nas ferramentas que gravam" \
  json_ok '.hooks.PostToolUse | any(.matcher == "Edit|Write|MultiEdit|NotebookEdit"
    and (.hooks[0].command | endswith("jangada-hook-regras gravacao")))' agentes/claude/hooks.json

echo "== lembrete de decisões ao coordenador (jangada-hook-regras coordenacao)"
coord="$tmp/coord"
mkdir -p "$coord/.jangada" "$tmp/sem-coord"
: >"$coord/.jangada/coordenacao.md"
inicio() { # pasta, origem; demais argumentos vão para o env
  local json
  json="$(jq -cn --arg c "$1" --arg s "$2" '{hook_event_name: "SessionStart", cwd: $c, source: $s}')"
  shift 2
  env "$@" bin/jangada-hook-regras coordenacao <<<"$json" 2>/dev/null \
    | jq -r '.hookSpecificOutput | select(.hookEventName == "SessionStart") | .additionalContext'
}
conferir "depois do resumo, lembra de registrar as decisões" \
  bash -c 'grep -q "acabou de ser resumida" <<<"$1" && grep -qF "$2" <<<"$1"' _ \
  "$(inicio "$coord" compact -u JANGADA_SESSAO)" "$coord/.jangada/coordenacao.md"
conferir "ao abrir, lembra de registrar as decisões" \
  bash -c 'grep -q "Registre ali cada decisão" <<<"$1"' _ "$(inicio "$coord" startup -u JANGADA_SESSAO)"
conferir "sessão de agente não recebe o lembrete" [ -z "$(inicio "$coord" compact JANGADA_SESSAO=t)" ]
conferir "pasta sem coordenacao.md não recebe o lembrete" [ -z "$(inicio "$tmp/sem-coord" compact -u JANGADA_SESSAO)" ]
conferir "/clear não recebe o lembrete" [ -z "$(inicio "$coord" clear -u JANGADA_SESSAO)" ]
conferir "hooks.json: lembrete no início, na retomada e depois do resumo" \
  json_ok '.hooks.SessionStart | any(.matcher == "startup|resume|compact"
    and (.hooks[0].command | endswith("jangada-hook-regras coordenacao")))' agentes/claude/hooks.json

if ((falhas)); then
  echo "$falhas teste(s) dos hooks falharam"
  exit 1
fi
echo "todos os testes dos hooks passaram"
