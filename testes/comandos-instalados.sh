#!/usr/bin/env bash
# Testa a etapa install/20-comandos.sh (invólucros em ~/.local/bin) e a
# fronteira com o Shell: o JANGADA_PATH herdado da sessão do Shell não vale
# para o Core. Usa um HOME temporário fora do /tmp. Não toca no HOME real.
#
# Uso: testes/comandos-instalados.sh
set -uo pipefail
export LC_ALL=C.UTF-8
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else falha "$d"; fi; }

mkdir -p "$HOME/.cache"
tmp="$(mktemp -d "$HOME/.cache/teste-comandos.XXXX")"
trap 'rm -rf "$tmp"' EXIT
unset JANGADA_ISOLADO TMUX JANGADA_SIMULAR JANGADA_CORE_PATH
casa="$tmp/home"
mkdir -p "$casa"
destino="$casa/.local/bin"

# Roda a etapa como o install.sh a roda: lib.sh carregada, etapa por source.
etapa() {
  HOME="$casa" XDG_CONFIG_HOME="$casa/.config" XDG_STATE_HOME="$casa/.local/state" \
    JANGADA_CORE_PATH="$repo_jangada" JANGADA_SIMULAR="${1:-0}" bash -c '
      set -euo pipefail
      source "$JANGADA_CORE_PATH/install/lib.sh"
      source "$JANGADA_CORE_PATH/install/20-comandos.sh"'
}

# Simulação: não grava nada.
etapa 1 >"$tmp/saida" 2>&1; rc=$?
conferir "simulação: sai com 0 ($rc)" test "$rc" -eq 0
conferir "simulação: mostra o que faria" grep -q 'simulação' "$tmp/saida"
conferir "simulação: não cria ~/.local/bin" test ! -e "$destino"

# Criação.
etapa >"$tmp/saida" 2>&1; rc=$?
conferir "criação: sai com 0 ($rc)" test "$rc" -eq 0
total="$(find "$repo_jangada/bin" -maxdepth 1 -name 'jangada*' -type f -perm -u+x | wc -l)"
conferir "criação: um invólucro por comando de bin/ ($total)" test "$(find "$destino" -name 'jangada*' -type f | wc -l)" -eq "$total"
conferir "criação: invólucro tem modo 755" test "$(stat -c %a "$destino/jangada-versao")" = 755
conferir "criação: invólucro não é link simbólico" test ! -L "$destino/jangada-versao"
conferir "criação: marca na segunda linha" test "$(sed -n 2p "$destino/jangada-versao")" = "# gerado pelo jangada-core; não edite"
conferir "criação: exec aponta para o comando da raiz" \
  grep -qxF "$(printf 'exec %q "$@"' "$repo_jangada/bin/jangada-versao")" "$destino/jangada-versao"
conferir "criação: sem temporários esquecidos" test -z "$(find "$destino" -name '*.jangada-*')"

# O invólucro executa o comando certo.
esperado="$(HOME="$casa" "$repo_jangada/bin/jangada-versao" 2>&1)"
obtido="$(HOME="$casa" "$destino/jangada-versao" 2>&1)"
conferir "invólucro: jangada-versao dá a mesma saída do comando ($obtido)" test -n "$obtido" -a "$obtido" = "$esperado"

# Repetir não muda nada.
antes="$(stat -c %Y "$destino/jangada-versao")"
sleep 1
etapa >"$tmp/saida" 2>&1; rc=$?
conferir "repetição: sai com 0 ($rc)" test "$rc" -eq 0
conferir "repetição: invólucro intacto" test "$(stat -c %Y "$destino/jangada-versao")" = "$antes"

# Arquivo alheio não é sobrescrito e a etapa sai com erro.
printf '#!/bin/sh\necho alheio\n' >"$destino/jangada-fila"
cp "$destino/jangada-fila" "$tmp/alheio.bak"
rm -f "$destino/jangada-versao"
etapa >"$tmp/saida" 2>&1; rc=$?
conferir "alheio: etapa sai com erro ($rc)" test "$rc" -ne 0
conferir "alheio: arquivo preservado" cmp -s "$destino/jangada-fila" "$tmp/alheio.bak"
conferir "alheio: o conflito é listado" grep -q "$destino/jangada-fila" "$tmp/saida"
conferir "alheio: o resto foi gravado mesmo assim" test -x "$destino/jangada-versao"
rm -f "$destino/jangada-fila"

# Invólucro órfão com marca é removido; sem marca fica.
printf '#!/usr/bin/env bash\n# gerado pelo jangada-core; não edite\nexec "/x/bin/jangada-fantasma" "$@"\n' >"$destino/jangada-fantasma"
printf '#!/bin/sh\necho meu\n' >"$destino/jangada-meu-script"
chmod +x "$destino/jangada-fantasma" "$destino/jangada-meu-script"
etapa 1 >/dev/null 2>&1
conferir "órfão: a simulação não remove" test -e "$destino/jangada-fantasma"
etapa >"$tmp/saida" 2>&1; rc=$?
conferir "órfão: etapa sai com 0 ($rc)" test "$rc" -eq 0
conferir "órfão: invólucro com marca removido" test ! -e "$destino/jangada-fantasma"
conferir "órfão: arquivo sem marca preservado" test -e "$destino/jangada-meu-script"

# Fronteira: o JANGADA_PATH do Shell, herdado da sessão, não vale para o Core.
raiz="$(env -u JANGADA_CORE_PATH JANGADA_PATH=/caminho/inexistente HOME="$casa" "$repo_jangada/bin/jangada-config" 2>/dev/null \
  | sed -n 's/^JANGADA_CORE_PATH=//p')"
conferir "fronteira: com JANGADA_PATH inexistente, JANGADA_CORE_PATH é a raiz real ($raiz)" test "$raiz" = "$repo_jangada"
raiz="$(env -u JANGADA_CORE_PATH JANGADA_PATH=/caminho/inexistente HOME="$casa" "$destino/jangada-config" 2>/dev/null \
  | sed -n 's/^JANGADA_CORE_PATH=//p')"
conferir "fronteira: o mesmo vale pelo invólucro" test "$raiz" = "$repo_jangada"

if ((falhas)); then echo "$falhas falha(s)"; exit 1; fi
echo "tudo certo"
