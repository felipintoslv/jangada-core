#!/usr/bin/env bash
# Testa, em repositórios temporários, o que chega à cópia instalada: o
# jangada-update só aplica commits novos da origem com confirmação e, com
# allowed_signers, só os assinados; depois do avanço roda o jangada-migrar, e
# o jangada-sistema-update (do jangada-shell) só entra quando existe no PATH e
# sem --so-core. Sem rede: a origem é uma pasta local. tmux e o
# jangada-sistema-update são substituídos por scripts falsos.
#
# Uso: testes/update.sh
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
  if "$@"; then ok "$d"
  elif ! pulado_se_recusado "${tmp:-}" "$d"; then falha "$d"; fi
}

tmp="$(mktemp -d)"
erros_dos_pulados "$tmp"
trap 'rm -rf "$tmp"' EXIT

# Nada da configuração do git do usuário (assinatura, ganchos) entra no teste.
export GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
: >"$GIT_CONFIG_GLOBAL"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/home/.config" XDG_STATE_HOME="$tmp/home/.local/state"
mkdir -p "$HOME" "$XDG_CONFIG_HOME/jangada" "$XDG_STATE_HOME"
unset HYPRLAND_INSTANCE_SIGNATURE JANGADA_SESSAO JANGADA_REPO JANGADA_SIMULAR JANGADA_ISOLADO

# tmux falso sem sessões e, à parte, um jangada-sistema-update falso que
# registra a chamada e devolve o código de FALSO_SISTEMA_RC.
falsos="$tmp/falsos"; mkdir -p "$falsos"
sistema="$tmp/sistema-falso"; mkdir -p "$sistema"
registro="$tmp/chamadas"
cat >"$falsos/tmux" <<'EOF'
#!/bin/sh
for a in "$@"; do [ "$a" = list-sessions ] && echo "no server running on /tmp/x" >&2 && exit 1; done
exit 0
EOF
cat >"$sistema/jangada-sistema-update" <<EOF
#!/bin/sh
echo "sistema \$*" >>"$registro"
exit "\${FALSO_SISTEMA_RC:-0}"
EOF
chmod +x "$falsos/tmux" "$sistema/jangada-sistema-update"
export PATH="$falsos:$PATH"

# Origem (a cópia de trabalho) com o bin/ atual e sem migrações; a cópia
# instalada é um clone dela, como na máquina.
origem="$tmp/origem"; instalado="$tmp/instalado"
mkdir -p "$origem/migrations"
cp -r "$repo_jangada/bin" "$origem/"
cp -r "$repo_jangada/agentes" "$repo_jangada/install" "$origem/"
echo "migrações" >"$origem/migrations/README.md"
git -C "$origem" init --quiet -b main
git -C "$origem" add -A
git -C "$origem" commit --quiet -m "feat(base): início"
git clone --quiet "$origem" "$instalado"
export JANGADA_CORE_PATH="$instalado"

marca="$HOME/migracao-nova"
cat >"$origem/migrations/900-teste.sh" <<'EOF'
touch "$HOME/migracao-nova"
EOF
git -C "$origem" add -A
git -C "$origem" commit --quiet -m $'feat(teste): migração \e[2Jnova'
novo="$(git -C "$origem" rev-parse HEAD)"
antes="$(git -C "$instalado" rev-parse HEAD)"

# PATH sem diretório que traga o jangada-sistema-update de verdade (máquina com
# o Shell instalado): "sem o comando no PATH" não herda o comando real.
path_sem_sistema() {
  local d out="" IFS=:
  for d in $PATH; do
    [[ -x "$d/jangada-sistema-update" ]] || out+="${out:+:}$d"
  done
  printf '%s' "$out"
}
atualizar() { (cd "$tmp" && executar "$tmp" env PATH="$(path_sem_sistema)" "$instalado/bin/jangada-update" "$@") >"$tmp/saida" 2>&1; rc=$?; }
head_instalado() { git -C "$instalado" rev-parse HEAD; }

echo "== jangada-update"

atualizar <<<n
conferir "resposta n: termina com erro ($rc)" test "$rc" -ne 0
conferir "resposta n: cópia instalada não avança" test "$(head_instalado)" = "$antes"
conferir "resposta n: migração nova não roda" test ! -e "$marca"
conferir "mostra o commit novo" grep -q 'migração \[2Jnova' "$tmp/saida"
conferir "assunto sem o caractere ESC" bash -c '! grep -q $'"'"'\e'"'"' "$1"' _ "$tmp/saida"
conferir "destaca a mudança em migrations/" grep -q '^   migrations/900-teste.sh' "$tmp/saida"
conferir "avisa do código que roda fora do isolamento" grep -q 'mudam código que roda fora' "$tmp/saida"
conferir "avisa que não aplicou" grep -q 'não aplicadas' "$tmp/saida"

atualizar </dev/null
conferir "sem terminal: termina com erro ($rc)" test "$rc" -ne 0
conferir "sem terminal: cópia instalada não avança" test "$(head_instalado)" = "$antes"
conferir "sem terminal: migração nova não roda" test ! -e "$marca"

atualizar --so-core <<<s
conferir "resposta s: termina sem erro ($rc)" test "$rc" -eq 0
conferir "resposta s: cópia instalada avança" test "$(head_instalado)" = "$novo"
conferir "resposta s: migração nova roda" test -e "$marca"
conferir "resposta s: a marca da migração fica no estado" test -e "$XDG_STATE_HOME/jangada/migracoes/900-teste.sh"
conferir "resposta s: mostra as novidades" grep -q 'jangada agora em' "$tmp/saida"

atualizar --so-core <<<s
conferir "sem novidade: já atualizado" grep -q 'jangada já atualizado' "$tmp/saida"

# Fast-forward: a origem reescrita (não avança em linha reta) é recusada.
git -C "$origem" commit --quiet --amend -m "fix(teste): reescrito"
atualizar --so-core <<<s
conferir "origem reescrita: termina com erro ($rc)" test "$rc" -ne 0
conferir "origem reescrita: cópia instalada não muda" test "$(head_instalado)" = "$novo"
conferir "origem reescrita: explica a recusa" grep -q 'não avança em linha reta' "$tmp/saida"
git -C "$origem" reset --quiet --hard "$novo"

echo "== opções"

atualizar --ajuda
conferir "--ajuda sai com 0" test "$rc" -eq 0
conferir "opção desconhecida é recusada" bash -c '! "$1" --nada >/dev/null 2>&1' _ "$instalado/bin/jangada-update"
(cd "$tmp" && executar "$tmp" env JANGADA_SIMULAR=1 "$instalado/bin/jangada-update") >"$tmp/saida" 2>&1; rc=$?
conferir "simulação é recusada" bash -c '[ "$1" -ne 0 ] && grep -q "não oferece simulação" "$2"' _ "$rc" "$tmp/saida"

echo "== jangada-sistema-update"

echo s1 >"$origem/s1.txt"
git -C "$origem" add s1.txt
git -C "$origem" commit --quiet -m "feat(teste): s1"
: >"$registro"
atualizar --so-core <<<s
conferir "--so-core: não chama o jangada-sistema-update" bash -c 'PATH="$1:$PATH" true; ! test -s "$2"' _ "$sistema" "$registro"

echo s2 >"$origem/s2.txt"
git -C "$origem" add s2.txt
git -C "$origem" commit --quiet -m "feat(teste): s2"
: >"$registro"
(cd "$tmp" && executar "$tmp" env PATH="$sistema:$PATH" "$instalado/bin/jangada-update" --so-core <<<s) >"$tmp/saida" 2>&1; rc=$?
conferir "--so-core com o comando no PATH: não chama ($rc)" bash -c '[ "$1" -eq 0 ] && ! test -s "$2"' _ "$rc" "$registro"

echo s3 >"$origem/s3.txt"
git -C "$origem" add s3.txt
git -C "$origem" commit --quiet -m "feat(teste): s3"
: >"$registro"
(cd "$tmp" && executar "$tmp" env PATH="$sistema:$PATH" "$instalado/bin/jangada-update" <<<s) >"$tmp/saida" 2>&1; rc=$?
conferir "sem --so-core, com o comando: chama sem argumentos ($rc)" bash -c '[ "$1" -eq 0 ] && [ "$(cat "$2")" = "sistema " ]' _ "$rc" "$registro"
conferir "sem --so-core: o código novo vem antes" test "$(head_instalado)" = "$(git -C "$origem" rev-parse HEAD)"

: >"$registro"
(cd "$tmp" && executar "$tmp" env PATH="$sistema:$PATH" FALSO_SISTEMA_RC=7 "$instalado/bin/jangada-update" <<<s) >"$tmp/saida" 2>&1; rc=$?
conferir "repassa o código de saída do sistema ($rc)" test "$rc" -eq 7

atualizar </dev/null
conferir "sem o comando no PATH: termina com 0 ($rc)" test "$rc" -eq 0

# Código recusado: o sistema ainda roda, e o erro do código vale no fim.
echo s4 >"$origem/s4.txt"
git -C "$origem" add s4.txt
git -C "$origem" commit --quiet -m "feat(teste): s4"
: >"$registro"
(cd "$tmp" && executar "$tmp" env PATH="$sistema:$PATH" "$instalado/bin/jangada-update" <<<n) >"$tmp/saida" 2>&1; rc=$?
conferir "código recusado: o sistema roda e o código de saída é de erro ($rc)" \
  bash -c '[ "$1" -ne 0 ] && [ -s "$2" ]' _ "$rc" "$registro"
atualizar --so-core <<<s

echo "== invólucros em ~/.local/bin"

# Comando novo na origem ganha invólucro; arquivo alheio com o mesmo nome de
# outro comando novo fica como está, com aviso e erro no fim.
mkdir -p "$HOME/.local/bin"
echo "meu script" >"$HOME/.local/bin/jangada-alheio"
for c in jangada-novo jangada-alheio; do
  printf '#!/bin/sh\necho %s\n' "$c" >"$origem/bin/$c"
  chmod +x "$origem/bin/$c"
done
git -C "$origem" add bin
git -C "$origem" commit --quiet -m "feat(teste): comandos novos"
atualizar --so-core <<<s
conferir "comando novo: o invólucro é gravado" \
  bash -c 'grep -qxF "# gerado pelo jangada-core; não edite" "$1" && [ "$("$1")" = jangada-novo ]' \
  _ "$HOME/.local/bin/jangada-novo"
conferir "arquivo alheio fica intocado" test "$(cat "$HOME/.local/bin/jangada-alheio")" = "meu script"
conferir "arquivo alheio: aviso na saída" grep -q 'jangada-alheio já existe e não é invólucro' "$tmp/saida"
conferir "arquivo alheio: termina com erro ($rc)" test "$rc" -ne 0
conferir "não lista os invólucros já gravados" bash -c '! grep -q "invólucro já gravado" "$1"' _ "$tmp/saida"
rm "$HOME/.local/bin/jangada-alheio"
atualizar --so-core <<<s
conferir "sem o conflito: o invólucro que faltava é gravado ($rc)" \
  bash -c '[ "$1" -eq 0 ] && [ "$("$2")" = jangada-alheio ]' _ "$rc" "$HOME/.local/bin/jangada-alheio"

echo "== migrações"

migracoes="$tmp/migracoes-vazias"; mkdir -p "$migracoes/bin" "$migracoes/migrations"
cp "$repo_jangada"/bin/jangada-config "$repo_jangada"/bin/jangada-migrar "$migracoes/bin/"
cp -r "$repo_jangada/agentes" "$migracoes/"
(cd "$tmp" && JANGADA_CORE_PATH="$migracoes" "$migracoes/bin/jangada-migrar") >"$tmp/saida" 2>&1; rc=$?
conferir "pasta sem scripts: sai com 0 ($rc)" test "$rc" -eq 0
conferir "pasta sem scripts: nenhuma aplicada" grep -q 'migrações aplicadas: 0' "$tmp/saida"
echo 'touch "$HOME/simulada"' >"$migracoes/migrations/100-a.sh"
(cd "$tmp" && JANGADA_SIMULAR=1 JANGADA_CORE_PATH="$migracoes" "$migracoes/bin/jangada-migrar") >"$tmp/saida" 2>&1; rc=$?
conferir "simulação não grava a marca" test ! -e "$XDG_STATE_HOME/jangada/migracoes/100-a.sh"
(cd "$tmp" && JANGADA_CORE_PATH="$migracoes" "$migracoes/bin/jangada-migrar") >"$tmp/saida" 2>&1
conferir "execução grava a marca" test -e "$XDG_STATE_HOME/jangada/migracoes/100-a.sh"
rm -f "$HOME/simulada"
(cd "$tmp" && JANGADA_CORE_PATH="$migracoes" "$migracoes/bin/jangada-migrar") >"$tmp/saida" 2>&1
conferir "com a marca, não reaplica" test ! -e "$HOME/simulada"
echo 'exit 3' >"$migracoes/migrations/200-b.sh"
echo 'touch "$HOME/depois"' >"$migracoes/migrations/300-c.sh"
(cd "$tmp" && JANGADA_CORE_PATH="$migracoes" "$migracoes/bin/jangada-migrar") >"$tmp/saida" 2>&1; rc=$?
conferir "migração que falha para a sequência ($rc)" bash -c '[ "$1" -ne 0 ] && [ ! -e "$2" ]' _ "$rc" "$HOME/depois"

echo "== assinaturas"

mkdir -p "$HOME/.ssh"
ssh-keygen -q -t ed25519 -N '' -C t -f "$HOME/.ssh/id_ed25519"
ssh-keygen -q -t ed25519 -N '' -C outra -f "$tmp/outra"
printf 't@t namespaces="git" %s\n' "$(cat "$HOME/.ssh/id_ed25519.pub")" >"$XDG_CONFIG_HOME/jangada/allowed_signers"
assinatura() { git -C "$origem" -c gpg.ssh.allowedSignersFile="$XDG_CONFIG_HOME/jangada/allowed_signers" log -1 --format=%G? "$1"; }
commitar() { # arquivo, chave (vazio = sem assinar)
  echo "$1" >"$origem/$1.txt"
  git -C "$origem" add "$1.txt"
  if [[ -n "${2:-}" ]]; then
    git -C "$origem" -c gpg.format=ssh -c user.signingkey="$2" commit --quiet -S -m "feat(teste): $1"
  else
    git -C "$origem" commit --quiet -m "feat(teste): $1"
  fi
}

commitar c1
antes_ass="$(head_instalado)"
atualizar --so-core <<<s
conferir "sem assinatura: a cópia instalada não avança" test "$(head_instalado)" = "$antes_ass"
conferir "sem assinatura: diz o commit e o jangada-assinar" \
  bash -c 'grep -q "sem assinatura válida" "$1" && grep -q "feat(teste): c1" "$1" && grep -q jangada-assinar "$1"' _ "$tmp/saida"
conferir "sem assinatura: termina com erro ($rc)" test "$rc" -ne 0

git -C "$origem" reset --quiet --hard HEAD^
commitar c2 "$HOME/.ssh/id_ed25519"
conferir "commit assinado pela chave do arquivo é válido" test "$(assinatura HEAD)" = G
atualizar --so-core <<<s
conferir "assinado: a cópia instalada avança ($rc)" bash -c '[ "$1" -eq 0 ] && [ "$2" = "$3" ]' _ "$rc" "$(head_instalado)" "$(git -C "$origem" rev-parse HEAD)"

# Assinado por uma chave fora do allowed_signers vale como sem assinatura.
commitar c3 "$tmp/outra"
antes_ass="$(head_instalado)"
atualizar --so-core <<<s
conferir "outra chave: a cópia instalada não avança" test "$(head_instalado)" = "$antes_ass"

# Um commit sem assinatura no meio da série basta para recusar tudo.
git -C "$origem" reset --quiet --hard HEAD^
commitar c4 ""
commitar c5 "$HOME/.ssh/id_ed25519"
atualizar --so-core <<<s
conferir "um sem assinatura no meio: nada é aplicado" test "$(head_instalado)" = "$antes_ass"

# O gpg.ssh.program do repositório não roda na conferência.
alerta="$tmp/executou-codigo-do-agente"
printf '#!/bin/sh\ntouch "%s"\nexit 1\n' "$alerta" >"$tmp/programa.sh"
chmod +x "$tmp/programa.sh"
git -C "$instalado" config gpg.ssh.program "$tmp/programa.sh"
git -C "$origem" reset --quiet --hard "$antes_ass"
commitar c6 "$HOME/.ssh/id_ed25519"
atualizar --so-core <<<s
conferir "gpg.ssh.program do repositório: aplica" test "$(head_instalado)" = "$(git -C "$origem" rev-parse HEAD)"
conferir "gpg.ssh.program do repositório: não roda" test ! -e "$alerta"
git -C "$instalado" config --unset gpg.ssh.program

# fsmonitor e ganchos da configuração da cópia instalada não rodam.
printf '#!/bin/sh\ntouch "%s"\n' "$alerta" >"$tmp/fsmonitor.sh"
mkdir -p "$tmp/ganchos"
for h in pre-merge-commit post-merge post-checkout reference-transaction; do cp "$tmp/fsmonitor.sh" "$tmp/ganchos/$h"; done
chmod +x "$tmp/fsmonitor.sh" "$tmp/ganchos"/*
git -C "$instalado" config core.fsmonitor "$tmp/fsmonitor.sh"
git -C "$instalado" config core.hooksPath "$tmp/ganchos"
commitar c7 "$HOME/.ssh/id_ed25519"
atualizar --so-core <<<s
conferir "fsmonitor e ganchos da cópia instalada: aplica" test "$(head_instalado)" = "$(git -C "$origem" rev-parse HEAD)"
conferir "fsmonitor e ganchos da cópia instalada: não rodam" test ! -e "$alerta"
git -C "$instalado" config --unset core.fsmonitor
git -C "$instalado" config --unset core.hooksPath
rm -f "$XDG_CONFIG_HOME/jangada/allowed_signers"

echo "== canal"

git -C "$origem" switch --quiet -c estavel
commitar e1 ""
git -C "$origem" switch --quiet main
echo 'JANGADA_CANAL=estavel' >"$XDG_CONFIG_HOME/jangada/jangada.conf"
atualizar --so-core <<<s
conferir "canal estavel: a cópia instalada muda de ramo ($rc)" \
  bash -c '[ "$1" = estavel ] && [ "$(git -C "$2" rev-parse HEAD)" = "$(git -C "$3" rev-parse estavel)" ]' \
  _ "$(git -C "$instalado" rev-parse --abbrev-ref HEAD)" "$instalado" "$origem"
echo 'JANGADA_CANAL=inexistente' >"$XDG_CONFIG_HOME/jangada/jangada.conf"
atualizar --so-core <<<s
conferir "canal que não existe: avisa e segue no ramo atual" \
  bash -c 'grep -q "não existe na origem" "$1"' _ "$tmp/saida"
rm -f "$XDG_CONFIG_HOME/jangada/jangada.conf"

if ((falhas)); then
  echo "--- última saída"; cat "$tmp/saida"
  echo "$falhas falha(s)"
  exit 1
fi
echo "tudo certo"
