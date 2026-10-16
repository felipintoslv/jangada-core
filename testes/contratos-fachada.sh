#!/usr/bin/env bash
# Testa o contrato K1 (docs/modularizacao-3.0/03-contratos.md): todo nome de
# testes/contratos/comandos.txt existe em bin/ com permissão de execução, o
# despachante bin/jangada chega a cada um e o jangada-config, carregado a
# partir de bin/, define JANGADA_CORE_PATH como a pasta acima. Nome com a marca
# "carregado" é biblioteca lida por source: só precisa existir.
#
# Nenhum comando real roda: o despacho é conferido com o bin/jangada copiado
# para uma pasta temporária, ao lado de comandos falsos com os mesmos nomes.
#
# Uso: testes/contratos-fachada.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
lista="$repo_jangada/testes/contratos/comandos.txt"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

nomes() { grep -v -e '^#' -e '^$' "$lista" | cut -d' ' -f1; }
carregado() { grep -qxF -- "$1 carregado" "$lista"; }

# Um problema por linha; sem saída, a fachada de RAIZ cumpre o contrato.
problemas() {
  local raiz="$1" nome f falso
  falso="$(mktemp -d -p "$tmp")"
  for f in "$raiz"/bin/*; do
    nome="${f##*/}"
    nomes | grep -qxF -- "$nome" || echo "fora da lista: bin/$nome"
    [[ "$nome" == jangada-* && -f "$f" && -x "$f" ]] || continue
    printf '#!/bin/sh\necho "%s $*"\n' "$nome" >"$falso/$nome"
    chmod +x "$falso/$nome"
  done
  [[ -f "$raiz/bin/jangada" ]] && cp "$raiz/bin/jangada" "$falso/jangada"
  while IFS= read -r nome; do
    f="$raiz/bin/$nome"
    if [[ ! -f "$f" ]]; then
      echo "ausente: bin/$nome"
    elif carregado "$nome"; then
      continue
    elif [[ ! -x "$f" ]]; then
      echo "sem permissão de execução: bin/$nome"
    fi
    { [[ "$nome" == jangada ]] || carregado "$nome"; } && continue
    [[ "$("$falso/jangada" "${nome#jangada-}" a b 2>/dev/null)" == "$nome a b" ]] \
      || echo "bin/jangada não despacha: ${nome#jangada-}"
  done < <(nomes)
}

conferir "lista de comandos sem nome repetido" [ -z "$(nomes | sort | uniq -d)" ]
achados="$(problemas "$repo_jangada")"
conferir "todo nome da lista existe em bin/, é executável e é despachado" [ -z "$achados" ]
[[ -n "$achados" ]] && printf '      %s\n' "$achados"
conferir "bin/jangada recusa comando desconhecido" \
  bash -c '! "$1" comando-que-nao-existe 2>/dev/null' _ "$repo_jangada/bin/jangada"

# Forma usada pelos comandos: source "$(dirname "${BASH_SOURCE[0]}")/jangada-config".
mkdir -p "$tmp/casa"
caminho="$(env -u JANGADA_CORE_PATH HOME="$tmp/casa" XDG_CONFIG_HOME="$tmp/casa/config" XDG_STATE_HOME="$tmp/casa/state" \
  bash -c 'source "$(dirname "$1")/jangada-config" >/dev/null 2>&1; printf %s "$JANGADA_CORE_PATH"' _ "$repo_jangada/bin/jangada")"
conferir "jangada-config carregado de bin/ define JANGADA_CORE_PATH como a pasta acima" [ "$caminho" = "$repo_jangada" ]

# O teste precisa falhar quando a fachada muda: prova em cópias de bin/. As
# cópia de bin/ basta, porque os comandos são arquivos reais.
copia() { rm -rf "$tmp/copia"; mkdir "$tmp/copia"; cp -a "$repo_jangada/bin" "$tmp/copia/"; }
copia
conferir "cópia intacta de bin/ passa" [ -z "$(problemas "$tmp/copia")" ]
rm "$tmp/copia/bin/jangada-mapa"
achados="$(problemas "$tmp/copia")"
conferir "comando retirado de bin/ é apontado como ausente" grep -qxF "ausente: bin/jangada-mapa" <<<"$achados"
conferir "comando retirado de bin/ deixa de ser despachado" grep -qxF "bin/jangada não despacha: mapa" <<<"$achados"
copia
chmod -x "$tmp/copia/bin/jangada-filtrar"
conferir "comando sem permissão de execução é apontado" \
  grep -qxF "sem permissão de execução: bin/jangada-filtrar" <<<"$(problemas "$tmp/copia")"
copia
cp "$tmp/copia/bin/jangada-mapa" "$tmp/copia/bin/jangada-fora-da-lista"
conferir "comando novo fora da lista é apontado" \
  grep -qxF "fora da lista: bin/jangada-fora-da-lista" <<<"$(problemas "$tmp/copia")"

((falhas == 0)) && echo "tudo certo" || echo "$falhas falha(s)"
exit $((falhas > 0))
