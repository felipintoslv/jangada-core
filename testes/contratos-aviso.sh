#!/usr/bin/env bash
# Testa o contrato K3 (docs/modularizacao-3.0/03-contratos.md): o Core avisa a
# interface só por jangada_avisar_interface e jangada_notificar, de
# bin/jangada-config. Confere, com waybar, pkill e notify-send falsos, que cada
# ponto do Core ainda manda o sinal 10 e a notificação com os mesmos
# argumentos, e que sem sessão gráfica os comandos saem com 0 e gravam o estado.
#
# Uso: testes/contratos-aviso.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
agentes="$tmp/state/jangada/agentes"
sinais="$tmp/sinais"
avisos="$tmp/avisos"
mkdir -p "$agentes" "$tmp/bin" "$tmp/config/jangada" "$tmp/casa"

# pkill (só o de sinal de tempo real; o resto vai para o verdadeiro) e
# notify-send registram os argumentos, um por chamada, e saem com FALSO_RC. O notify-send devolve FALSO_ACAO, como no clique do botão. O
# setsid roda o comando na hora, para o registro não depender de espera.
cat >"$tmp/bin/pkill" <<EOF
#!/usr/bin/env bash
[[ "\${1:-}" == -RTMIN* ]] || exec "$(command -v pkill)" "\$@"
printf '%s\n' "\$*" >>"\$FALSO_SINAIS"
exit "\${FALSO_RC:-0}"
EOF
cat >"$tmp/bin/notify-send" <<'EOF'
#!/usr/bin/env bash
{ printf '[%s]' "$@"; echo; } >>"$FALSO_AVISOS"
[[ -z "${FALSO_ACAO:-}" ]] || printf '%s\n' "$FALSO_ACAO"
exit "${FALSO_RC:-0}"
EOF
cat >"$tmp/bin/setsid" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == -f ]] && shift
exec "$@"
EOF
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/waybar"
chmod +x "$tmp/bin/"*

rodar() {
  env -u HYPRLAND_INSTANCE_SIGNATURE -u JANGADA_HOOK_DESLIGADO -u JANGADA_SESSAO -u JANGADA_ISOLADO \
    -u FALSO_RC -u FALSO_ACAO PATH="$tmp/bin:$PATH" HOME="$tmp/casa" WAYLAND_DISPLAY=wayland-teste \
    XDG_STATE_HOME="$tmp/state" XDG_CONFIG_HOME="$tmp/config" XDG_RUNTIME_DIR="$tmp/runtime" \
    JANGADA_CORE_PATH="$repo_jangada" FALSO_SINAIS="$sinais" FALSO_AVISOS="$avisos" "$@"
}
# Uso: hook NOME SESSAO EVENTO JSON [VARIÁVEL=VALOR...]
hook() {
  local nome="$1" sessao="$2" evento="$3" json="$4"
  shift 4
  : >"$sinais"; : >"$avisos"
  printf '%s' "$json" | rodar JANGADA_SESSAO="$sessao" "$@" "$repo_jangada/bin/jangada-hook-$nome" "$evento" >/dev/null
}
sessao_nova() { jq -n --arg s "$1" '{sessao: $s, dir: "/x/proj", raiz: "/x/proj", estado: "iniciado"}' >"$agentes/$1.json"; }
estado_de() { jq -r '.estado // ""' "$agentes/$1.json"; }
sinal_10() { [ "$(cat "$sinais")" = "-RTMIN+10 -x waybar" ]; }
aviso() { [ "$(cat "$avisos")" = "$1" ]; }
sinal_sem_aviso() { sinal_10 && [ ! -s "$avisos" ]; }
sinal_e_aviso() { sinal_10 && aviso "$1"; }

echo "== funções do jangada-config"
for e in estado-sessao fila validacao; do
  : >"$sinais"
  rodar bash -c 'source bin/jangada-config && jangada_avisar_interface "$1"' _ "$e"
  conferir "jangada_avisar_interface $e manda o sinal 10" sinal_10
done
: >"$avisos"
rodar bash -c 'source bin/jangada-config && jangada_notificar "Título" "corpo"'
conferir "jangada_notificar sem opção mantém o aplicativo jangada" aviso "[-a][jangada][Título][corpo]"
r="$(rodar FALSO_ACAO=abrir bash -c 'source bin/jangada-config && jangada_notificar -a jangada-agente -u normal -A abrir=Abrir T C')"
conferir "jangada_notificar com -A devolve a ação escolhida" [ "$r" = abrir ]

echo "== jangada_alterar_estado"
sessao_nova alterar
: >"$sinais"
rodar bash -c 'source bin/jangada-config && jangada_alterar_estado "$1" "$1.tmp" ".estado = \"trabalhando\""' _ "$agentes/alterar.json"
conferir "grava o estado" [ "$(estado_de alterar)" = trabalhando ]
conferir "manda o sinal 10" sinal_10

echo "== jangada-hook-claude"
sessao_nova s-claude
hook claude s-claude aguardando '{"message": "permissão", "notification_type": "permission_prompt"}'
conferir "aguardando: grava o estado" [ "$(estado_de s-claude)" = aguardando ]
conferir "aguardando: manda o sinal 10" sinal_10
conferir "aguardando: notificação crítica com o botão abrir" \
  aviso "[-a][jangada-agente][-u][critical][-A][abrir=Abrir][Agente aguardando: s-claude][permissão]"
hook claude s-claude concluido '{}'
conferir "concluido: manda o sinal 10" sinal_10
conferir "concluido: notificação normal com o botão abrir" \
  aviso "[-a][jangada-agente][-u][normal][-A][abrir=Abrir][Agente concluiu: s-claude][turno concluído]"
hook claude s-claude aguardando '{"message": "pergunta"}' JANGADA_ISOLADO=1
conferir "isolado: notificação sem o botão" \
  aviso "[-a][jangada-agente][-u][critical][Agente aguardando: s-claude][pergunta]"
hook claude s-claude trabalhando '{"prompt": "faça"}'
conferir "trabalhando: sinal 10 sem notificação" sinal_sem_aviso

echo "== jangada-hook-agy"
sessao_nova s-agy
hook agy s-agy concluido '{"fullyIdle": true}'
conferir "concluido: grava o estado" [ "$(estado_de s-agy)" = concluido ]
conferir "concluido: manda o sinal 10" sinal_10
conferir "concluido: notificação normal com o botão abrir" \
  aviso "[-a][jangada-agente][-u][normal][-A][abrir=Abrir][Agente concluiu: s-agy][turno concluído]"
hook agy s-agy concluido '{"error": "falhou"}' JANGADA_ISOLADO=1
conferir "isolado: notificação sem o botão" \
  aviso "[-a][jangada-agente][-u][normal][Agente concluiu: s-agy][erro: falhou]"
hook agy s-agy trabalhando '{}'
conferir "trabalhando: sinal 10 sem notificação" sinal_sem_aviso

echo "== jangada-hook-codex"
sessao_nova s-codex
hook codex s-codex aguardando '{"prompt": "confirma?"}'
conferir "aguardando: grava o estado" [ "$(estado_de s-codex)" = aguardando ]
conferir "aguardando: manda o sinal 10" sinal_10
conferir "aguardando: notificação do aplicativo jangada" aviso "[-a][jangada][Codex aguardando: s-codex][confirma?]"
hook codex s-codex concluido '{}'
conferir "concluido: sinal 10 e notificação" \
  sinal_e_aviso "[-a][jangada][Codex concluido: s-codex][turno concluído]"

# O observador do jangada-isolar roda no host. O bwrap falso faz o papel do
# hook isolado: grava o estado da sessão e espera o aviso.
echo "== jangada-isolar"
if command -v inotifywait >/dev/null 2>&1; then
  git init -q -b main "$tmp/repo"
  git -C "$tmp/repo" -c user.name=t -c user.email=t@t commit -q --allow-empty -m inicio
  git -C "$tmp/repo" worktree add -q -b agente/t "$tmp/wt"
  mkdir -p "$tmp/bwrap"
  cat >"$tmp/bwrap/bwrap" <<EOF
#!/usr/bin/env bash
[[ "\${*: -1}" == ponto-do-teste ]] || exit 1
sleep 0.3
printf '{"estado": "trabalhando"}\n' >"$agentes/s-isolar.json"
for ((i = 0; i < 50; i++)); do [[ -s "$sinais" ]] && break; sleep 0.1; done
EOF
  chmod +x "$tmp/bwrap/bwrap"
  sessao_nova s-isolar
  : >"$sinais"
  (cd "$tmp/wt" && rodar PATH="$tmp/bwrap:$tmp/bin:$PATH" JANGADA_SESSAO=s-isolar JANGADA_MARCA_ISOLADO="$tmp/.marca" \
    "$repo_jangada/bin/jangada-isolar" -- ponto-do-teste) </dev/null >"$tmp/isolar.log" 2>&1
  # Dentro de uma sessão isolada, o jangada-isolar recusa abrir outra.
  if grep -q AUTORIZACAO_RECUSADA "$tmp/isolar.log"; then
    echo "pulado jangada-isolar: recusado dentro do isolamento"
  else
    conferir "o observador manda o sinal 10 quando o estado da sessão muda" \
      [ "$(sort -u "$sinais")" = "-RTMIN+10 -x waybar" ]
  fi
else
  echo "pulado jangada-isolar: sem inotifywait"
fi

# Sem sessão gráfica: sem WAYLAND_DISPLAY, sem barra (pkill sai com 1) e sem
# serviço de notificação (notify-send sai com 1).
echo "== sem sessão gráfica"
sem_grafico() { rodar env -u WAYLAND_DISPLAY -u DISPLAY -u DBUS_SESSION_BUS_ADDRESS FALSO_RC=1 "$@"; }
for h in claude agy codex; do
  sessao_nova "sem-$h"
  printf '{"fullyIdle": true}' | sem_grafico JANGADA_SESSAO="sem-$h" "$repo_jangada/bin/jangada-hook-$h" concluido >/dev/null
  conferir "jangada-hook-$h sai com 0" [ "$?" = 0 ]
  conferir "jangada-hook-$h grava o estado" [ "$(estado_de "sem-$h")" = concluido ]
done
sessao_nova sem-alterar
sem_grafico bash -c 'source bin/jangada-config && jangada_alterar_estado "$1" "$1.tmp" ".estado = \"concluido\""' _ "$agentes/sem-alterar.json"
conferir "jangada_alterar_estado sai com 0" [ "$?" = 0 ]
conferir "jangada_alterar_estado grava o estado" [ "$(estado_de sem-alterar)" = concluido ]
sem_grafico bash -c 'source bin/jangada-config && jangada_avisar_interface estado-sessao && jangada_notificar T C'
conferir "as duas funções saem com 0" [ "$?" = 0 ]

# Sem os programas no PATH, as funções não fazem nada e saem com 0.
mkdir -p "$tmp/vazio"
for c in bash jq dirname mkdir rmdir mv sleep date; do ln -s "$(command -v "$c")" "$tmp/vazio/$c"; done
sessao_nova sem-programa
: >"$sinais"; : >"$avisos"
rodar PATH="$tmp/vazio" bash -c 'source bin/jangada-config && jangada_alterar_estado "$1" "$1.tmp" ".estado = \"concluido\"" \
  && jangada_notificar T C' _ "$agentes/sem-programa.json" 2>/dev/null
conferir "sem pkill e sem notify-send: sai com 0" [ "$?" = 0 ]
conferir "sem pkill e sem notify-send: grava o estado" [ "$(estado_de sem-programa)" = concluido ]

echo
if ((falhas)); then
  echo "$falhas falha(s)"
  exit 1
fi
echo "tudo certo"
