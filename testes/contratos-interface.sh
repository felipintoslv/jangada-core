#!/usr/bin/env bash
# Testa o contrato K10 (docs/modularizacao-3.0/03-contratos.md): o Core abre
# terminal e Central e foca janela só pelas funções de bin/jangada-config.
# Com hyprctl, setsid, tmux, jangada-terminal e jangada-tarefas falsos no PATH,
# confere os argumentos de cada chamada, o exec onde há exec e o terminal
# solto em focar. Sem sessão gráfica, confere aviso e saída 0.
#
# O tmux é falso (a sessão S existe quando há o arquivo $tmp/sessoes/=S), e
# HOME, XDG_STATE_HOME e XDG_CONFIG_HOME ficam na pasta temporária: o
# resultado não depende das sessões abertas na máquina nem do isolamento.
#
# Uso: testes/contratos-interface.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
jangada="$tmp/jangada"
log="$tmp/log"
mkdir -p "$tmp/bin" "$tmp/setsid" "$tmp/sessoes" "$tmp/casa" "$tmp/state/jangada/agentes" "$tmp/config/jangada" "$jangada/bin"
for d in nucleo orquestracao delegacao provedores validacao agentes; do
  ln -s "$repo_jangada/$d" "$jangada/$d"
done

# Cada falso grava uma linha "NOME PID [ARG]..." no registro. O jangada-terminal
# espera FALSO_ESPERA segundos depois de gravar, para o teste ver se ele ficou
# solto do processo que o abriu.
for f in jangada-terminal jangada-tarefas; do
  cat >"$tmp/bin/$f" <<EOF
#!/usr/bin/env bash
{ printf '%s %s' $f "\$\$"; ((\$#)) && printf ' [%s]' "\$@"; echo; } >>"\$FALSO_LOG"
sleep "\${FALSO_ESPERA:-0}"
EOF
done
cat >"$tmp/bin/hyprctl" <<'EOF'
#!/usr/bin/env bash
{ printf 'hyprctl'; printf ' [%s]' "$@"; echo; } >>"$FALSO_LOG"
case "$1" in
  clients) printf '%s\n' "${FALSO_CLIENTES:-[]}" ;;
  activewindow) printf '{"title": "%s"}\n' "${FALSO_ATIVA:-}" ;;
  dispatch) exit "${FALSO_FOCO_RC:-0}" ;;
esac
EOF
cat >"$tmp/setsid/setsid" <<'EOF'
#!/usr/bin/env bash
{ printf 'setsid'; printf ' [%s]' "$@"; echo; } >>"$FALSO_LOG"
[[ "${1:-}" == -f ]] && shift
exec "$@"
EOF
cat >"$tmp/bin/tmux" <<EOF
#!/usr/bin/env bash
case " \$* " in
  *" has-session "*) [[ -e "$tmp/sessoes/\${*: -1}" ]] ;;
  *" list-sessions "*) ls "$tmp/sessoes" | sed 's/^=//' ;;
esac
EOF
# Roda o comando no lugar de um bash que grava o próprio PID: com exec, o
# falso tem o mesmo PID.
cat >"$tmp/com-pid" <<EOF
#!/usr/bin/env bash
echo \$\$ >"$tmp/pid"
exec "\$@"
EOF
chmod +x "$tmp/bin/"* "$tmp/setsid/setsid" "$tmp/com-pid"

# PATH sem setsid, para o caminho em segundo plano de focar. O setsid falso
# fica numa pasta à parte.
mkdir -p "$tmp/sem-setsid"
for c in "$(dirname "$(command -v setsid || command -v bash)")"/*; do
  [[ "${c##*/}" == setsid ]] || ln -s "$c" "$tmp/sem-setsid/"
done

base() {
  env -u TMUX -u DISPLAY -u JANGADA_SESSAO -u JANGADA_ISOLADO -u JANGADA_HOOK_DESLIGADO \
    -u FALSO_CLIENTES -u FALSO_ATIVA -u FALSO_FOCO_RC -u FALSO_ESPERA \
    PATH="$tmp/bin:$tmp/setsid:$PATH" HOME="$tmp/casa" XDG_STATE_HOME="$tmp/state" XDG_CONFIG_HOME="$tmp/config" \
    XDG_RUNTIME_DIR="$tmp/runtime" JANGADA_CORE_PATH="$jangada" FALSO_LOG="$log" "$@"
}
grafico() { : >"$log"; base WAYLAND_DISPLAY=wayland-teste HYPRLAND_INSTANCE_SIGNATURE=teste "$@"; }
sem_grafico() { : >"$log"; base env -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE "$@"; }
config() { printf 'source "%s/bin/jangada-config"; %s' "$repo_jangada" "$1"; }
registro() { [ "$(cat "$log")" = "$1" ]; }
linhas() { [ "$(sed -n "$1p" "$log")" = "$2" ]; }
# A linha N do registro é do jangada-terminal, com o attach da sessão s1.
terminal_na_linha() { [[ "$(sed -n "$1p" "$log")" == "jangada-terminal "*" [--classe] [org.jangada.agente] [-e] $tmux_args" ]]; }
nada_fora() { ! grep -qv "^$1" "$log"; }
pid() { cat "$tmp/pid"; }
tmux_args="[tmux] [-L] [jangada] [-f] [$jangada/agentes/tmux/agentes.conf] [attach] [-t] [=s1]"
clientes='[{"title": "outra", "address": "0x1"}, {"title": "s1: claude", "address": "0x2"}, {"title": "s2", "address": "0x3"}]'

echo "== jangada-agente"
grafico "$tmp/com-pid" "$repo_jangada/bin/jangada-agente" --janela
conferir "--janela sem tarefa: exec da Central com --nova" registro "jangada-tarefas $(pid) [--nova]"
grafico "$tmp/com-pid" "$repo_jangada/bin/jangada-agente" --janela --nome x --direto
conferir "--janela com tarefa: exec do terminal com o próprio comando" \
  registro "jangada-terminal $(pid) [--classe] [org.jangada.agente] [-e] [$repo_jangada/bin/jangada-agente] [--nome] [x] [--direto]"
mkdir -p "$tmp/proj"
touch "$tmp/sessoes/=proj"
# O anexo exige a identidade da sessão, mesmo neste ensaio de interface.
mkdir -p "$tmp/state/jangada/revisoes"
jq -n --arg raiz "$tmp/proj" \
  '{sessao:"proj",agente:"true",raiz:$raiz,delegar:"local",revisor:"codex"}' \
  >"$tmp/state/jangada/revisoes/proj.json"
grafico TMUX=teste "$tmp/com-pid" "$repo_jangada/bin/jangada-agente" --projeto "$tmp/proj" --agente true </dev/null
conferir "sessão que já existe, dentro de outro tmux: exec do terminal com o attach" \
  registro "jangada-terminal $(pid) [--classe] [org.jangada.agente] [-e] ${tmux_args/=s1/=proj}"
rm "$tmp/sessoes/=proj"

echo "== jangada-agentes"
grafico "$tmp/com-pid" "$repo_jangada/bin/jangada-agentes" --janela
conferir "--janela: exec da Central sem argumentos" registro "jangada-tarefas $(pid)"
touch "$tmp/sessoes/=s1" "$tmp/sessoes/=s2"
grafico FALSO_CLIENTES="$clientes" "$repo_jangada/bin/jangada-agentes" --focar s1
conferir "--focar com janela: foca pelo endereço do título que começa pela sessão" \
  registro "hyprctl [clients] [-j]
hyprctl [dispatch] [hl.dsp.focus({ window = \"address:0x2\" })]"
grafico "$repo_jangada/bin/jangada-agentes" --focar s1
conferir "--focar sem janela: terminal solto por setsid -f" \
  linhas 1,2 "hyprctl [clients] [-j]
setsid [-f] [jangada-terminal] [--classe] [org.jangada.agente] [-e] $tmux_args"
conferir "--focar sem janela: o terminal recebe o attach da sessão" terminal_na_linha 3
inicio=$SECONDS
grafico PATH="$tmp/bin:$tmp/sem-setsid" FALSO_ESPERA=5 timeout 4 "$repo_jangada/bin/jangada-agentes" --focar s1
conferir "--focar sem setsid: sai com 0" [ "$?" = 0 ]
conferir "--focar sem setsid: não espera o terminal" [ $((SECONDS - inicio)) -lt 4 ]
for ((i = 0; i < 30; i++)); do grep -q '^jangada-terminal' "$log" && break; sleep 0.1; done
conferir "--focar sem setsid: terminal em segundo plano com o attach da sessão" terminal_na_linha 2
grafico FALSO_CLIENTES="$clientes" FALSO_FOCO_RC=1 "$repo_jangada/bin/jangada-agentes" --focar s1
conferir "--focar com foco recusado: sai com erro" [ "$?" != 0 ]
conferir "--focar com foco recusado: não abre terminal" nada_fora hyprctl
grafico "$repo_jangada/bin/jangada-agentes" --focar s3
conferir "--focar sem janela e sem sessão: sai com 0" [ "$?" = 0 ]
conferir "--focar sem janela e sem sessão: não abre terminal" registro "hyprctl [clients] [-j]"
printf 's2\ns1\n' >"$tmp/state/jangada/agentes/foco.historico"
grafico FALSO_CLIENTES="$clientes" FALSO_ATIVA=s1 "$repo_jangada/bin/jangada-agentes" --anterior
conferir "--anterior: lê a janela ativa e foca a sessão anterior" \
  registro "hyprctl [activewindow] [-j]
hyprctl [clients] [-j]
hyprctl [dispatch] [hl.dsp.focus({ window = \"address:0x3\" })]"
for s in s1 s2; do
  jq -n --arg s "$s" --arg a "2026-10-10T10:0${s#s}:00-03:00" \
    '{sessao: $s, dir: "/x/proj", raiz: "/x/proj", estado: "aguardando", atualizado: $a}' \
    >"$tmp/state/jangada/agentes/$s.json"
done
grafico FALSO_CLIENTES="$clientes" FALSO_ATIVA=s1 "$repo_jangada/bin/jangada-agentes" --proximo
conferir "--proximo: lê a janela ativa e foca a sessão seguinte da fila" \
  registro "hyprctl [activewindow] [-j]
hyprctl [clients] [-j]
hyprctl [dispatch] [hl.dsp.focus({ window = \"address:0x3\" })]"
rm "$tmp/state/jangada/agentes/"s[12].json

echo "== funções do jangada-config"
r="$(grafico FALSO_ATIVA="título" bash -c "$(config jangada_janela_ativa)")"
conferir "jangada_janela_ativa imprime o título" [ "$r" = "título" ]
r="$(grafico env -u HYPRLAND_INSTANCE_SIGNATURE bash -c "$(config jangada_janela_ativa)")"
conferir "jangada_janela_ativa fora do Hyprland não imprime nada" [ -z "$r" ]
conferir "jangada_janela_ativa fora do Hyprland não chama o hyprctl" [ ! -s "$log" ]
grafico env -u HYPRLAND_INSTANCE_SIGNATURE bash -c "$(config 'jangada_focar_janela s1')"
conferir "jangada_focar_janela fora do Hyprland devolve 1" [ "$?" = 1 ]
grafico FALSO_CLIENTES="$clientes" FALSO_FOCO_RC=1 bash -c "$(config 'jangada_focar_janela s1')"
conferir "jangada_focar_janela com foco recusado devolve 2" [ "$?" = 2 ]
grafico "$tmp/com-pid" bash -c "$(config 'jangada_abrir_terminal --exec classe-x cmd "a b"; echo depois')"
conferir "jangada_abrir_terminal --exec substitui o processo" \
  registro "jangada-terminal $(pid) [--classe] [classe-x] [-e] [cmd] [a b]"
grafico bash -c "$(config 'jangada_abrir_terminal --outro classe-x cmd')"
conferir "jangada_abrir_terminal com modo desconhecido devolve 1" [ "$?" = 1 ]
conferir "jangada_abrir_terminal com modo desconhecido não abre terminal" [ ! -s "$log" ]

echo "== sem as aplicações do Shell no PATH"
# PATH só com o que o teste precisa, sem jangada-terminal nem jangada-tarefas.
mkdir -p "$tmp/pouco"
for c in bash env dirname basename sed jq cat sleep; do ln -sf "$(command -v "$c")" "$tmp/pouco/$c"; done
sem_shell() { : >"$log"; env -i HOME="$tmp/casa" PATH="$tmp/pouco" WAYLAND_DISPLAY=wayland-teste FALSO_LOG="$log" "$@"; }
sem_shell "$tmp/pouco/bash" -c "$(config 'jangada_abrir_terminal --solto classe-x cmd')" 2>"$tmp/erro"
conferir "sem jangada-terminal e sem TERMINAL: devolve 1" [ "$?" = 1 ]
conferir "sem jangada-terminal e sem TERMINAL: avisa" grep -q '^aviso: nenhum terminal encontrado' "$tmp/erro"
printf '#!/usr/bin/env bash\necho "terminal-alheio $*" >>"$FALSO_LOG"\n' >"$tmp/pouco/terminal-alheio"; chmod +x "$tmp/pouco/terminal-alheio"
sem_shell TERMINAL=terminal-alheio "$tmp/pouco/bash" -c "$(config 'jangada_abrir_terminal --solto classe-x cmd')"
for ((i = 0; i < 30; i++)); do [[ -s "$log" ]] && break; sleep 0.1; done
conferir "sem jangada-terminal, com TERMINAL: usa o terminal definido" registro "terminal-alheio -e cmd"
sem_shell "$tmp/pouco/bash" -c "$(config 'jangada_abrir_central --nova')" 2>"$tmp/erro"
conferir "sem jangada-tarefas: devolve 1" [ "$?" = 1 ]
conferir "sem jangada-tarefas: avisa" grep -q 'Central de Tarefas não instalada (jangada-shell)' "$tmp/erro"

echo "== sem sessão gráfica"
for f in 'jangada_abrir_terminal --exec classe-x cmd' 'jangada_abrir_terminal --solto classe-x cmd' \
  'jangada_abrir_central --nova' jangada_janela_ativa 'jangada_focar_janela s1'; do
  r="$(sem_grafico bash -c "$(config "$f; echo depois")" 2>"$tmp/erro")"
  rc=$?
  conferir "$f: sai com 0" [ "$rc" = 0 ]
  conferir "$f: avisa" grep -q '^aviso: sem sessão gráfica' "$tmp/erro"
  conferir "$f: não chama terminal, Central nem hyprctl" [ ! -s "$log" ]
  case "$f" in
    *--exec* | *central*) conferir "$f: encerra o script" [ -z "$r" ] ;;
    *) conferir "$f: volta ao chamador" [ "$r" = depois ] ;;
  esac
done
for c in "jangada-agente --janela" "jangada-agente --janela --nome x" "jangada-agentes --janela" "jangada-agentes --focar s1"; do
  read -ra argv <<<"$c"
  sem_grafico "$repo_jangada/bin/${argv[0]}" "${argv[@]:1}" 2>"$tmp/erro"
  conferir "$c: sai com 0" [ "$?" = 0 ]
  conferir "$c: avisa" grep -q '^aviso: sem sessão gráfica' "$tmp/erro"
  conferir "$c: não chama terminal, Central nem hyprctl" [ ! -s "$log" ]
done

echo
if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "tudo certo"
