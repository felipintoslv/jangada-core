#!/usr/bin/env bash
# Testa a restauração de sessões (jangada-agentes --restaurar): o comando é
# recomposto de campos conferidos e da configuração, nunca lido do estado,
# que o agente isolado consegue gravar.
#
# O tmux é falso: o new-session guarda a pasta, e o send-keys roda o texto
# digitado num bash, como faria o shell da sessão. O jangada-isolar, o claude
# e o agy também são falsos e só registram como foram chamados.
#
# Uso: testes/restaurar.sh
set -uo pipefail
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
estado="$tmp/state/jangada/agentes"
jp="$tmp/jangada"
log="$tmp/agente.log"
invadido="$tmp/invadido"
mkdir -p "$estado" "$tmp/bin" "$tmp/config/jangada/agentes" "$jp/bin" \
  "$tmp/projetos/proj" "$tmp/wt/proj/tarefa" "$tmp/fora" "$tmp/outro"
mkdir -p "$tmp/codex"
for pasta in "$tmp/projetos/proj" "$tmp/wt/proj/tarefa"; do
  printf '[projects."%s"]\ntrust_level = "trusted"\n' "$pasta" >>"$tmp/codex/config.toml"
done
for pasta in agentes nucleo orquestracao delegacao provedores validacao; do
  ln -s "$repo_jangada/$pasta" "$jp/$pasta"
done
ln -s "$repo_jangada/bin/jangada-codex" "$jp/bin/jangada-codex"
ln -s "$repo_jangada/bin/jangada-hook-codex" "$jp/bin/jangada-hook-codex"
ln -s "$repo_jangada/bin/jangada-codex-hooks" "$jp/bin/jangada-codex-hooks"
ln -s "$repo_jangada/testes" "$jp/testes"
ln -s "$repo_jangada/bin/jangada-config" "$jp/bin/jangada-config"
cat >"$tmp/config/jangada/jangada.conf" <<EOF
JANGADA_PROJETOS=$tmp/projetos
JANGADA_WORKTREES=$tmp/wt
EOF
# Perfil do usuário que desliga o isolamento: o estado não pode escolhê-lo
# para sair do bwrap.
printf 'COMANDO=claude\nJANGADA_AGENTE_ISOLAR=0\nFALSO_PERFIL=1\n' >"$tmp/config/jangada/agentes/solto.conf"
# A instalação e um repositório fora das pastas de projeto são repositórios git.
git -C "$jp" init -q
git -C "$tmp/outro" init -q

cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case " $* " in
  *" has-session "*) exit 1 ;;
  *" new-session "*)
    while (($#)); do
      case "$1" in
        -c) printf '%s\n' "$2" >"$FALSO_DIR/pasta"; shift 2 ;;
        -e) printf '%s\n' "$2" >>"$FALSO_DIR/ambiente"; shift 2 ;;
        *) shift ;;
      esac
    done
    ;;
  *" send-keys "*)
    texto="${*: -2:1}"
    printf '%s\n' "$texto" >>"$FALSO_DIR/digitado"
    (cd "$(cat "$FALSO_DIR/pasta")" && bash -c "$texto")
    ;;
esac
exit 0
EOF
for a in claude agy codex; do
  cat >"$tmp/bin/$a" <<EOF
#!/usr/bin/env bash
for arg in "\$@"; do
  if [[ "\$arg" == app-server ]]; then
    exec python3 "\$JANGADA_CORE_PATH/testes/falso-codex-hooks.py" "\$@"
  fi
done
if [[ "\${1:-}" == --help ]]; then echo --no-daemon; exit 0; fi
printf '%s|%s|%s%s\n' "\${FALSO_ISOLADO:-fora}" "\$PWD" "$a" "\$(printf ' %q' "\$@")" >>"\$FALSO_LOG"
EOF
done
cat >"$jp/bin/jangada-isolar" <<'EOF'
#!/usr/bin/env bash
# Opções com valor antes do "--": a conta e a delegação ficam registradas.
while [[ "${1:-}" == --conta || "${1:-}" == --delegar || "${1:-}" == --provedor ]]; do
  printf '%s\n' "$2" >"$FALSO_DIR/${1#--}"; shift 2
done
[[ "$1" == -- ]] && shift
FALSO_ISOLADO=isolado JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ exec "$@"
EOF
chmod +x "$tmp/bin/"* "$jp/bin/jangada-isolar"

uuid=0123abcd-4567-89ab-cdef-0123456789ab
# restaurar JSON [env extra...]: grava o estado da sessão "s" e restaura.
restaurar() {
  rm -f "$log" "$tmp/pasta" "$tmp/ambiente" "$tmp/digitado" "$invadido" "$estado/s.json" "$tmp/delegar"
  jq -n --arg dir "$tmp/projetos/proj" --argjson extra "$1" \
    '{sessao:"s", dir:$dir, agente:"claude", estado:"interrompido",
      atualizado:(now | todate)} + $extra' >"$estado/s.json"
  executar "$tmp" env -u TMUX -u JANGADA_ISOLADO -u JANGADA_AGENTE_ISOLAR -u JANGADA_DELEGAR -u JANGADA_VALIDAR_REVISOR \
    PATH="$tmp/bin:$PATH" FALSO_DIR="$tmp" FALSO_LOG="$log" CODEX_HOME="$tmp/codex" \
    XDG_STATE_HOME="$tmp/state" XDG_CONFIG_HOME="$tmp/config" JANGADA_CORE_PATH="$jp" \
    "${@:2}" "$repo_jangada/bin/jangada-agentes" --restaurar s >"$tmp/saida" 2>&1
}
linha() { cat "$log" 2>/dev/null; }
nada_rodou() { [[ ! -e "$log" && ! -e "$tmp/digitado" && ! -e "$invadido" ]]; }

# Caso 1: estado legítimo do Claude volta isolado, na pasta, na conversa e
# com o protocolo refeito.
restaurar "{\"conversa\":\"$uuid\"}"
conferir "caso 1: o Claude abre isolado na pasta do projeto" \
  bash -c '[[ "$(cut -d"|" -f1,2 "$1")" == "isolado|$2" ]]' _ "$log" "$tmp/projetos/proj"
conferir "caso 1: retoma a conversa e recebe o protocolo" \
  bash -c 'grep -q -- "--resume $2" "$1" && grep -q -- "--append-system-prompt" "$1" && grep -q "Subagentes" "$1"' _ "$log" "$uuid"
conferir "caso 1: o estado passa a iniciado" [ "$(jq -r .estado "$estado/s.json")" = iniciado ]

conferir "restauração Claude sem perfil: destino padrão agy" grep -qx JANGADA_DELEGAR=agy "$tmp/ambiente"
conferir "restauração Claude sem perfil: isolador recebe a delegação agy" grep -qx agy "$tmp/delegar"
conferir "restauração Claude: leitor e redator locais, demais papéis no agy" \
  bash -c 'grep -q -- "--destino local --arquivos FONTES" "$1" && grep -q -- "--destino agy --permitir-remoto" "$1"' _ "$estado/protocolo-s.md"
for perfil in claude-codex codex-claude; do
  restaurar "{\"perfil\":\"$perfil\", \"agente\":\"${perfil%%-*}\"}"
  conferir "restauração $perfil: leitor e redator locais, demais papéis no agy, sem fallback" \
    bash -c 'grep -q -- "--destino local --arquivos FONTES" "$1" && grep -q -- "--destino agy --permitir-remoto" "$1" &&
             grep -q "Não reencaminhe ao agy" "$1"' _ "$estado/protocolo-s.md"
done

# Caso 2: comando com um segundo comando depois do ";". O .comando é ignorado.
restaurar "{\"conversa\":\"$uuid\", \"comando\":\"claude; touch $invadido #\"}"
conferir "caso 2: o comando gravado no estado não roda" [ ! -e "$invadido" ]
conferir "caso 2: a sessão abre com o comando recomposto" grep -q "^isolado|.*claude .*--resume $uuid" "$log"

# Caso 3: .isolar falso no estado não tira o isolamento.
restaurar '{"isolar":false, "comando":"claude"}'
conferir "caso 3: isolar:false no estado é ignorado" grep -q '^isolado|' "$log"

# Caso 4: só a configuração do usuário desliga o isolamento.
restaurar '{}' JANGADA_AGENTE_ISOLAR=0
conferir "caso 4: JANGADA_AGENTE_ISOLAR=0 mantém isolamento obrigatório" \
  bash -c 'grep -q "^isolado|" "$1" && grep -q jangada-isolar "$2"' _ "$log" "$tmp/digitado"

# Caso 5: campos que não passam na conferência: recusa sem rodar nada.
restaurar "{\"agente\":\"claude; touch $invadido #\"}"
conferir "caso 5: agente com comando anexado é recusado" nada_rodou
restaurar '{"agente":"bash"}'
conferir "caso 5: agente fora da lista é recusado" nada_rodou
restaurar "{\"conversa\":\"x; touch $invadido #\"}"
conferir "caso 5: id de conversa inválido é recusado" nada_rodou
conferir "caso 5: a recusa diz o motivo" grep -q "id de conversa inválido" "$tmp/saida"
restaurar "{\"dir\":\"$tmp/fora\"}"
conferir "caso 5: pasta fora dos projetos e sem git é recusada" nada_rodou
restaurar "{\"dir\":\"$jp\"}"
conferir "caso 5: a instalação do jangada é recusada, mesmo sendo repositório git" nada_rodou
restaurar "{\"dir\":\"$tmp/projetos/proj/../../fora\"}"
conferir "caso 5: .. no caminho não escapa da conferência" nada_rodou
restaurar '{"perfil":"../../x"}'
conferir "caso 5: perfil com caminho é recusado" nada_rodou
restaurar '{"revisor":"sh -c x"}'
conferir "caso 5: revisor fora da lista é recusado" nada_rodou

# Caso 6: perfil do usuário com JANGADA_AGENTE_ISOLAR=0 escolhido pelo estado.
restaurar '{"perfil":"solto"}'
conferir "caso 6: o perfil não desliga o isolamento na restauração" grep -q '^isolado|' "$log"
conferir "caso 6: o resto do ambiente do perfil vale" \
  bash -c 'grep -qx FALSO_PERFIL=1 "$1" && ! grep -q "^JANGADA_AGENTE_ISOLAR=" "$1"' _ "$tmp/ambiente"

# Caso 7: sessão antiga do agy (ele não abre mais sessão nova) volta na mesma
# conversa; a que usava um perfil retirado é recusada com o motivo.
restaurar "{\"agente\":\"agy\", \"conversa\":\"$uuid\", \"comando\":\"agy --yolo\"}"
conferir "caso 7: a sessão antiga do agy volta na mesma conversa" \
  grep -qx "isolado|$tmp/projetos/proj|agy --conversation $uuid" "$log"
restaurar "{\"agente\":\"agy\", \"perfil\":\"agy\", \"conversa\":\"$uuid\"}"
conferir "caso 7: o perfil agy retirado é recusado com o motivo" \
  bash -c 'grep -q "perfil agy não existe mais" "$1"' _ "$tmp/saida"
conferir "caso 7: a recusa não roda nada" nada_rodou

# Caso 8: worktree sem id de conversa usa --continue.
restaurar "{\"dir\":\"$tmp/wt/proj/tarefa\", \"worktree\":\"$tmp/wt/proj/tarefa\"}"
conferir "caso 8: worktree sem id retoma com --continue" grep -q "^isolado|$tmp/wt/proj/tarefa|claude .*--continue" "$log"

# Caso 9: repositório git fora das pastas de projeto continua restaurável.
restaurar "{\"dir\":\"$tmp/outro\"}"
conferir "caso 9: repositório git fora de JANGADA_PROJETOS restaura" grep -q "^isolado|$tmp/outro|" "$log"

# Caso 10: link simbólico plantado no lugar do protocolo é trocado, não seguido.
echo "SEGREDO-PLANTADO-42" >"$tmp/segredo"
ln -sf "$tmp/segredo" "$estado/protocolo-s.md"
restaurar '{}'
conferir "caso 10: o protocolo é refeito das fontes" \
  bash -c '[[ ! -L "$1" ]] && ! grep -q SEGREDO-PLANTADO "$2" && grep -q SEGREDO-PLANTADO "$3"' _ "$estado/protocolo-s.md" "$log" "$tmp/segredo"

printf 'COMANDO=codex\nJANGADA_VALIDAR_REVISOR=codex\nJANGADA_DELEGAR=local\n' >"$tmp/config/jangada/agentes/codex-mesmo.conf"
restaurar "{\"agente\":\"codex\", \"perfil\":\"codex-mesmo\", \"revisor\":\"codex\", \"conversa\":\"$uuid\", \"isolar\":false}"
conferir "caso 11: Codex retoma isolado com UUID e revisor Codex" \
  bash -c 'grep -q "^isolado|.*codex .*--no-daemon.*resume $2" "$1" && grep -qx JANGADA_VALIDAR_REVISOR=codex "$3"' _ "$log" "$uuid" "$tmp/ambiente"
conferir "restauração Codex: perfil local explícito preservado" grep -qx JANGADA_DELEGAR=local "$tmp/ambiente"
conferir "restauração Codex: isolador recebe a delegação local" grep -qx local "$tmp/delegar"
conferir "caso 11: protocolo de delegação do Codex refeito" grep -q 'Não tente chamar subagentes do Claude' "$estado/protocolo-s.md"
restaurar "{\"agente\":\"codex\", \"dir\":\"$tmp/wt/proj/tarefa\", \"worktree\":\"$tmp/wt/proj/tarefa\"}"
conferir "caso 12: Codex sem UUID no worktree retoma por pasta" grep -q 'resume --last' "$log"
restaurar '{"agente":"codex", "delegar":"local"}'
conferir "restauração Codex: destino antigo do estado não vira preferência" grep -qx JANGADA_DELEGAR=agy "$tmp/ambiente"
conferir "restauração Codex: isolador recebe a delegação da preferência" grep -qx agy "$tmp/delegar"
conferir "restauração Codex: leitor e redator locais, demais papéis no agy" \
  bash -c 'grep -q "inclusive leitor e redator" "$1" && grep -q -- "--destino local --arquivos FONTES" "$1"' _ "$estado/protocolo-s.md"
conferir "caso 13: Codex direto sem UUID abre conversa nova" \
  bash -c 'test -s "$1" && ! grep -q "resume" "$1"' _ "$log"

mv "$tmp/bin/agy" "$tmp/agy-guardado"
rm -f "$estado/protocolo-s.md"
restaurar '{}' env PATH="$tmp/bin:/usr/bin:/bin"
conferir "caso 14: sem revisor, restauração preserva o protocolo" \
  bash -c 'grep -q "append-system-prompt" "$1" && grep -q "^7. Escrita" "$2"' _ "$log" "$estado/protocolo-s.md"
conferir "caso 14: sem revisor, restauração avisa" grep -q 'revisão indisponível' "$tmp/saida"
mv "$tmp/agy-guardado" "$tmp/bin/agy"

# A barra limpa estados órfãos a cada atualização: o contexto da rodada do
# jangada-validar mora na mesma pasta e precisa sobreviver até a decisão.
rm -f "$estado/s.json"
printf '{"sessao":"s","rodada":1}\n' >"$estado/validacao-s-r1.contexto.json"
printf '{"sessao":"morta"}\n' >"$estado/morta.json"
for opcao in --limpar-orfaos --lista-atualizada; do
  executar "$tmp" env -u TMUX -u JANGADA_ISOLADO PATH="$tmp/bin:$PATH" FALSO_DIR="$tmp" \
    XDG_STATE_HOME="$tmp/state" XDG_CONFIG_HOME="$tmp/config" JANGADA_CORE_PATH="$jp" \
    "$repo_jangada/bin/jangada-agentes" "$opcao" >"$tmp/lista" 2>&1
done
conferir "caso 15: a limpeza de órfãos preserva o contexto da rodada" \
  test -s "$estado/validacao-s-r1.contexto.json"
conferir "caso 15: o contexto da rodada não aparece como sessão" \
  bash -c '! grep -q "validacao-s-r1" "$1"' _ "$tmp/lista"
conferir "caso 15: o estado órfão de sessão continua sendo limpo" test ! -e "$estado/morta.json"

# Caso 16: a conta do agy volta a do registro protegido, mesmo com o saldo e o
# ambiente de hoje apontando para outra; sem o campo, sem --conta.
revisoes="$tmp/state/jangada/revisoes"
mkdir -p "$revisoes" "$tmp/state/jangada/contas/conta1" "$tmp/state/jangada/contas/conta2"
printf '[{"nome":"conta1","pasta":"%s","argon":false},{"nome":"conta2","pasta":"%s","argon":false}]\n' \
  "$tmp/state/jangada/contas/conta1" "$tmp/state/jangada/contas/conta2" >"$tmp/state/jangada/contas/agy.json"
jq -n '{versao:1, gerado:"2026-10-24T11:50:40+00:00", provedores:
  [["conta1",99],["conta2",10]] | map({provedor:"agy", conta:.[0], grupos:[{grupo:"gemini", janelas:[], origem:"x",
    medido_em:"2026-10-24T11:50:40+00:00", valido_ate:"2026-10-24T11:50:40+00:00", motivo:null, percentual:.[1]}]})}' \
  >"$tmp/state/jangada/cotas.json"
registro() {
  jq -n --arg raiz "$tmp/projetos/proj" --argjson extra "$1" \
    '{sessao:"s", agente:"claude", raiz:$raiz, worktree:"", delegar:"local", revisor:"claude"} + $extra' >"$revisoes/s.json"
}
conta_usada() { rm -f "$tmp/conta"; restaurar '{}' "$@"; cat "$tmp/conta" 2>/dev/null; }
registro '{"conta_agy":"conta2"}'
conferir "caso 16: restaura com a conta registrada, apesar do saldo maior da outra" \
  test "$(conta_usada)" = conta2
conferir "caso 16: a sessão restaurada abre isolada com a conta registrada" grep -q '^isolado|' "$log"
conferir "caso 16: a conta do ambiente não vence a do registro" \
  test "$(conta_usada JANGADA_AGY_CONTA=conta1)" = conta2
registro '{}'
conferir "caso 16: registro sem conta não passa --conta" test -z "$(conta_usada)"
registro '{"conta_agy":"nenhuma"}'
conta_usada >/dev/null
conferir "caso 16: conta do registro fora do catálogo é recusada com o motivo" \
  grep -q 'conta do agy do registro (nenhuma) não está mais no catálogo' "$tmp/saida"
conferir "caso 16: a recusa não roda nada" nada_rodou
rm -f "$revisoes/s.json"

if ((falhas)); then
  echo "$falhas falha(s); saídas em $tmp (mantido)"
  trap - EXIT
  exit 1
fi
echo "todos os testes da restauração passaram"
