#!/usr/bin/env bash
# Testa a separação do Git entre as sessões: cada sessão aberta pelo
# jangada-agente é um clone próprio, que lê os objetos da raiz pelo
# alternates. Os agentes rodam no jangada-isolar de verdade (bwrap), ao mesmo
# tempo, e tentam mover refs e gravar objetos do outro e da base. Depois a
# integração: base que anda durante a espera, entrega aprovada, entrega com
# objeto adulterado, limpeza que leva o ramo à raiz e sessão antiga em
# worktree, que segue funcionando. O tmux e o agente são falsos.
#
# Sem bwrap capaz de criar o namespace, a parte isolada é pulada; com
# JANGADA_TESTES_EXIGIR_ISOLAMENTO=1, pular vira falha.
#
# Uso: testes/git-separado.sh
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

# Dentro de uma sessão isolada o jangada-agente recusa abrir sessão nova, e
# tudo aqui depende dele.
if sem_autoridade; then
  pulado_no_isolamento "git-separado: abrir sessões exige o controlador de fora"
  exit 0
fi
if ! bwrap --ro-bind / / --dev /dev --proc /proc true 2>/dev/null; then
  pular "git-separado: bwrap não cria namespace aqui"
  ((falhas == 0)) || exit 1
  exit 0
fi

# Fora do /tmp: no isolamento ele vira uma pasta vazia, e a raiz e o roteiro
# do agente têm de aparecer lá dentro, somente leitura.
tmp="$(mktemp -d -p /var/tmp jangada-git-separado.XXXXXX)"
trap 'chmod -R u+w "$tmp" 2>/dev/null; rm -rf "$tmp"' EXIT
casa="$tmp/casa"
mkdir -p "$casa" "$tmp/bin" "$tmp/config/jangada"
export GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
: >"$GIT_CONFIG_GLOBAL"
export HOME="$casa" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$casa/.local/state"
export JANGADA_CORE_PATH="$repo_jangada" FALSO_DIR="$tmp" JANGADA_VALIDAR_SEM_GITLEAKS=1
unset HYPRLAND_INSTANCE_SIGNATURE JANGADA_SESSAO JANGADA_REPO JANGADA_SIMULAR JANGADA_WORKTREES JANGADA_ISOLADO \
  JANGADA_VALIDAR_REVISOR JANGADA_VALIDAR_MODELO JANGADA_DELEGAR GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL \
  GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
estado="$XDG_STATE_HOME/jangada/agentes"
revisoes="$XDG_STATE_HOME/jangada/revisoes"
wts="$casa/.local/share/jangada-worktrees"
mkdir -p "$estado" "$revisoes"

cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case " $* " in
  *" has-session "*) exit 1 ;;
  *" kill-session "*) printf '%s\n' "${*: -1}" >>"$FALSO_DIR/mortas" ;;
esac
exit 0
EOF
for c in claude agy codex notify-send pkill; do
  printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/$c"
done
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"

# Projeto com identidade só no config local, que o clone tem de herdar, e a
# suíte que a integração roda.
proj="$tmp/proj"
git init -q -b main "$proj"
git -C "$proj" config user.name dono
git -C "$proj" config user.email dono@exemplo.invalid
mkdir -p "$proj/testes"
printf '#!/usr/bin/env bash\npwd >>"$FALSO_DIR/verificar-chamado"\nexit 0\n' >"$proj/testes/verificar.sh"
chmod +x "$proj/testes/verificar.sh"
echo base >"$proj/base.txt"
git -C "$proj" add -A
git -C "$proj" commit -q -m inicio
inicio="$(git -C "$proj" rev-parse HEAD)"

abrir() { # nome
  "$repo_jangada/bin/jangada-agente" --agente claude --projeto "$proj" --nome "$1" </dev/null >"$tmp/abrir-$1" 2>&1
}
fim() { # opções e sessão; a resposta à confirmação vem de $resposta
  "$repo_jangada/bin/jangada-agente-fim" "$@" <<<"${resposta:-}" >"$tmp/saida" 2>&1; rc=$?
}
# Parecer como o jangada-validar grava: marca, contexto da rodada e texto.
marca() { # sessão, commit aprovado, pasta onde o commit está
  local t b
  t="$(git -C "$3" rev-parse "$2^{tree}")"
  b="$(git -C "$proj" rev-parse main)"
  jq -n --arg c "$2" --arg t "$t" --arg b "$b" \
    '{cabeca: $c, num: 1, limpo: true, base: "main", base_sha: $b, candidate_sha: $c, candidate_tree: $t,
      reviewer: "agy", author: "claude", local_verified: true, independent: true}' >"$revisoes/validacao-$1.aprovado"
  jq -n --arg c "$2" --arg t "$t" --arg b "$b" '{candidate_sha: $c, candidate_tree: $t, base_sha: $b}' \
    >"$revisoes/validacao-$1-r1.contexto.json"
  echo "APROVADO" >"$revisoes/validacao-$1-r1.md"
}
# Refs e conteúdo de cada arquivo de objeto de um repositório.
retrato() {
  git -C "$1" for-each-ref --format='%(refname) %(objectname)'
  (cd "$1/.git/objects" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum)
}

echo "== abertura: clone próprio por sessão"
abrir a; conferir "sessão a aberta" test "$?" -eq 0
abrir b; conferir "sessão b aberta" test "$?" -eq 0
ca="$wts/proj/a"; cb="$wts/proj/b"
for n in a b; do
  c="$wts/proj/$n"
  conferir "$n: .git é pasta própria, não worktree" test -d "$c/.git"
  conferir "$n: a raiz não registra worktree" bash -c '! git -C "$1" worktree list --porcelain | grep -qxF "worktree $2"' _ "$proj" "$c"
  conferir "$n: objetos da raiz pelo alternates" grep -qxF "$(realpath "$proj/.git/objects")" "$c/.git/objects/info/alternates"
  conferir "$n: raiz gravada no config" test "$(git -C "$c" config --get jangada.raiz)" = "$proj"
  conferir "$n: identidade herdada da raiz" test "$(git -C "$c" config --get user.email)" = dono@exemplo.invalid
  conferir "$n: no ramo agente/$n, no commit da base" \
    test "$(git -C "$c" symbolic-ref HEAD) $(git -C "$c" rev-parse HEAD)" = "refs/heads/agente/$n $inicio"
  conferir "$n: ramo também na raiz" test "$(git -C "$proj" rev-parse "agente/$n")" = "$inicio"
  conferir "$n: sem hooks no clone" bash -c '[[ -z "$(ls -A "$1/.git/hooks" 2>/dev/null)" ]]' _ "$c"
done

echo "== dois agentes isolados ao mesmo tempo"
# Cada agente faz o próprio commit e tenta, de dentro do bwrap, alterar o
# outro e a base. Uma linha por tentativa: "feito" é falha do isolamento.
cat >"$tmp/agente.sh" <<'EOF'
nome="$1" outro="$2" raiz="$3" objetos_raiz="$4"
tentar() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then echo "feito: $d"; else echo "bloqueado: $d"; fi; }
echo "$nome" >"$nome.txt"
git add "$nome.txt" && git commit -q -m "commit de $nome" && echo "commit: $(git rev-parse HEAD)"
tentar "mover o ramo do outro" git -C "$outro" update-ref "refs/heads/agente/${outro##*/}" HEAD
tentar "gravar objeto no outro" sh -c 'echo x >"$1/.git/objects/plantado"' _ "$outro"
tentar "mover a main da raiz" git -C "$raiz" update-ref refs/heads/main HEAD
tentar "mover o ramo do outro na raiz" git -C "$raiz" update-ref "refs/heads/agente/${outro##*/}" HEAD
tentar "gravar objeto na raiz" sh -c 'echo x >"$1/plantado"' _ "$objetos_raiz"
tentar "regravar objeto da raiz" sh -c 'f="$(find "$1" -type f -path "*/[0-9a-f][0-9a-f]/*" | head -1)"; [ -n "$f" ] && chmod u+w "$f" && echo x >"$f"' _ "$objetos_raiz"
tentar "apagar objeto da raiz" sh -c 'f="$(find "$1" -type f -path "*/[0-9a-f][0-9a-f]/*" | head -1)"; [ -n "$f" ] && rm -f "$f"' _ "$objetos_raiz"
tentar "trocar o alternates" sh -c 'echo /tmp >.git/objects/info/alternates'
tentar "plantar hook" sh -c 'echo "touch /tmp/x" >.git/hooks/post-merge'
tentar "mudar o config" git config core.fsmonitor 'touch /tmp/x'
tentar "criar commondir" sh -c 'echo "$1/.git" >.git/commondir' _ "$raiz"
EOF
antes_raiz="$(retrato "$proj")"
marca_isolado="/tmp/.jangada-isolado-git-separado.$$"
isolado() { # clone, nome, outro clone
  (cd "$1" && env -u JANGADA_SESSAO -u CODEX_HOME -u XDG_CACHE_HOME -u JANGADA_ISOLADO \
    JANGADA_MARCA_ISOLADO="$marca_isolado" "$repo_jangada/bin/jangada-isolar" --provedor nenhum -- \
    bash "$tmp/agente.sh" "$2" "$3" "$proj" "$(realpath "$proj/.git/objects")")
}
isolado "$ca" a "$cb" >"$tmp/isolado-a" 2>&1 & pa=$!
isolado "$cb" b "$ca" >"$tmp/isolado-b" 2>&1 & pb=$!
wait "$pa"; ra=$?
wait "$pb"; rb=$?
conferir "agente a rodou isolado ($ra)" test "$ra" -eq 0
conferir "agente b rodou isolado ($rb)" test "$rb" -eq 0
for n in a b; do
  conferir "$n: commit feito no próprio clone" grep -q '^commit: ' "$tmp/isolado-$n"
  conferir "$n: as onze tentativas foram feitas" test "$(grep -c '^\(bloqueado\|feito\): ' "$tmp/isolado-$n")" -eq 11
  while IFS= read -r linha; do
    falha "$n: $linha"
  done < <(grep '^feito: ' "$tmp/isolado-$n")
done
conferir "a raiz não mudou: refs e cada objeto" test "$(retrato "$proj")" = "$antes_raiz"
c_a="$(sed -n 's/^commit: //p' "$tmp/isolado-a")"
c_b="$(sed -n 's/^commit: //p' "$tmp/isolado-b")"
conferir "a: ramo no próprio commit, filho da base" \
  test "$(git -C "$ca" rev-parse agente/a) $(git -C "$ca" rev-parse agente/a^)" = "$c_a $inicio"
conferir "b: ramo no próprio commit, filho da base" \
  test "$(git -C "$cb" rev-parse agente/b) $(git -C "$cb" rev-parse agente/b^)" = "$c_b $inicio"
conferir "nenhum objeto plantado nos clones" bash -c 'test ! -e "$1/.git/objects/plantado" && test ! -e "$2/.git/objects/plantado"' _ "$ca" "$cb"
conferir "os commits ficam fora da raiz" bash -c '! git -C "$1" cat-file -e "$2" 2>/dev/null && ! git -C "$1" cat-file -e "$3" 2>/dev/null' _ "$proj" "$c_a" "$c_b"
conferir "alternates intacto" grep -qxF "$(realpath "$proj/.git/objects")" "$ca/.git/objects/info/alternates"
conferir "config sem fsmonitor" bash -c '! git -C "$1" config --get core.fsmonitor' _ "$ca"

echo "== casa inteira: o outro clone aparece, mas só para leitura"
(cd "$ca" && env -u JANGADA_SESSAO -u JANGADA_ISOLADO JANGADA_ISOLAR_CASA=inteira JANGADA_MARCA_ISOLADO="$marca_isolado" \
  "$repo_jangada/bin/jangada-isolar" --provedor nenhum -- \
  bash -c 'test -d "$1/.git" || exit 3; git -C "$1" update-ref refs/heads/agente/b HEAD 2>/dev/null && exit 4
           echo x >"$1/.git/objects/plantado" 2>/dev/null && exit 5; exit 0' _ "$cb") >/dev/null 2>&1
conferir "casa inteira: b visível e intocável ($?)" test "$?" -eq 0
conferir "casa inteira: ramo de b intacto" test "$(git -C "$cb" rev-parse agente/b)" = "$c_b"

echo "== integração"
resposta=s
marca proj--a "$c_a" "$ca"
marca proj--b "$c_b" "$cb"
fim --integrar proj--a
conferir "a aprovada integra ($rc)" test "$rc" -eq 0
conferir "a: main no commit de a, sem merge" test "$(git -C "$proj" rev-parse main)" = "$c_a"
conferir "a: objetos de a entram na raiz" git -C "$proj" cat-file -e "$c_a^{tree}"
conferir "a: ramo de a na raiz aponta a entrega" test "$(git -C "$proj" rev-parse agente/a)" = "$c_a"
conferir "a: a suíte rodou fora da pasta do agente" grep -q "^$XDG_STATE_HOME/jangada/integracoes/" "$tmp/verificar-chamado"
conferir "a: a raiz segue íntegra" git -C "$proj" fsck --no-dangling --connectivity-only

# A base andou depois do parecer de b: recusa, com rebase no clone de b, e o
# parecer novo vale para o commit novo.
fim --integrar proj--b
conferir "base andou: recusa ($rc)" test "$rc" -ne 0
conferir "base andou: pede parecer do commit novo" grep -q 'o parecer tem de ser do commit novo' "$tmp/saida"
conferir "base andou: main intocada" test "$(git -C "$proj" rev-parse main)" = "$c_a"
novo_b="$(git -C "$cb" rev-parse agente/b)"
conferir "base andou: b refeito sobre a base nova, no clone" test "$(git -C "$cb" rev-parse agente/b^)" = "$c_a"
fim --integrar proj--b
conferir "base andou: parecer antigo não vale ($rc)" bash -c '[ "$1" -ne 0 ] && grep -q "falta parecer APROVADO" "$2"' _ "$rc" "$tmp/saida"
marca proj--b "$novo_b" "$cb"
fim --integrar proj--b
conferir "b com parecer novo integra ($rc)" test "$rc" -eq 0
conferir "b: main no commit novo de b" test "$(git -C "$proj" rev-parse main)" = "$novo_b"
git -C "$proj" reset -q --hard main

# Parecer dado contra a base, que anda depois sob a trava: recusa sem avanço.
abrir c; conferir "sessão c aberta" test "$?" -eq 0
cc="$wts/proj/c"
echo bom >"$cc/c.txt"
git -C "$cc" add c.txt
git -C "$cc" commit -q -m "commit de c"
c_c="$(git -C "$cc" rev-parse HEAD)"
marca proj--c "$c_c" "$cc"
git -C "$proj" commit -q --allow-empty -m "base andou"
base_nova="$(git -C "$proj" rev-parse main)"
fim --integrar proj--c
conferir "c: base mudou depois do parecer: recusa ($rc)" test "$rc" -ne 0
conferir "c: main intocada" test "$(git -C "$proj" rev-parse main)" = "$base_nova"

echo "== entrega com objeto adulterado"
abrir d; conferir "sessão d aberta" test "$?" -eq 0
cd_="$wts/proj/d"
echo bom-de-d >"$cd_/d.txt"
git -C "$cd_" add d.txt
git -C "$cd_" commit -q -m "commit de d"
c_d="$(git -C "$cd_" rev-parse HEAD)"
bom="$(git -C "$cd_" rev-parse HEAD:d.txt)"
mau="$(echo mau-de-d | git -C "$cd_" hash-object -w --stdin)"
arq_bom="$cd_/.git/objects/${bom:0:2}/${bom:2}"
chmod u+w "$arq_bom"
cp -f "$cd_/.git/objects/${mau:0:2}/${mau:2}" "$arq_bom"
marca proj--d "$c_d" "$cd_"
antes_d="$(retrato "$proj")"
rm -f "$tmp/verificar-chamado"
fim --integrar proj--d
conferir "adulterado: recusa ($rc)" test "$rc" -ne 0
conferir "adulterado: main intocada" test "$(git -C "$proj" rev-parse main)" = "$base_nova"
conferir "adulterado: o conteúdo trocado não entra na raiz" bash -c '! git -C "$1" cat-file -e "$2" 2>/dev/null' _ "$proj" "$mau"
conferir "adulterado: a raiz segue íntegra" git -C "$proj" fsck --no-dangling
conferir "adulterado: a raiz não mudou: refs e cada objeto" test "$(retrato "$proj")" = "$antes_d"
conferir "adulterado: a suíte nem rodou" test ! -e "$tmp/verificar-chamado"

echo "== encerramento"
resposta=""
fim proj--a
conferir "a encerra ($rc)" test "$rc" -eq 0
conferir "a: clone removido" test ! -e "$ca"
conferir "a: ramo mantido na raiz, com a entrega" test "$(git -C "$proj" rev-parse agente/a)" = "$c_a"
# Commit novo em c depois da recusa, e um ramo extra: o ramo vai para a raiz,
# o extra pede confirmação.
echo mais >"$cc/mais.txt"
git -C "$cc" add mais.txt
git -C "$cc" commit -q -m mais
c_c2="$(git -C "$cc" rev-parse HEAD)"
git -C "$cc" branch extra
git -C "$cc" checkout -q -b extra2
git -C "$cc" commit -q --allow-empty -m "só no extra2"
git -C "$cc" checkout -q agente/c
fim proj--c
conferir "ramo extra com commit próprio: sem confirmação, recusa ($rc)" test "$rc" -ne 0
conferir "ramo extra: explica" grep -q 'refs/heads/extra2' "$tmp/saida"
conferir "ramo extra: o contido no ramo da sessão não pede nada" bash -c '! grep -q "refs/heads/extra$" "$1"' _ "$tmp/saida"
conferir "ramo extra: clone mantido" test -d "$cc/.git"
resposta=s
fim proj--c
conferir "ramo extra confirmado: encerra ($rc)" test "$rc" -eq 0
conferir "c: clone removido" test ! -e "$cc"
conferir "c: commits do clone no ramo da raiz" test "$(git -C "$proj" rev-parse agente/c)" = "$c_c2"
conferir "c: objetos levados à raiz íntegros" git -C "$proj" fsck --no-dangling
# Ramo com objeto adulterado: o fetch recusa e o clone fica.
resposta=""
fim proj--d
conferir "d adulterado: não encerra ($rc)" test "$rc" -ne 0
conferir "d adulterado: clone mantido" test -d "$cd_/.git"
conferir "d adulterado: o conteúdo trocado não entra na raiz" bash -c '! git -C "$1" cat-file -e "$2" 2>/dev/null' _ "$proj" "$mau"

echo "== sessão antiga em worktree"
git -C "$proj" worktree add -q -b agente/velha "$wts/proj/velha" main
echo velha >"$wts/proj/velha/velha.txt"
git -C "$wts/proj/velha" add velha.txt
git -C "$wts/proj/velha" commit -q -m velha
abrir velha; conferir "worktree antigo reaproveitado ($?)" test "$?" -eq 0
conferir "worktree antigo: avisa, sem converter" grep -q 'worktree antigo' "$tmp/abrir-velha"
conferir "worktree antigo: segue worktree" test -f "$wts/proj/velha/.git"
c_v="$(git -C "$proj" rev-parse agente/velha)"
marca proj--velha "$c_v" "$proj"
resposta=s
fim --integrar proj--velha
conferir "worktree antigo: integra ($rc)" test "$rc" -eq 0
conferir "worktree antigo: main no commit dele" test "$(git -C "$proj" rev-parse main)" = "$c_v"
resposta=""
fim proj--velha
conferir "worktree antigo: encerra ($rc)" test "$rc" -eq 0
conferir "worktree antigo: removido pelo git" bash -c '! git -C "$1" worktree list --porcelain | grep -q velha && test ! -e "$2"' _ "$proj" "$wts/proj/velha"

if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "tudo certo"
