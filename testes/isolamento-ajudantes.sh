#!/usr/bin/env bash
# Testa o testes/isolamento.sh: só pula o caso cujo próprio comando saiu com o
# código da recusa e a escreveu no stdout ou no stderr. Roda igual dentro e
# fora do isolamento, com a marca simulada.
#
# Uso: testes/isolamento-ajudantes.sh
set -uo pipefail
export LC_ALL=C.UTF-8
cd "$(dirname "$0")/.." || exit 1
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
unset JANGADA_TESTES_PULADOS
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
recusa='AUTORIZACAO_RECUSADA: executor isolado não possui autoridade'
sai() { printf '%s\n' "$2"; printf '%s\n' "$3" >&2; return "$1"; }
pulou() { pulado_se_recusado "$tmp" "$1" >/dev/null; }
pulou_sem() { pulado_sem_o_passo "$tmp" tarefa "$1" >/dev/null; }
nao() { ! "$@"; }

vigiar_comandos

executar "$tmp" sai 1 "na saída" "no erro" >"$tmp/out" 2>"$tmp/err"
conferir "executar devolve o código do comando" [ "$?" = 1 ]
conferir "executar devolve o stdout" grep -qx "na saída" "$tmp/out"
conferir "executar devolve o stderr" grep -qx "no erro" "$tmp/err"

printf 'echo "%s"\n' "$recusa" >"$tmp/fonte.sh"
executar "$tmp" sai 1 "" "erro de sintaxe" >/dev/null 2>&1
conferir "fonte com a recusa e comando falhando por outro motivo não pula" nao pulou fonte

executar "$tmp" sai 1 "" "comando não encontrado" >/dev/null 2>&1
conferir "comando falhando sem recusa continua falha" nao pulou sem-recusa

executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
conferir "recusa no stderr com o código 1 pula" pulou stderr
executar "$tmp" sai 2 "$recusa" "" >/dev/null 2>&1
conferir "recusa no stdout com o código 2 pula" pulou stdout
executar "$tmp" sai 4 "" "atualização exige terminal externo ao agente isolado" >/dev/null 2>&1
conferir "recusa do jangada-update com o código 4 pula" pulou update

executar "$tmp" sai 3 "" "$recusa" >/dev/null 2>&1
conferir "recusa com código fora da lista não pula" nao pulou codigo-3
executar "$tmp" sai 0 "$recusa" "" >/dev/null 2>&1
conferir "recusa com código 0 não pula" nao pulou codigo-0

executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
executar "$tmp" sai 1 "" "outro erro" >/dev/null 2>&1
conferir "a recusa do comando anterior não vale para o seguinte" nao pulou anterior
executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
novo_comando "$tmp"
conferir "novo_comando apaga o registro" nao pulou novo

executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
conferir "a linha do pulo traz a recusa" \
  grep -qxF "pulado no isolamento: caso (recusa: $recusa)" <(pulado_se_recusado "$tmp" caso)

printf '%s\n' "$recusa" >"$tmp/interno.err"; : >"$tmp/interno.out"
executar "$tmp" true
registrar_comando "$tmp" 1 "$tmp/interno.out" "$tmp/interno.err"
conferir "registrar_comando associa o comando interno" pulou interno
registrar_comando "$tmp" 5 "$tmp/interno.out" "$tmp/interno.err"
conferir "registrar_comando com outro código não pula" nao pulou interno-5

executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
rc=$?
conferir "o rc=\$? não anula o registro (rc $rc)" pulou rc
executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
printf 'x\n' >"$tmp/preparo"
conferir "comando entre o passo e a conferência anula o registro" nao pulou preparo
executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
_="$(cat "$tmp/preparo")"
conferir "\$(...) sem executar também anula o registro" nao pulou substituicao
_="$(executar "$tmp" sai 1 "" "$recusa" 2>&1)"
conferir "executar dentro de \$(...) vale como passo" pulou substituicao-passo
executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
for vez in 1 2; do
  conferir "o cabeçalho do for não anula o registro ($vez)" pulou "laco-$vez"
done
passo() { executar "$tmp" sai 1 "" "$recusa"; }
passo >/dev/null 2>&1
conferir "executar dentro de função vale como passo" pulou funcao

executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
guardar_recusa "$tmp" tarefa
conferir "guardar_recusa não anula o registro do passo" pulou guardado
executar "$tmp" sai 1 "" "falha do hook" >/dev/null 2>&1
conferir "recusa guardada e falha própria do comando seguinte continua falha" nao pulou hook
conferir "conferência que exige o passo recusado pula" pulou_sem sessao
executar "$tmp" sai 1 "" "outro erro" >/dev/null 2>&1
guardar_recusa "$tmp" tarefa
conferir "passo sem recusa não é guardado" nao pulou_sem sem-recusa

trap - DEBUG
_sem_autoridade=0
rm -f "$tmp"/.comando.*
executar "$tmp" sai 1 "" "$recusa" >/dev/null 2>&1
conferir "fora do isolamento a recusa não pula" nao pulou fora
conferir "fora do isolamento executar não grava registro" test ! -e "$tmp/.comando.rc"
executar "$tmp" sai 1 "na saída" "no erro" >"$tmp/out" 2>"$tmp/err"
conferir "fora do isolamento executar devolve código e saídas" \
  bash -c '[ "$1" = 1 ] && grep -qx "na saída" "$2" && grep -qx "no erro" "$3"' _ "$?" "$tmp/out" "$tmp/err"

((falhas == 0)) && echo "tudo certo" || { echo "$falhas falha(s)"; exit 1; }
