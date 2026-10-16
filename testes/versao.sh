#!/usr/bin/env bash
# Testa o jangada-versao num repositório temporário: versão, novidades,
# registro, lançamento e as recusas do --lancar.
#
# Uso: testes/versao.sh
set -uo pipefail
export LC_ALL=C.UTF-8
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/config"
repo="$tmp/repo"

# Nada da configuração do git do usuário (assinatura, ganchos) entra no teste.
export GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
: >"$GIT_CONFIG_GLOBAL"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export XDG_CONFIG_HOME="$tmp/config" JANGADA_CORE_PATH="$repo_jangada"
hoje="$(date +%F)"

versao() { "$repo_jangada/bin/jangada-versao" "$@"; }
# Roda de fora do repositório, com -C, e guarda a saída, os erros e o código.
rodar() { (cd "$tmp" && versao -C "$repo" "$@") >"$tmp/saida" 2>"$tmp/erros"; rc=$?; }
saida() { cat "$tmp/saida"; }
# A saída sem as linhas em branco: a especificação fixa a ordem dos grupos e
# dos itens, não o espaçamento dentro de um grupo.
compacta() { grep -v '^$' "$tmp/saida"; }
tem() { grep -qxF -- "$1" "$tmp/saida"; }
nao_tem() { ! grep -qF -- "$1" "$tmp/saida"; }
# Commits com datas crescentes, para a ordem do git log não depender do relógio.
n=0
commitar() {
  n=$((n + 1))
  echo "$1" >"$repo/arquivo$n.txt"
  git -C "$repo" add "arquivo$n.txt"
  GIT_AUTHOR_DATE="2026-01-01T00:00:$(printf %02d "$n")" GIT_COMMITTER_DATE="2026-01-01T00:00:$(printf %02d "$n")" \
    git -C "$repo" commit -q -m "$1"
}
linha() { grep -nxF -- "$1" "$2" | head -n1 | cut -d: -f1; }
quantas() { grep -cxF -- "$1" "$2"; }
# Recusa do --lancar: rc 1, motivo no stderr, nenhum commit e nenhuma tag nova.
recusa() {
  local antes tags
  antes="$(git -C "$repo" rev-parse HEAD)"
  tags="$(git -C "$repo" tag -l)"
  rodar --lancar "$1"
  ((rc == 1)) && [[ -s "$tmp/erros" ]] && [[ "$(git -C "$repo" rev-parse HEAD)" = "$antes" ]] &&
    [[ "$(git -C "$repo" tag -l)" = "$tags" ]] && [[ -z "$(git -C "$repo" status --porcelain -- CHANGELOG.md)" ]]
}
# Verdadeiro se as duas linhas foram achadas e a primeira vem antes.
antes() { [[ -n "$1" && -n "$2" ]] && (($1 < $2)); }

git init -q -b main "$repo"
commitar "inicio"
commitar "feat(validar): procura segredos"
commitar "fix: corrige o atalho"
git -C "$repo" switch -q -c lateral
commitar "feat: recurso lateral"
git -C "$repo" switch -q main
commitar "correção: ajusta a barra"
commitar "docs: explica o canal"
commitar "Integra agente/x"
n=$((n + 1))
GIT_AUTHOR_DATE="2026-01-01T00:00:$(printf %02d "$n")" GIT_COMMITTER_DATE="2026-01-01T00:00:$(printf %02d "$n")" \
  git -C "$repo" merge -q --no-ff -m "Merge branch 'lateral'" lateral
commitar "correções: vários ajustes"

# Sem tag.
rodar
conferir "sem tag: sem versão (hash curto)" \
  [ "$(saida)" = "sem versão ($(git -C "$repo" rev-parse --short HEAD))" ]
conferir "-h responde" bash -c '"$1" -h >/dev/null' _ "$repo_jangada/bin/jangada-versao"
conferir "--ajuda responde fora de repositório" \
  bash -c 'cd "$2" && JANGADA_CORE_PATH="$2" "$1" --ajuda | grep -q "^Uso:"' _ "$repo_jangada/bin/jangada-versao" "$tmp"
conferir "-C PASTA -h responde" \
  bash -c '"$1" -C "$2" -h | grep -q "^Uso:"' _ "$repo_jangada/bin/jangada-versao" "$tmp"

# Novidades de todo o histórico.
rodar --novidades
esperado="### Novidades
- recurso lateral
- validar: procura segredos
### Correções
- vários ajustes
- ajusta a barra
- corrige o atalho
### Outras mudanças
- docs: explica o canal
- inicio"
conferir "novidades: rc 0" [ "$rc" = 0 ]
conferir "novidades: feat(x) vira x: ..." tem "- validar: procura segredos"
conferir "novidades: commit do ramo integrado entra" tem "- recurso lateral"
conferir "novidades: fix: sem prefixo" tem "- corrige o atalho"
conferir "novidades: correção: sem prefixo" tem "- ajusta a barra"
conferir "novidades: correções: sem prefixo" tem "- vários ajustes"
conferir "novidades: outros ficam inteiros" tem "- docs: explica o canal"
conferir "novidades: ignora Integra" nao_tem "Integra"
conferir "novidades: ignora merge" nao_tem "Merge"
conferir "novidades: grupos, ordem e itens exatos" [ "$(compacta)" = "$esperado" ]
if [[ "$(compacta)" != "$esperado" ]]; then diff <(echo "$esperado") <(compacta) | sed 's/^/      /'; fi
conferir "novidades: linha em branco antes de cada grupo seguinte" \
  bash -c '[ "$(grep -B1 "^### Correções" "$1" | head -n1)" = "" ] && [ "$(grep -B1 "^### Outras mudanças" "$1" | head -n1)" = "" ]' _ "$tmp/saida"

# Lançamento da 0.1.0.
rodar --lancar 0.1.0
conferir "lancar 0.1.0: rc 0" [ "$rc" = 0 ]
conferir "lancar 0.1.0: tag anotada v0.1.0" [ "$(git -C "$repo" cat-file -t v0.1.0 2>/dev/null)" = tag ]
conferir "lancar 0.1.0: mensagem da tag" \
  [ "$(git -C "$repo" tag -l --format='%(contents:subject)' v0.1.0)" = "jangada 0.1.0" ]
conferir "lancar 0.1.0: a tag aponta para HEAD" \
  [ "$(git -C "$repo" rev-parse 'v0.1.0^{commit}' 2>/dev/null)" = "$(git -C "$repo" rev-parse HEAD)" ]
conferir "lancar 0.1.0: assunto do commit" [ "$(git -C "$repo" log -1 --format=%s)" = "chore(versao): 0.1.0" ]
conferir "lancar 0.1.0: o commit só muda o CHANGELOG.md" \
  [ "$(git -C "$repo" show --name-only --format= HEAD)" = CHANGELOG.md ]
conferir "lancar 0.1.0: árvore limpa depois" [ -z "$(git -C "$repo" status --porcelain)" ]
cl="$repo/CHANGELOG.md"
conferir "lancar 0.1.0: título do CHANGELOG" [ "$(head -n1 "$cl" 2>/dev/null)" = "# Registro de mudanças" ]
conferir "lancar 0.1.0: seção com a data de hoje" grep -qxF "## 0.1.0 ($hoje)" "$cl"
conferir "lancar 0.1.0: itens no CHANGELOG" \
  bash -c 'grep -qxF -- "- validar: procura segredos" "$1" && grep -qxF -- "- ajusta a barra" "$1" && grep -qxF "### Outras mudanças" "$1"' _ "$cl"
conferir "lancar 0.1.0: sem Integra nem Não lançado" bash -c '! grep -qE "Integra|Não lançado|chore\(versao\)" "$1"' _ "$cl"
rodar
conferir "lancar 0.1.0: versão 0.1.0" [ "$(saida)" = 0.1.0 ]

# Recusas.
conferir "recusa: nada novo desde a tag" recusa 0.2.0
commitar "feat(barra): mostra a versão"
echo x >"$repo/sujo.txt"
conferir "recusa: árvore suja" recusa 0.2.0
rm -f "$repo/sujo.txt"
conferir "recusa: versão menor" recusa 0.0.9
conferir "recusa: versão igual (tag existente)" recusa 0.1.0
conferir "recusa: semver inválido 1.2" recusa 1.2
conferir "recusa: semver inválido a.b.c" recusa a.b.c
# Tag maior que a última, mas já criada num commit fora do ramo.
git -C "$repo" switch -q -c solto v0.1.0~1
commitar "fora do ramo"
git -C "$repo" tag v0.5.0
git -C "$repo" switch -q main
conferir "recusa: tag já existe" recusa 0.5.0
conferir "recusa: a tag existente continua no lugar" \
  [ "$(git -C "$repo" rev-parse 'v0.5.0^{commit}')" = "$(git -C "$repo" rev-parse solto)" ]
git -C "$repo" tag -d v0.5.0 >/dev/null
git -C "$repo" branch -q -D solto

# Depois de um commit novo.
rodar
conferir "depois do commit: versão 0.1.0-1-g..." bash -c '[[ "$1" =~ ^0\.1\.0-1-g[0-9a-f]+$ ]]' _ "$(saida)"
rodar --novidades
conferir "depois do commit: novidades só com o novo" [ "$(compacta)" = "### Novidades
- barra: mostra a versão" ]
rodar --novidades v0.1.0 HEAD
conferir "novidades DE ATE explícitos" [ "$(compacta)" = "### Novidades
- barra: mostra a versão" ]
rodar --novidades HEAD
conferir "novidades sem mudança: saída vazia" [ -z "$(saida)" ]
rodar --registro
cp "$tmp/saida" "$tmp/registro"
l_nao="$(linha "## Não lançado" "$tmp/registro")"
l_item="$(linha "- barra: mostra a versão" "$tmp/registro")"
l_010="$(grep -n '^## 0\.1\.0 (' "$tmp/registro" | head -n1 | cut -d: -f1)"
conferir "registro: Não lançado antes de 0.1.0" antes "$l_nao" "$l_010"
conferir "registro: o item novo fica em Não lançado" bash -c '[[ -n "$1" && -n "$2" && -n "$3" ]] && (($1 < $2 && $2 < $3))' _ "$l_nao" "$l_item" "$l_010"
conferir "registro: não grava" [ -z "$(git -C "$repo" status --porcelain)" ]

# Lançamento da 0.2.0.
rodar --lancar 0.2.0
conferir "lancar 0.2.0: rc 0" [ "$rc" = 0 ]
conferir "lancar 0.2.0: tag v0.2.0" [ "$(git -C "$repo" cat-file -t v0.2.0 2>/dev/null)" = tag ]
l_020="$(linha "## 0.2.0 ($hoje)" "$cl")"
l_010="$(grep -n '^## 0\.1\.0 (' "$cl" | head -n1 | cut -d: -f1)"
l_item="$(linha "- barra: mostra a versão" "$cl")"
conferir "lancar 0.2.0: 0.2.0 antes de 0.1.0" antes "$l_020" "$l_010"
conferir "lancar 0.2.0: item novo sob 0.2.0" bash -c '[[ -n "$1" && -n "$2" && -n "$3" ]] && (($1 < $2 && $2 < $3))' _ "$l_020" "$l_item" "$l_010"
conferir "lancar 0.2.0: itens da 0.1.0 não se repetem" \
  [ "$(quantas "- validar: procura segredos" "$cl"):$(quantas "- barra: mostra a versão" "$cl")" = 1:1 ]
conferir "lancar 0.2.0: itens da 0.1.0 continuam sob 0.1.0" \
  antes "$l_010" "$(linha "- validar: procura segredos" "$cl")"
conferir "lancar 0.2.0: sem Não lançado" bash -c '! grep -qF "Não lançado" "$1"' _ "$cl"

# Sem -C: o repositório da pasta atual, ou o JANGADA_CORE_PATH fora de um.
conferir "sem -C: usa o repositório da pasta atual" [ "$(cd "$repo" && versao)" = 0.2.0 ]
conferir "sem -C: fora de um repositório usa o JANGADA_CORE_PATH" [ "$(cd "$tmp" && JANGADA_CORE_PATH="$repo" versao)" = 0.2.0 ]

if ((falhas)); then
  echo "$falhas falha(s); saídas em $tmp (mantido)"
  trap - EXIT
  exit 1
fi
echo "todos os testes do jangada-versao passaram"
