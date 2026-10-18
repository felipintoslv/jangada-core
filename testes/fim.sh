#!/usr/bin/env bash
# Testa o jangada-agente-fim e o jangada-agentes --limpar-concluidos com estado
# adulterado: o arquivo SESSAO.json é gravável pelo agente isolado, então pid,
# ramo, worktree, raiz, base e estado vindos dele não podem levar a operação
# destrutiva fora da sessão. O tmux é falso: lista as sessões de um arquivo e
# registra o kill-session.
#
# Uso: testes/fim.sh
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
  if "$@" >/dev/null; then ok "$d"
  elif ! pulado_se_recusado "${tmp:-}" "$d"; then falha "$d"; fi
}

tmp="$(mktemp -d)"
erros_dos_pulados "$tmp"
vitima=""
trap '[[ -n "$vitima" ]] && kill "$vitima" 2>/dev/null; rm -rf "$tmp"' EXIT

export GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
: >"$GIT_CONFIG_GLOBAL"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/home/.config" XDG_STATE_HOME="$tmp/home/.local/state"
export JANGADA_CORE_PATH="$repo_jangada"
unset HYPRLAND_INSTANCE_SIGNATURE JANGADA_SESSAO JANGADA_REPO JANGADA_SIMULAR JANGADA_WORKTREES JANGADA_ISOLADO
unset JANGADA_VALIDAR_REVISOR JANGADA_VALIDAR_MODELO
export JANGADA_VALIDAR_SEM_GITLEAKS=1
estado="$XDG_STATE_HOME/jangada/agentes"
wts="$HOME/.local/share/jangada-worktrees"
mkdir -p "$estado" "$wts" "$tmp/bin"

export FALSO_DIR="$tmp"
: >"$tmp/sessoes"
cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case " $* " in
  *" list-sessions "*) cat "$FALSO_DIR/sessoes" ;;
  *" has-session "*) s="${*: -1}"; grep -qxF "${s#=}" "$FALSO_DIR/sessoes" ;;
  *" kill-session "*) printf '%s\n' "${*: -1}" >>"$FALSO_DIR/mortas" ;;
esac
EOF
# Revisor falso do jangada-validar: registra a chamada e responde
# $FALSO_RESPOSTA. Com $FALSO_AVANCA, faz antes um commit nesse worktree, como
# o agente que segue trabalhando durante a revisão; com $FALSO_COMANDO, roda
# o comando.
cat >"$tmp/bin/claude" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
: >>"$FALSO_DIR/revisor-chamado"
if [[ -n "${FALSO_AVANCA:-}" ]]; then
  echo depois >"$FALSO_AVANCA/depois.txt"
  git -C "$FALSO_AVANCA" add depois.txt
  git -C "$FALSO_AVANCA" commit --quiet -m depois
fi
[[ -z "${FALSO_COMANDO:-}" ]] || eval "$FALSO_COMANDO"
printf '%b\n' "${FALSO_RESPOSTA:-STATUS: REVISAR}"
EOF
chmod +x "$tmp/bin/tmux" "$tmp/bin/claude"
export PATH="$tmp/bin:$PATH"

# Repositório do projeto e um segundo repositório, alvo do agente.
proj="$tmp/proj"; outro="$tmp/outro"
for r in "$proj" "$outro"; do
  git init --quiet -b main "$r"
  echo a >"$r/a"; git -C "$r" add a; git -C "$r" commit --quiet -m inicio
done
git -C "$outro" branch agente/x

gravar() { # sessão e campos em JSON
  printf '%s\n' "$2" >"$estado/$1.json"
}
fim() { executar "$tmp" "$repo_jangada/bin/jangada-agente-fim" "$@" </dev/null >"$tmp/saida" 2>&1; rc=$?; }
novo_worktree() { # repositório, nome
  git -C "$1" worktree add --quiet -b "agente/$2" "$wts/$(basename "$1")/$2" main
}
recusado() { # descrição, sessão
  conferir "$1: recusado ($rc)" test "$rc" -ne 0
  conferir "$1: explica" grep -q 'estado inválido' "$tmp/saida"
  conferir "$1: estado mantido" test -f "$estado/$2.json"
  conferir "$1: tmux intocado" test ! -s "$tmp/mortas"
}

echo "== pid do estado"
sleep 300 & vitima=$!
gravar p "{\"raiz\": \"$proj\", \"estado\": \"trabalhando\", \"pid\": $vitima}"
fim p
conferir "sessão direta encerra ($rc)" test "$rc" -eq 0
conferir "o pid gravado não é morto" kill -0 "$vitima"
kill "$vitima" 2>/dev/null; wait "$vitima" 2>/dev/null; vitima=""
: >"$tmp/mortas"

echo "== ramo inválido"
novo_worktree "$proj" r1
gravar r1 "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/r1\", \"ramo\": \"main\", \"base\": \"main\"}"
fim r1
recusado "ramo main" r1
conferir "ramo main: worktree mantido" test -d "$wts/proj/r1"

echo "== worktree fora de JANGADA_WORKTREES"
git -C "$proj" worktree add --quiet -b agente/f "$tmp/fora/proj/f" main
gravar f "{\"raiz\": \"$proj\", \"worktree\": \"$tmp/fora/proj/f\", \"ramo\": \"agente/f\", \"base\": \"main\"}"
fim f
recusado "worktree fora" f
conferir "worktree fora: mantido" test -d "$tmp/fora/proj/f"

gravar d "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/../../x/r1\", \"ramo\": \"agente/r1\", \"base\": \"main\"}"
fim d
recusado "worktree com .." d

echo "== worktree por link simbólico"
mkdir -p "$tmp/alvo"
git -C "$outro" worktree add --quiet -b agente/l "$tmp/alvo/l" main
ln -s "$tmp/alvo" "$wts/outro"
gravar l "{\"raiz\": \"$outro\", \"worktree\": \"$wts/outro/l\", \"ramo\": \"agente/l\", \"base\": \"main\"}"
fim l
recusado "link simbólico" l
conferir "link simbólico: worktree mantido" test -d "$tmp/alvo/l"
rm "$wts/outro"

echo "== raiz de outro repositório"
novo_worktree "$proj" x
gravar x "{\"raiz\": \"$outro\", \"worktree\": \"$wts/proj/x\", \"ramo\": \"agente/x\", \"base\": \"main\"}"
fim x
recusado "raiz trocada" x
conferir "raiz trocada: ramo do outro repositório mantido" git -C "$outro" show-ref --quiet --verify refs/heads/agente/x
fim --integrar x
conferir "raiz trocada com --integrar: recusado ($rc)" test "$rc" -ne 0

# Worktree já removido: a raiz precisa ter o nome da pasta do repositório.
gravar y "{\"raiz\": \"$outro\", \"worktree\": \"$wts/proj/x-sumiu\", \"ramo\": \"agente/x-sumiu\", \"base\": \"main\"}"
fim y
recusado "raiz trocada sem worktree" y

echo "== pasta que não é worktree registrado"
mkdir -p "$wts/proj/solto"
git init --quiet "$wts/proj/solto"
gravar s1 "{\"raiz\": \"$wts/proj/solto\", \"worktree\": \"$wts/proj/solto\", \"ramo\": \"agente/solto\", \"base\": \"main\"}"
fim s1
recusado "worktree igual à raiz" s1
gravar s2 "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/solto\", \"ramo\": \"agente/solto\", \"base\": \"main\"}"
fim s2
recusado "pasta de outro repositório" s2
# Pasta cujo .git aponta para o registro de outro worktree do projeto: mesmo
# diretório comum, mas não é ela que o repositório registra.
mkdir -p "$wts/proj/copia"
printf 'gitdir: %s\n' "$proj/.git/worktrees/r1" >"$wts/proj/copia/.git"
gravar s3 "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/copia\", \"ramo\": \"agente/copia\", \"base\": \"main\"}"
fim s3
recusado "pasta sem registro" s3
conferir "pasta sem registro: motivo" grep -q 'não é worktree registrado' "$tmp/saida"

echo "== base que vira opção do git"
gravar b "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/x\", \"ramo\": \"agente/x\", \"base\": \"--output=$tmp/escrito\"}"
fim b
recusado "base --output" b
conferir "base --output: nada gravado" test ! -e "$tmp/escrito"

echo "== estado válido"
mkdir -p "$XDG_STATE_HOME/jangada"
printf '%s\n' '{"sessao":"x","execucao":null,"autor":"antigo","inicio":"2026-04-02T00:00:00Z"}' \
  >"$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"
printf '[]\n{"truncado":\n' >>"$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"
ln -s "$proj" "$tmp/proj-alias"
gravar x "{\"raiz\": \"$tmp/proj-alias\", \"worktree\": \"$wts/proj/x\", \"ramo\": \"agente/x\", \"base\": \"main\", \"estado\": \"concluido\", \"execucao\": \"forjada\", \"agente\": \"/usr/bin/claude --flag\", \"desde\": \"2026-04-02T00:00:00Z\"}"
mkdir -p "$XDG_STATE_HOME/jangada/revisoes"
jq -n --arg raiz "$proj" --arg wt "$wts/proj/x" \
  '{sessao:"x", raiz:$raiz, worktree:$wt, execucao:"exe-1111111111111111", agente:"codex", desde:"2026-04-01T12:00:00Z"}' \
  >"$XDG_STATE_HOME/jangada/revisoes/x.json"
# Pareceres da sessão x e da vizinha x-rotas, com o mesmo prefixo.
printf 'STATUS: APROVADO\n' >"$estado/validacao-x-r1.md"
printf 'STATUS: APROVADO\n' >"$estado/validacao-x-rotas-r1.md"
fim x
conferir "pareceres da sessão apagados" test ! -e "$estado/validacao-x-r1.md"
conferir "parecer da sessão vizinha mantido" test -f "$estado/validacao-x-rotas-r1.md"
rm -f "$estado/validacao-x-rotas-r1.md"
conferir "encerra ($rc)" test "$rc" -eq 0
conferir "worktree removido" test ! -d "$wts/proj/x"
conferir "estado apagado" test ! -f "$estado/x.json"
conferir "estado divergente não controla a duplicidade nem o projeto" \
  jq -Rne '[inputs | fromjson? | objects] | map(select(.sessao == "x")) | length == 2 and any(.[]; .sessao == "x" and .inicio == "2026-04-01T12:00:00Z" and .execucao == "exe-1111111111111111" and .autor == "codex" and .projeto == "proj")' \
  "$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"
conferir "ramo mantido" git -C "$proj" show-ref --quiet --verify refs/heads/agente/x

echo "== cópia protegida controla duplicidade com JSONL danificado"
gravar dup "{\"raiz\": \"$outro\", \"estado\": \"concluido\", \"execucao\": \"forjada\"}"
jq -n --arg raiz "$proj" \
  '{sessao:"dup", raiz:$raiz, worktree:"", execucao:"exe-2222222222222222", agente:"codex", desde:"2026-04-03T00:00:00Z"}' \
  >"$XDG_STATE_HOME/jangada/revisoes/dup.json"
jq -nc '{sessao:"dup",projeto:"proj",execucao:"exe-2222222222222222",autor:"codex",inicio:"2026-04-03T00:00:00Z"}' \
  >>"$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"
fim dup
conferir "duplicidade ignora linhas JSONL inválidas" test "$rc" -eq 0
conferir "registro duplicado não é gravado de novo" \
  jq -Rne '[inputs | fromjson? | objects | select(.sessao == "dup")] | length == 1' "$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"

echo "== duas tarefas seguidas e a mesma tarefa duas vezes"
consumo="$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"
encerrar_seq() { # sessão, execução
  gravar "$1" "{\"raiz\": \"$proj\", \"estado\": \"concluido\"}"
  jq -n --arg s "$1" --arg raiz "$proj" --arg e "$2" \
    '{sessao:$s, raiz:$raiz, worktree:"", execucao:$e, agente:"codex", desde:"2026-04-05T00:00:00Z"}' \
    >"$XDG_STATE_HOME/jangada/revisoes/$1.json"
  fim "$1"
}
encerrar_seq seq1 exe-4444444444444444
encerrar_seq seq2 exe-5555555555555555
conferir "duas tarefas seguidas gravam duas linhas" \
  jq -Rne '[inputs | fromjson? | objects | select(.sessao == "seq1" or .sessao == "seq2")] | length == 2' "$consumo"
encerrar_seq seq1 exe-4444444444444444
conferir "a mesma tarefa encerrada duas vezes grava uma linha" \
  jq -Rne '[inputs | fromjson? | objects | select(.sessao == "seq1")] | length == 1' "$consumo"

echo "== tokens do revisor somados por sessão e execução"
# Só entram as rodadas de revisoes/validar.jsonl. As do validar.jsonl do
# estado, que o agente grava, ficam fora, mesmo forjadas com tokens.
rodada_rev() { # execução, data, resultado, tokens_revisor (JSON ou vazio)
  jq -nc --arg e "$1" --arg d "$2" --arg r "$3" --arg t "$4" \
    '{data:$d, rotulo:"rev", rodada:1, resultado:$r, etapa:"revisor", execucao:$e}
     + (if $t == "" then {} else {tokens_revisor:($t | fromjson)} end)'
}
{
  rodada_rev exe-6666666666666666 2026-04-06T10:00:00Z revisar '{"entrada":null,"saida":null,"cache_lido":null,"total":1000}'
  rodada_rev exe-6666666666666666 2026-04-06T11:00:00Z revisar '{"entrada":null,"saida":null,"cache_lido":null,"total":null}'
  rodada_rev exe-7777777777777777 2026-04-06T11:30:00Z aprovado '{"entrada":9,"saida":9,"cache_lido":9,"total":9}'
  rodada_rev exe-6666666666666666 2026-04-05T23:00:00Z revisar '{"entrada":9,"saida":9,"cache_lido":9,"total":9}'
  rodada_rev exe-6666666666666666 2026-04-06T11:40:00Z erro ''
} >"$XDG_STATE_HOME/jangada/validar.jsonl"
{
  rodada_rev exe-6666666666666666 2026-04-06T10:00:00Z revisar '{"entrada":null,"saida":null,"cache_lido":null,"total":1000}'
  rodada_rev exe-6666666666666666 2026-04-06T11:00:00Z revisar '{"entrada":null,"saida":null,"cache_lido":null,"total":null}'
  rodada_rev exe-7777777777777777 2026-04-06T11:30:00Z aprovado '{"entrada":9,"saida":9,"cache_lido":9,"total":9}'
  rodada_rev exe-6666666666666666 2026-04-05T23:00:00Z revisar '{"entrada":9,"saida":9,"cache_lido":9,"total":9}'
  rodada_rev exe-6666666666666666 2026-04-06T11:40:00Z erro ''
  rodada_rev exe-6666666666666666 2026-04-06T12:00:00Z aprovado '{"entrada":300,"saida":40,"cache_lido":200,"total":560}'
} >"$XDG_STATE_HOME/jangada/revisoes/validar.jsonl"
gravar rev "{\"raiz\": \"$proj\", \"estado\": \"concluido\"}"
jq -n --arg raiz "$proj" \
  '{sessao:"rev", raiz:$raiz, worktree:"", execucao:"exe-6666666666666666", agente:"codex", desde:"2026-04-06T00:00:00Z"}' \
  >"$XDG_STATE_HOME/jangada/revisoes/rev.json"
fim rev
conferir "tokens do revisor: soma campo a campo de revisoes/, nulo onde nenhuma rodada mediu" \
  jq -Rne '[inputs | fromjson? | objects | select(.sessao == "rev")] | length == 1 and .[0].tokens_revisor
    == {entrada:300, saida:40, cache_lido:200, total:1560, rodadas_medidas:2, rodadas:3}' "$consumo"
conferir "tokens do revisor: linha antiga continua sem o campo" \
  jq -Rne '[inputs | fromjson? | objects | select(.sessao == "x" and .autor == "antigo")] | length == 1 and (.[0] | has("tokens_revisor") | not)' "$consumo"
rm -f "$XDG_STATE_HOME/jangada/validar.jsonl" "$XDG_STATE_HOME/jangada/revisoes/validar.jsonl"

echo "== cópia protegida ausente"
gravar sem-copia "{\"raiz\": \"$outro\", \"estado\": \"concluido\", \"execucao\": \"forjada\"}"
fim sem-copia
conferir "encerramento sem cópia protegida sai com 0" test "$rc" -eq 0
conferir "sem cópia, projeto e tokens ficam nulos com motivo" \
  jq -Rne '[inputs | fromjson? | objects] | any(.[]; .sessao == "sem-copia" and .projeto == null and .tokens.entrada == null and (.motivo | strings | length > 0))' \
  "$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"

echo "== estado de agente ausente, cópia protegida presente"
mkdir -p "$XDG_STATE_HOME/jangada/revisoes"
printf '%s\n' 'sem-estado' >>"$tmp/sessoes"
jq -n --arg raiz "$proj" '{sessao:"sem-estado",raiz:$raiz,worktree:"",execucao:"exe-3333333333333333",agente:"codex",desde:"2026-04-04T00:00:00Z"}' \
  >"$XDG_STATE_HOME/jangada/revisoes/sem-estado.json"
fim sem-estado
conferir "encerramento sem estado sai com 0" test "$rc" -eq 0
conferir "estado ausente ainda grava consumo com dados protegidos" \
  jq -Rne '[inputs | fromjson? | objects] | any(.[]; .sessao == "sem-estado" and .projeto == "proj" and .execucao == "exe-3333333333333333")' \
  "$XDG_STATE_HOME/jangada/consumo-tarefas.jsonl"
: >"$tmp/mortas"

echo "== --integrar: avanço rápido com parecer de fora, suíte e confirmação"
revisoes="$XDG_STATE_HOME/jangada/revisoes"
mkdir -p "$revisoes"
# Suíte falsa do projeto: registra a pasta em que rodou, roda $FALSO_COMANDO
# (o que acontece na máquina enquanto a suíte roda) e sai com $FALSO_VERIFICAR.
mkdir -p "$proj/testes"
cat >"$proj/testes/verificar.sh" <<'EOF'
#!/usr/bin/env bash
pwd >>"$FALSO_DIR/verificar-chamado"
[[ -z "${JANGADA_ISOLADO:-}" ]] || exit 9
[[ -z "${FALSO_COMANDO:-}" ]] || eval "$FALSO_COMANDO"
exit "${FALSO_VERIFICAR:-0}"
EOF
chmod +x "$proj/testes/verificar.sh"
git -C "$proj" add testes/verificar.sh
git -C "$proj" commit --quiet -m "suíte do projeto"
# Remoto do projeto e git que registra as chamadas: nada pode ser enviado.
git init --quiet --bare "$tmp/remoto.git"
git -C "$proj" remote add origin "$tmp/remoto.git"
git -C "$proj" push --quiet -u origin main 2>/dev/null
remoto_antes="$(git -C "$tmp/remoto.git" rev-parse main)"
git_real="$(command -v git)"
cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
exec "$git_real" "\$@"
EOF
chmod +x "$tmp/bin/git"

integrar_teste() { # sessão, resposta à confirmação, opções extras
  local s="$1" r="$2"; shift 2
  rm -f "$tmp/verificar-chamado"
  executar "$tmp" "$repo_jangada/bin/jangada-agente-fim" --integrar "$@" "$s" <<<"$r" >"$tmp/saida" 2>&1; rc=$?
}
preparar() { # sessão
  novo_worktree "$proj" "$1"
  echo "$1" >"$wts/proj/$1/$1.txt"
  git -C "$wts/proj/$1" add "$1.txt"
  git -C "$wts/proj/$1" commit --quiet -m "$1"
  gravar "$1" "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/$1\", \"ramo\": \"agente/$1\", \"base\": \"main\", \"estado\": \"concluido\"}"
  # Cópia protegida que o jangada-agente grava ao abrir a sessão.
  cp "$estado/$1.json" "$revisoes/$1.json"
}
# Marca como o jangada-validar grava: sessão, pasta e, para trocar um campo,
# um filtro do jq.
marca() {
  local c
  c="$(git -C "$proj" rev-parse "agente/$1")"
  jq -n --arg c "$c" --arg t "$(git -C "$proj" rev-parse "$c^{tree}")" --arg b "$(git -C "$proj" rev-parse main)" \
    '{cabeca: $c, num: 1, limpo: true, base: "main", base_sha: $b, candidate_sha: $c, candidate_tree: $t,
      reviewer: "agy", author: "claude", local_verified: true, independent: true}' | jq "${3:-.}" >"$2/validacao-$1.aprovado"
}
# HEAD, índice, arquivos rastreados e arquivos novos da cópia principal.
foto() {
  git -C "$proj" rev-parse HEAD
  git -C "$proj" status --porcelain --untracked-files=all --ignore-submodules=none
  git -C "$proj" diff --ignore-submodules=none
  git -C "$proj" diff --cached --ignore-submodules=none
}
intacta() { [[ "$(foto)" == "$1" ]]; }
mantida() { # descrição, sessão
  conferir "$1: sessão mantida" test -f "$estado/$2.json"
  conferir "$1: worktree mantido" test -d "$wts/proj/$2"
  conferir "$1: ramo mantido" git -C "$proj" show-ref --quiet --verify "refs/heads/agente/$2"
  conferir "$1: tmux intocado" test ! -s "$tmp/mortas"
}
recusa() { # descrição, sessão, trecho do motivo, foto da cópia principal
  conferir "$1: recusa ($rc)" test "$rc" -ne 0
  conferir "$1: explica" grep -q -- "$3" "$tmp/saida"
  conferir "$1: cópia principal intacta" intacta "$4"
  mantida "$1" "$2"
}

# Cópia principal com trabalho do usuário: arquivo rastreado alterado, índice
# e arquivo novo. Recusa antes de qualquer etapa, com aprovação válida.
preparar suja
marca suja "$revisoes"
echo usuario >"$proj/a"
echo indice >"$proj/indice"; git -C "$proj" add indice
echo novo >"$proj/nao-rastreado"
antes="$(foto)"
for modo in terminal grafica; do
  args=()
  [[ "$modo" == terminal ]] || args=(--confirmacao "$(git -C "$proj" rev-parse HEAD)" "$(git -C "$proj" rev-parse agente/suja)")
  integrar_teste suja s "${args[@]}"
  recusa "cópia principal alterada ($modo)" suja 'tem alterações sem commit' "$antes"
  conferir "cópia principal alterada ($modo): a suíte não roda" test ! -e "$tmp/verificar-chamado"
  conferir "cópia principal alterada ($modo): arquivo novo preservado" grep -qx novo "$proj/nao-rastreado"
done
git -C "$proj" rm --quiet --cached indice
rm -f "$proj/indice" "$proj/nao-rastreado"
echo a >"$proj/a"
antes="$(foto)"
# Só um arquivo novo também conta como alteração, mesmo com a configuração
# do repositório escondendo-o.
echo novo >"$proj/nao-rastreado"
git -C "$proj" config status.showUntrackedFiles no
integrar_teste suja s
git -C "$proj" config --unset status.showUntrackedFiles
conferir "arquivo novo na cópia principal: recusa ($rc)" \
  bash -c '[ "$1" -ne 0 ] && grep -q "tem alterações sem commit" "$2" && grep -qx novo "$3/nao-rastreado"' _ "$rc" "$tmp/saida" "$proj"
conferir "arquivo novo na cópia principal: a suíte não roda" test ! -e "$tmp/verificar-chamado"
rm -f "$proj/nao-rastreado"

# --sem-revisao não libera, nem com aprovação válida e resposta s.
integrar_teste suja s --sem-revisao
recusa "--sem-revisao" suja 'sem-revisao não libera' "$antes"
conferir "--sem-revisao: a suíte não roda" test ! -e "$tmp/verificar-chamado"

# Dentro do isolamento não há parecer que valha.
JANGADA_ISOLADO=1 integrar_teste suja s
recusa "dentro do isolamento" suja 'fora dele' "$antes"

# Pareceres que não valem: ausente, forjado em agentes/, de outro commit, com
# worktree sujo na revisão, sem verificação local, com outra árvore, contra
# outra base, formato antigo e autorrevisão. O revisor não é chamado aqui.
preparar p1
integrar_teste p1 s
recusa "sem parecer" p1 'falta parecer APROVADO gravado fora do isolamento' "$antes"
conferir "sem parecer: diz como revisar" grep -q 'JANGADA_SESSAO=p1 jangada-validar --base main' "$tmp/saida"
marca p1 "$estado"
printf 'STATUS: APROVADO\n' >"$estado/validacao-p1-r1.md"
integrar_teste p1 s
recusa "parecer forjado em agentes/" p1 'falta parecer APROVADO' "$antes"
for caso in '.candidate_sha = "0123456789012345678901234567890123456789"' '.limpo = false' \
    '.local_verified = false' '.candidate_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"'; do
  marca p1 "$revisoes" "$caso"
  integrar_teste p1 s
  recusa "parecer com $caso" p1 'falta parecer APROVADO' "$antes"
done
marca p1 "$revisoes" '.base_sha = "0123456789012345678901234567890123456789"'
integrar_teste p1 s
recusa "parecer contra outra base" p1 'foi dado contra main' "$antes"
printf '%s 1 limpo\n' "$(git -C "$proj" rev-parse agente/p1)" >"$revisoes/validacao-p1.aprovado"
integrar_teste p1 s
recusa "marca no formato antigo" p1 'falta parecer APROVADO' "$antes"
marca p1 "$revisoes" '.independent = false | .reviewer = "claude"'
integrar_teste p1 s
recusa "autorrevisão" p1 'só tem autorrevisão' "$antes"
conferir "pareceres inválidos: a suíte não roda e o revisor não é chamado" \
  bash -c 'test ! -e "$1/verificar-chamado" && test ! -e "$1/revisor-chamado"' _ "$tmp"

# Estado gravável pelo agente diferente da cópia protegida da sessão.
marca p1 "$revisoes"
git -C "$proj" branch outra main
gravar p1 "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/p1\", \"ramo\": \"agente/p1\", \"base\": \"outra\", \"estado\": \"concluido\"}"
integrar_teste p1 s
recusa "base trocada no estado" p1 'diferem da cópia protegida' "$antes"
cp "$revisoes/p1.json" "$estado/p1.json"

# Sem a confirmação humana nada roda.
integrar_teste p1 n
recusa "resposta n" p1 'sem confirmação' "$antes"
conferir "resposta n: a suíte não roda" test ! -e "$tmp/verificar-chamado"
integrar_teste p1 ''
recusa "sem resposta" p1 'sem confirmação' "$antes"

# Suíte com falha: nada é integrado. Ela roda numa cópia em integracoes/,
# fora da worktree da tarefa, e a cópia sai no fim.
FALSO_VERIFICAR=1 integrar_teste p1 s
recusa "suíte com falha" p1 'não saiu com 0' "$antes"
conferir "suíte: roda numa cópia protegida, não na worktree" \
  grep -q "^$XDG_STATE_HOME/jangada/integracoes/" "$tmp/verificar-chamado"
conferir "suíte: a cópia protegida é removida" bash -c '[[ -z "$(ls -A "$1")" ]]' _ "$XDG_STATE_HOME/jangada/integracoes"

# Aprovação para o commit exato, confirmação e suíte com 0: avanço rápido.
c_p1="$(git -C "$proj" rev-parse agente/p1)"
integrar_teste p1 s
conferir "aprovada: integra ($rc)" test "$rc" -eq 0
conferir "aprovada: a base está no commit aprovado, sem commit de merge" test "$(git -C "$proj" rev-parse main)" = "$c_p1"
conferir "aprovada: arquivo na cópia principal, que fica limpa" \
  bash -c 'test -e "$1/p1.txt" && [ -z "$(git -C "$1" status --porcelain)" ]' _ "$proj"
conferir "aprovada: a suíte rodou" test -s "$tmp/verificar-chamado"
conferir "aprovada: a marca fica" test -f "$revisoes/validacao-p1.aprovado"
mantida "aprovada" p1
integrar_teste p1 s
conferir "já integrada: nada a integrar ($rc)" bash -c '[ "$1" -eq 0 ] && grep -q "nada a integrar" "$2"' _ "$rc" "$tmp/saida"

# Entrega com link de pasta versionado: a cópia da suíte leva o link e fica em
# integracoes/, fora de revisoes/. Enquanto a suíte roda, outro lançamento pelo
# jangada-isolar no mesmo estado não é recusado por causa da cópia.
integracoes="$XDG_STATE_HOME/jangada/integracoes"
preparar lk
mkdir "$wts/proj/lk/pasta-real"
echo real >"$wts/proj/lk/pasta-real/dentro.txt"
ln -s pasta-real "$wts/proj/lk/atalho"
git -C "$wts/proj/lk" add pasta-real atalho
git -C "$wts/proj/lk" commit --quiet -m "link de pasta"
marca lk "$revisoes"
c_lk="$(git -C "$proj" rev-parse agente/lk)"
if command -v bwrap >/dev/null 2>&1 && bwrap --ro-bind / / --dev /dev --proc /proc true 2>/dev/null; then
  mkdir -p "$tmp/concorrente"
  # shellcheck disable=SC2016  # avaliado pela suíte falsa, na cópia
  FALSO_COMANDO='{ test -L atalho && cat atalho/dentro.txt; } >"$FALSO_DIR/lk-visto" 2>&1
    (cd "$FALSO_DIR/concorrente" && "$JANGADA_CORE_PATH/bin/jangada-isolar" -- true) </dev/null >"$FALSO_DIR/lk-concorrente.log" 2>&1
    echo "$?" >"$FALSO_DIR/lk-concorrente"' integrar_teste lk s
  # O lançamento concorrente, dentro da suíte falsa, é o comando conferido.
  [[ ! -f $tmp/lk-concorrente ]] ||
    registrar_comando "$tmp" "$(cat "$tmp/lk-concorrente")" "$tmp/lk-concorrente.log" /dev/null
  conferir "link de pasta: lançamento concorrente não é recusado durante a suíte" \
    bash -c '[ "$(cat "$1/lk-concorrente" 2>/dev/null)" = 0 ] && ! grep -q AUTORIZACAO_RECUSADA "$1/lk-concorrente.log"' _ "$tmp"
else
  # shellcheck disable=SC2016
  FALSO_COMANDO='{ test -L atalho && cat atalho/dentro.txt; } >"$FALSO_DIR/lk-visto" 2>&1' integrar_teste lk s
  if [[ "${JANGADA_TESTES_EXIGIR_ISOLAMENTO:-}" == 1 ]]; then
    falha "link de pasta: bwrap ausente ou sem namespaces e o isolamento real é exigido"
  else
    echo "pulado link de pasta, lançamento concorrente: bwrap ausente ou namespaces indisponíveis"
  fi
fi
conferir "link de pasta: integra ($rc)" \
  bash -c '[ "$1" -eq 0 ] && [ "$(git -C "$2" rev-parse main)" = "$3" ]' _ "$rc" "$proj" "$c_lk"
conferir "link de pasta: a suíte roda na cópia em integracoes/, com o link" \
  bash -c 'grep -q "^$1/" "$2/verificar-chamado" && [ "$(cat "$2/lk-visto")" = real ]' _ "$integracoes" "$tmp"
conferir "link de pasta: a pasta das cópias é só do dono" [ "$(stat -c %a "$integracoes" 2>/dev/null)" = 700 ]
conferir "link de pasta: a cópia é removida" bash -c '[[ -z "$(ls -A "$1" 2>/dev/null)" ]]' _ "$integracoes"
mantida "link de pasta" lk

# A base andou depois da revisão: o rebase acontece na worktree da tarefa, a
# cópia principal não muda e o commit novo precisa de parecer próprio.
preparar r2
marca r2 "$revisoes"
c_r2="$(git -C "$proj" rev-parse agente/r2)"
echo b >"$proj/base.txt"; git -C "$proj" add base.txt; git -C "$proj" commit --quiet -m "base anda"
antes="$(foto)"
integrar_teste r2 s
recusa "base andou" r2 'o parecer tem de ser do commit novo' "$antes"
conferir "base andou: a suíte não roda" test ! -e "$tmp/verificar-chamado"
n_r2="$(git -C "$proj" rev-parse agente/r2)"
conferir "base andou: o ramo foi refeito sobre a base na worktree" \
  bash -c '[ "$3" != "$4" ] && git -C "$1" merge-base --is-ancestor main agente/r2 \
           && [ "$(git -C "$2" rev-parse HEAD)" = "$4" ] && [ -z "$(git -C "$2" status --porcelain)" ]' \
  _ "$proj" "$wts/proj/r2" "$c_r2" "$n_r2"
integrar_teste r2 s
recusa "base andou: o parecer antigo não vale para o commit novo" r2 'falta parecer APROVADO' "$antes"
marca r2 "$revisoes"
integrar_teste r2 s
conferir "base andou: integra com o parecer do commit final ($rc)" \
  bash -c '[ "$1" -eq 0 ] && [ "$(git -C "$2" rev-parse main)" = "$3" ]' _ "$rc" "$proj" "$n_r2"
mantida "base andou" r2

# Rebase com conflito: para na worktree da tarefa e a cópia principal não muda.
preparar r3
echo ramo >"$wts/proj/r3/a"; git -C "$wts/proj/r3" commit --quiet -am "ramo mexe em a"
echo base >"$proj/a"; git -C "$proj" commit --quiet -am "base mexe em a"
antes="$(foto)"
integrar_teste r3 s
recusa "rebase com conflito" r3 'o rebase de agente/r3 parou' "$antes"
git -C "$wts/proj/r3" rebase --abort

# Enquanto a suíte roda: a base anda, a cópia principal recebe trabalho do
# usuário ou o ramo avança. Tudo é conferido de novo sob a trava.
preparar d1
marca d1 "$revisoes"
FALSO_COMANDO="echo c >'$proj/durante.txt'; git -C '$proj' add durante.txt; git -C '$proj' commit --quiet -m durante" \
  integrar_teste d1 s
antes="$(foto)"
recusa "base andou durante a suíte" d1 'a base main mudou depois da conferência' "$antes"
conferir "base andou durante a suíte: o commit concorrente fica e o ramo não entra" \
  bash -c 'test -e "$1/durante.txt" && test ! -e "$1/d1.txt"' _ "$proj"

preparar d2
marca d2 "$revisoes"
ponta="$(git -C "$proj" rev-parse HEAD)"
FALSO_COMANDO="echo usuario >'$proj/a'; echo indice >'$proj/indice'; git -C '$proj' add indice; echo novo >'$proj/nao-rastreado'" \
  integrar_teste d2 s
antes="$(foto)"
recusa "trabalho concorrente durante a suíte" d2 'recebeu alterações depois da conferência' "$antes"
conferir "trabalho concorrente: HEAD, arquivo, índice e arquivo novo preservados" \
  bash -c '[ "$(git -C "$1" rev-parse HEAD)" = "$2" ] && grep -qx usuario "$1/a" \
           && [ "$(git -C "$1" diff --cached --name-only)" = indice ] && grep -qx novo "$1/nao-rastreado" \
           && test ! -e "$1/d2.txt"' _ "$proj" "$ponta"
git -C "$proj" rm --quiet --cached indice
rm -f "$proj/indice" "$proj/nao-rastreado"
git -C "$proj" show HEAD:a >"$proj/a"

antes="$(foto)"
FALSO_COMANDO="echo depois >'$wts/proj/d2/depois.txt'; git -C '$wts/proj/d2' add depois.txt; git -C '$wts/proj/d2' commit --quiet -m depois" \
  integrar_teste d2 s
recusa "ramo avançou durante a suíte" d2 'mudou depois da conferência' "$antes"

# Outra integração segura a trava do repositório.
marca d2 "$revisoes"
trava="$revisoes/travas/$(realpath "$proj/.git" | sha256sum | cut -c1-16)"
mkdir -p "$trava"
flock "$trava" sleep 8 &
vitima=$!
sleep 1
integrar_teste d2 s
kill "$vitima" 2>/dev/null; wait "$vitima" 2>/dev/null; vitima=""
recusa "trava ocupada" d2 'outra integração segura a trava' "$antes"

# Confirmação gráfica: vale só para os dois commits exibidos e não lê a
# entrada padrão.
b_gui="$(git -C "$proj" rev-parse main)"
c_gui="$(git -C "$proj" rev-parse agente/d2)"
integrar_teste d2 '' --confirmacao "$b_gui" "$b_gui"
recusa "GUI: candidato diferente" d2 'mudaram desde a confirmação gráfica' "$antes"
integrar_teste d2 '' --confirmacao "$c_gui" "$c_gui"
recusa "GUI: base diferente" d2 'mudaram desde a confirmação gráfica' "$antes"
rm -f "$revisoes/validacao-d2.aprovado"
integrar_teste d2 '' --confirmacao "$b_gui" "$c_gui"
recusa "GUI: sem parecer" d2 'falta parecer APROVADO' "$antes"
marca d2 "$revisoes"
# O parecer é retirado depois da conferência, antes da reconferência sob trava.
FALSO_COMANDO="rm -f '$revisoes/validacao-d2.aprovado'" integrar_teste d2 '' --confirmacao "$b_gui" "$c_gui"
recusa "GUI: parecer retirado antes da trava" d2 'falta parecer APROVADO' "$antes"
marca d2 "$revisoes"
integrar_teste d2 '' --confirmacao "$b_gui" "$c_gui"
conferir "GUI: confirmação exata integra sem entrada padrão ($rc)" \
  bash -c '[ "$1" -eq 0 ] && [ "$(git -C "$2" rev-parse main)" = "$3" ]' _ "$rc" "$proj" "$c_gui"
mantida "GUI" d2

# Duas integrações ao mesmo tempo, aprovadas contra a mesma base: entra uma,
# e a outra é recusada porque a base andou.
preparar s1; preparar s2
marca s1 "$revisoes"; marca s2 "$revisoes"
# As duas saídas e o primeiro código diferente de 0 formam o comando conferido.
simultaneas() {
  local n rc=0
  for n in s1 s2; do
    ( "$repo_jangada/bin/jangada-agente-fim" --integrar "$n" <<<s >"$tmp/saida-$n" 2>&1
      echo $? >"$tmp/rc-$n" ) &
  done
  wait
  for n in s1 s2; do
    cat "$tmp/saida-$n"
    ((rc)) || rc="$(cat "$tmp/rc-$n")"
  done
  return "$rc"
}
executar "$tmp" simultaneas >/dev/null
conferir "simultâneas: só uma integra ($(cat "$tmp/rc-s1"), $(cat "$tmp/rc-s2"))" \
  bash -c 'a="$(cat "$1/rc-s1")"; b="$(cat "$1/rc-s2")"; { [ "$a" = 0 ] && [ "$b" != 0 ]; } || { [ "$a" != 0 ] && [ "$b" = 0 ]; }' _ "$tmp"
for n in s1 s2; do
  conferir "simultâneas: $n entrou se e só se saiu com 0" \
    bash -c 'if [ "$(cat "$1/rc-$3")" = 0 ]; then test -e "$2/$3.txt"; else test ! -e "$2/$3.txt"; fi' _ "$tmp" "$proj" "$n"
done
conferir "simultâneas: repositório íntegro e cópia principal limpa" \
  bash -c 'git -C "$1" fsck --no-dangling >/dev/null 2>&1 && [ -z "$(git -C "$1" status --porcelain)" ]' _ "$proj"

# Submódulo com alteração na cópia principal.
git init --quiet "$tmp/sub"
echo s >"$tmp/sub/s"; "$git_real" -C "$tmp/sub" add s; "$git_real" -C "$tmp/sub" commit --quiet -m sub
"$git_real" -C "$proj" -c protocol.file.allow=always submodule --quiet add "$tmp/sub" sub >/dev/null 2>&1
"$git_real" -C "$proj" commit --quiet -m "submódulo"
preparar m1
marca m1 "$revisoes"
echo usuario >"$proj/sub/s"
antes="$(foto)"
integrar_teste m1 s
recusa "submódulo alterado" m1 'tem alterações sem commit' "$antes"
# A configuração do repositório não esconde o submódulo.
git -C "$proj" config submodule.sub.ignore all
git -C "$proj" config diff.ignoreSubmodules all
integrar_teste m1 s
recusa "submódulo alterado e ignorado na configuração" m1 'tem alterações sem commit' "$antes"
conferir "submódulo ignorado na configuração: a suíte não roda" test ! -e "$tmp/verificar-chamado"
git -C "$proj" config --unset submodule.sub.ignore
git -C "$proj" config --unset diff.ignoreSubmodules
conferir "submódulo alterado: a alteração fica" grep -qx usuario "$proj/sub/s"
echo s >"$proj/sub/s"
antes="$(foto)"

# Objeto trocado em .git/objects depois de o espelho receber o original: o
# git leria o conteúdo forjado com o nome do original.
forjar='import sys, zlib
d = b"forjado\n"
sys.stdout.buffer.write(zlib.compress(b"blob %d\0" % len(d) + d))'
preparar o1
marca o1 "$revisoes"
FALSO_VERIFICAR=1 integrar_teste o1 s
blob="$(git -C "$proj" rev-parse agente/o1:o1.txt)"
objeto="$proj/.git/objects/${blob:0:2}/${blob:2}"
chmod u+w "$objeto"
cp "$objeto" "$tmp/objeto-o1"
python3 -c "$forjar" >"$objeto"
antes="$(foto)"
integrar_teste o1 s
recusa "objeto forjado" o1 'não conferem com o espelho' "$antes"
conferir "objeto forjado: a suíte não roda" test ! -e "$tmp/verificar-chamado"
cp "$tmp/objeto-o1" "$objeto"

# Objeto trocado entre a conferência com o espelho e o avanço: o avanço lê
# os objetos do espelho, e a cópia principal recebe o conteúdo aprovado.
cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
if [[ " \$* " == *" merge --ff-only "* ]]; then
  python3 -c '$forjar' >"$objeto"
fi
exec "$git_real" "\$@"
EOF
integrar_teste o1 s
conferir "objeto forjado durante o avanço: integra ($rc)" \
  bash -c '[ "$1" -eq 0 ] && [ "$(git -C "$2" rev-parse main)" = "$3" ]' _ "$rc" "$proj" "$(git -C "$proj" rev-parse agente/o1)"
conferir "objeto forjado durante o avanço: a cópia principal recebe o conteúdo aprovado" grep -qx o1 "$proj/o1.txt"
conferir "objeto forjado durante o avanço: o forjado não chega à cópia principal" \
  bash -c 'python3 -c "import zlib,sys; sys.exit(zlib.decompress(open(sys.argv[1],\"rb\").read()) != b\"blob 8\\0forjado\\n\")" "$1" \
           && ! grep -rqx forjado "$2" --exclude-dir=.git' _ "$objeto" "$proj"
mantida "objeto forjado durante o avanço" o1
cp "$tmp/objeto-o1" "$objeto"

# Git de fora da trava move a base para um ancestral do candidato logo antes
# do merge: o --ff-only aceita, e o reflog só detecta depois do avanço.
preparar w1
echo w2 >"$wts/proj/w1/w2.txt"
git -C "$wts/proj/w1" add w2.txt
git -C "$wts/proj/w1" commit --quiet -m w2
marca w1 "$revisoes"
concorrente="$(git -C "$proj" rev-parse agente/w1~1)"
cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
if [[ " \$* " == *" merge --ff-only "* && ! -e "$tmp/concorreu" ]]; then
  touch "$tmp/concorreu"
  "$git_real" -C "$proj" merge --quiet --ff-only "$concorrente"
fi
exec "$git_real" "\$@"
EOF
integrar_teste w1 s
conferir "base movida antes do merge: sai com erro ($rc)" test "$rc" -ne 0
conferir "base movida antes do merge: avisa" grep -q 'a base mudou depois da última conferência' "$tmp/saida"
conferir "base movida antes do merge: nada é desfeito" grep -q 'Nada foi desfeito' "$tmp/saida"
conferir "base movida antes do merge: o HEAD concorrente fica no histórico e no reflog" \
  bash -c 'git -C "$1" merge-base --is-ancestor "$2" main && [ "$(git -C "$1" rev-parse "main@{1}")" = "$2" ]' _ "$proj" "$concorrente"
mantida "base movida antes do merge" w1

# git status que falha sem saída conta como alteração.
cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
[[ " \$* " != *" status --porcelain --untracked-files=all "* ]] || exit 128
exec "$git_real" "\$@"
EOF
preparar g1
marca g1 "$revisoes"
antes="$(foto)"
integrar_teste g1 s
recusa "git status falha" g1 'o git status falhou' "$antes"
conferir "git status falha: a suíte não roda" test ! -e "$tmp/verificar-chamado"

# Filtro do git ligado por .gitattributes no candidato, definido no config,
# no config.worktree ou por include: recusa antes da suíte, e o comando do
# filtro não roda.
cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
exec "$git_real" "\$@"
EOF
for via in config worktree include; do
  preparar "f$via"
  printf '*.txt filter=mal\n' >"$wts/proj/f$via/.gitattributes"
  git -C "$wts/proj/f$via" add .gitattributes
  git -C "$wts/proj/f$via" commit --quiet -m filtro
  marca "f$via" "$revisoes"
  case "$via" in
    config) alvo="$proj/.git/config" ;;
    worktree)
      git -C "$proj" config extensions.worktreeConfig true
      alvo="$proj/.git/config.worktree"
      ;;
    include)
      alvo="$tmp/filtro.inc"
      git -C "$proj" config include.path "$alvo"
      ;;
  esac
  git config --file "$alvo" filter.mal.smudge "touch '$tmp/filtro-rodou'; cat"
  git config --file "$alvo" filter.mal.process "touch '$tmp/filtro-rodou'"
  antes="$(foto)"
  integrar_teste "f$via" s
  recusa "filtro ($via)" "f$via" 'define filter\.mal\.' "$antes"
  conferir "filtro ($via): a suíte não roda" test ! -e "$tmp/verificar-chamado"
  conferir "filtro ($via): o comando do filtro não roda" test ! -e "$tmp/filtro-rodou"
  git config --file "$alvo" --remove-section filter.mal
  case "$via" in
    worktree) git -C "$proj" config --unset extensions.worktreeConfig; rm -f "$alvo" ;;
    include) git -C "$proj" config --unset include.path ;;
  esac
done

# Escrita concorrente recria, durante o avanço, um caminho que o commit
# remove: como arquivo ou como link pendente. O comando avisa, sai com erro
# e não apaga o que foi recriado.
for tipo in arquivo link; do
  echo removido >"$proj/removido-$tipo"
  git -C "$proj" add "removido-$tipo"
  git -C "$proj" commit --quiet -m "removido-$tipo"
  preparar "x$tipo"
  git -C "$wts/proj/x$tipo" rm --quiet "removido-$tipo"
  git -C "$wts/proj/x$tipo" commit --quiet -m "remove removido-$tipo"
  marca "x$tipo" "$revisoes"
  if [[ "$tipo" == arquivo ]]; then
    recriar="echo concorrente >'$proj/removido-$tipo'"
  else
    recriar="ln -s '$tmp/nao-existe' '$proj/removido-$tipo'"
  fi
  cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
"$git_real" "\$@"; rc=\$?
[[ " \$* " != *" merge --ff-only "* ]] || $recriar
exit \$rc
EOF
  integrar_teste "x$tipo" s
  conferir "removido recriado ($tipo): sai com erro ($rc)" test "$rc" -ne 0
  conferir "removido recriado ($tipo): avisa" grep -q 'não conferem com o espelho' "$tmp/saida"
  conferir "removido recriado ($tipo): nada é desfeito" grep -q 'Nada foi desfeito' "$tmp/saida"
  conferir "removido recriado ($tipo): a escrita concorrente fica" test -L "$proj/removido-$tipo" -o -e "$proj/removido-$tipo"
  mantida "removido recriado ($tipo)" "x$tipo"
  rm -f "$proj/removido-$tipo"
done

# Pasta no lugar de um arquivo removido, como o commit pede, não é divergência.
echo d >"$proj/vira-pasta"
git -C "$proj" add vira-pasta
git -C "$proj" commit --quiet -m vira-pasta
preparar xpasta
git -C "$wts/proj/xpasta" rm --quiet vira-pasta
mkdir "$wts/proj/xpasta/vira-pasta"
echo d >"$wts/proj/xpasta/vira-pasta/dentro"
git -C "$wts/proj/xpasta" add vira-pasta/dentro
git -C "$wts/proj/xpasta" commit --quiet -m "vira-pasta é pasta"
marca xpasta "$revisoes"
cat >"$tmp/bin/git" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$tmp/git-chamadas"
exec "$git_real" "\$@"
EOF
integrar_teste xpasta s
conferir "arquivo que vira pasta: integra ($rc)" \
  bash -c '[ "$1" -eq 0 ] && test -f "$2/vira-pasta/dentro"' _ "$rc" "$proj"

conferir "listas temporárias ficam em revisoes/ e saem no fim" \
  bash -c '! compgen -G "$1/objetos-*" >/dev/null && ! compgen -G "$1/avanco-*" >/dev/null' _ "$revisoes"

# Nenhuma chamada desta seção enviou ao remoto, atualizou a cópia instalada
# ou descartou trabalho.
conferir "remoto intocado" test "$(git -C "$tmp/remoto.git" rev-parse main)" = "$remoto_antes"
conferir "git: sem push, reset, clean, stash, merge --no-ff nem remoção de worktree ou ramo" \
  bash -c '! grep -Eq "(^| )(push|reset|clean|stash|restore)( |$)|--no-ff|worktree remove|branch -[dD]" "$1"' _ "$tmp/git-chamadas"
conferir "backend: integra só por merge --ff-only" \
  bash -c '[ "$(grep -c "merge --ff-only \"" "$1")" -eq 1 ] && ! grep -Eq "reset +(-q +)?--hard|merge --no-ff|git clean|(seguro|git)[^|]* (push|clean|stash)( |$)" "$1"' \
  _ "$repo_jangada/bin/jangada-agente-fim"
conferir "backend: não chama o jangada-update" \
  bash -c '! grep -Eq "bin/jangada-update|^[^#]*exec.*jangada-update" "$1"' _ "$repo_jangada/bin/jangada-agente-fim"
rm -f "$tmp/bin/git"
: >"$tmp/mortas"

echo "== --limpar-concluidos"
rm -f "$estado"/*.json
agora="$(date -Iseconds)"
novo_worktree "$proj" viva
# Outra sessão, viva no tmux, marcada como concluída pelo agente.
printf 'viva\n' >"$tmp/sessoes"
gravar viva "{\"raiz\": \"$proj\", \"worktree\": \"$wts/proj/viva\", \"ramo\": \"agente/viva\", \"base\": \"main\", \"estado\": \"concluido\", \"atualizado\": \"$agora\", \"dir\": \"$wts/proj/viva\"}"
limpar() { executar "$tmp" "$repo_jangada/bin/jangada-agentes" --limpar-concluidos >"$tmp/saida" 2>&1; rc=$?; }
limpar <<<n
conferir "resposta n: termina sem erro ($rc)" test "$rc" -eq 0
conferir "resposta n: lista a sessão" grep -q 'viva.*sessão aberta no tmux' "$tmp/saida"
conferir "resposta n: sessão não encerrada" test ! -s "$tmp/mortas"
conferir "resposta n: worktree mantido" test -d "$wts/proj/viva"
limpar </dev/null
conferir "sem terminal: sessão não encerrada" test ! -s "$tmp/mortas"
conferir "sem terminal: estado mantido" test -f "$estado/viva.json"
limpar <<<s
conferir "resposta s: encerra ($rc)" test "$rc" -eq 0
conferir "resposta s: sessão encerrada" grep -qx '=viva' "$tmp/mortas"
conferir "resposta s: worktree removido" test ! -d "$wts/proj/viva"

if ((falhas)); then
  echo "--- última saída"; cat "$tmp/saida"
  echo "$falhas falha(s)"
  exit 1
fi
echo "tudo certo"
