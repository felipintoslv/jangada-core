#!/usr/bin/env bash
# Diz o que a máquina tem para os testes rodarem por inteiro. Sem uma dessas
# peças o teste que depende dela se pula, e a suíte passa sem ter conferido.
# JANGADA_TESTES_EXIGIR (nomes separados por espaço) faz a falta reprovar.
set -uo pipefail
# shellcheck source=testes/ambiente.sh
source "$(dirname "$0")/ambiente.sh"

tem() {
  case "$1" in
    bwrap) command -v bwrap >/dev/null 2>&1 && bwrap --ro-bind / / --dev /dev --proc /proc true 2>/dev/null ;;
    sem-rede) command -v bwrap >/dev/null 2>&1 && bwrap --ro-bind / / --dev /dev --proc /proc --unshare-net true 2>/dev/null ;;
    R) command -v Rscript >/dev/null 2>&1 ;;
    lintr) Rscript -e 'quit(status = !requireNamespace("lintr", quietly = TRUE))' >/dev/null 2>&1 ;;
    pyarrow) python3 -c 'import pyarrow' >/dev/null 2>&1 ;;
    *) command -v "$1" >/dev/null 2>&1 ;;
  esac
}

faltam=0
for c in bwrap sem-rede shellcheck jq gitleaks zsh pdftotext pyarrow R lintr; do
  if tem "$c"; then
    printf '%-10s sim\n' "$c"
  elif [[ " ${JANGADA_TESTES_EXIGIR:-} " == *" $c "* ]]; then
    printf '%-10s não (exigido)\n' "$c"
    faltam=1
  else
    printf '%-10s não (os testes que dependem dele se pulam)\n' "$c"
  fi
done
exit "$faltam"
