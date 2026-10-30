#!/usr/bin/env bash
# Testa os dados por sessão dos provedores: conversas, memória e histórico do
# Claude, do agy e do Codex. Duas sessões de projetos distintos rodam ao mesmo
# tempo no jangada-isolar de verdade (bwrap), com um cliente falso que grava e
# lê nos caminhos que os clientes reais usam. Nenhuma lê nem altera os dados
# da outra, nenhuma vê o histórico pessoal de fora, e cada uma retoma o
# próprio ao reabrir. A configuração global segue somente leitura e o login
# segue renovável. Também: execução sem sessão (efêmera), CLAUDE_CONFIG_DIR e
# CODEX_HOME alternativos, conta do agy pelo catálogo e recusas. Credenciais e
# clientes são fictícios; nenhum provedor é chamado.
#
# Sem bwrap capaz de criar o namespace, o teste é pulado; com
# JANGADA_TESTES_EXIGIR_ISOLAMENTO=1, pular vira falha.
#
# Uso: testes/dados-provedores.sh
set -uo pipefail
export LC_ALL=C.UTF-8
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
conferir() {
  local d="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$d"; else falha "$d"; fi
}
pular() {
  if [[ "${JANGADA_TESTES_EXIGIR_ISOLAMENTO:-}" == 1 ]]; then
    falha "$* (o isolamento real é exigido)"
  else
    echo "pulado $*"
  fi
}

# Dentro de uma sessão isolada o jangada-isolar de agente não monta de novo.
if sem_autoridade; then
  pulado_no_isolamento "dados-provedores: abrir isolamento exige o controlador de fora"
  exit 0
fi
if ! bwrap --ro-bind / / --dev /dev --proc /proc true 2>/dev/null; then
  pular "dados-provedores: bwrap não cria namespace aqui"
  ((falhas == 0)) || exit 1
  exit 0
fi

# Fora do /tmp: no isolamento ele vira uma pasta vazia.
tmp="$(mktemp -d -p /var/tmp jangada-dados-provedores.XXXXXX)"
vivos=()
trap '((${#vivos[@]} == 0)) || kill "${vivos[@]}" 2>/dev/null; chmod -R u+w "$tmp" 2>/dev/null; rm -rf "$tmp"' EXIT
casa="$tmp/casa"
mkdir -p "$casa" "$tmp/config/jangada"
export GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
: >"$GIT_CONFIG_GLOBAL"
export HOME="$casa" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$casa/.local/state"
export JANGADA_CORE_PATH="$repo_jangada"
unset JANGADA_SESSAO JANGADA_ISOLADO JANGADA_AGY_CONTA CLAUDE_CONFIG_DIR CODEX_HOME CODEX_SQLITE_HOME \
  ANTIGRAVITY_GEMINI_DIR ANTIGRAVITY_APP_DATA_DIR ANTIGRAVITY_CONFIG_REL_DIR ANTIGRAVITY_EXECUTABLE_DATA_DIR \
  GEMINI_DIR JANGADA_ISOLAR_PROVEDORES JANGADA_ISOLAR_ESCRITA JANGADA_ISOLAR_CASA_LER XDG_CACHE_HOME
estado="$XDG_STATE_HOME/jangada"
mkdir -p "$estado"
marca_isolado="/tmp/.jangada-isolado-dados-provedores.$$"

# Pastas dos clientes como fora: configuração, login fictício e o histórico
# pessoal, que nenhuma sessão pode ver.
c="$casa/.claude"
mkdir -p "$c/projects/-pessoal/memory" "$c/commands"
printf '{"ficticio":"config"}\n' >"$c/settings.json"
printf 'config-claude\n' >"$c/CLAUDE.md"
printf '{"ficticio":"login-original"}\n' >"$c/.credentials.json"
printf 'conversa-pessoal\n' >"$c/projects/-pessoal/conv.jsonl"
printf 'memoria-pessoal\n' >"$c/projects/-pessoal/memory/MEMORY.md"
printf 'prompt-pessoal\n' >"$c/history.jsonl"
printf '{"projects":{}}\n' >"$casa/.claude.json"
a="$casa/.gemini/antigravity-cli"
mkdir -p "$a/conversations" "$a/agents" "$casa/.gemini/config" "$casa/.gemini/antigravity/brain" "$casa/.gemini/tmp/x"
printf 'token-original\n' >"$a/antigravity-oauth-token"
printf '{"ficticio":"settings-agy"}\n' >"$a/settings.json"
printf 'id-ficticio\n' >"$a/installation_id"
printf 'revisor\n' >"$a/agents/revisor"
printf 'agy-pessoal\n' >"$a/conversations/pessoal.pb"
printf 'agyprompt-pessoal\n' >"$a/history.jsonl"
printf 'resumo-pessoal\n' >"$a/conversation_summaries.db"
printf 'brain-pessoal\n' >"$casa/.gemini/antigravity/brain/b"
printf 'gemtmp-pessoal\n' >"$casa/.gemini/tmp/x/chat"
printf '{"ficticio":"gemini-login"}\n' >"$casa/.gemini/oauth_creds.json"
printf '{}\n' >"$casa/.gemini/config/hooks.json"
x="$casa/.codex"
mkdir -p "$x/sessions"
printf '{"ficticio":"auth"}\n' >"$x/auth.json"
printf 'model = "ficticio"\n' >"$x/config.toml"
printf 'codex-pessoal\n' >"$x/sessions/pessoal.jsonl"

# O cliente falso: grava como o Claude (conversa e memória por projeto,
# histórico por acréscimo, login por temporário e rename), como o agy
# (conversa, histórico, banco de resumos, login regravado no lugar) e como o
# Codex. Depois relata, na pasta do projeto, tudo o que enxerga com marca de
# conversa, e o que conseguiu gravar onde não devia.
cat >"$tmp/cliente.sh" <<'CLIENTE'
#!/usr/bin/env bash
modo="$1" s="$2" estado="$3" codex="$4"
c="${CLAUDE_CONFIG_DIR:-$HOME/.claude}" a="$HOME/.gemini/antigravity-cli" x="${CODEX_HOME:-$HOME/.codex}"
settings_inicial="$(cat "$a/settings.json" 2>/dev/null)"
if [[ "$modo" == escrever ]]; then
  mkdir -p "$c/projects/-p-$s/memory" || exit 10
  echo "conversa-$s" >>"$c/projects/-p-$s/conv-$s.jsonl" || exit 11
  echo "memoria-$s" >>"$c/projects/-p-$s/memory/MEMORY.md" || exit 12
  echo "prompt-$s" >>"$c/history.jsonl" || exit 13
  printf '{"ficticio":"login-%s"}\n' "$s" >"$c/.credentials.json.tmp.$s" || exit 14
  mv -f "$c/.credentials.json.tmp.$s" "$c/.credentials.json" || exit 14
  mkdir -p "$a/conversations" && echo "agy-$s" >"$a/conversations/c-$s.pb" || exit 15
  echo "agyprompt-$s" >>"$a/history.jsonl" || exit 16
  echo "resumo-$s" >>"$a/conversation_summaries.db" || exit 17
  printf 'token-%s\n' "$s" >"$a/antigravity-oauth-token" || exit 18
  printf '{"mudado":"%s"}\n' "$s" >"$a/settings.json.tmp" && mv -f "$a/settings.json.tmp" "$a/settings.json" || exit 19
  if [[ "$codex" == com-codex ]]; then
    mkdir -p "$x/sessions" && echo "codex-$s" >"$x/sessions/s-$s.jsonl" || exit 20
  fi
  sleep 2
fi
r="$PWD/visto-$s"
grep -rhoaE '(conversa|memoria|prompt|agyprompt|agy|resumo|brain|gemtmp|codex)-[a-z0-9]+' \
  "$c" "$a" "$x" "$HOME/.gemini" "$estado" 2>/dev/null | sort -u >"$r"
ls -A "$estado/provedores" 2>/dev/null | sed 's/^/provedores:/' >>"$r"
ls -A "$estado/codex" 2>/dev/null | sed 's/^/codex-estado:/' >>"$r"
echo mau >>"$c/settings.json" 2>/dev/null && echo gravou:settings >>"$r"
echo mau >>"$c/CLAUDE.md" 2>/dev/null && echo gravou:claude-md >>"$r"
[[ ! -e "$c/.claude.json" ]] || { echo mau >>"$c/.claude.json" 2>/dev/null && echo gravou:claude-json >>"$r"; }
echo mau >>"$x/auth.json" 2>/dev/null && echo gravou:auth >>"$r"
echo mau >>"$HOME/.gemini/config/hooks.json" 2>/dev/null && echo gravou:hooks >>"$r"
[[ ! -e "$HOME/.gemini/oauth_creds.json" ]] || [[ ! -s "$HOME/.gemini/oauth_creds.json" ]] || echo viu:oauth-gemini >>"$r"
[[ "$settings_inicial" != *ficticio* ]] || echo settings-agy:copia >>"$r"
grep -q 'login' "$c/.credentials.json" 2>/dev/null && echo login-claude:visivel >>"$r"
exit 0
CLIENTE

# rodar SESSÃO MODO PROVEDORES [VAR=valor...]: abre o isolamento de agente
# na pasta do projeto da sessão. SESSÃO "-" roda sem JANGADA_SESSAO, com o
# nome "efe" no relatório.
rodar() {
  local s="$1" modo="$2" provs="$3" nome codex=sem-codex
  shift 3
  nome="$s"; [[ "$s" != - ]] || nome=efe
  [[ ":$provs:" != *:codex:* ]] || codex=com-codex
  local dir="${PASTA_RODAR:-$tmp/proj-$nome}"
  mkdir -p "$tmp/proj-$nome" "$dir"
  local -a sessao=(JANGADA_SESSAO="$s")
  [[ "$s" != - ]] || sessao=()
  (cd "$dir" && env -u JANGADA_SESSAO -u JANGADA_ISOLADO "${sessao[@]}" \
    JANGADA_MARCA_ISOLADO="$marca_isolado" JANGADA_ISOLAR_PROVEDORES="$provs" "$@" \
    "$repo_jangada/bin/jangada-isolar" --provedor claude -- \
    bash "$tmp/cliente.sh" "$modo" "$nome" "$estado" "$codex")
}
visto() { grep -qxF -- "$2" "$tmp/proj-$1/visto-$1"; }
nao_visto() { [[ -f "$tmp/proj-$1/visto-$1" ]] && ! grep -qE -e "$2" "$tmp/proj-$1/visto-$1"; }

# Uma efêmera de processo morto, deixada por um SIGKILL: some na abertura.
sleep 0 & morto=$!; wait "$morto"
mkdir -p "$estado/provedores/claude/efemera-$morto/projects"
# Recuperação conjunta: pasta de execução viva fica; delegação de um
# jangada-delegar morto por SIGKILL some, salvo se um isolamento órfão ainda
# a usa (JANGADA_ISOLAR_DADOS no ambiente de um processo vivo).
sleep 300 & vivo=$!; vivos+=("$vivo")
# O nome é delegacao-<pid>-<uuid>-<n>. O do formato anterior,
# delegacao-<uuid>-<n>, não é tocado, nem quando o uuid começa por algarismos.
u=0a1b2c3d-1111-4222-8333-444455556666
antiga=delegacao-12345678-1111-4222-8333-444455556666-1
env JANGADA_ISOLAR_DADOS="delegacao-$morto-$u-3" sleep 300 & orfao=$!; vivos+=("$orfao")
mkdir -p "$estado/provedores/claude/efemera-$vivo/projects" \
  "$estado/provedores/agy-principal/delegacao-$morto-$u-1/conversations" \
  "$estado/provedores/agy-principal/delegacao-$vivo-$u-2/conversations" \
  "$estado/provedores/agy-principal/delegacao-$morto-$u-3/conversations" \
  "$estado/provedores/agy-principal/delegacao-semdono/conversations" \
  "$estado/provedores/agy-principal/$antiga/conversations"
recuperacao_preservada() {
  test -d "$estado/provedores/claude/efemera-$vivo" \
    && test -d "$estado/provedores/agy-principal/delegacao-$vivo-$u-2" \
    && test -d "$estado/provedores/agy-principal/delegacao-$morto-$u-3" \
    && test ! -e "$estado/provedores/agy-principal/delegacao-$morto-$u-1"
}

# Caso 1: duas sessões de projetos distintos, ao mesmo tempo.
rodar alfa escrever agy:codex >"$tmp/rodar-alfa" 2>&1 & pa=$!
rodar beta escrever agy:codex >"$tmp/rodar-beta" 2>&1 & pb=$!
wait "$pa"; ra=$?; wait "$pb"; rb=$?
conferir "caso 1: a sessão alfa gravou conversa, memória, histórico e login ($ra)" test "$ra" -eq 0
conferir "caso 1: a sessão beta gravou conversa, memória, histórico e login ($rb)" test "$rb" -eq 0
for s in alfa beta; do
  for m in conversa memoria prompt agy agyprompt resumo codex; do
    conferir "caso 1: $s vê o próprio $m" visto "$s" "$m-$s"
  done
done
conferir "caso 1: alfa não vê nada de beta" nao_visto alfa '-beta$'
conferir "caso 1: beta não vê nada de alfa" nao_visto beta '-alfa$'
conferir "caso 1: alfa não vê o histórico pessoal de fora" nao_visto alfa '-pessoal$'
conferir "caso 1: beta não vê o histórico pessoal de fora" nao_visto beta '-pessoal$'
conferir "caso 1: a pasta que reúne os dados por sessão aparece vazia" nao_visto alfa '^(provedores|codex-estado):'
conferir "caso 1: a configuração do Claude segue somente leitura" nao_visto alfa '^gravou:(settings|claude-md|claude-json)$'
conferir "caso 1: o login do Codex e os hooks do agy seguem somente leitura" nao_visto alfa '^gravou:(auth|hooks)$'
conferir "caso 1: o login do gemini-cli some" nao_visto alfa '^viu:oauth-gemini$'
conferir "caso 1: o agy recebe a cópia do settings.json da conta" visto alfa settings-agy:copia
conferir "caso 1: o login do Claude aparece" visto alfa login-claude:visivel
conferir "caso 1: a configuração de fora ficou intacta" \
  bash -c 'grep -qx "{\"ficticio\":\"config\"}" "$1/settings.json" && grep -qx config-claude "$1/CLAUDE.md" \
           && grep -qx "{\"ficticio\":\"auth\"}" "$2/auth.json" && grep -qx "{}" "$3"' _ "$c" "$x" "$casa/.gemini/config/hooks.json"
conferir "caso 1: a renovação do login do Claude chega a fora (rename na pasta real)" \
  grep -qE '"login-(alfa|beta)"' "$c/.credentials.json"
conferir "caso 1: a renovação do login do agy chega a fora (regravado no lugar)" \
  grep -qxE 'token-(alfa|beta)' "$a/antigravity-oauth-token"
conferir "caso 1: o settings.json do agy de fora não muda" grep -qx '{"ficticio":"settings-agy"}' "$a/settings.json"
conferir "caso 1: nada das sessões na pasta real do Claude" \
  bash -c '! grep -rqaE "(conversa|memoria|prompt)-(alfa|beta)" "$1"' _ "$c"
conferir "caso 1: nada das sessões na pasta real do agy" \
  bash -c '! grep -rqaE "(agy|agyprompt|resumo)-(alfa|beta)" "$1"' _ "$a"
conferir "caso 1: nada das sessões na pasta real do Codex" \
  bash -c '! grep -rqaE "codex-(alfa|beta)" "$1"' _ "$x"
conferir "caso 1: o histórico pessoal segue fora, intacto" \
  bash -c 'grep -qx prompt-pessoal "$1/history.jsonl" && test "$(wc -l <"$1/history.jsonl")" -eq 1 \
           && grep -qx conversa-pessoal "$1/projects/-pessoal/conv.jsonl"' _ "$c"
conferir "caso 1: os dados ficam na pasta da sessão, só do dono" \
  bash -c 'grep -qx conversa-alfa "$1/provedores/claude/alfa/projects/-p-alfa/conv-alfa.jsonl" \
           && grep -qx agy-beta "$1/provedores/agy-principal/beta/conversations/c-beta.pb" \
           && grep -qx codex-alfa "$1/codex/alfa/sessions/s-alfa.jsonl" \
           && test "$(stat -c %a "$1/provedores/claude/alfa")" = 700' _ "$estado"
conferir "caso 1: a efêmera do processo morto foi removida" test ! -e "$estado/provedores/claude/efemera-$morto"
conferir "caso 1: a delegação de jangada-delegar morto foi removida" \
  test ! -e "$estado/provedores/agy-principal/delegacao-$morto-$u-1"
conferir "caso 1: efêmera e delegação de processo vivo e delegação em uso por órfão ficam" recuperacao_preservada
conferir "caso 1: pasta delegacao-* sem PID de dono não é tocada" \
  test -d "$estado/provedores/agy-principal/delegacao-semdono"
conferir "caso 1: pasta delegacao-* do formato anterior não é tocada" \
  test -d "$estado/provedores/agy-principal/$antiga"
# A procura de quem usa a pasta lê o /proc inteiro; o environ de processo de
# outro usuário não se lê, e isso não pode chegar ao terminal.
conferir "caso 1: a limpeza não imprime erro de /proc/*/environ" \
  bash -c '! grep -q "/proc/[0-9]*/environ" "$1" "$2"' _ "$tmp/rodar-alfa" "$tmp/rodar-beta"

# Caso 2: restaurar alfa retoma o que é dela, sem o que beta gravou.
rm -f "$tmp/proj-alfa/visto-alfa"
rodar alfa ler agy:codex >"$tmp/rodar-alfa2" 2>&1
conferir "caso 2: alfa reaberta ($?)" test -f "$tmp/proj-alfa/visto-alfa"
for m in conversa memoria prompt agy agyprompt resumo codex; do
  conferir "caso 2: alfa retoma o próprio $m" visto alfa "$m-alfa"
done
conferir "caso 2: alfa reaberta não vê beta nem o pessoal" nao_visto alfa '-(beta|pessoal)$'
conferir "caso 2: a segunda recuperação não muda o resultado da primeira" recuperacao_preservada

# Fim dos processos vivos: a próxima abertura (caso 3) recolhe as pastas deles.
kill "$vivo" "$orfao"; wait "$vivo" "$orfao" 2>/dev/null

# Caso 3: sem JANGADA_SESSAO, os dados valem só durante a execução.
rodar - escrever agy >"$tmp/rodar-efe" 2>&1
conferir "caso 3: a execução sem sessão gravou ($?)" visto efe conversa-efe
conferir "caso 3: sem sessão não vê alfa, beta nem o pessoal" nao_visto efe '-(alfa|beta|pessoal)$'
conferir "caso 3: os dados efêmeros somem no fim" \
  bash -c '! compgen -G "$1/provedores/*/efemera-*" >/dev/null' _ "$estado"
conferir "caso 3: com os donos mortos, as pastas antes vivas somem" \
  bash -c '! compgen -G "$1/provedores/*/delegacao-[0-9]*-$2-*" >/dev/null && test -d "$1/provedores/agy-principal/$3"' _ "$estado" "$u" "$antiga"
conferir "caso 3: nada da execução efêmera na pasta real" \
  bash -c '! grep -rqaE "(conversa|prompt|agy)-efe" "$1" "$2"' _ "$c" "$a"

# Caso 4: CLAUDE_CONFIG_DIR e CODEX_HOME em outro lugar.
c2="$casa/claude-alt" x2="$casa/codex-alt"
mkdir -p "$c2/projects" "$x2"
printf '{"ficticio":"config-alt"}\n' >"$c2/settings.json"
printf '{"ficticio":"login-alt"}\n' >"$c2/.credentials.json"
printf '{"projects":{}}\n' >"$c2/.claude.json"
printf 'prompt-pessoalalt\n' >"$c2/history.jsonl"
printf '{"ficticio":"auth-alt"}\n' >"$x2/auth.json"
rodar gama escrever agy:codex CLAUDE_CONFIG_DIR="$c2" CODEX_HOME="$x2" >"$tmp/rodar-gama" 2>&1
conferir "caso 4: gama gravou com as pastas alternativas ($?)" visto gama conversa-gama
conferir "caso 4: gama vê o próprio Codex" visto gama codex-gama
conferir "caso 4: gama não vê alfa, beta nem o histórico da pasta alternativa" nao_visto gama '-(alfa|beta|pessoalalt|pessoal)$'
conferir "caso 4: config e .claude.json da pasta alternativa somente leitura" nao_visto gama '^gravou:'
conferir "caso 4: nada de gama na pasta alternativa do Claude" \
  bash -c '! grep -rqaE "(conversa|memoria|prompt)-gama" "$1"' _ "$c2"
conferir "caso 4: o login da pasta alternativa se renova" grep -q '"login-gama"' "$c2/.credentials.json"
conferir "caso 4: nada de gama no CODEX_HOME alternativo" bash -c '! grep -rqa codex-gama "$1"' _ "$x2"
conferir "caso 4: os dados de gama ficam na pasta da sessão" \
  bash -c 'grep -qx conversa-gama "$1/provedores/claude/gama/projects/-p-gama/conv-gama.jsonl" \
           && grep -qx codex-gama "$1/codex/gama/sessions/s-gama.jsonl"' _ "$estado"

# Caso 5: recusas. Variável que desvia o agy, CLAUDE_CONFIG_DIR relativo e
# pasta de conversas do Claude que é link.
rodar delta escrever agy ANTIGRAVITY_GEMINI_DIR="$casa/outro" >"$tmp/rodar-recusa1" 2>&1
r=$?
conferir "caso 5: ANTIGRAVITY_GEMINI_DIR recusada ($r)" \
  bash -c 'test "$1" -ne 0 && grep -q "ANTIGRAVITY_GEMINI_DIR definida" "$2"' _ "$r" "$tmp/rodar-recusa1"
rodar delta escrever agy ANTIGRAVITY_APP_DATA_DIR="$casa/outro" >"$tmp/rodar-recusa1b" 2>&1
r=$?
conferir "caso 5: ANTIGRAVITY_APP_DATA_DIR fora do padrão recusada ($r)" \
  bash -c 'test "$1" -ne 0 && grep -q "ANTIGRAVITY_APP_DATA_DIR definida" "$2"' _ "$r" "$tmp/rodar-recusa1b"
# O agy define ANTIGRAVITY_APP_DATA_DIR com a pasta padrão nos comandos que
# roda: delegar de dentro de um coordenador agy precisa abrir, sem a variável.
mkdir -p "$tmp/proj-padrao"
(cd "$tmp/proj-padrao" && env -u JANGADA_SESSAO -u JANGADA_ISOLADO JANGADA_SESSAO=omega \
  JANGADA_MARCA_ISOLADO="$marca_isolado" JANGADA_ISOLAR_PROVEDORES=agy \
  ANTIGRAVITY_APP_DATA_DIR="$casa/.gemini/antigravity-cli/" \
  "$repo_jangada/bin/jangada-isolar" --provedor claude -- \
  bash -c 'printf "%s\n" "${ANTIGRAVITY_APP_DATA_DIR-ausente}"') >"$tmp/rodar-padrao" 2>&1
r=$?
conferir "caso 5: ANTIGRAVITY_APP_DATA_DIR na pasta padrão aceita e retirada ($r)" \
  bash -c 'test "$1" -eq 0 && test "$(tail -1 "$2")" = ausente' _ "$r" "$tmp/rodar-padrao"
rodar delta escrever agy CLAUDE_CONFIG_DIR=relativo >"$tmp/rodar-recusa2" 2>&1
r=$?
conferir "caso 5: CLAUDE_CONFIG_DIR relativo recusado ($r)" \
  bash -c 'test "$1" -ne 0 && grep -q "caminho absoluto" "$2"' _ "$r" "$tmp/rodar-recusa2"
c3="$casa/claude-link"
mkdir -p "$c3" "$casa/conversas-fora"
ln -s "$casa/conversas-fora" "$c3/projects"
rodar delta escrever agy CLAUDE_CONFIG_DIR="$c3" >"$tmp/rodar-recusa3" 2>&1
r=$?
conferir "caso 5: projects como link recusado ($r)" \
  bash -c 'test "$1" -ne 0 && grep -q "é link; as conversas" "$2"' _ "$r" "$tmp/rodar-recusa3"
conferir "caso 5: nada gravado pelas recusas" bash -c '! compgen -G "$1/provedores/*/delta" >/dev/null' _ "$estado"
rodar delta escrever agy JANGADA_ISOLAR_DADOS=delegacao-t1 >"$tmp/rodar-recusa4" 2>&1
r=$?
conferir "caso 5: JANGADA_ISOLAR_DADOS com sessão recusada ($r)" \
  bash -c 'test "$1" -ne 0 && grep -q "aceita só delegacao" "$2"' _ "$r" "$tmp/rodar-recusa4"
rodar - escrever agy JANGADA_ISOLAR_DADOS=outra >"$tmp/rodar-recusa5" 2>&1
r=$?
conferir "caso 5: JANGADA_ISOLAR_DADOS sem o prefixo recusada ($r)" \
  bash -c 'test "$1" -ne 0 && grep -q "aceita só delegacao" "$2"' _ "$r" "$tmp/rodar-recusa5"
conferir "caso 5: nenhuma pasta das recusas da delegação" \
  bash -c '! compgen -G "$1/provedores/*/delegacao-t1" >/dev/null && ! compgen -G "$1/provedores/*/outra" >/dev/null' _ "$estado"

# Caso 5b: a chave da delegação guarda os dados depois da saída, para o
# jangada-delegar ler o log e a conversa; uma sessão com esse prefixo não
# a alcança e vira efêmera.
rodar - escrever agy JANGADA_ISOLAR_DADOS=delegacao-t2 >"$tmp/rodar-deleg" 2>&1
r=$?
d="$estado/provedores/agy-principal/delegacao-t2"
conferir "caso 5b: dados da delegação ficam para quem chamou ($r)" \
  bash -c 'test "$1" -eq 0 && grep -qx agy-efe "$2/conversations/c-efe.pb"' _ "$r" "$d"
rodar delegacao-t2 escrever agy >"$tmp/rodar-deleg2" 2>&1
r=$?
conferir "caso 5b: sessão delegacao-* vira efêmera ($r)" \
  bash -c 'test "$1" -eq 0 && test ! -e "$2/conversations/c-delegacao-t2.pb" && ! compgen -G "$3/provedores/*/efemera-*" >/dev/null' \
  _ "$r" "$d" "$estado"
rm -rf -- "$d"

# Caso 6: conta do agy pelo catálogo. A pasta da conta recebe a mesma
# separação, e as conversas da conta não se misturam às da principal.
conta="$estado/contas/conta1"
mkdir -p "$conta/conversations"
printf 'token-conta\n' >"$conta/antigravity-oauth-token"
printf '{"ficticio":"settings-conta"}\n' >"$conta/settings.json"
printf 'agy-pessoalconta\n' >"$conta/conversations/pessoal.pb"
printf '[{"nome":"conta1","pasta":"%s","argon":false}]\n' "$conta" >"$estado/contas/agy.json"
rodar delta escrever agy JANGADA_AGY_CONTA=conta1 >"$tmp/rodar-delta" 2>&1
conferir "caso 6: delta gravou pela conta1 ($?)" visto delta agy-delta
conferir "caso 6: delta não vê alfa, beta nem as conversas da conta" nao_visto delta '-(alfa|beta|pessoal|pessoalconta)$'
conferir "caso 6: o login da conta se renova fora" grep -qx token-delta "$conta/antigravity-oauth-token"
conferir "caso 6: o settings.json da conta não muda" grep -qx '{"ficticio":"settings-conta"}' "$conta/settings.json"
conferir "caso 6: nada de delta na pasta da conta" bash -c '! grep -rqaE "(agy|agyprompt|resumo)-delta" "$1"' _ "$conta"
conferir "caso 6: os dados de delta ficam na pasta da sessão da conta" \
  grep -qx agy-delta "$estado/provedores/agy-conta1/delta/conversations/c-delta.pb"

# Caso 7: transição. Uma sessão registrada antes da mudança, numa pasta de
# sessão, traz da pasta real só a conversa da própria pasta na primeira
# abertura; outra sessão registrada não a vê.
rm -f "$estado/contas/agy.json"
wt="$casa/.local/share/jangada-worktrees/projeto/epsilon"
mkdir -p "$wt" "$estado/agentes"
enc="${wt//[^A-Za-z0-9]/-}"
mkdir -p "$c/projects/$enc"
printf 'conversa-antigaeps\n' >"$c/projects/$enc/antiga.jsonl"
printf '{"conversa":"conv-eps-1"}\n' >"$estado/agentes/epsilon.json"
mkdir -p "$a/brain/conv-eps-1"
printf 'agy-antigaeps\n' >"$a/conversations/conv-eps-1.db"
printf 'brain-antigaeps\n' >"$a/brain/conv-eps-1/plano"
printf '{}\n' >"$estado/agentes/zeta.json"
PASTA_RODAR="$wt" rodar epsilon ler agy >"$tmp/rodar-epsilon" 2>&1
cp "$wt/visto-epsilon" "$tmp/proj-epsilon/" 2>/dev/null
conferir "caso 7: a sessão antiga retoma a conversa da própria pasta" visto epsilon conversa-antigaeps
conferir "caso 7: e a conversa do agy pelo id registrado" visto epsilon agy-antigaeps
conferir "caso 7: com o cérebro dela" visto epsilon brain-antigaeps
conferir "caso 7: e nada mais do histórico de fora" nao_visto epsilon '-(pessoal|alfa|beta)$'
conferir "caso 7: a conversa antiga segue também na pasta real" grep -qx conversa-antigaeps "$c/projects/$enc/antiga.jsonl"
rodar zeta ler agy >"$tmp/rodar-zeta" 2>&1
conferir "caso 7: outra sessão registrada não recebe a conversa" nao_visto zeta '-(antigaeps|pessoal)$'
printf 'conversa-depoiseps\n' >"$c/projects/$enc/depois.jsonl"
rm -f "$wt/visto-epsilon"
PASTA_RODAR="$wt" rodar epsilon ler agy >"$tmp/rodar-epsilon2" 2>&1
cp "$wt/visto-epsilon" "$tmp/proj-epsilon/" 2>/dev/null
conferir "caso 7: a cópia acontece só na primeira abertura" nao_visto epsilon '-depoiseps$'

if ((falhas)); then
  for f in "$tmp"/rodar-*; do
    [[ -s "$f" ]] || continue
    echo "--- ${f##*/}"; tail -n 5 "$f"
  done
  echo "$falhas verificações falharam"
  exit 1
fi
echo "todas as verificações dos dados por sessão passaram"
