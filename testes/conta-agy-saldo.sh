#!/usr/bin/env bash
# Testa a conta do agy escolhida na abertura da sessão: a que confia na pasta e
# tem o maior saldo conhecido do grupo gemini, registrada para a sessão e
# repassada ao jangada-isolar.
#
# O catálogo, as medidas e os settings.json das contas são arquivos de uma
# pasta temporária. O agy, o tmux, o claude e o codex são falsos: nenhum caso
# chama o agy real nem a rede, e o agy falso registra qualquer chamada.
#
# Uso: testes/conta-agy-saldo.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(realpath "$(mktemp -d)")"
trap 'rm -rf "$tmp"' EXIT
estado="$tmp/state/jangada"
raiz="$tmp/projetos/app"
mkdir -p "$tmp/bin" "$tmp/home" "$tmp/config/jangada/agentes" "$estado/revisoes" "$estado/agentes" \
  "$estado/contas/conta1" "$estado/contas/conta2" "$raiz"

cat >"$tmp/bin/agy" <<'EOF'
#!/usr/bin/env bash
pwd >>"$FALSO_DIR/agy.chamadas"
exit 0
EOF
cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FALSO_DIR/tmux.log"
case " $* " in
  *" has-session "*) [[ -e "$FALSO_DIR/sessao-viva" ]]; exit ;;
esac
exit 0
EOF
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/claude"
cp "$tmp/bin/claude" "$tmp/bin/codex"
chmod +x "$tmp/bin"/*

git -C "$raiz" init -q -b main
git -C "$raiz" -c user.name=t -c user.email=t@t commit -qm inicio --allow-empty

catalogo() {
  printf '[{"nome":"conta1","pasta":"%s","argon":false},{"nome":"conta2","pasta":"%s","argon":false}]\n' \
    "$estado/contas/conta1" "$estado/contas/conta2" >"$estado/contas/agy.json"
}
confia() { jq -n --arg w "$raiz" '{trustedWorkspaces: [$w]}' >"$estado/contas/$1/settings.json"; }
nao_confia() { echo '{"trustedWorkspaces": []}' >"$estado/contas/$1/settings.json"; }
# cotas C1 C2 [DATA]: grupo gemini de cada conta em cotas.json; "-" é percentual nulo.
cotas() {
  jq -n --arg a "$1" --arg b "$2" --arg d "${3:-2026-10-24T11:50:40+00:00}" '
    def conta($n; $p): {provedor: "agy", conta: $n, grupos: [{grupo: "gemini", janelas: [], origem: "agy -p /usage",
      medido_em: $d, valido_ate: $d, motivo: null, percentual: (if $p == "-" then null else ($p | tonumber) end)}]};
    {versao: 1, gerado: $d, provedores: [conta("conta1"; $a), conta("conta2"; $b)]}' >"$estado/cotas.json"
}
# delegacao CONTA PERCENTUAL DATA [MODELO]: uma linha do delegacoes.jsonl.
delegacao() {
  jq -nc --arg c "$1" --arg p "$2" --arg d "$3" --arg m "${4:-gemini-3.8-flash-high}" \
    '{data: $d, destino: "agy", conta: $c, modelo: $m, cota_depois: ($p | tonumber)}' >>"$estado/delegacoes.jsonl"
}
limpar_medidas() { rm -f "$estado/cotas.json" "$estado/delegacoes.jsonl"; }

extra_env=()
# Roda um comando do jangada no ambiente falso, sem terminal e sem conta fixada.
rodar() {
  env -u JANGADA_ISOLADO -u JANGADA_SESSAO -u JANGADA_DELEGAR -u JANGADA_VALIDAR_REVISOR \
    -u JANGADA_AGY_SETTINGS -u JANGADA_AGY_CONTA -u JANGADA_AGY_CONTA_MONTADA -u JANGADA_AGY_PASTA \
    -u TMUX -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE "${extra_env[@]}" \
    HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$tmp/state" TZ=UTC \
    PATH="$tmp/bin:$PATH" JANGADA_CORE_PATH="$repo_jangada" FALSO_DIR="$tmp" \
    JANGADA_AGENTE_ESCOLHER=0 "$@" </dev/null >"$tmp/saida" 2>&1
}

# Escolha da conta, sem abrir sessão: CONTA|SALDO|HORA.
escolher() {
  rodar bash -c 'source "$JANGADA_CORE_PATH/bin/jangada-config"
    jangada_conta_agy_escolher "$@" || exit
    printf "%s|%s|%s\n" "$CONTA_AGY_ESCOLHIDA" "$CONTA_AGY_SALDO" "$CONTA_AGY_MEDIDA_EM"' _ "$@"
}
resultado() { escolher "$@"; cat "$tmp/saida"; }
escolhida() { resultado "$@" | cut -d'|' -f1; }

catalogo; confia conta1; confia conta2

limpar_medidas
conferir "sem medida nenhuma: fica a primeira do catálogo" test "$(resultado "$raiz")" = 'conta1||'

cotas 95.13 98
conferir "saldo maior no cotas.json escolhe a conta2" test "$(resultado "$raiz")" = 'conta2|98|11:50'
cotas 94.6 90.59
conferir "saldo maior da conta1 e formato com vírgula" test "$(resultado "$raiz")" = 'conta1|94,6|11:50'

cotas 95.13 98
delegacao conta2 50 2026-10-24T09:05:12-03:00
conferir "a medida mais nova do delegacoes.jsonl vence a do cotas.json, mesmo menor" \
  test "$(resultado "$raiz")" = 'conta1|95,13|11:50'
delegacao conta1 99.5 2026-10-24T09:30:00-03:00
conferir "linha mais nova da conta1 passa a decidir e mostra a hora local" \
  test "$(resultado "$raiz")" = 'conta1|99,5|12:30'

limpar_medidas
cotas - 10
conferir "conta sem medida fica atrás de qualquer saldo conhecido" test "$(resultado "$raiz")" = 'conta2|10|11:50'
cotas 0 -
conferir "saldo zero conhecido ainda vence a conta sem medida" test "$(resultado "$raiz")" = 'conta1|0|11:50'

limpar_medidas
cotas 50 50
conferir "empate fica com a primeira do catálogo" test "$(escolhida "$raiz")" = conta1

limpar_medidas
cotas 10 90
nao_confia conta2
conferir "conta que não confia na pasta é pulada" test "$(escolhida "$raiz")" = conta1
nao_confia conta1
escolher "$raiz"; rc=$?
conferir "nenhuma conta confia: devolve 1" test "$rc" = 1
confia conta1; confia conta2

limpar_medidas
cotas 10 90
conferir "NOME fixa a conta e mede só ela, sem exigir confiança" test "$(resultado "$raiz" conta1)" = 'conta1|10|11:50'

limpar_medidas
delegacao conta1 5 2026-10-24T09:00:00-03:00 gemini-4-argon-high
delegacao conta1 5 2026-10-24T09:00:00-03:00 claude-sonnet-5-5
delegacao conta2 7 2999-01-01T00:00:00-03:00
delegacao conta2 8 sem-data
printf 'lixo\n' >>"$estado/delegacoes.jsonl"
conferir "outros grupos, datas futuras e linhas inválidas não contam como medida" \
  test "$(resultado "$raiz")" = 'conta1||'

limpar_medidas
echo '{"provedores": 3}' >"$estado/cotas.json"
conferir "cotas.json malformado não derruba a escolha" test "$(escolhida "$raiz")" = conta1

# Abertura de sessão: registra a execução e a sessão, o que o isolamento do
# jangada não permite a quem roda dentro dele.
if grep -q ' /tmp/\.jangada-sem-autoridade ' /proc/self/mountinfo 2>/dev/null; then
  echo "aviso: sessão isolada; casos de abertura de sessão pulados"
else
  abrir() { rodar "$repo_jangada/bin/jangada-agente" --projeto "$raiz" --agente claude --delegacao agy "$@"; }
  conta_do() { jq -r '.conta_agy // "-"' "$estado/revisoes/app--$1.json" 2>/dev/null; }
  estado_conta_do() { jq -r '.conta_agy // "-"' "$estado/agentes/app--$1.json" 2>/dev/null; }
  isolar_com() { grep -F "send-keys -t =app--$1:" "$tmp/tmux.log" | grep -qF "jangada-isolar --conta $2 -- "; }

  limpar_medidas; cotas 95.13 98; : >"$tmp/tmux.log"
  abrir --nome saldo
  conferir "abertura: escolhe a conta2 de maior saldo" test "$(conta_do saldo)" = conta2
  conferir "abertura: o estado da sessão guarda a mesma conta" test "$(estado_conta_do saldo)" = conta2
  conferir "abertura: mostra a conta e a medida" grep -qxF 'conta do agy: conta2 (gemini 98%, medido às 11:50)' "$tmp/saida"
  conferir "abertura: o jangada-isolar recebe --conta" isolar_com saldo conta2

  limpar_medidas; : >"$tmp/tmux.log"
  abrir --nome vazio
  conferir "abertura sem medida: conta1 e linha 'sem medida'" test "$(conta_do vazio)" = conta1
  conferir "abertura sem medida: mostra a linha" grep -qxF 'conta do agy: conta1 (sem medida)' "$tmp/saida"

  cotas 10 90; : >"$tmp/tmux.log"
  abrir --nome fixa --conta-agy conta1
  conferir "--conta-agy fixa a conta mesmo com saldo menor" test "$(conta_do fixa)" = conta1
  conferir "--conta-agy repassa a conta ao isolar" isolar_com fixa conta1
  conferir "--conta-agy mostra a medida da conta fixada" grep -qxF 'conta do agy: conta1 (gemini 10%, medido às 11:50)' "$tmp/saida"

  : >"$tmp/tmux.log"
  extra_env=(JANGADA_AGY_CONTA=conta1); abrir --nome ambiente; extra_env=()
  conferir "JANGADA_AGY_CONTA no ambiente é respeitada" test "$(conta_do ambiente)" = conta1
  conferir "JANGADA_AGY_CONTA vai ao isolar" isolar_com ambiente conta1

  abrir --nome inexistente --conta-agy nenhuma; rc=$?
  conferir "conta inexistente recusa" test "$rc" != 0
  conferir "conta inexistente diz o motivo" grep -qF 'conta do agy inexistente: nenhuma' "$tmp/saida"
  conferir "conta inexistente não cria worktree" test ! -e "$tmp/home/.local/share/jangada-worktrees/app/inexistente"
  conferir "conta inexistente não cria ramo" test -z "$(git -C "$raiz" branch --list agente/inexistente)"
  extra_env=(JANGADA_AGY_CONTA=nenhuma); abrir --nome ambiente-ruim; rc=$?; extra_env=()
  conferir "JANGADA_AGY_CONTA inexistente recusa antes do worktree" \
    test "$rc" != 0 -a ! -e "$tmp/home/.local/share/jangada-worktrees/app/ambiente-ruim"

  nao_confia conta1; nao_confia conta2; limpar_medidas; cotas 10 90
  abrir --nome ninguem
  conferir "nenhuma conta confia: vale a primeira do catálogo" test "$(conta_do ninguem)" = conta1
  confia conta1; confia conta2

  # Retomada: a sessão existe, as medidas mudaram, e a conta registrada fica.
  limpar_medidas; cotas 10 90; abrir --nome retomar
  conferir "retomada: sessão aberta com a conta2" test "$(conta_do retomar)" = conta2
  cotas 99 10; : >"$tmp/sessao-viva"; : >"$tmp/tmux.log"
  abrir --nome retomar
  conferir "retomada: a conta registrada continua a conta2" test "$(conta_do retomar)" = conta2
  conferir "retomada: mostra a conta registrada" grep -qxF 'conta do agy: conta2 (registrada na sessão)' "$tmp/saida"
  conferir "retomada: não reenvia o comando da sessão" bash -c '! grep -q send-keys "$1"' _ "$tmp/tmux.log"
  abrir --nome retomar --conta-agy conta1
  conferir "retomada: a conta pedida é ignorada com aviso" grep -qF 'a conta pedida (conta1) foi ignorada' "$tmp/saida"
  conferir "retomada: a conta pedida não altera o registro" test "$(conta_do retomar)" = conta2
  abrir --nome retomar --conta-agy inexistente; rc=$?
  conferir "retomada: --conta-agy inválida não impede anexar" test "$rc" = 0
  conferir "retomada: --conta-agy inválida mantém a conta registrada" grep -qxF 'conta do agy: conta2 (registrada na sessão)' "$tmp/saida"
  extra_env=(JANGADA_AGY_CONTA=inexistente); abrir --nome retomar; rc=$?; extra_env=()
  conferir "retomada: JANGADA_AGY_CONTA inválida não impede anexar" test "$rc" = 0
  conferir "retomada: JANGADA_AGY_CONTA inválida mantém a conta registrada" grep -qxF 'conta do agy: conta2 (registrada na sessão)' "$tmp/saida"
  conferir "retomada: nome inválido não altera o registro" test "$(conta_do retomar)" = conta2
  jq 'del(.conta_agy)' "$estado/revisoes/app--retomar.json" >"$tmp/antigo.json" && mv "$tmp/antigo.json" "$estado/revisoes/app--retomar.json"
  abrir --nome retomar
  conferir "sessão antiga sem conta no registro segue como antes" bash -c '! grep -q "conta do agy" "$1"' _ "$tmp/saida"
  rm -f "$tmp/sessao-viva"

  # Sem catálogo nada muda.
  rm -f "$estado/contas/agy.json"; : >"$tmp/tmux.log"
  abrir --nome antigo
  conferir "sem catálogo: nenhuma conta no registro" test "$(conta_do antigo)" = -
  conferir "sem catálogo: nenhuma linha de conta" bash -c '! grep -q "conta do agy" "$1"' _ "$tmp/saida"
  conferir "sem catálogo: o isolar não recebe --conta" bash -c '! grep -q -- "--conta" "$1"' _ "$tmp/tmux.log"
  abrir --nome antigo2 --conta-agy outra; rc=$?
  conferir "sem catálogo: --conta-agy aceita só o nome da conta implícita" test "$rc" != 0
  catalogo
fi

conferir "nenhum caso chamou o agy" test ! -e "$tmp/agy.chamadas"

((falhas == 0)) || { echo "$falhas falha(s)"; exit 1; }
echo "ok: conta do agy por saldo"
