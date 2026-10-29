#!/usr/bin/env bash
# Testa a confiança do agy na abertura, no reaproveitamento e na retomada de
# tarefas: o worktree só herda a confiança de uma raiz que o usuário autorizou
# no próprio agy, e a sincronização não refaz a preparação do worktree.
#
# O settings.json do agy é um arquivo temporário (HOME falso). O agy, o tmux,
# o claude e o codex são falsos: nada vai para a rede. O agy falso só grava a
# raiz em trustedWorkspaces com FALSO_AUTORIZA=1, no papel do usuário que
# responde à pergunta nativa.
#
# Uso: testes/confianca-agy-fluxo.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }
jqok() { jq "$@" >/dev/null; }

tmp="$(realpath "$(mktemp -d)")"
trap 'rm -rf "$tmp"' EXIT
conf_agy="$tmp/home/.gemini/antigravity-cli/settings.json"
estado="$tmp/state/jangada"
raiz="$tmp/projetos/app"
wts="$tmp/home/.local/share/jangada-worktrees/app"
mkdir -p "$tmp/bin" "$tmp/sem-agy" "${conf_agy%/*}" "$tmp/config/jangada/agentes" "$estado/agentes" \
  "$estado/revisoes" "$raiz" "$tmp/arbitraria" "$tmp/outro"

cat >"$tmp/bin/agy" <<'EOF'
#!/usr/bin/env bash
pwd >>"$FALSO_DIR/agy.chamadas"
if [[ "${FALSO_AUTORIZA:-0}" == 1 ]]; then
  c="$HOME/.gemini/antigravity-cli/settings.json"
  jq --arg w "$PWD" '.trustedWorkspaces += [$w]' "$c" >"$c.novo" && mv "$c.novo" "$c"
fi
exit 0
EOF
cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case " $* " in
  *" has-session "*)
    if [[ "${FALSO_TMUX_TARDIO:-0}" == 1 && ! -e "$FALSO_DIR/primeira-consulta" ]]; then
      touch "$FALSO_DIR/primeira-consulta"
      exit 1
    fi
    [[ -e "$FALSO_DIR/sessao-viva" ]]; exit ;;
  *" attach "*) touch "$FALSO_DIR/tmux.anexou" ;;
esac
exit 0
EOF
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/claude"
cp "$tmp/bin/claude" "$tmp/bin/codex"
chmod +x "$tmp/bin"/*
# PATH sem nenhum agy, nem o do sistema.
for pasta in /usr/bin /bin; do
  for arquivo in "$pasta"/*; do
    nome="${arquivo##*/}"
    [[ "$nome" == agy || -L "$tmp/sem-agy/$nome" ]] || ln -s "$arquivo" "$tmp/sem-agy/$nome"
  done
done
for nome in tmux claude codex; do ln -sf "$tmp/bin/$nome" "$tmp/sem-agy/$nome"; done

git -C "$raiz" init -q -b main
printf '.env\n' >"$raiz/.gitignore"
printf '.env\n' >"$raiz/.worktreeinclude"
echo SEGREDO=raiz >"$raiz/.env"
mkdir "$raiz/.jangada" "$raiz/sub"
echo 'touch .preparou' >"$raiz/.jangada/preparar.sh"
git -C "$raiz" add .gitignore .worktreeinclude .jangada
git -C "$raiz" -c user.name=t -c user.email=t@t commit -qm inicio
git -C "$tmp/outro" init -q -b main
git -C "$tmp/outro" -c user.name=t -c user.email=t@t commit -qm inicio --allow-empty
git -C "$tmp/outro" worktree add -q -b agente/x "$tmp/outro-wt"

# Roda um comando do jangada no ambiente falso, sem terminal.
rodar() {
  rm -f "$tmp/tmux.anexou"
  env -u JANGADA_ISOLADO -u JANGADA_SESSAO -u JANGADA_DELEGAR -u JANGADA_VALIDAR_REVISOR \
    -u JANGADA_AGY_SETTINGS -u TMUX -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE \
    HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$tmp/state" \
    PATH="${CAMINHO:-$tmp/bin:$PATH}" JANGADA_CORE_PATH="$repo_jangada" FALSO_DIR="$tmp" \
    JANGADA_AGENTE_ESCOLHER=0 "$@" </dev/null >"$tmp/saida" 2>&1
}
# O mesmo num pseudoterminal, com RESPOSTA digitada na pergunta.
rodar_tty() {
  local resposta="$1"; shift
  printf '%s\n' "$resposta" | env -u JANGADA_ISOLADO -u JANGADA_SESSAO -u JANGADA_DELEGAR \
    -u JANGADA_VALIDAR_REVISOR -u JANGADA_AGY_SETTINGS -u TMUX -u WAYLAND_DISPLAY \
    -u HYPRLAND_INSTANCE_SIGNATURE HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" \
    XDG_STATE_HOME="$tmp/state" PATH="$tmp/bin:$PATH" JANGADA_CORE_PATH="$repo_jangada" \
    FALSO_DIR="$tmp" JANGADA_AGENTE_ESCOLHER=0 \
    script -qec "$(printf '%q ' "$@")" /dev/null >"$tmp/saida" 2>&1
}
abrir() { rodar "$repo_jangada/bin/jangada-agente" --projeto "$raiz" --agente claude "$@"; }
so_confianca() { rodar "$repo_jangada/bin/jangada-worktree-preparar" --so-confianca "$@"; }
confiaveis() { jq -c '.trustedWorkspaces' "$conf_agy"; }
vazio() { echo '{"trustedWorkspaces": [], "outra": 1}' >"$conf_agy"; }
so_raiz() { jq -n --arg w "$raiz" '{trustedWorkspaces: [$w], outra: 1}' >"$conf_agy"; }
chamadas_agy() { [[ -e "$tmp/agy.chamadas" ]] && wc -l <"$tmp/agy.chamadas" || echo 0; }

# Dentro de uma sessão isolada do jangada nenhuma sessão nova é registrada
# (trava do confianca.py). A conferência da confiança vem antes do registro,
# então só as conferências que dependem da sessão aberta são puladas.
autoridade=1
if grep -q ' /tmp/\.jangada-sem-autoridade ' /proc/self/mountinfo 2>/dev/null; then
  autoridade=0
  echo "aviso: sessão isolada; conferências de sessão aberta puladas"
fi

# Caso 1: raiz sem confiança e sem terminal. A tarefa abre, o agy fica
# indisponível e a saída diz como retomar.
vazio
abrir --nome nova1
conferir "caso 1: nada é confiado" test "$(confiaveis)" = '[]'
conferir "caso 1: informa a raiz" grep -qF "o agy não confia na raiz $raiz" "$tmp/saida"
conferir "caso 1: diz como retomar a conferência" grep -qF "jangada-agentes --confianca app--nova1" "$tmp/saida"
conferir "caso 1: sem terminal, o agy não é aberto" test "$(chamadas_agy)" = 0
if ((autoridade)); then
  conferir "caso 1: a tarefa abre mesmo sem a confiança" test -f "$estado/agentes/app--nova1.json"
  conferir "caso 1: a preparação completa copiou o ignorado" test -f "$wts/nova1/.env"
fi

# Tarefa já existente, com trabalho do agente no worktree, que a
# sincronização não pode desfazer. A cópia protegida é a que o jangada-agente
# grava em revisoes/ ao abrir a sessão.
git -C "$raiz" worktree add -q -b agente/t1 "$wts/t1"
echo SEGREDO=agente >"$wts/t1/.env"
copia_protegida() {
  jq -n --arg r "$raiz" --arg w "$wts/t1" --arg d "$1" --arg v "$2" \
    '{sessao:"app--t1", raiz:$r, worktree:$w, ramo:"agente/t1", base:"main", agente:"claude", delegar:$d, revisor:$v}' \
    >"$estado/revisoes/app--t1.json"
}
intacto() { grep -qx SEGREDO=agente "$wts/t1/.env" && [[ ! -e "$wts/t1/.preparou" ]]; }

# Caso 2: com terminal. Recusa da oferta, agy aberto sem resposta e, por fim,
# a autorização dada pelo usuário dentro do agy.
if command -v script >/dev/null 2>&1 && script -qec true /dev/null >/dev/null 2>&1; then
  rodar_tty n "$repo_jangada/bin/jangada-agente" --projeto "$raiz" --agente claude --nome t1
  conferir "caso 2: oferta recusada não abre o agy" test "$(chamadas_agy)" = 0
  conferir "caso 2: oferta recusada não confia em nada" test "$(confiaveis)" = '[]'
  conferir "caso 2: oferta recusada mantém a pendência" grep -q "confiança do agy pendente" "$tmp/saida"
  rodar_tty s "$repo_jangada/bin/jangada-agente" --projeto "$raiz" --agente claude --nome t1
  conferir "caso 2: aceita a oferta, o agy abre uma vez, na raiz" \
    bash -c '[ "$(cat "$1")" = "$2" ]' _ "$tmp/agy.chamadas" "$raiz"
  conferir "caso 2: agy fechado sem resposta não vale como autorização" test "$(confiaveis)" = '[]'
  conferir "caso 2: pergunta sem resposta mantém a pendência" grep -q "confiança do agy pendente" "$tmp/saida"
  rm -f "$tmp/agy.chamadas"
  FALSO_AUTORIZA=1 rodar_tty s "$repo_jangada/bin/jangada-agente" --projeto "$raiz" --agente claude --nome t1
  conferir "caso 2: autorizada no agy, a raiz e o worktree ficam confiáveis" \
    jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
  conferir "caso 2: sem pendência depois da autorização" bash -c '! grep -q pendente "$1"' _ "$tmp/saida"
  rm -f "$tmp/agy.chamadas"
else
  echo "aviso: sem pseudoterminal (script); caso 2 pulado"
fi

# Caso 3: raiz autorizada antes da criação.
so_raiz
abrir --nome nova2
conferir "caso 3: worktree novo herda a confiança da raiz" \
  jqok -e --arg r "$raiz" --arg w "$wts/nova2" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
conferir "caso 3: guarda o settings.json original" test -f "$conf_agy.jangada-orig"

# Caso 4: raiz autorizada depois da criação; o reaproveitamento sincroniza
# sem copiar, sem rodar .jangada/preparar.sh e sem sobrescrever.
so_raiz
abrir --nome t1
conferir "caso 4: reaproveitamento sincroniza a confiança" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
conferir "caso 4: sem cópia e sem rodar .jangada/preparar.sh" intacto
conferir "caso 4: o resto do settings.json fica" jqok -e '.outra == 1' "$conf_agy"
abrir --nome t1
conferir "caso 4: repetir não duplica a confiança" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"

# Caso 5: sessão que já existe só sincroniza, e os provedores valem os do
# registro protegido da tarefa, não os da chamada que anexa.
so_raiz
copia_protegida agy codex
touch "$tmp/sessao-viva"
abrir --nome t1 --delegacao local --revisor codex
conferir "caso 5: sessão já aberta com agy recebe a confiança, apesar das opções da chamada" \
  jqok -e --arg w "$wts/t1" '.trustedWorkspaces | index($w)' "$conf_agy"
so_raiz
copia_protegida local agy
abrir --nome t1 --delegacao local --revisor codex
conferir "caso 5: revisor agy no registro também conta" \
  jqok -e --arg w "$wts/t1" '.trustedWorkspaces | index($w)' "$conf_agy"
so_raiz
copia_protegida local codex
abrir --nome t1
conferir "caso 5: sessão já aberta sem agy não recebe o fluxo, apesar dos padrões da chamada" \
  bash -c '! grep -q "agy" "$1" && [ "$2" = 1 ]' _ "$tmp/saida" "$(jq '.trustedWorkspaces | length' "$conf_agy")"
vazio
abrir --nome t1
conferir "caso 5: sessão já aberta sem agy não recebe aviso de raiz" bash -c '! grep -q "agy" "$1"' _ "$tmp/saida"
rm -f "$tmp/sessao-viva"

# Caso 6: perfil que não usa o agy não recebe o fluxo.
vazio
abrir --nome t1 --delegacao local --revisor codex
conferir "caso 6: sem agy no perfil, nenhum aviso" bash -c '! grep -q "agy" "$1"' _ "$tmp/saida"
so_raiz
abrir --nome t1 --delegacao local --revisor codex
conferir "caso 6: sem agy no perfil, nada é sincronizado" \
  jqok -e --arg r "$raiz" '.trustedWorkspaces == [$r]' "$conf_agy"
conferir "caso 6: o agy não é aberto" test "$(chamadas_agy)" = 0
abrir --nome nova3 --delegacao local --revisor codex
conferir "caso 6: worktree novo de perfil sem agy não recebe a confiança" \
  jqok -e --arg r "$raiz" '.trustedWorkspaces == [$r]' "$conf_agy"
((autoridade)) && conferir "caso 6: o worktree novo foi preparado" test -f "$wts/nova3/.env"

# Caso 7: atualização explícita de tarefa existente, pela cópia protegida.
so_raiz
copia_protegida local codex
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 7: tarefa sem agy não é sincronizada pela opção explícita" \
  bash -c 'grep -q "não delega nem revisa pelo agy" "$1" && [ "$2" = 1 ]' _ "$tmp/saida" "$(jq '.trustedWorkspaces | length' "$conf_agy")"
vazio
if command -v script >/dev/null 2>&1 && script -qec true /dev/null >/dev/null 2>&1; then
  FALSO_AUTORIZA=1 rodar_tty s "$repo_jangada/bin/jangada-agentes" --confianca app--t1
  conferir "caso 7: tarefa sem agy não abre o agy nem com terminal" \
    bash -c '[ "$1" = 0 ] && [ "$2" = "[]" ]' _ "$(chamadas_agy)" "$(confiaveis)"
fi
copia_protegida agy codex
vazio
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 7: raiz sem confiança devolve erro" test "$?" = 1
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 7: raiz sem confiança informa e não grava" \
  bash -c 'grep -qF "não confia na raiz $2" "$1" && [ "$3" = "[]" ]' _ "$tmp/saida" "$raiz" "$(confiaveis)"
so_raiz
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 7: depois da autorização, a opção sincroniza" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
conferir "caso 7: sem cópia nem preparação" intacto

# Caso 8: estado manipulado pelo agente. O JSON gravável não decide nada.
so_raiz
copia_protegida agy codex
jq -n --arg r "$tmp/outro" --arg w "$tmp/arbitraria" '{raiz:$r, worktree:$w, dir:$w}' >"$estado/agentes/app--t1.json"
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 8: pasta declarada no estado gravável não é confiada" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
so_raiz
jq -n --arg r "$raiz" --arg w "$tmp/arbitraria" '{raiz:$r, worktree:$w}' >"$estado/agentes/forjada.json"
rodar "$repo_jangada/bin/jangada-agentes" --confianca forjada
conferir "caso 8: sessão sem cópia protegida é recusada" \
  bash -c 'grep -q "sem registro protegido" "$1" && [ "$2" = 1 ]' _ "$tmp/saida" "$(jq '.trustedWorkspaces | length' "$conf_agy")"
rodar "$repo_jangada/bin/jangada-agentes" --confianca '../agentes/forjada'
conferir "caso 8: nome de sessão com caminho é recusado" grep -q "nome de sessão inválido" "$tmp/saida"

# Caso 9: correspondência pelo Git. Só worktree registrado da raiz autorizada.
so_raiz
so_confianca "$raiz" "$tmp/arbitraria"
conferir "caso 9: pasta comum não é worktree da raiz (código 3)" test "$?" = 3
so_confianca "$raiz" "$tmp/outro-wt"
conferir "caso 9: worktree de outro repositório é recusado" test "$?" = 3
so_confianca "$raiz" "$tmp/outro"
conferir "caso 9: outro repositório é recusado" test "$?" = 3
so_confianca "$raiz" "$raiz/sub"
conferir "caso 9: subpasta da raiz é recusada" test "$?" = 3
so_confianca "$raiz/sub" "$wts/t1"
conferir "caso 9: raiz que não é topo de repositório é recusada" test "$?" = 3
git clone -q "$raiz" "$tmp/clone"
so_confianca "$raiz" "$tmp/clone"
conferir "caso 9: clone da raiz não é worktree dela" test "$?" = 3
ln -s "$tmp/arbitraria" "$tmp/atalho"
so_confianca "$raiz" "$tmp/atalho"
conferir "caso 9: link para pasta estranha é recusado" test "$?" = 3
conferir "caso 9: nenhuma recusa alterou a confiança" \
  jqok -e --arg r "$raiz" '.trustedWorkspaces == [$r]' "$conf_agy"
jq -n --arg w "$tmp/outro" '{trustedWorkspaces: [$w]}' >"$conf_agy"
so_confianca "$raiz" "$wts/t1"
conferir "caso 9: outra raiz autorizada não vale para esta (código 2)" test "$?" = 2
conferir "caso 9: raiz nova não é gravada" jqok -e --arg w "$tmp/outro" '.trustedWorkspaces == [$w]' "$conf_agy"
ln -s "$wts/t1" "$tmp/atalho-wt"
so_raiz
so_confianca "$raiz" "$tmp/atalho-wt"
conferir "caso 9: caminho com link é resolvido antes de gravar" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"

# Caso 10: a gravação é conferida.
so_raiz
mv "$conf_agy" "$tmp/settings-real"
ln -s "$tmp/settings-real" "$conf_agy"
so_confianca "$raiz" "$wts/t1"
conferir "caso 10: gravação não confirmada devolve 4" test "$?" = 4
conferir "caso 10: o alvo do link não é alterado" \
  jqok -e --arg r "$raiz" '.trustedWorkspaces == [$r]' "$tmp/settings-real"
rm -f "$conf_agy"
so_confianca "$raiz" "$wts/t1"
conferir "caso 10: sem settings.json, a raiz conta como não autorizada" test "$?" = 2
conferir "caso 10: o settings.json não é criado" test ! -e "$conf_agy"

# Caso 11: o processo isolado não sincroniza nem aciona o fluxo.
so_raiz
rodar env JANGADA_ISOLADO=1 "$repo_jangada/bin/jangada-worktree-preparar" --so-confianca "$raiz" "$wts/t1"
conferir "caso 11: isolado, a sincronização é recusada (código 5)" test "$?" = 5
rodar env JANGADA_ISOLADO=1 "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 11: isolado, a opção explícita é recusada" \
  bash -c 'grep -q "fora da sessão isolada" "$1"' _ "$tmp/saida"
conferir "caso 11: isolado, nada é gravado" jqok -e --arg r "$raiz" '.trustedWorkspaces == [$r]' "$conf_agy"

# Caso 12: sem o agy instalado. A delegação cai nos subagentes do Claude; com
# revisor agy, a conferência é adiada sem gravar nem travar.
so_raiz
copia_protegida local agy
CAMINHO="$tmp/sem-agy" rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 12: sem agy, a conferência avisa e não grava" \
  bash -c 'grep -q "agy não instalado" "$1" && [ "$2" = 1 ]' _ "$tmp/saida" "$(jq '.trustedWorkspaces | length' "$conf_agy")"
CAMINHO="$tmp/sem-agy" abrir --nome t1 --revisor agy
conferir "caso 12: sem agy, a abertura segue" \
  bash -c 'grep -q "agy não instalado" "$1" && [ "$2" = 1 ]' _ "$tmp/saida" "$(jq '.trustedWorkspaces | length' "$conf_agy")"

# Caso 13: restauração de sessão interrompida.
jq -n --arg d "$wts/t1" --arg a "$(date -Iseconds)" \
  '{estado:"trabalhando", agente:"claude", dir:$d, worktree:$d, atualizado:$a}' >"$estado/agentes/app--t1.json"
vazio
copia_protegida agy codex
rodar "$repo_jangada/bin/jangada-agentes" --restaurar app--t1
conferir "caso 13: restauração sem confiança avisa e não grava" \
  bash -c 'grep -qF "não confia na raiz $2" "$1" && [ "$3" = "[]" ]' _ "$tmp/saida" "$raiz" "$(confiaveis)"
((autoridade)) && conferir "caso 13: restauração sem confiança segue" grep -q "restaurada: app--t1" "$tmp/saida"
conferir "caso 13: restauração não abre o agy" test "$(chamadas_agy)" = 0
so_raiz
copia_protegida agy codex
jq '.estado = "trabalhando"' "$estado/agentes/app--t1.json" >"$tmp/json" && cp "$tmp/json" "$estado/agentes/app--t1.json"
rodar "$repo_jangada/bin/jangada-agentes" --restaurar app--t1
conferir "caso 13: restauração sincroniza depois da autorização" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
conferir "caso 13: restauração não copia nem prepara" intacto
# Provedores calculados na restauração divergem do registro protegido.
printf 'COMANDO=claude\nJANGADA_DELEGAR=local\n' >"$tmp/config/jangada/agentes/semagy.conf"
estado_t1() {
  jq -n --arg d "$wts/t1" --arg a "$(date -Iseconds)" --arg p "$1" --arg v "$2" \
    '{estado:"trabalhando", agente:"claude", dir:$d, worktree:$d, atualizado:$a, perfil:$p, revisor:$v}
     | with_entries(select(.value != ""))' >"$estado/agentes/app--t1.json"
}
so_raiz
copia_protegida agy codex
estado_t1 semagy codex
rodar "$repo_jangada/bin/jangada-agentes" --restaurar app--t1
conferir "caso 13: registro protegido com agy sincroniza, apesar do perfil do estado" \
  jqok -e --arg r "$raiz" --arg w "$wts/t1" '.trustedWorkspaces == [$r, $w]' "$conf_agy"
vazio
copia_protegida local codex
estado_t1 "" ""
rodar "$repo_jangada/bin/jangada-agentes" --restaurar app--t1
conferir "caso 13: registro protegido sem agy não recebe o fluxo na restauração" \
  bash -c '! grep -q "não confia" "$1" && [ "$2" = "[]" ]' _ "$tmp/saida" "$(confiaveis)"

# Caso 14: projetos homônimos. Duas raízes com o mesmo nome de pasta e a
# mesma tarefa dão o mesmo identificador de sessão; a chamada feita pelo
# segundo projeto deve recusar o anexo sem criar worktree, sem preparar
# e sem levar confiança a pasta nenhuma. A raiz e o worktree da sessão aberta
# vêm do registro protegido.
raiz_b="$tmp/homonimo/app"
mkdir -p "$raiz_b/.jangada"
git -C "$raiz_b" init -q -b main
printf '.env\n' >"$raiz_b/.gitignore"
printf '.env\n' >"$raiz_b/.worktreeinclude"
echo SEGREDO=homonimo >"$raiz_b/.env"
echo 'touch "$FALSO_DIR/preparou-homonimo"' >"$raiz_b/.jangada/preparar.sh"
git -C "$raiz_b" add .gitignore .worktreeinclude .jangada
git -C "$raiz_b" -c user.name=t -c user.email=t@t commit -qm inicio
registro() {
  jq -n --arg s "$1" --arg r "$2" --arg w "$3" \
    '{sessao:$s, raiz:$r, worktree:$w, agente:"claude", delegar:"agy", revisor:"codex"}
     | with_entries(select(.value != ""))' >"$estado/revisoes/$1.json"
}
duas_raizes() { jq -n --arg a "$raiz" --arg b "$raiz_b" '{trustedWorkspaces: [$a, $b]}' >"$conf_agy"; }
so_as_raizes() { jqok -e --arg a "$raiz" --arg b "$raiz_b" '.trustedWorkspaces == [$a, $b]' "$conf_agy"; }
abrir_b() { rodar "$repo_jangada/bin/jangada-agente" --projeto "$raiz_b" --agente claude "$@"; }
sem_preparo_b() {
  [[ ! -e "$tmp/preparou-homonimo" ]] && ! grep -rqsx SEGREDO=homonimo "$wts" \
    && [[ -z "$(git -C "$raiz_b" branch --list 'agente/*')" ]] \
    && [[ "$(git -C "$raiz_b" worktree list | wc -l)" == 1 ]]
}
touch "$tmp/sessao-viva"

# O worktree da sessão do primeiro projeto continua no lugar.
duas_raizes
copia_protegida agy codex
abrir_b --nome t1
conferir "caso 14: homônimo sai com erro" test "$?" = 2
conferir "caso 14: homônimo não anexa a sessão alheia" test ! -e "$tmp/tmux.anexou"
conferir "caso 14: chamada do homônimo é recusada com a pasta da sessão aberta" \
  grep -qF "a sessão app--t1 já existe e é de outra pasta (raiz $raiz, worktree $wts/t1)" "$tmp/saida"
conferir "caso 14: chamada do homônimo não sincroniza nada" so_as_raizes
conferir "caso 14: chamada do homônimo não cria worktree, não copia e não prepara" sem_preparo_b
conferir "caso 14: o worktree da sessão aberta fica como estava" intacto
abrir --nome t1
conferir "caso 14: o mesmo projeto continua anexando a sessão" test -e "$tmp/tmux.anexou"
conferir "caso 14: a chamada do projeto da sessão sincroniza o worktree dela" \
  jqok -e --arg a "$raiz" --arg b "$raiz_b" --arg w "$wts/t1" '.trustedWorkspaces == [$a, $b, $w]' "$conf_agy"

# O worktree do primeiro projeto sumiu: o homônimo não cria o dele no mesmo
# caminho, e o projeto da sessão também não recria nem prepara.
git -C "$raiz" worktree add -q -b agente/h1 "$wts/h1"
registro app--h1 "$raiz" "$wts/h1"
git -C "$raiz" worktree remove --force "$wts/h1"
duas_raizes
abrir_b --nome h1
conferir "caso 14: homônimo com worktree ausente sai com erro" test "$?" = 2
conferir "caso 14: homônimo com worktree ausente não anexa" test ! -e "$tmp/tmux.anexou"
conferir "caso 14: o homônimo não cria worktree no caminho da sessão alheia" test ! -e "$wts/h1"
conferir "caso 14: sem cópia, sem preparação e sem ramo no homônimo" sem_preparo_b
conferir "caso 14: nada é confiado" so_as_raizes
conferir "caso 14: a recusa cita a raiz da sessão aberta" grep -qF "é de outra pasta (raiz $raiz," "$tmp/saida"
abrir --nome h1
conferir "caso 14: worktree registrado que sumiu é recusado e não é recriado" \
  bash -c 'grep -q "o worktree do registro protegido dela não existe" "$1" && [ ! -e "$2" ]' _ "$tmp/saida" "$wts/h1"
conferir "caso 14: worktree que sumiu não é confiado" so_as_raizes

# O caminho registrado existe, mas é worktree do homônimo: os caminhos da
# chamada batem com o registro e quem recusa é o Git.
git -C "$raiz_b" worktree add -q -b copia/h1 "$wts/h1"
abrir --nome h1
conferir "caso 14: worktree que diverge da raiz registrada é recusado pelo Git" \
  grep -qF "$wts/h1 não é worktree do repositório em $raiz" "$tmp/saida"
conferir "caso 14: worktree divergente não é confiado" so_as_raizes
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--h1
conferir "caso 14: a opção explícita também recusa o worktree divergente" \
  bash -c 'grep -qF "não é worktree do repositório em" "$1"' _ "$tmp/saida"
conferir "caso 14: a opção explícita não confia no worktree divergente" so_as_raizes
git -C "$raiz_b" worktree remove --force "$wts/h1"
git -C "$raiz_b" branch -qD copia/h1

# Sessão direta na raiz, sem worktree.
registro app "$raiz" ""
vazio
abrir_b --direto
conferir "caso 14: homônimo direto sai com erro" test "$?" = 2
conferir "caso 14: homônimo direto não anexa" test ! -e "$tmp/tmux.anexou"
conferir "caso 14: sessão direta do homônimo é recusada" \
  grep -qF "a sessão app já existe e é de outra pasta (raiz $raiz)" "$tmp/saida"
conferir "caso 14: sessão direta do homônimo não recebe a conferência da raiz dele" \
  bash -c '! grep -q "não confia na raiz" "$1" && [ "$2" = "[]" ]' _ "$tmp/saida" "$(confiaveis)"
rm -f "$tmp/primeira-consulta"
FALSO_TMUX_TARDIO=1 abrir_b --direto
conferir "caso 14: sessão alheia que aparece na segunda consulta é recusada" test "$?" = 2
conferir "caso 14: sessão alheia tardia não é anexada" test ! -e "$tmp/tmux.anexou"
registro app--t1 "$raiz" ""
abrir --nome t1
conferir "caso 14: chamada com worktree não vale para registro sem worktree" \
  bash -c 'grep -q "é de outra pasta" "$1" && [ "$2" = "[]" ]' _ "$tmp/saida" "$(confiaveis)"

# Registro protegido ausente, ilegível ou com caminho que não serve.
recusado() { grep -q "$1" "$tmp/saida" && so_as_raizes && [[ "$(chamadas_agy)" == 0 ]]; }
duas_raizes
rm -f "$estado/revisoes/app--t1.json"
abrir --nome t1
conferir "caso 14: sessão aberta sem registro protegido é recusada" recusado "sem registro protegido válido"
abrir --nome t1 --delegacao local --revisor codex
conferir "caso 14: sem registro, as opções da chamada não dispensam a recusa" recusado "sem registro protegido válido"
echo lixo >"$estado/revisoes/app--t1.json"
abrir --nome t1
conferir "caso 14: registro protegido ilegível é recusado" recusado "sem registro protegido válido"
registro app--t1 "" "$wts/t1"
abrir --nome t1
conferir "caso 14: registro sem raiz é recusado" recusado "sem registro protegido válido"
registro app--t1 "projetos/app" "$wts/t1"
abrir --nome t1
conferir "caso 14: registro com raiz relativa é recusado" recusado "sem registro protegido válido"
registro app--t1 "$raiz" "$wts/t1"
jq 'del(.agente)' "$estado/revisoes/app--t1.json" >"$tmp/json" && cp "$tmp/json" "$estado/revisoes/app--t1.json"
abrir --nome t1
conferir "caso 14: registro sem agente é recusado" recusado "sem registro protegido válido"
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 14: a opção explícita devolve erro para registro sem agente" test "$?" = 1
conferir "caso 14: a opção explícita diz que o registro é inválido" recusado "sem registro protegido válido"
jq '.agente = 7' "$estado/revisoes/app--t1.json" >"$tmp/json" && cp "$tmp/json" "$estado/revisoes/app--t1.json"
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 14: a opção explícita recusa agente de tipo errado" recusado "sem registro protegido válido"
registro app--t1 "$raiz" "$tmp/sumiu"
abrir --nome t1
conferir "caso 14: registro com worktree inexistente é recusado" recusado "o worktree do registro protegido dela não existe"
registro app--t1 "$raiz" "$tmp/arbitraria"
abrir --nome t1
conferir "caso 14: registro com outro worktree é recusado" recusado "é de outra pasta"
# Campo de tipo errado não vira sessão direta nem provedor padrão.
tipo_errado() {
  registro app--t1 "$raiz" "$wts/t1"
  jq "$1" "$estado/revisoes/app--t1.json" >"$tmp/json" && cp "$tmp/json" "$estado/revisoes/app--t1.json"
}
for filtro in '.worktree = 7' '.worktree = {"a": 1}' '.worktree = ["/tmp"]' '.worktree = false' \
  '.worktree = "wts/t1"' '.raiz = 7' '.raiz = null' '.delegar = 7' '.revisor = {"a": 1}' \
  '.sessao = "app--outra"' 'del(.sessao)' '[.]'; do
  tipo_errado "$filtro"
  abrir --nome t1
  conferir "caso 14: abertura recusa registro com $filtro" recusado "sem registro protegido válido"
  rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
  conferir "caso 14: a opção explícita devolve erro com $filtro" test "$?" = 1
  conferir "caso 14: a opção explícita recusa registro com $filtro" recusado "sem registro protegido válido"
done
registro app--t1 "$raiz" "$tmp/sumiu"
rodar "$repo_jangada/bin/jangada-agentes" --confianca app--t1
conferir "caso 14: a opção explícita devolve erro com worktree inexistente" test "$?" = 1
conferir "caso 14: a opção explícita diz que o worktree registrado não existe" \
  recusado "o worktree do registro protegido não existe"
# O estado gravável pelo agente aponta a pasta desta chamada; não vale.
jq -n --arg r "$raiz" --arg w "$wts/t1" '{raiz:$r, worktree:$w, dir:$w, agente:"claude", delegar:"agy"}' >"$estado/agentes/app--t1.json"
rm -f "$estado/revisoes/app--t1.json"
abrir --nome t1
conferir "caso 14: o estado gravável não substitui o registro protegido" recusado "sem registro protegido válido"
rm -f "$tmp/sessao-viva"

# Restauração com registro protegido ausente ou inválido: a sessão volta, com
# o aviso e sem confiança.
restaurar_t1() {
  jq -n --arg d "$wts/t1" --arg a "$(date -Iseconds)" \
    '{estado:"trabalhando", agente:"claude", dir:$d, worktree:$d, raiz:$d, delegar:"agy", atualizado:$a}' \
    >"$estado/agentes/app--t1.json"
  rodar "$repo_jangada/bin/jangada-agentes" --restaurar app--t1
}
duas_raizes
rm -f "$estado/revisoes/app--t1.json"
restaurar_t1
conferir "caso 14: restauração sem registro protegido avisa e não confia" recusado "app--t1: sem registro protegido válido"
((autoridade)) && conferir "caso 14: restauração sem registro protegido segue" grep -q "restaurada: app--t1" "$tmp/saida"
echo lixo >"$estado/revisoes/app--t1.json"
restaurar_t1
conferir "caso 14: restauração com registro ilegível avisa e não confia" recusado "app--t1: sem registro protegido válido"
tipo_errado '.worktree = 7'
restaurar_t1
conferir "caso 14: restauração com worktree de tipo errado avisa e não confia" recusado "app--t1: sem registro protegido válido"
((autoridade)) && conferir "caso 14: restauração com registro inválido segue" grep -q "restaurada: app--t1" "$tmp/saida"
tipo_errado 'del(.agente)'
restaurar_t1
conferir "caso 14: restauração com registro sem agente avisa e não confia" recusado "app--t1: sem registro protegido válido"
registro app--t1 "$raiz" "$tmp/sumiu"
restaurar_t1
conferir "caso 14: restauração com worktree registrado inexistente avisa e não confia" \
  recusado "o worktree do registro protegido não existe"
registro app--t1 "$raiz" "$wts/t1"
restaurar_t1
conferir "caso 14: restauração com registro válido sincroniza" \
  jqok -e --arg a "$raiz" --arg b "$raiz_b" --arg w "$wts/t1" '.trustedWorkspaces == [$a, $b, $w]' "$conf_agy"

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "confiança do agy na abertura e na retomada: tudo passou"
