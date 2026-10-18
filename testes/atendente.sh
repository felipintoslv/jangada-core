#!/usr/bin/env bash
# Testa a revisão pedida pelo agente isolado ao atendente que o jangada-isolar
# mantém fora, com revisor falso: nada vai para a rede e nada toca o estado
# real. Onde o bwrap não cria o namespace, o jangada-isolar roda com um bwrap
# falso, que só repassa ambiente e pasta; aí não se confere a montagem
# somente leitura do soquete nem que revisoes/ some para o agente (com
# JANGADA_TESTES_EXIGIR_ISOLAMENTO=1, isso vira falha).
#
# Uso: testes/atendente.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
conferir() {
  local d="$1"; shift
  if "$@" >/dev/null; then ok "$d"; conferencia_feita "${tmp:-}"
  elif ! pulado_se_recusado "${tmp:-}" "$d"; then falha "$d"; fi
}

tmp="$(mktemp -d)"
erros_dos_pulados "$tmp"
# O bwrap também leva a pasta do soquete nos argumentos; o atendente é o python.
atendente_vivo() { pgrep -f "^python3 -c import json, os, re, signal.* $tmp/run/jangada-isolar/atendente-" >/dev/null; }
trap 'pkill -f "^python3 -c import json, os, re, signal.* $tmp/run/" 2>/dev/null; rm -rf "$tmp"' EXIT
casa="$tmp/casa"
estado="$casa/.local/state/jangada"
F="$tmp/falso"
mkdir -p "$casa" "$tmp/bin" "$tmp/config/jangada" "$F" "$estado/revisoes"
mkdir -m 0700 "$tmp/run"

if bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --unshare-pid true 2>/dev/null; then
  real=1
else
  real=0
  if [[ "${JANGADA_TESTES_EXIGIR_ISOLAMENTO:-}" == 1 ]]; then
    falha "bwrap não cria o namespace (o isolamento real é exigido)"
  else
    echo "aviso: sem bwrap utilizável, roda com bwrap falso; ficam sem conferir a montagem somente leitura do soquete e a pasta revisoes/ oculta"
  fi
  mkdir -p "$tmp/bwrap-falso"
  cat >"$tmp/bwrap-falso/bwrap" <<'EOF'
#!/usr/bin/env bash
soquete=""
while (($#)); do
  case "$1" in
    --) shift; break ;;
    --setenv) export "$2=$3"; shift 3 ;;
    --unsetenv) unset "$2"; shift 2 ;;
    --chdir) cd "$2" || exit 1; shift 2 ;;
    --ro-bind) [[ "$3" == /tmp/.jangada-atendente ]] && soquete="$2/soquete"; shift 3 ;;
    *) shift ;;
  esac
done
(($#)) || exit 1
[[ -z "$soquete" ]] || export JANGADA_VALIDAR_SOQUETE="$soquete"
exec "$@"
EOF
  chmod +x "$tmp/bwrap-falso/bwrap"
fi

# Revisor falso: guarda o pedido, conta as chamadas e responde o que está em
# $F/resposta, depois de $F/espera segundos, se houver.
cat >"$tmp/bin/claude" <<'EOF'
#!/usr/bin/env bash
cat >"$FALSO_DIR/pedido"
echo x >>"$FALSO_DIR/chamadas"
[[ -f "$FALSO_DIR/espera" ]] && sleep "$(cat "$FALSO_DIR/espera")"
printf '%b\n' "$(cat "$FALSO_DIR/resposta")"
EOF
chmod +x "$tmp/bin/claude"
chamadas() { [[ -f "$F/chamadas" ]] && wc -l <"$F/chamadas" || echo 0; }

git init -q -b main "$tmp/repo"
git -C "$tmp/repo" -c user.name=t -c user.email=t@t commit -q --allow-empty -m inicio
git -C "$tmp/repo" worktree add -q -b agente/t "$tmp/wt"
base_sha="$(git -C "$tmp/repo" rev-parse main)"
n=0
commitar() {
  n=$((n + 1))
  echo "linha $n" >>"$tmp/wt/arquivo.txt"
  git -C "$tmp/wt" add arquivo.txt
  git -C "$tmp/wt" -c user.name=t -c user.email=t@t commit -q -m "feat: passo $n"
}
jq -n --arg raiz "$tmp/repo" --arg wt "$tmp/wt" \
  '{sessao:"t", raiz:$raiz, worktree:$wt, ramo:"agente/t", base:"main", agente:"codex",
    revisor:"claude", tarefa:"tarefa de teste", execucao:"exe-1", desde:"2026-10-17T00:00:00-03:00"}' \
  >"$estado/revisoes/t.json"

path_teste="$tmp/bin:$PATH"
((real)) || path_teste="$tmp/bwrap-falso:$path_teste"
ambiente=(HOME="$casa" XDG_STATE_HOME="$casa/.local/state" XDG_CONFIG_HOME="$tmp/config"
  XDG_RUNTIME_DIR="$tmp/run" JANGADA_CORE_PATH="$repo_jangada" JANGADA_MARCA_ISOLADO="$tmp/.marca-teste"
  PATH="$path_teste" FALSO_DIR="$F" JANGADA_ISOLAR_ESCRITA="$F" JANGADA_VALIDAR_RODADAS=2)
limpar_ambiente=(-u JANGADA_ISOLADO -u DBUS_SESSION_BUS_ADDRESS -u JANGADA_VALIDAR_REVISOR
  -u JANGADA_VALIDAR_MODELO -u JANGADA_VALIDAR_ESFORCO -u JANGADA_VALIDAR_PULAR_LOCAL
  -u JANGADA_VALIDAR_TESTANDO -u JANGADA_VALIDAR_SOQUETE
  -u JANGADA_DELEGAR -u JANGADA_ISOLAR_FOTO -u JANGADA_ISOLAR_PERFIL)
command -v gitleaks >/dev/null 2>&1 || ambiente+=(JANGADA_VALIDAR_SEM_GITLEAKS=1)
# isolar SESSAO COMANDO...: abre a sessão no worktree, como o jangada-agente.
# $extra vale para o atendente, fora.
extra=()
isolar() {
  novo_comando "$tmp"
  (cd "$tmp/wt" && env "${limpar_ambiente[@]}" "${ambiente[@]}" "${extra[@]}" JANGADA_SESSAO="$1" \
    "$repo_jangada/bin/jangada-isolar" -- "${@:2}" </dev/null)
}
validar="$repo_jangada/bin/jangada-validar"
# Pedido do agente: a saída fica em $F/NOME.out e .err, o código em $F/NOME.rc.
pedir() {
  local nome="$1"; shift
  isolar t bash -c '"$@" >"$FALSO_DIR/$0.out" 2>"$FALSO_DIR/$0.err"; echo $? >"$FALSO_DIR/$0.rc"' \
    "$nome" "$@"
}
rc() { cat "$F/$1.rc" 2>/dev/null; }
pareceres() { find "$estado/revisoes" -maxdepth 1 -name 'validacao-t-r*.md' | wc -l; }
linhas() { [[ -s "$1" ]] && grep -c . "$1" || echo 0; }
sem_atendente_vivo() {
  local _
  for _ in 1 2 3 4 5 6; do
    if ! atendente_vivo \
       && [[ -z "$(find "$tmp/run/jangada-isolar" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# Caso 1: o sha da cabeça vai ao atendente; o parecer volta e fica em revisoes/.
commitar
echo 'STATUS: REVISAR\n1. arquivo.txt:1 falta teste' >"$F/resposta"
pedir c1 "$validar"
conferir "caso 1: REVISAR volta com 3" [ "$(rc c1)" = 3 ]
conferir "caso 1: o parecer volta pelo soquete" grep -q 'STATUS: REVISAR' "$F/c1.out"
conferir "caso 1: o revisor foi chamado uma vez" [ "$(chamadas)" = 1 ]
conferir "caso 1: parecer gravado em revisoes/" test -f "$estado/revisoes/validacao-t-r1.md"
conferir "caso 1: a rodada vai para revisoes/validar.jsonl" [ "$(linhas "$estado/revisoes/validar.jsonl")" = 1 ]
conferir "caso 1: o contexto guarda o sha pedido" \
  jq -e --arg c "$(git -C "$tmp/wt" rev-parse HEAD)" '.candidate_sha == $c and .protegido' \
  "$estado/revisoes/validacao-t-r1.contexto.json"
conferir "caso 1: nada gravado nos arquivos do agente" \
  bash -c '[ ! -s "$1/validar.jsonl" ] && ! ls "$1/agentes/validacao-t"* >/dev/null 2>&1' _ "$estado"
conferir "caso 1: o atendente acabou com a sessão" sem_atendente_vivo

# Caso 2: o mesmo sha devolve o parecer gravado, sem revisor nem rodada nova.
pedir c2 "$validar"
conferir "caso 2: mesmo sha volta com o código do parecer" [ "$(rc c2)" = 3 ]
conferir "caso 2: mesmo parecer" grep -q 'falta teste' "$F/c2.out"
conferir "caso 2: o revisor não foi chamado de novo" [ "$(chamadas)" = 1 ]
conferir "caso 2: nenhuma rodada nova" bash -c '[ "$1" = 1 ] && [ "$2" = 1 ]' _ \
  "$(pareceres)" "$(linhas "$estado/revisoes/validar.jsonl")"

# Caso 3: opções que mudariam a revisão são recusadas dentro, sem o atendente.
for opcao in "--forcar" "--pular-local" "--revisor codex" "--modelo x" "--esforco high" \
             "--base HEAD" "--reverter-se-limite" "--atendido $base_sha"; do
  read -ra partes <<<"$opcao"
  pedir op "$validar" "${partes[@]}"
  conferir "caso 3: ${partes[0]} recusada com 1 e mensagem" \
    bash -c '[ "$1" = 1 ] && grep -q "dentro do isolamento ${2} não vale" "$3"' _ "$(rc op)" "${partes[0]}" "$F/op.err"
done
pedir op "$validar" --metricas --forcar
conferir "caso 3: --metricas com --forcar recusada" [ "$(rc op)" = 1 ]
conferir "caso 3: nenhuma recusa chamou o revisor ou gravou rodada" \
  bash -c '[ "$1" = 1 ] && [ "$2" = 1 ]' _ "$(chamadas)" "$(pareceres)"
pedir op "$validar" --metricas
conferir "caso 3: --metricas sozinha roda dentro" [ "$(rc op)" = 0 ]

# Caso 4: pedidos que não são o sha da cabeça do ramo.
cabeca="$(git -C "$tmp/wt" rev-parse HEAD)"
git -C "$tmp/wt" checkout -q --detach HEAD~1
pedir c4 "$validar"
conferir "caso 4: pasta fora da cabeça do ramo recusada" \
  bash -c '[ "$1" = 1 ] && grep -q "não é a cabeça do ramo agente/t" "$2"' _ "$(rc c4)" "$F/c4.err"
git -C "$tmp/wt" checkout -q agente/t
echo sujo >"$tmp/wt/novo.txt"
pedir c4 "$validar"
conferir "caso 4: alteração sem commit recusada" \
  bash -c '[ "$1" = 1 ] && grep -q "sem commit" "$2"' _ "$(rc c4)" "$F/c4.err"
rm -f "$tmp/wt/novo.txt"
cat >"$F/cru.py" <<'EOF'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(30)
s.connect(sys.argv[1])
s.sendall(sys.argv[2].encode("utf-8", "surrogateescape"))
s.shutdown(socket.SHUT_WR)
print(s.makefile(encoding='utf-8', errors='replace').read())
EOF
isolar t bash -c 'for p in "$@"; do python3 "$FALSO_DIR/cru.py" "$JANGADA_VALIDAR_SOQUETE" "$p"; echo "--"; done' _ \
  "$cabeca"$'\n'"$(printf 'a%.0s' {1..8300})" "nao-e-sha" "$cabeca; touch $F/injetado" "$base_sha" \
  "$cabeca"$'\n'"1 corrigido"$'\e'"[2J" "$cabeca"$'\n'"1 corrigido"$'\t'"x" "$cabeca"$'\n'"1 "$'\xff' \
  >"$F/cru.out" 2>&1
conferir "caso 4: resposta maior que 8 KiB recusada" grep -q '^RECUSADO a resposta passa de 8 KiB' "$F/cru.out"
conferir "caso 4: resposta com caractere de controle recusada" \
  bash -c '[ "$(grep -c "^RECUSADO a resposta tem caracteres de controle" "$1")" = 2 ]' _ "$F/cru.out"
conferir "caso 4: resposta fora do UTF-8 recusada" grep -q '^RECUSADO a resposta não é UTF-8 válido' "$F/cru.out"
conferir "caso 4: texto que não é sha recusado" \
  bash -c '[ "$(grep -c "^RECUSADO o pedido não é um sha" "$1")" = 2 ]' _ "$F/cru.out"
conferir "caso 4: o texto do pedido não roda" test ! -e "$F/injetado"
conferir "caso 4: sha que não é a cabeça recusado com 1" \
  bash -c 'grep -q "\"codigo\": 1" "$1" && grep -q "não é a cabeça do ramo" "$1"' _ "$F/cru.out"
conferir "caso 4: nenhuma recusa chamou o revisor ou gravou rodada" \
  bash -c '[ "$1" = 1 ] && [ "$2" = 1 ] && [ "$3" = 1 ]' _ "$(chamadas)" "$(pareceres)" \
  "$(linhas "$estado/revisoes/validar.jsonl")"

# Caso 5: dois pedidos na mesma sessão: o segundo recebe OCUPADO.
commitar
echo 'STATUS: APROVADO' >"$F/resposta"
echo 3 >"$F/espera"
isolar t bash -c '"$1" >"$FALSO_DIR/p1.out" 2>"$FALSO_DIR/p1.err" & p=$!; sleep 1
  "$1" >"$FALSO_DIR/p2.out" 2>"$FALSO_DIR/p2.err"; echo $? >"$FALSO_DIR/p2.rc"
  wait "$p"; echo $? >"$FALSO_DIR/p1.rc"' _ "$validar"
conferir "caso 5: o primeiro aprova" [ "$(rc p1)" = 0 ]
conferir "caso 5: o segundo recebe ocupado" \
  bash -c '[ "$1" = 1 ] && grep -q "já revisa outro pedido" "$2"' _ "$(rc p2)" "$F/p2.err"
conferir "caso 5: marca de aprovação em revisoes/ com o sha" \
  jq -e --arg c "$(git -C "$tmp/wt" rev-parse HEAD)" '.candidate_sha == $c' "$estado/revisoes/validacao-t.aprovado"
conferir "caso 5: uma chamada ao revisor" [ "$(chamadas)" = 2 ]

# Caso 6: duas sessões abertas ao mesmo tempo: a trava de revisoes/ faz a
# segunda esperar, e ela recebe o parecer da primeira para o mesmo sha.
commitar
echo 'STATUS: REVISAR\n1. arquivo.txt:3 x' >"$F/resposta"
pedir s1 "$validar" &
primeiro=$!
sleep 1.5
pedir s2 "$validar"
wait "$primeiro"
conferir "caso 6: as duas recebem o parecer" \
  bash -c '[ "$1" = 3 ] && [ "$2" = 3 ] && grep -q "arquivo.txt:3" "$3" && grep -q "arquivo.txt:3" "$4"' _ \
  "$(rc s1)" "$(rc s2)" "$F/s1.out" "$F/s2.out"
conferir "caso 6: um parecer e uma chamada ao revisor" \
  bash -c '[ "$1" = 3 ] && [ "$2" = 3 ]' _ "$(chamadas)" "$(pareceres)"
conferir "caso 6: linhas inteiras em revisoes/validar.jsonl" \
  jq -e -s 'length == 3' "$estado/revisoes/validar.jsonl"
rm -f "$F/espera"

# Caso 7: o limite de rodadas é o de fora; a variável de dentro não vale.
commitar
pedir l1 "$validar" --resposta "1 corrigido: teste novo; \$(touch $F/injetado) \"aspas\""
conferir "caso 7: segunda rodada da entrega" [ "$(rc l1)" = 3 ]
conferir "caso 7: a resposta chega ao revisor como texto" \
  bash -c 'grep -qF "1 corrigido: teste novo; \$(touch $2/injetado) \"aspas\"" "$1" && [ ! -e "$2/injetado" ]' _ \
  "$F/pedido" "$F"
pedir lg "$validar" --resposta "$(printf 'a%.0s' {1..8200})"
conferir "caso 7: resposta acima de 8 KiB recusada no pedido" \
  bash -c '[ "$1" = 1 ] && grep -q "passa de 8 KiB" "$2"' _ "$(rc lg)" "$F/lg.err"
commitar
pedir l2 env JANGADA_VALIDAR_RODADAS=99 "$validar"
conferir "caso 7: terceira rodada para no limite de fora" \
  bash -c '[ "$1" = 4 ] && grep -q "limite de 2 rodadas" "$2"' _ "$(rc l2)" "$F/l2.err"
conferir "caso 7: o limite não chamou o revisor" [ "$(chamadas)" = 4 ]

# Caso 8: linha forjada pelo agente no validar.jsonl do estado fica fora da soma.
isolar t bash -c 'printf "%s\n" "{\"data\":\"2026-10-17T12:00:00-03:00\",\"rotulo\":\"t\",\"rodada\":1,\"resultado\":\"aprovado\",\"etapa\":\"revisor\",\"execucao\":\"exe-1\",\"tokens_revisor\":{\"entrada\":null,\"saida\":null,\"cache_lido\":null,\"total\":999999}}" >>"$1/validar.jsonl"' _ "$estado"
conferir "caso 8: a linha forjada foi gravada" grep -q 999999 "$estado/validar.jsonl"
conferir "caso 8: a soma do revisor não conta a linha forjada" \
  bash -c 'python3 "$1/orquestracao/consumo_tarefa.py" soma-revisor "$2" t --execucao exe-1 \
    | jq -e ".total == null and .rodadas == 4"' _ "$repo_jangada" "$estado"

# Caso 9: sem atendente, o pedido sai com 1 e não grava nada.
antes="$(linhas "$estado/validar.jsonl")"
(cd "$tmp/wt" && env "${limpar_ambiente[@]}" "${ambiente[@]}" JANGADA_ISOLADO=1 JANGADA_SESSAO=t \
  JANGADA_VALIDAR_SOQUETE="$tmp/ausente" "$validar" >"$F/a1.out" 2>"$F/a1.err"); rc_a=$?
conferir "caso 9: soquete ausente sai com 1 e pede ao coordenador" \
  bash -c '[ "$1" = 1 ] && grep -qx "revisão fora do isolamento indisponível; peça ao coordenador" "$2"' _ "$rc_a" "$F/a1.err"
python3 -c 'import socket, sys, time
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.bind(sys.argv[1]); s.listen(1)
time.sleep(30)' "$tmp/mudo" &
mudo=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do [[ -S "$tmp/mudo" ]] && break; sleep 0.2; done
SECONDS=0
(cd "$tmp/wt" && env "${limpar_ambiente[@]}" "${ambiente[@]}" JANGADA_ISOLADO=1 JANGADA_SESSAO=t \
  JANGADA_VALIDAR_SOQUETE="$tmp/mudo" "$validar" >"$F/a2.out" 2>"$F/a2.err"); rc_a=$?
kill "$mudo" 2>/dev/null; wait "$mudo" 2>/dev/null
conferir "caso 9: atendente mudo sai com 1 em cerca de 10 s" \
  bash -c '[ "$1" = 1 ] && (($2 >= 9 && $2 <= 20)) && grep -q "indisponível; peça ao coordenador" "$3"' _ "$rc_a" "$SECONDS" "$F/a2.err"
isolar u bash -c '"$1" >"$FALSO_DIR/a3.out" 2>"$FALSO_DIR/a3.err"; echo $? >"$FALSO_DIR/a3.rc"' _ "$validar"
conferir "caso 9: sessão sem cópia protegida não abre atendente" \
  bash -c '[ "$1" = 1 ] && grep -q "indisponível; peça ao coordenador" "$2"' _ "$(rc a3)" "$F/a3.err"
sem_runtime=(); mkdir -p "$tmp/tmpdir"
for v in "${ambiente[@]}"; do [[ "$v" == XDG_RUNTIME_DIR=* ]] || sem_runtime+=("$v"); done
novo_comando "$tmp"
(cd "$tmp/wt" && env "${limpar_ambiente[@]}" -u XDG_RUNTIME_DIR "${sem_runtime[@]}" TMPDIR="$tmp/tmpdir" \
  JANGADA_SESSAO=t "$repo_jangada/bin/jangada-isolar" -- \
  bash -c '"$1" >"$FALSO_DIR/a4.out" 2>"$FALSO_DIR/a4.err"; echo $? >"$FALSO_DIR/a4.rc"' _ "$validar" </dev/null)
conferir "caso 9: sem XDG_RUNTIME_DIR o atendente não abre e o pedido diz indisponível" \
  bash -c '[ "$1" = 1 ] && grep -q "indisponível; peça ao coordenador" "$2" \
    && [ -z "$(find "$3" -mindepth 1 2>/dev/null)" ]' _ "$(rc a4)" "$F/a4.err" "$tmp/tmpdir"
conferir "caso 9: nada gravado" bash -c '[ "$1" = "$2" ] && [ "$3" = 4 ] && [ "$4" = 4 ] \
  && ! ls "$5/agentes/validacao-"* >/dev/null 2>&1' _ "$antes" "$(linhas "$estado/validar.jsonl")" \
  "$(pareceres)" "$(chamadas)" "$estado"

# Caso 10: com o jangada-isolar morto por KILL, o atendente sai sozinho.
( isolar t sleep 31 ) 2>"$F/c10.err" &
for _ in $(seq 1 25); do atendente_vivo && break; sleep 0.2; done
conferir "caso 10: o atendente abre com a sessão" atendente_vivo
pkill -KILL -f "$repo_jangada/bin/jangada-isolar -- sleep 31"
sleep 2
atendente_morto() { ! atendente_vivo; }
conferir "caso 10: o atendente acaba depois do KILL" atendente_morto
pkill -f '^sleep 31$' 2>/dev/null
pkill -f "^bwrap .*$tmp/" 2>/dev/null
wait 2>/dev/null

# Caso 12: o revisor que vence o prazo. Três erros seguidos param os pedidos;
# a rodada com parecer zera a contagem.
extra=(JANGADA_VALIDAR_RODADAS=10 JANGADA_VALIDAR_PRAZO=1)
echo 'STATUS: REVISAR\n1. arquivo.txt:9 y' >"$F/resposta"
commitar
echo 4 >"$F/espera"
pedir e1 "$validar"; pedir e2 "$validar"
conferir "caso 12: prazo vencido sai com 1, sem parecer" \
  bash -c '[ "$1" = 1 ] && [ "$2" = 1 ] && grep -q "não respondeu em 1s" "$3" && [ "$4" = 4 ]' _ \
  "$(rc e1)" "$(rc e2)" "$F/e2.err" "$(pareceres)"
rm -f "$F/espera"
pedir e3 "$validar"
conferir "caso 12: a rodada com parecer zera a contagem" \
  bash -c '[ "$1" = 3 ] && [ ! -e "$2" ]' _ "$(rc e3)" "$estado/revisoes/validacao-t.erros"
commitar
echo 4 >"$F/espera"
pedir e4 "$validar"; pedir e5 "$validar"; pedir e6 "$validar"
conferir "caso 12: o terceiro erro seguido avisa" \
  bash -c '[ "$1" = 1 ] && [ "$2" = 1 ] && ! grep -q "3 vezes" "$3" && grep -q "o revisor falhou 3 vezes seguidas; peça ao coordenador" "$4"' _ \
  "$(rc e4)" "$(rc e6)" "$F/e5.err" "$F/e6.err"
antes="$(chamadas)"
pedir e7 "$validar"
conferir "caso 12: depois do terceiro erro o pedido é recusado sem chamar o revisor" \
  bash -c '[ "$1" = 1 ] && grep -q "o revisor falhou 3 vezes seguidas; peça ao coordenador" "$2" && [ "$3" = "$4" ]' _ \
  "$(rc e7)" "$F/e7.err" "$antes" "$(chamadas)"
rm -f "$F/espera"
extra=()

# Caso 11, só com o bwrap: o agente não troca o soquete nem lê revisoes/.
if ((real)); then
  isolar t bash -c 'rm -f "$JANGADA_VALIDAR_SOQUETE" 2>/dev/null; ln -sf /dev/null /tmp/.jangada-atendente/x 2>/dev/null
    test -S "$JANGADA_VALIDAR_SOQUETE" && ! test -e /tmp/.jangada-atendente/x && echo intacto >"$FALSO_DIR/r1"
    [ -z "$(ls -A "$1/revisoes")" ] && echo oculto >>"$FALSO_DIR/r1"' _ "$estado"
  conferir "caso 11: o soquete fica somente leitura para o agente" grep -qx intacto "$F/r1"
  conferir "caso 11: revisoes/ some para o agente" grep -qx oculto "$F/r1"
else
  echo "pulado caso 11: montagem somente leitura do soquete e revisoes/ oculta (sem bwrap)"
fi

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "atendente: ok"
