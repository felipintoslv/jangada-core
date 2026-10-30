#!/usr/bin/env bash
# Testa o jangada-delegar com um agy falso no PATH: nada vai para a rede.
#
# Uso: testes/delegar.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
source "$repo_jangada/bin/jangada-config"
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
# jq -e em silêncio: redirecionar a linha do conferir calaria o ok e a FALHA.
jqok() { jq "$@" >/dev/null; }

exemplos_validos() {
  python3 - "$repo_jangada" "$ollama_reqs" <<'PY'
import json, pathlib, re, sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / 'delegacao'))
import extracao
pedidos = [json.loads(linha) for linha in pathlib.Path(sys.argv[2]).read_text().splitlines()]
assert pedidos
for pedido in pedidos:
    fonte, dados = pedido['messages'][1]['content'].rsplit('Exemplos de referência deste trecho (dados):\n', 1)
    exemplos, _ = json.JSONDecoder().raw_decode(dados)
    assert exemplos
    for exemplo in exemplos:
        assert set(exemplo) == {'rotulo', 'referencia'}
        assert re.search(re.escape(exemplo['rotulo']) + r'(?::[0-9]+)?: ', fonte)
        resposta = json.dumps({'fato': {'valor': 'teste', 'referencia': exemplo['referencia']}})
        conferida = extracao.conferir(resposta, fonte, {'fato': 'texto'})
        assert conferida['fato']['referencia'] == exemplo['rotulo']
        assert exemplo['rotulo'] not in pedido['messages'][0]['content']
PY
}

tmp="$(mktemp -d)"
# Com --capacidade, cada linha da fonte leva o caminho absoluto, que conta no
# contexto local. As fontes dos casos de fatiamento ficam numa pasta curta,
# para o número de fatias não depender do tamanho do TMPDIR.
curto="$(mktemp -d /tmp/jd.XXXXXX)"
erros_dos_pulados "$tmp"
pid_ollama=""
limpar() {
  [[ -n "$pid_ollama" ]] && kill "$pid_ollama" 2>/dev/null || true
  rm -rf "$tmp" "$curto"
}
trap limpar EXIT
mkdir -p "$tmp/bin" "$tmp/home/.gemini/antigravity-cli/log" "$tmp/falso" "$tmp/projeto"
# O agy roda pelo jangada-isolar, que troca o /tmp por um vazio: a pasta em
# que o falso registra cada chamada entra como gravável a mais.
export JANGADA_ISOLAR_ESCRITA="$tmp/falso"
# O ambiente do agente é mínimo por padrão: as variáveis de controle do agy
# falso entram por nome, sem abrir o filtro de credenciais.
export JANGADA_ISOLAR_AMBIENTE_MANTER="FALSO_AGENTES:FALSO_CODIGO:FALSO_COTA:FALSO_DIR:FALSO_ESGOTADO:FALSO_ESPERA:FALSO_ESPERA_USAGE:FALSO_IGNORAR_TERM:FALSO_JOGO_ATIVO:FALSO_LOG:FALSO_NEGADO:FALSO_PASSOS:FALSO_RESPOSTA:FALSO_SEMANAL:FALSO_SEM_VRAM:FALSO_TERCEIROS:FALSO_USAGE_FALHA:FALSO_USAGE_JSON:FALSO_VRAM"

# O agy falso responde ao /usage com a cota de $FALSO_COTA (fração) e ao
# pedido com $FALSO_RESPOSTA. Grava os argumentos de cada chamada.
# $FALSO_SEMANAL troca a cota semanal do Gemini, $FALSO_TERCEIROS acrescenta o
# grupo dos modelos Claude e GPT e $FALSO_ESGOTADO é o modelo que responde
# sem cota.
cat >"$tmp/bin/agy" <<'EOF'
#!/usr/bin/env bash
# A cópia privada oculta a pasta de observação do teste junto das fontes.
[[ -d "$FALSO_DIR" ]] || FALSO_DIR="$HOME/.gemini/antigravity-cli"
if [[ "$1" == agents ]]; then
  printf '%s\n' ${FALSO_AGENTES:-explorador leitor pesquisador verificador auditor arquiteto designer otimizador redator}
  exit 0
fi
if [[ "$2" == /usage ]]; then
  echo usage >>"$FALSO_DIR/usage.chamadas"
  if [[ -n "${FALSO_ESPERA_USAGE:-}" ]]; then
    trap '' TERM
    sleep "$FALSO_ESPERA_USAGE"
  fi
  [[ "${FALSO_USAGE_FALHA:-0}" == 1 ]] && exit 1
  if [[ -n "${FALSO_USAGE_JSON:-}" ]]; then
    printf '%s\n' "$FALSO_USAGE_JSON"
    exit 0
  fi
  terceiros=""
  if [[ -n "${FALSO_TERCEIROS:-}" ]]; then
    terceiros=',{"name":"Claude and GPT models","buckets":[{"id":"3p-weekly","remaining_fraction":1},{"id":"3p-5h","remaining_fraction":'"$FALSO_TERCEIROS"'}]}'
  fi
  printf '{"status":"SUCCESS","response":"","command":{"name":"usage","data":{"groups":[{"name":"Gemini Models","buckets":[{"id":"gemini-weekly","remaining_fraction":%s},{"id":"gemini-5h","remaining_fraction":%s}]}%s]}}}\n' \
    "${FALSO_SEMANAL:-0.9}" "$FALSO_COTA" "$terceiros"
  exit 0
fi
printf '%s\n' "$@" >"$FALSO_DIR/agy.args"
for a in "$@"; do
  if [[ -n "${FALSO_ESGOTADO:-}" && "$a" == "$FALSO_ESGOTADO" ]]; then
    echo "RESOURCE_EXHAUSTED (code 429): Individual quota reached." >&2
    exit 3
  fi
done
printf '%s\n' "${TMPDIR:-/tmp}" >"$FALSO_DIR/temporario"
if [[ "${FALSO_IGNORAR_TERM:-0}" == 1 ]]; then
  trap '' TERM
fi
if [[ -n "${FALSO_ESPERA:-}" ]]; then
  sleep "$FALSO_ESPERA" &
  wait "$!"
fi
printf '%s\n' "${JANGADA_AGY_PAPEL:-}" >"$FALSO_DIR/agy.papel"
pwd >"$FALSO_DIR/agy.pasta"
if [[ -f "$HOME/.gemini/antigravity-cli/settings.json" ]]; then
  cat "$HOME/.gemini/antigravity-cli/settings.json" >"$FALSO_DIR/agy.settings.json"
fi
if [[ -n "${FALSO_PASSOS:-}" ]]; then
  mkdir -p "$HOME/.gemini/antigravity-cli/conversations"
  sqlite3 "$HOME/.gemini/antigravity-cli/conversations/c1.db" \
    "create table steps(n); insert into steps values(1),(2);"
fi
[[ -n "${FALSO_LOG:-}" ]] && echo "$FALSO_LOG" >"$HOME/.gemini/antigravity-cli/log/cli-1.log"
[[ "${FALSO_CODIGO:-0}" != 0 ]] && { echo "falha falsa" >&2; exit "$FALSO_CODIGO"; }
jq -n --arg r "$FALSO_RESPOSTA" --arg n "${FALSO_NEGADO:-}" \
  '{conversation_id: "c1", status: "SUCCESS", response: $r,
    denied_actions: (if $n == "" then [] else [{action: "read_url", display_name: $n}] end)}'
EOF
chmod +x "$tmp/bin/agy"
cat >"$tmp/bin/nvidia-smi" <<'EOF'
#!/bin/sh
if [ "${FALSO_SEM_VRAM:-0}" = "1" ]; then
  exit 1
fi
if [ "${FALSO_SEM_VRAM:-0}" = "2" ]; then
  echo "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver."
  exit 1
fi
echo "${FALSO_VRAM:-8000}"
EOF
chmod +x "$tmp/bin/nvidia-smi"
cat >"$tmp/bin/pgrep" <<'EOF'
#!/bin/sh
if [ -n "${FALSO_JOGO_ATIVO:-}" ] || [ -f "${FALSO_DIR:-}/jogo-ativo" ]; then
  for arg in "$@"; do
    if [ "$arg" = "reaper SteamLaunch" ]; then
      echo 9999
      exit 0
    fi
  done
fi
exit 1
EOF
chmod +x "$tmp/bin/pgrep"
conf_agy="$tmp/home/.gemini/antigravity-cli/settings.json"
jq -n --arg w "$(realpath "$tmp/projeto")" '{trustedWorkspaces: [$w]}' >"$conf_agy"
mkdir -p "$tmp/home/.gemini/config"
sed "s|@JANGADA_CORE_PATH@|$repo_jangada|g" agentes/agy/hooks.json >"$tmp/home/.gemini/config/hooks.json"

delegar() {
  rm -f "$tmp/falso/agy.args" "$tmp/falso/agy.settings.json"
  touch "$tmp/inicio-delegacao"
  (cd "$tmp/projeto${SUBPASTA:+/$SUBPASTA}" && executar "$tmp" env -u JANGADA_DELEGAR -u JANGADA_DELEGAR_MODELOS -u JANGADA_ISOLADO -u XDG_CACHE_HOME -u XDG_STATE_HOME -u XDG_CONFIG_HOME \
    -u JANGADA_DELEGAR_ROTEAMENTO_ID -u JANGADA_DELEGAR_TENTATIVAS -u JANGADA_DELEGAR_CHAMADAS_RESTANTES \
    HOME="$tmp/home" PATH="$tmp/bin:$PATH" JANGADA_CORE_PATH="$repo_jangada" FALSO_DIR="$tmp/falso" \
    FALSO_COTA="${COTA:-0.9}" FALSO_RESPOSTA="${RESPOSTA-relatorio em a.sh:1}" \
    FALSO_CODIGO="${CODIGO:-0}" FALSO_NEGADO="${NEGADO:-}" FALSO_LOG="${LOG:-}" FALSO_USAGE_FALHA="${USAGE_FALHA:-0}" \
    ${AGENTES:+FALSO_AGENTES="$AGENTES"} \
    ${SETTINGS_AGY:+JANGADA_AGY_SETTINGS="$SETTINGS_AGY"} \
    ${PASSOS:+FALSO_PASSOS="$PASSOS"} \
    ${USAGE_JSON:+FALSO_USAGE_JSON="$USAGE_JSON"} \
    ${SEMANAL:+FALSO_SEMANAL=$SEMANAL} \
    ${TERCEIROS:+FALSO_TERCEIROS=$TERCEIROS} \
    ${ESGOTADO:+FALSO_ESGOTADO=$ESGOTADO} \
    ${MODELOS:+JANGADA_DELEGAR_MODELOS="$MODELOS"} \
    ${DELEGAR:+JANGADA_DELEGAR=$DELEGAR} \
    ${AGENTE:+JANGADA_AGENTE=$AGENTE} \
    ${CHAMADAS_MAX:+JANGADA_DELEGAR_CHAMADAS_MAX=$CHAMADAS_MAX} \
    ${TEMPO_TOTAL:+JANGADA_DELEGAR_TEMPO_TOTAL=$TEMPO_TOTAL} \
    ${ESPERA_AGY:+FALSO_ESPERA=$ESPERA_AGY} \
    ${IGNORAR_TERM:+FALSO_IGNORAR_TERM=$IGNORAR_TERM} \
    ${ESPERA_USAGE:+FALSO_ESPERA_USAGE=$ESPERA_USAGE} \
    ${FALSO_JOGO_ATIVO:+FALSO_JOGO_ATIVO="$FALSO_JOGO_ATIVO"} \
    ${FALSO_VRAM:+FALSO_VRAM="$FALSO_VRAM"} \
    ${SEM_VRAM:+FALSO_SEM_VRAM="$SEM_VRAM"} \
    ${ISOLADO:+JANGADA_ISOLADO="$ISOLADO"} \
    ${LOCAL_IGNORAR_VRAM:+JANGADA_LOCAL_IGNORAR_VRAM="$LOCAL_IGNORAR_VRAM"} \
    ${OLLAMA_URL:+JANGADA_OLLAMA_URL="$OLLAMA_URL"} \
    ${LOCAL_MODELO:+JANGADA_LOCAL_MODELO="$LOCAL_MODELO"} \
    ${LOCAL_CTX:+JANGADA_LOCAL_CTX="$LOCAL_CTX"} \
    ${LOCAL_VRAM_MIN:+JANGADA_LOCAL_VRAM_MIN="$LOCAL_VRAM_MIN"} \
    ${LOCAL_ESPERA:+JANGADA_LOCAL_ESPERA="$LOCAL_ESPERA"} \
    ${LOCAL_FATIAS_MAX:+JANGADA_LOCAL_FATIAS_MAX="$LOCAL_FATIAS_MAX"} \
    "$repo_jangada/bin/jangada-delegar" "$@" >"$tmp/saida" 2>"$tmp/erro")
  echo $? >"$tmp/codigo"
  local privado
  privado="$(tail -n 1 "$tmp/home/.local/state/jangada/delegacoes.jsonl" 2>/dev/null | jq -r '.registro_ferramentas // empty')"
  if [[ -z "$privado" || ! -f "$privado/agy.args" ]]; then
    local marcador_privado
    marcador_privado="$(find "$tmp/home/.local/state/jangada/agentes" -mindepth 2 -maxdepth 2 \
      -path '*/pesquisa-*/agy.args' -type f -newer "$tmp/inicio-delegacao" -print -quit 2>/dev/null)"
    [[ -z "$marcador_privado" ]] || privado="${marcador_privado%/*}"
  fi
  if [[ -n "$privado" && -f "$privado/agy.args" ]]; then
    for nome in agy.args agy.papel agy.pasta agy.settings.json temporario; do
      [[ ! -f "$privado/$nome" ]] || cp "$privado/$nome" "$tmp/falso/$nome"
    done
  fi
}
codigo() { cat "$tmp/codigo"; }

delegar --permitir-remoto explorador "mapeie"
conferir "caso 1: código 0" [ "$(codigo)" = 0 ]
conferir "caso 1: imprime o relatório" grep -qx "relatorio em a.sh:1" "$tmp/saida"
conferir "caso 1: o agy recebe o papel, que o hook do leitor lê" grep -qx explorador "$tmp/falso/agy.papel"
conferir "caso 1: agente do papel" grep -qx -- explorador "$tmp/falso/agy.args"
conferir "caso 1: Flash high para o explorador" grep -qx -- gemini-3.8-flash-high "$tmp/falso/agy.args"
conferir "caso 1: roda com --sandbox" grep -qx -- --sandbox "$tmp/falso/agy.args"
conferir "caso 1: roda na pasta atual" [ "$(cat "$tmp/falso/agy.pasta")" = "$tmp/projeto" ]

reg="$tmp/home/.local/state/jangada/delegacoes.jsonl"
delegar --permitir-remoto verificador "confira"
conferir "caso 2: Flash high para o verificador" grep -qx -- gemini-3.8-flash-high "$tmp/falso/agy.args"
# Antes da primeira, depois de cada uma; o antes da segunda vem do cache.
conferir "caso 2: cota do antes vem do cache" [ "$(wc -l <"$tmp/falso/usage.chamadas")" = 3 ]
conferir "caso 2: uma linha por chamada" [ "$(wc -l <"$reg")" = 2 ]
conferir "caso 2: linha com os campos" jqok -e 'select(.papel == "verificador")
  | .destino == "agy" and .modelo == "gemini-3.8-flash-high" and .codigo_saida == 0 and .recusa == false
    and .cota_antes == 90 and .cota_depois == 90 and .palavras == 3 and .tokens_retorno == 5
    and .conversa == "c1" and .pasta != "" and (.segundos | type) == "number"' "$reg"


rm -f "$tmp/home/.cache/jangada/agy-usage.json"
COTA=0.15 delegar --permitir-remoto explorador "leia"
conferir "caso 3: cota baixa recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 3: agy não é chamado" test ! -e "$tmp/falso/agy.args"
conferir "caso 3: diz a cota" grep -q "15%" "$tmp/erro"
conferir "caso 3: informa bloqueio do apoio" grep -q "Delegação bloqueada" "$tmp/saida"
conferir "caso 3: recusa registrada com o motivo" \
  jqok -se 'last | .recusa and .codigo_saida == 4 and (.motivo | test("15"))' "$reg"

# A cota semanal zerada recusa mesmo com a de 5 horas cheia.
rm -f "$tmp/home/.cache/jangada/agy-usage.json"
SEMANAL=0 COTA=0.99 delegar --permitir-remoto explorador "leia"
conferir "caso 3b: cota semanal zerada recusa" [ "$(codigo)" = 4 ]
conferir "caso 3b: agy não é chamado" test ! -e "$tmp/falso/agy.args"
conferir "caso 3b: motivo é a cota" \
  jqok -se 'last | .motivo_codigo == "cota_insuficiente" and .cota_antes == 0' "$reg"

# Sem cota no Gemini, o modelo seguinte da lista atende pelo outro grupo.
rm -f "$tmp/home/.cache/jangada/agy-usage.json"
SEMANAL=0 TERCEIROS=0.8 delegar --permitir-remoto explorador "leia"
conferir "caso 3c: Gemini sem cota passa ao modelo seguinte" [ "$(codigo)" = 0 ]
conferir "caso 3c: chama o Sonnet do agy" grep -qx -- claude-sonnet-5-5-high "$tmp/falso/agy.args"
conferir "caso 3c: registra o modelo usado e a cota do grupo dele" \
  jqok -se 'last | .modelo == "claude-sonnet-5-5-high" and .cota_antes == 80 and .recusa == false' "$reg"

# Argon tem orçamento separado de Flash/Pro, inclusive quando falta um grupo.
for caso in flash_livre argon_livre flash_ausente argon_ausente flash_invalido argon_invalido flash_sem_argon argon_sem_flash argon_proprio_invalido; do
  flash=0.8; argon=0.9; esperado=0; cota_esperada=80
  MODELOS=gemini-3.8-flash-high
  case "$caso" in
    flash_livre) argon=0 ;;
    argon_livre) flash=0; MODELOS=gemini-4-argon-high; cota_esperada=90 ;;
    flash_ausente) flash=null; esperado=4 ;;
    argon_ausente) argon=null; MODELOS=gemini-4-argon-high; esperado=4 ;;
    flash_invalido) flash='"inválida"'; esperado=4 ;;
    argon_invalido) argon='"inválida"' ;;
    flash_sem_argon) argon=null ;;
    argon_sem_flash) flash=null; MODELOS=gemini-4-argon-high; cota_esperada=90 ;;
    argon_proprio_invalido) argon='"inválida"'; MODELOS=gemini-4-argon-high; esperado=4 ;;
  esac
  USAGE_JSON="$(jq -nc --argjson f "$flash" --argjson a "$argon" '
    {command:{data:{groups:[
      {buckets: (if $f == null then [] else
        [{id:"gemini-weekly",remaining_fraction:$f},{id:"gemini-5h",remaining_fraction:1}] end)},
      {buckets: (if $a == null then [] else
        [{id:"gemini-argon-wtu-weekly",remaining_fraction:$a}] end)}]}}}')"
  rm -f "$tmp/home/.cache/jangada/agy-usage.json"
  ISOLADO=1 delegar --permitir-remoto explorador "mapeie" --json
  conferir "grupos $caso: código esperado" [ "$(codigo)" = "$esperado" ]
  if [[ "$esperado" == 0 ]]; then
    conferir "grupos $caso: modelo e cota próprios" jqok -e \
      --arg m "$MODELOS" --argjson c "$cota_esperada" '.modelo == $m and .cota_antes == $c' "$tmp/saida"
  else
    conferir "grupos $caso: cota desconhecida sem chamada" jqok -e \
      '.motivo_codigo == "cota_desconhecida" and .chamadas_executor == 0' "$tmp/saida"
    conferir "grupos $caso: não usa cota alheia" test ! -e "$tmp/falso/agy.args"
  fi
done
unset MODELOS USAGE_JSON
rm -f "$tmp/home/.cache/jangada/agy-usage.json"

ISOLADO=1 MODELOS=gemini-teste delegar --permitir-remoto explorador "mapeie" --json
conferir "cota: identificador Gemini legado preserva o grupo comum" jqok -e \
  '.codigo_saida == 0 and .modelo == "gemini-teste" and .cota_antes == 90
    and .cotas_modelos[0].grupo == "gemini"' "$tmp/saida"
rm -f "$tmp/home/.cache/jangada/agy-usage.json"

# O /usage diz que há cota, mas o agy responde que acabou: tenta o seguinte.
rm -f "$tmp/home/.cache/jangada/agy-usage.json"
TERCEIROS=0.8 ESGOTADO=gemini-3.8-flash-high delegar --permitir-remoto explorador "leia"
conferir "caso 3d: modelo esgotado na chamada passa ao seguinte" [ "$(codigo)" = 0 ]
conferir "caso 3d: avisa da troca" grep -q "tentando o próximo modelo" "$tmp/erro"
conferir "caso 3d: registra o modelo que respondeu" \
  jqok -se 'last | .modelo == "claude-sonnet-5-5-high"' "$reg"

rm -f "$tmp/home/.cache/jangada/agy-usage.json"
SEMANAL=0 TERCEIROS=0.8 delegar --permitir-remoto explorador "mapeie" --destino agy --modelo gemini-3.8-flash-high --json
conferir "modelo explícito: não troca por terceiro com cota" jqok -e \
  '.codigo_saida == 4 and .modelo == "gemini-3.8-flash-high" and (.cotas_modelos | length) == 1' "$tmp/saida"
conferir "modelo explícito: não chama outro modelo" test ! -e "$tmp/falso/agy.args"

# Sem o grupo dos demais modelos no /usage, a cota deles é desconhecida.
rm -f "$tmp/home/.cache/jangada/agy-usage.json"
ESGOTADO=gemini-3.8-flash-high delegar --permitir-remoto explorador "leia"
conferir "caso 3e: esgotado e sem outro grupo, recusa" [ "$(codigo)" = 4 ]
conferir "caso 3e: motivo é a cota do primeiro modelo" \
  jqok -se 'last | .motivo_codigo == "cota_insuficiente" and .modelo == "gemini-3.8-flash-high"' "$reg"

rm -f "$tmp/home/.cache/jangada/agy-usage.json"
MODELOS="gemini-3.1-pro-high" delegar --permitir-remoto explorador "leia"
conferir "caso 3f: JANGADA_DELEGAR_MODELOS troca o modelo" grep -qx -- gemini-3.1-pro-high "$tmp/falso/agy.args"
rm -f "$tmp/home/.cache/jangada/agy-usage.json"
COTA='"invalida"' TERCEIROS=0.8 delegar --permitir-remoto explorador "leia"
conferir "cota parcial: grupo ilegível não impede outro válido" [ "$(codigo)" = 0 ]
conferir "cota parcial: usa somente o grupo válido" grep -qx -- claude-sonnet-5-5-high "$tmp/falso/agy.args"
rm -f "$tmp/home/.cache/jangada/agy-usage.json"
MODELOS="claude-sonnet-5-5-high gemini-3.8-flash-high" delegar --permitir-remoto explorador "leia"
conferir "cota parcial: primeiro grupo ausente permite Gemini" [ "$(codigo)" = 0 ]
conferir "cota parcial: preserva ordem e pula cota desconhecida" grep -qx -- gemini-3.8-flash-high "$tmp/falso/agy.args"
chamadas_antes="$(wc -l <"$tmp/falso/usage.chamadas")"

rm -f "$tmp/home/.cache/jangada/agy-usage.json"
USAGE_FALHA=1 delegar --permitir-remoto explorador "leia"
conferir "caso 4: /usage falhou, recusa" [ "$(codigo)" = 4 ]
conferir "caso 4: consulta o /usage uma vez, não uma por modelo" \
  [ "$(wc -l <"$tmp/falso/usage.chamadas")" = "$((chamadas_antes + 1))" ]

rm -f "$tmp/home/.cache/jangada/agy-usage.json"
CODIGO=1 delegar --permitir-remoto pesquisador "busque"
conferir "caso 5: agy falhou, recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 5: informa bloqueio do apoio" grep -q "Delegação bloqueada" "$tmp/saida"

LOG='Agent "explorador" not found, using default' delegar --permitir-remoto explorador "mapeie"
conferir "caso 6: agente não achado, recusa" [ "$(codigo)" = 4 ]
conferir "caso 6: diz o motivo" grep -q "não achou o agente" "$tmp/erro"
rm -f "$tmp/home/.gemini/antigravity-cli/log/cli-1.log"

RESPOSTA="$(yes palavra | head -n 700 | paste -sd ' ')" delegar --permitir-remoto explorador "mapeie"
conferir "caso 7: relatório longo sai cortado" [ "$(head -n 1 "$tmp/saida" | wc -w)" = 600 ]
conferir "caso 7: arquivo completo existe" bash -c 'arq="$(sed -n "s/.*completo em \(.*\)\]\$/\1/p" "$1")"
  [ "$(wc -w <"${arq:-/nada}" 2>/dev/null)" = 700 ]' _ "$tmp/saida"

RESPOSTA="curto" delegar --permitir-remoto explorador "mapeie" --arquivo "$tmp/rel.md"
conferir "caso 8: --arquivo grava o relatório" grep -qx curto "$tmp/rel.md"

RESPOSTA="$(printf '%s\n' "# Um título comprido sem fonte nenhuma" "- a função está em bin/jangada-validar:82, perto do fim" \
  "- esta afirmação comprida não tem fonte alguma" "- a norma está em https://exemplo.org/norma, item 3")" \
  delegar --permitir-remoto explorador "leia"
conferir "caso 8b: conta as afirmações sem fonte" jqok -se 'last | .sem_fonte == 1' "$reg"

DELEGAR=claude delegar explorador "mapeie"
conferir "caso 9: perfil claude recusa sem chamar o agy" \
  bash -c '[ "$1" = 4 ] && [ ! -e "$2" ]' _ "$(codigo)" "$tmp/falso/agy.args"
conferir "caso 9: registrada com destino claude" jqok -se 'last | .destino == "claude" and .recusa' "$reg"
DELEGAR=nativo delegar explorador "mapeie"
conferir "caso 10: sessão do agy aponta o invoke_subagent" grep -q invoke_subagent "$tmp/erro"

ISOLADO=1 RESPOSTA="" NEGADO=ReadUrlContent delegar --permitir-remoto explorador "busque"
conferir "caso 12: ação negada sem resposta recusa" \
  bash -c '[ "$1" = 4 ] && grep -q "ReadUrlContent" "$2"' _ "$(codigo)" "$tmp/erro"
ISOLADO=1 NEGADO=ReadUrlContent delegar --permitir-remoto explorador "busque" --json
conferir "caso 13: ação negada com resposta também recusa" \
  jqok -e '.codigo_saida == 4 and .motivo_codigo == "destino_proibido" and .relatorio == ""' "$tmp/saida"

delegar --permitir-remoto pesquisador "busque" --destino agy --json
conferir "pesquisa: sem domínio autorizado não chama modelo" jqok -e \
  '.codigo_saida == 4 and .chamadas_executor == 0 and .motivo_codigo == "destino_proibido"' "$tmp/saida"
printf 'fonte local não autorizada para pesquisa\n' >"$tmp/projeto/fonte-pesquisa.txt"
ISOLADO=1 delegar --permitir-remoto pesquisador "busque" --destino agy --json \
  --arquivos "$tmp/projeto/fonte-pesquisa.txt"
conferir "pesquisa: arquivos sem URL recusam antes do modelo" jqok -e \
  '.codigo_saida == 4 and .chamadas_executor == 0 and .motivo_codigo == "destino_proibido"' "$tmp/saida"
conferir "pesquisa: arquivo local sem URL não chega ao agy" test ! -e "$tmp/falso/agy.args"

delegar leitor "leia" --destino local --modelo gemini-3.8-flash-high
conferir "modelo: destino local com modelo agy dá código 2" [ "$(codigo)" = 2 ]
conferir "modelo: combinação inválida não chama agy" test ! -e "$tmp/falso/agy.args"
delegar leitor "leia" --destino agy --url https://ai.google.dev/
conferir "URL: papel diferente de pesquisador dá código 2" [ "$(codigo)" = 2 ]
delegar pesquisador "busque" --destino agy --url https://ai.google.dev/ --arquivos fonte.txt
conferir "URL: fontes locais na pesquisa dão código 2" [ "$(codigo)" = 2 ]
delegar pesquisador "busque" --destino agy --url https://ai.google.dev/ --capacidade leitura_documental
conferir "URL: capacidade na pesquisa dá código 2" [ "$(codigo)" = 2 ]
conferir "URL: combinações inválidas não chamam agy" test ! -e "$tmp/falso/agy.args"

mkdir -p "$tmp/home/.gemini/antigravity-cli/conversations"
sqlite3 "$tmp/home/.gemini/antigravity-cli/conversations/c1.db" \
  'create table steps(n); insert into steps values(1),(2),(3),(4),(5);'
ISOLADO=1 PASSOS=1 delegar --permitir-remoto pesquisador "busque" --destino agy \
  --modelo gemini-3.8-flash-high --url https://ai.google.dev/ --json
conferir "pesquisa: executor e banco privados" jqok -e \
  '.codigo_saida == 0 and (.registro_ferramentas | length) > 0 and .passos == 2' "$tmp/saida"
conferir "pesquisa: instrução para parar na ação negada" grep -q \
  'Se uma ferramenta ou comando for negado, pare e informe qual ação foi negada.' "$tmp/falso/agy.args"

rm -f "$tmp/home/.cache/jangada/agy-usage.json"
ISOLADO=1 TERCEIROS=0.8 ESGOTADO=gemini-3.8-flash-high delegar --permitir-remoto pesquisador \
  "busque" --destino agy --url https://ai.google.dev/ --json
conferir "pesquisa: segunda tentativa privada conclui" jqok -e \
  '.codigo_saida == 0 and .modelo == "claude-sonnet-5-5-high" and .chamadas_executor == 2' "$tmp/saida"
conferir "pesquisa: instrução aparece uma vez na segunda tentativa" \
  [ "$(grep -c 'Faça uma busca e abra a fonte pública oficial autorizada' "$tmp/falso/agy.args")" = 1 ]
rm -f "$tmp/home/.cache/jangada/agy-usage.json"

git init -q "$tmp/projeto"
mkdir -p "$tmp/projeto/subpasta"
printf 'autorizado\nsegunda linha inteira\n' >"$tmp/projeto/subpasta/relatório final.txt"
printf 'literal inteiro\nlinha que também precisa seguir\n' >"$tmp/projeto/subpasta/literal.txt:1-1"
for papel_privado in leitor redator arquiteto; do
  ISOLADO=1 SUBPASTA=subpasta delegar --permitir-remoto "$papel_privado" "leia" --destino agy \
    --modelo gemini-3.8-flash-high --json --arquivos 'relatório final.txt'
  conferir "$papel_privado: nome acentuado relativo à subpasta no executor privado" jqok -e \
    --arg fonte "$tmp/projeto/subpasta/relatório final.txt" \
    '.codigo_saida == 0 and (.registro_ferramentas | length) > 0 and .fontes_autorizadas == [$fonte]' "$tmp/saida"
  conferir "$papel_privado: somente o conteúdo fornecido chega ao pedido" grep -q '2: segunda linha inteira' "$tmp/falso/agy.args"
done
ISOLADO=1 delegar --permitir-remoto arquiteto "avalie" --destino agy \
  --modelo gemini-3.8-flash-high --json --arquivos "$tmp/projeto/subpasta"
conferir "arquiteto: pasta recusa antes do modelo" jqok -e \
  '.codigo_saida == 4 and .motivo_codigo == "entrada_invalida" and .chamadas_executor == 0' "$tmp/saida"
conferir "arquiteto: pasta não chega ao agy" test ! -e "$tmp/falso/agy.args"
python3 -c 'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("x" * (97 * 1024))' "$tmp/projeto/grande.txt"
ISOLADO=1 delegar --permitir-remoto arquiteto "avalie" --destino agy \
  --modelo gemini-3.8-flash-high --json --arquivos "$tmp/projeto/grande.txt"
conferir "arquiteto: pedido e fontes acima de 96 KiB recusam antes do modelo" jqok -e \
  '.codigo_saida == 4 and .motivo_codigo == "entrada_invalida" and .chamadas_executor == 0' "$tmp/saida"
conferir "arquiteto: excesso informa o limite sem chamar agy" bash -c \
  'grep -q "96 KiB" "$1" && [ ! -e "$2" ]' _ "$tmp/saida" "$tmp/falso/agy.args"
ISOLADO=1 SUBPASTA=subpasta delegar --permitir-remoto leitor "leia" --destino agy --json \
  --arquivos 'literal.txt:1-1'
conferir "fonte literal: sufixo de faixa existente vale inteiro" grep -q \
  '2: linha que também precisa seguir' "$tmp/falso/agy.args"
ISOLADO=1 SUBPASTA=subpasta delegar --permitir-remoto leitor "leia" --destino agy --json \
  --arquivos 'relatório final.txt:1-1'
conferir "fonte em faixa: segunda linha não é enviada" bash -c \
  'grep -q "1: autorizado" "$1" && ! grep -q "segunda linha inteira" "$1"' _ "$tmp/falso/agy.args"
ISOLADO=1 SUBPASTA=subpasta delegar --permitir-remoto leitor "leia" --destino agy --json \
  --arquivos 'relatório final.txt:9-10'
conferir "fonte inválida: motivo próprio sem contar modelo" jqok -e \
  '.codigo_saida == 4 and .motivo_codigo == "entrada_invalida" and .chamadas_executor == 0' "$tmp/saida"
conferir "fonte inválida: sem traceback ou chamada ao agy" bash -c \
  '! grep -q Traceback "$1" && [ ! -e "$2" ]' _ "$tmp/erro" "$tmp/falso/agy.args"
jq '.permissions.deny = ["read_url(negado.example)"]' "$conf_agy" \
  >"$tmp/projeto/subpasta/settings-selecionado.json"
jq '.trustedWorkspaces = []' "$conf_agy" >"$tmp/conf" && cp "$tmp/conf" "$conf_agy"
ISOLADO=1 SUBPASTA=subpasta SETTINGS_AGY=settings-selecionado.json delegar --permitir-remoto pesquisador "busque" \
  --destino agy --modelo gemini-3.8-flash-high --url https://ai.google.dev/ --json
conferir "settings: caminho relativo mantém a confiança escolhida após o cd" jqok -e \
  '.codigo_saida == 0 and (.registro_ferramentas | length) > 0' "$tmp/saida"
conferir "settings: preserva as recusas do arquivo escolhido" jqok -e \
  '.permissions.deny == ["read_url(negado.example)"]' "$tmp/falso/agy.settings.json"
jq -n --arg w "$(realpath "$tmp/projeto")" '{trustedWorkspaces: [$w]}' >"$conf_agy"
rm -rf "$tmp/projeto/.git"

# Pasta sem confiança do agy: recusa, sem confiar por conta própria.
jq '.trustedWorkspaces = []' "$conf_agy" >"$tmp/conf" && cp "$tmp/conf" "$conf_agy"
delegar --permitir-remoto explorador "mapeie"
conferir "caso 14: pasta sem confiança recusa sem chamar o agy" \
  bash -c '[ "$1" = 4 ] && [ ! -e "$2" ] && grep -q "não confia" "$3"' _ "$(codigo)" "$tmp/falso/agy.args" "$tmp/erro"
conferir "caso 14: o settings.json do agy fica como estava" jqok -e '.trustedWorkspaces == []' "$conf_agy"
jq -n --arg w "$(realpath "$tmp/projeto")" '{trustedWorkspaces: [$w]}' >"$conf_agy"

# Pasta confiada pelo caminho com link simbólico, como o agy grava quando foi
# aberta por ele.
ln -s "$tmp/projeto" "$tmp/atalho"
jq -n --arg w "$tmp/atalho" '{trustedWorkspaces: [$w]}' >"$conf_agy"
(cd "$tmp/atalho" && executar "$tmp" env -u JANGADA_DELEGAR -u JANGADA_ISOLADO -u XDG_CACHE_HOME -u XDG_STATE_HOME -u XDG_CONFIG_HOME \
  HOME="$tmp/home" PATH="$tmp/bin:$PATH" JANGADA_CORE_PATH="$repo_jangada" FALSO_DIR="$tmp/falso" \
  FALSO_COTA=0.9 FALSO_RESPOSTA="relatorio em a.sh:1" PWD="$tmp/atalho" \
  "$repo_jangada/bin/jangada-delegar" --permitir-remoto explorador "mapeie" >/dev/null 2>&1)
conferir "caso 14b: pasta confiada pelo link simbólico é aceita" [ $? = 0 ]
jq -n --arg w "$(realpath "$tmp/projeto")" '{trustedWorkspaces: [$w]}' >"$conf_agy"

# Papel que o agy não carregou: o agy rodaria o agente padrão.
AGENTES="leitor" delegar --permitir-remoto explorador "mapeie"
conferir "caso 15: papel ausente no agy recusa antes do pedido" \
  bash -c '[ "$1" = 4 ] && [ ! -e "$2" ] && grep -q "install.sh 50" "$3"' _ "$(codigo)" "$tmp/falso/agy.args" "$tmp/erro"

# Confiança no worktree (jangada-worktree-preparar e fim da sessão): a
# primeira alteração guarda o settings.json original, e só ela.
confianca() {
  env HOME="$tmp/home" XDG_STATE_HOME="$tmp/estado" JANGADA_CORE_PATH="$repo_jangada" \
    bash -c 'source "$1/bin/jangada-config"; jangada_agy_ajustar_confianca "$2" "$3"' _ "$repo_jangada" "$@"
}
echo '{"trustedWorkspaces": [], "outra": 1}' >"$conf_agy"
confianca adicionar "$tmp/projeto"
confianca adicionar "$tmp/falso"
confianca remover "$tmp/projeto"
conferir "caso 16: confiança adicionada e removida por caminho" \
  jqok -e --arg w "$(realpath "$tmp/falso")" '.trustedWorkspaces == [$w] and .outra == 1' "$conf_agy"
conferir "caso 16: cópia do settings.json de antes da primeira alteração" \
  jqok -e '.trustedWorkspaces == [] and .outra == 1' "$conf_agy.jangada-orig"

# A pasta do settings.json é gravável pelo agente isolado: um link posto ali
# não pode levar a escrita de fora do isolamento a outro arquivo.
echo '{"alvo": 1}' >"$tmp/alvo.json"
mv "$conf_agy" "$conf_agy.guardado"
ln -s "$tmp/alvo.json" "$conf_agy"
confianca adicionar "$tmp/projeto"
conferir "caso 16b: settings.json trocado por link não é seguido" \
  bash -c '[ -L "$1" ] && [ "$(cat "$2")" = "{\"alvo\": 1}" ]' _ "$conf_agy" "$tmp/alvo.json"
rm -f "$conf_agy"
mv "$conf_agy.guardado" "$conf_agy"
# O link aparece depois da conferência e o rename falha: nada é regravado no
# lugar, e o temporário nunca fica na pasta do settings.json.
mkdir -p "$tmp/mv-falso"
cat >"$tmp/mv-falso/mv" <<FIM
#!/bin/sh
printf '%s\\n' "\$*" >"$tmp/mv.args"
rm -f "$conf_agy"
ln -s "$tmp/alvo.json" "$conf_agy"
exit 1
FIM
chmod +x "$tmp/mv-falso/mv"
cp "$conf_agy" "$conf_agy.guardado"
PATH="$tmp/mv-falso:$PATH" confianca adicionar "$tmp/projeto"
conferir "caso 16c: rename falho com link no lugar não grava no alvo" \
  bash -c '[ "$(cat "$1")" = "{\"alvo\": 1}" ]' _ "$tmp/alvo.json"
conferir "caso 16c: o temporário fica no estado, fora da pasta do settings.json" \
  bash -c 'read -r _ _ origem _ <"$1"; [[ "$origem" == "$2"/* ]]' _ "$tmp/mv.args" "$tmp/estado"
rm -f "$conf_agy"
mv "$conf_agy.guardado" "$conf_agy"
# O link para uma pasta aparece logo antes do rename (um chmod falso o cria):
# o mv troca o próprio link, não põe o arquivo dentro da pasta apontada.
mkdir -p "$tmp/chmod-falso" "$tmp/pasta-alvo"
cat >"$tmp/chmod-falso/chmod" <<FIM
#!/bin/sh
rm -f "$conf_agy"
ln -s "$tmp/pasta-alvo" "$conf_agy"
FIM
chmod +x "$tmp/chmod-falso/chmod"
cp "$conf_agy" "$conf_agy.guardado"
PATH="$tmp/chmod-falso:$PATH" confianca adicionar "$tmp/projeto"
conferir "caso 16d: link para pasta posto antes do rename não recebe o arquivo" \
  bash -c '[ -z "$(ls -A "$1")" ] && [ ! -L "$2" ]' _ "$tmp/pasta-alvo" "$conf_agy"
rm -f "$conf_agy"
mv "$conf_agy.guardado" "$conf_agy"

# O worktree só herda a confiança do repositório principal: com a raiz fora
# do trustedWorkspaces, o jangada-worktree-preparar não confia no worktree.
git init --quiet "$tmp/raiz"
git -C "$tmp/raiz" -c user.name=t -c user.email=t@t commit --quiet --allow-empty -m inicio
git -C "$tmp/raiz" worktree add --quiet -b agente/t "$tmp/wt"
preparar() {
  executar "$tmp" env -u JANGADA_ISOLADO HOME="$tmp/home" XDG_STATE_HOME="$tmp/estado" JANGADA_CORE_PATH="$repo_jangada" \
    "$repo_jangada/bin/jangada-worktree-preparar" "$tmp/raiz" "$tmp/wt" </dev/null >"$tmp/saida-preparar" 2>&1
}
echo '{"trustedWorkspaces": []}' >"$conf_agy"
preparar
conferir "caso 17: raiz sem confiança, worktree sem confiança" jqok -e '.trustedWorkspaces == []' "$conf_agy"
conferir "caso 17: avisa que o worktree fica sem confiança" grep -q "fica sem confiança" "$tmp/saida-preparar"
jq -n --arg w "$(realpath "$tmp/raiz")" '{trustedWorkspaces: [$w]}' >"$conf_agy"
preparar
conferir "caso 17: raiz confiável, worktree confiável" \
  jqok -e --arg w "$(realpath "$tmp/wt")" '.trustedWorkspaces | index($w)' "$conf_agy"

# A recusa distingue a raiz sem autorização do worktree que ainda não recebeu
# a confiança derivada, diz o passo de cada caso e não concede nada.
delegar_wt() {
  (cd "$tmp/wt" && executar "$tmp" env -u JANGADA_DELEGAR -u JANGADA_ISOLADO -u XDG_CACHE_HOME -u XDG_STATE_HOME -u XDG_CONFIG_HOME \
    HOME="$tmp/home" PATH="$tmp/bin:$PATH" JANGADA_CORE_PATH="$repo_jangada" FALSO_DIR="$tmp/falso" \
    FALSO_COTA=0.9 FALSO_RESPOSTA="relatorio em a.sh:1" JANGADA_SESSAO=raiz--t \
    "$repo_jangada/bin/jangada-delegar" --permitir-remoto explorador "mapeie" >/dev/null 2>"$tmp/erro-wt"
    echo $? >"$tmp/codigo-wt")
}
jq -n --arg w "$(realpath "$tmp/raiz")" '{trustedWorkspaces: [$w]}' >"$conf_agy"
delegar_wt
conferir "caso 17b: worktree sem sincronização recusa com código 4 e o passo" \
  bash -c '[ "$(cat "$1")" = 4 ] && grep -q "ainda não recebeu a confiança derivada" "$2" && grep -q "jangada-agentes --confianca raiz--t" "$2"' \
  _ "$tmp/codigo-wt" "$tmp/erro-wt"
conferir "caso 17b: a recusa não sincroniza o worktree" \
  jqok -e --arg w "$(realpath "$tmp/raiz")" '.trustedWorkspaces == [$w]' "$conf_agy"
echo '{"trustedWorkspaces": []}' >"$conf_agy"
delegar_wt
conferir "caso 17c: raiz sem autorização recusa com código 4 e nomeia a raiz" \
  bash -c '[ "$(cat "$1")" = 4 ] && grep -qF "não confia na raiz $3" "$2" && grep -q "pergunta de confiança" "$2"' \
  _ "$tmp/codigo-wt" "$tmp/erro-wt" "$(realpath "$tmp/raiz")"
conferir "caso 17c: a recusa não autoriza a raiz" jqok -e '.trustedWorkspaces == []' "$conf_agy"
jq -n --arg w "$(realpath "$tmp/projeto")" '{trustedWorkspaces: [$w]}' >"$conf_agy"

# O leitor remoto recebe somente fontes explícitas, sem terminal nem ferramentas.
delegar --permitir-remoto leitor "leia" --json
conferir "leitor remoto: falta de fontes recusa antes do pedido" \
  jqok -e '.codigo_saida == 4 and .chamadas_executor == 0 and .motivo_codigo == "destino_proibido"' "$tmp/saida"
conferir "leitor remoto: sem fontes não chama agy" test ! -e "$tmp/falso/agy.args"

delegar revisor "revise"
conferir "caso 11: papel desconhecido dá código 2" [ "$(codigo)" = 2 ]

# ==============================================================================
# Destino local (Ollama)
# ==============================================================================
echo "teste de conteudo" >"$tmp/projeto/doc1.txt"

# 1. Papel não permitido (explorador)
delegar --destino local explorador "mapeie" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 19: destino local recusa papel não permitido (código 4)" [ "$(codigo)" = 4 ]
conferir "caso 19: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]
conferir "caso 19: erro indica papéis leitor e redator" grep -q "só aceita os papéis leitor e redator" "$tmp/erro"
conferir "caso 19: recusa registrada com destino local" \
  jqok -se 'last | .destino == "local" and .papel == "explorador" and .codigo_saida == 4 and .recusa == true' "$reg"

# 2. Sem --arquivos
delegar --destino local leitor "leia"
conferir "caso 20: destino local sem --arquivos dá código 2" [ "$(codigo)" = 2 ]

# 3. Arquivo inexistente
delegar --destino local leitor "leia" --arquivos "$tmp/projeto/inexistente.txt"
conferir "caso 21: arquivo inexistente recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 21: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 4. Ollama fora do ar
OLLAMA_URL="http://127.0.0.1:1" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 22: Ollama fora do ar recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 22: erro indica Ollama fora do ar" grep -q "Ollama fora do ar" "$tmp/erro"
conferir "caso 22: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# Servidor Ollama falso
cat >"$tmp/servidor_ollama.py" <<'EOF'
import http.server, socketserver, json, sys, os

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == '/api/tags':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            modelos = sys.argv[1].split()
            data = {"models": [{"name": m, "model": m} for m in modelos]}
            self.wfile.write(json.dumps(data).encode())
        elif self.path == '/api/ps':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                with open(sys.argv[5], 'r') as pf:
                    data = json.load(pf)
            except Exception:
                data = {"models": []}
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            with open(sys.argv[2], 'a') as f:
                f.write(body.decode('utf-8') + '\n')
            with open(sys.argv[3], 'r') as f:
                conteudo = f.read()
            if os.path.exists(sys.argv[3] + '.sequencia'):
                with open(sys.argv[3] + '.sequencia') as f:
                    partes = json.load(f)
                if partes:
                    conteudo = json.dumps(partes.pop(0))
                    with open(sys.argv[3] + '.sequencia', 'w') as f:
                        json.dump(partes, f)
            eval_in = 120
            if os.path.exists(sys.argv[6]):
                try:
                    payload = json.loads(body.decode('utf-8'))
                    eval_in = payload.get('options', {}).get('num_ctx', 8192)
                except Exception:
                    eval_in = 8192
            resp = {
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": conteudo},
                "prompt_eval_count": eval_in,
                "eval_count": 45,
                "done": True
            }
            if os.path.exists(sys.argv[3] + '.limite'):
                resp['done_reason'] = 'length'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())
        else:
            self.send_response(404)
            self.end_headers()

httpd = socketserver.TCPServer(('127.0.0.1', int(sys.argv[4])), Handler)
httpd.serve_forever()
EOF

porta_ollama="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
ollama_reqs="$tmp/ollama.reqs"
ollama_resp="$tmp/ollama.resp"
ollama_ps="$tmp/ollama.ps"
ollama_estouro="$tmp/ollama.estouro"
printf '%s\n' "doc1.txt:1: trecho relevante extraido do arquivo." >"$ollama_resp"
: >"$ollama_reqs"
printf '{"models": []}\n' >"$ollama_ps"

python3 "$tmp/servidor_ollama.py" "qwen3:4b modelo-simples" "$ollama_reqs" "$ollama_resp" "$porta_ollama" "$ollama_ps" "$ollama_estouro" &
pid_ollama=$!

for _ in {1..20}; do
  if curl -s "http://127.0.0.1:$porta_ollama/api/tags" >/dev/null 2>&1; then break; fi
  sleep 0.1
done

# 5. Modelo ausente
LOCAL_MODELO="modelo_inexistente" OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 23: modelo ausente recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 23: indica modelo não encontrado" grep -q "modelo_inexistente não encontrado" "$tmp/erro"
conferir "caso 23: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 6. Jogo aberto (simulado com marcador no pgrep falso)
FALSO_JOGO_ATIVO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 24: jogo aberto recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 24: indica jogo aberto" grep -q "jogo aberto" "$tmp/erro"
conferir "caso 24: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 7. Memória livre insuficiente (nvidia-smi falso retorna 1000 MiB)
FALSO_VRAM=1000 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 25: memória livre insuficiente recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 25: indica memória livre insuficiente" grep -q "memória de vídeo livre insuficiente" "$tmp/erro"
conferir "caso 25: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 8. Vaga ocupada (flock)
trava_local="$tmp/home/.local/state/jangada/local.lock"
mkdir -p "${trava_local%/*}"
(
  exec {tfd}>"$trava_local"
  flock -x "$tfd"
  sleep 4
) &
pid_trava=$!
sleep 0.2
LOCAL_ESPERA=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
kill "$pid_trava" 2>/dev/null || true
wait "$pid_trava" 2>/dev/null || true
conferir "caso 26: vaga ocupada recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 26: indica vaga ocupada" grep -q "vaga ocupada" "$tmp/erro"
conferir "caso 26: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 9. Sucesso: papel leitor e --arquivos
: >"$ollama_reqs"
printf '%s\n' "doc1.txt:1: informacao encontrada com sucesso." >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia este trecho" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 27: código 0 no destino local" [ "$(codigo)" = 0 ]
conferir "caso 27: imprime o relatório retornado" grep -q "doc1.txt:1:" "$tmp/saida"
conferir "caso 27: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]
conferir "caso 27: leitor envia temperatura zero" jqok -se 'last | .options.temperature == 0' "$ollama_reqs"
conferir "caso 27: pedido termina com a regra de citação e um prefixo real" jqok -se \
  'last | .messages[1].content | test("Regras da resposta: .* como em [^ ]*doc1\\.txt:1\\. .*não está nele\\.$")' "$ollama_reqs"
conferir "caso 27: registro com destino local e tokens Ollama" \
  jqok -se 'last | .destino == "local" and .codigo_saida == 0 and .tokens_local_entrada == 120 and .tokens_local_saida == 45 and .sem_fonte == 0 and .modelo == "qwen3:4b"' "$reg"

# 10. Sucesso: papel redator
printf '%s\n' "doc1.txt:1: remover termo de enchimento." >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local redator "revise este trecho" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 28: redator no destino local código 0" [ "$(codigo)" = 0 ]
conferir "caso 28: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]
conferir "caso 28: redator mantém a temperatura do modelo" \
  jqok -se 'last | .options | has("temperature") | not' "$ollama_reqs"
conferir "caso 28: redator não recebe a regra de citação" \
  jqok -se 'last | .messages[1].content | contains("Regras da resposta") | not' "$ollama_reqs"

# 11. Afirmações sem fonte
printf '%s\n' "Esta frase possui mais de vinte e cinco caracteres mas nao tem fonte." >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 29: conta afirmações sem fonte no destino local" \
  jqok -se 'last | .destino == "local" and .sem_fonte == 1' "$reg"

# 11b. Filtragem de tags think na mesma linha
printf '%s\n' "<think>raciocinio interno</think>doc1.txt:1: trecho util extraido." >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 29b: tags think na mesma linha sao filtradas" [ "$(codigo)" = 0 ]
conferir "caso 29b: mantem o texto util da linha" grep -q "doc1.txt:1: trecho util extraido." "$tmp/saida"
conferir "caso 29b: remove a tag think" [ "$(grep -c "<think>" "$tmp/saida" || true)" -eq 0 ]

# 12. Fatiamento de documento maior que o contexto
doc_grande="$curto/doc_grande.txt"
: >"$doc_grande"
for i in {1..8}; do
  printf 'Linha %02d com texto suficiente para ocupar caracteres e testar o fatiamento de blocos.\n' "$i" >>"$doc_grande"
done
: >"$ollama_reqs"
printf '%s\n' "doc_grande.txt:1: resumo da fatia." >"$ollama_resp"
LOCAL_CTX=2100 LOCAL_FATIAS_MAX=5 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "resuma tudo" --arquivos "$doc_grande"
conferir "caso 30: documento fatiado termina com código 0" [ "$(codigo)" = 0 ]
conferir "caso 30: executou fatias mais passada de consolidação" [ "$(wc -l <"$ollama_reqs")" -ge 3 ]
chamadas_fatiadas="$(wc -l <"$ollama_reqs")"
conferir "caso 30: todas as 8 linhas numeradas aparecem nas fatias" \
  bash -c 'for i in {1..8}; do grep -q "doc_grande\.txt:$i: Linha 0$i" "$1" || exit 1; done' _ "$ollama_reqs"
conferir "caso 30: passada final de consolidação executada" grep -q "Consolide os resumos" <(tail -n1 "$ollama_reqs")
conferir "caso 30: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 13. Documento excede limite de fatias (JANGADA_LOCAL_FATIAS_MAX)
LOCAL_FATIAS_MAX=2 LOCAL_CTX=2100 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "resuma tudo" --arquivos "$doc_grande"
conferir "caso 31: documento excedendo fatias máximas recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 31: erro indica fatias máximas" grep -q "documento muito grande para o modelo local" "$tmp/erro"
conferir "caso 31: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]

# 14. Modelo residente no Ollama (/api/ps) permite chamada mesmo com VRAM livre baixa
printf '{"models": [{"name": "qwen3:4b", "size_vram": 3774873600}]}\n' >"$ollama_ps"
FALSO_VRAM=1000 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia com modelo residente" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 32: modelo residente permite chamada com pouca memória livre" [ "$(codigo)" = 0 ]
conferir "caso 32: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]
printf '{"models": []}\n' >"$ollama_ps"

# 15. Perfil DELEGAR=claude recusa qualquer delegação
DELEGAR=claude OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 33: JANGADA_DELEGAR=claude recusa --destino local" [ "$(codigo)" = 4 ]
conferir "caso 33: erro indica recusa do perfil" grep -q "não delega ao agy nem ao destino local" "$tmp/erro"
conferir "caso 33: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]
DELEGAR=claude delegar --destino agy explorador "explore"
conferir "caso 33b: JANGADA_DELEGAR=claude recusa --destino agy" [ "$(codigo)" = 4 ]
conferir "caso 33b: erro indica recusa do perfil" grep -q "não delega ao agy nem ao destino local" "$tmp/erro"

# 16. DELEGAR=local sem flag --destino resolve para local
DELEGAR=local OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "leia sem destino explicito" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 34: JANGADA_DELEGAR=local sem --destino chama local" [ "$(codigo)" = 0 ]
conferir "caso 34: gravou destino local no registro" jqok -se 'last | .destino == "local"' "$reg"

# 17. jangada_delegacao aceita local
conferir "caso 35: jangada_delegacao aceita local para claude" [ "$(jangada_delegacao claude local)" = "local" ]
conferir "caso 35: jangada_delegacao mantém nativo para agy" [ "$(jangada_delegacao agy local)" = "nativo" ]

# 18. Destino inválido
delegar --destino inexistente leitor "leia"
conferir "caso 36: --destino inválido dá código 2" [ "$(codigo)" = 2 ]
conferir "caso 36: erro indica destino inválido" grep -q "destino inválido" "$tmp/erro"

# 19. Linha única gigante é fatiada
doc_linha_gigante="$tmp/projeto/doc_linha_gigante.txt"
python3 -c 'print("a" * 1500)' >"$doc_linha_gigante"
LOCAL_CTX=2100 LOCAL_FATIAS_MAX=10 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia gigante" --arquivos "$doc_linha_gigante"
conferir "caso 37: linha única gigante é fatiada com sucesso" [ "$(codigo)" = 0 ]
conferir "caso 37: pedaços seguintes da linha gigante mantêm prefixo" grep -q "doc_linha_gigante.txt:1: a" "$ollama_reqs"

# 19a. Faixa de linhas em --arquivos preserva a numeração do arquivo
: >"$ollama_reqs"
printf '%s\n' "doc_grande.txt:3: trecho da faixa." >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia a faixa" \
  --arquivos "$doc_grande:3-4" "$doc_grande:7-7"
conferir "caso 48: faixa de linhas termina com código 0" [ "$(codigo)" = 0 ]
conferir "caso 48: envia as linhas pedidas com o número original" \
  bash -c 'for i in 3 4 7; do grep -q "doc_grande\.txt:$i: Linha 0$i" "$1" || exit 1; done' _ "$ollama_reqs"
conferir "caso 48: não envia linhas fora das faixas" \
  bash -c 'for i in 1 2 5 6 8; do ! grep -q "doc_grande\.txt:$i: Linha 0$i" "$1" || exit 1; done' _ "$ollama_reqs"

: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia a faixa" --arquivos "$doc_grande:7-9"
conferir "caso 49: faixa além do fim do arquivo recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 49: erro indica a faixa e o total de linhas" grep -q "faixa fora do arquivo: .*:7-9 (8 linhas)" "$tmp/erro"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia a faixa" --arquivos "$doc_grande:5-2"
conferir "caso 49: faixa invertida recusa com código 4" [ "$(codigo)" = 4 ]
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia a faixa" --arquivos "$tmp/projeto/inexistente.txt:1-2"
conferir "caso 49: faixa de arquivo inexistente recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 49: nenhuma faixa inválida chega ao Ollama" [ ! -s "$ollama_reqs" ]

doc_dois_pontos="$tmp/projeto/nota:1-2"
printf 'primeira\nsegunda\nterceira\n' >"$doc_dois_pontos"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia tudo" --arquivos "$doc_dois_pontos"
conferir "caso 50: arquivo existente terminado em :1-2 é lido inteiro" \
  bash -c '[ "$1" = 0 ] && grep -q "nota:1-2:3: terceira" "$2"' _ "$(codigo)" "$ollama_reqs"

# 19b. Caminho longo com prefixo grande e contexto pequeno
pasta_longa="$tmp/projeto/caminho_$(printf 'longo_%.0s' {1..12})"
mkdir -p "$pasta_longa"
doc_longo="$pasta_longa/doc.txt"
python3 -c 'print("b" * 600)' >"$doc_longo"
LOCAL_CTX=2060 LOCAL_FATIAS_MAX=10 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia caminho longo" --arquivos "$doc_longo"
conferir "caso 37b: caminho longo com prefixo grande não entra em laço infinito" [ "$(codigo)" = 0 ]

# 20. Truncamento de contexto detectado
touch "$ollama_estouro"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia estouro" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 38: truncamento de contexto recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 38: erro indica contexto estourado" grep -q "contexto do modelo local estourado" "$tmp/erro"
conferir "caso 38: agy não é chamado" [ ! -e "$tmp/falso/agy.args" ]
rm -f "$ollama_estouro"

# 21. PDF extraído com pdftotext e numeração de páginas
cat >"$tmp/bin/pdftotext" <<'EOF'
#!/bin/sh
printf 'Texto de pagina um\n\fTexto de pagina dois\n'
EOF
chmod +x "$tmp/bin/pdftotext"
touch "$tmp/projeto/documento.pdf"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia o pdf" --arquivos "$tmp/projeto/documento.pdf"
conferir "caso 39: PDF extraído com pdftotext tem código 0" [ "$(codigo)" = 0 ]
conferir "caso 39: texto enviado traz numeracao de paginas" grep -q "p\. 1:" "$ollama_reqs"

# 21a. Faixa de linhas não vale para PDF, por extensão ou por tipo MIME
printf 'um\ndois\ntres\n' >"$tmp/projeto/faixa.pdf"
printf '%%PDF-1.4\num\ndois\n' >"$tmp/projeto/faixa_mime"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia o pdf" --arquivos "$tmp/projeto/faixa.pdf:1-2"
conferir "caso 51: faixa em PDF pela extensão recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 51: erro indica que a faixa não vale para PDF" grep -q "faixa de linhas não vale para PDF: .*faixa\.pdf" "$tmp/erro"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia o pdf" --arquivos "$tmp/projeto/faixa_mime:1-2"
conferir "caso 51: faixa em PDF pelo tipo MIME recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 51: erro indica o PDF sem extensão" grep -q "faixa de linhas não vale para PDF: .*faixa_mime" "$tmp/erro"
conferir "caso 51: nenhuma faixa de PDF chega ao Ollama" [ ! -s "$ollama_reqs" ]

# 22. Perfil nativo recusa mesmo com --destino explícito
DELEGAR=nativo delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 40: DELEGAR=nativo recusa --destino local" [ "$(codigo)" = 4 ]
conferir "caso 40: erro indica invoke_subagent" grep -q "use invoke_subagent" "$tmp/erro"

# 23. Perfil local recusa --destino agy
DELEGAR=local delegar --destino agy leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 41: DELEGAR=local recusa --destino agy" [ "$(codigo)" = 4 ]
conferir "caso 41: erro indica restricao ao destino local" grep -q "restringe a delegação ao destino local" "$tmp/erro"

# 24. Argumentos posicionais após --
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor --arquivos "$tmp/projeto/doc1.txt" -- "pedido posicional apos tracos"
conferir "caso 42: argumentos posicionais apos -- tratados corretamente" [ "$(codigo)" = 0 ]
conferir "caso 42: pedido apos -- enviado ao modelo" grep -q "pedido posicional apos tracos" "$ollama_reqs"
delegar --permitir-remoto -- explorador "pedido apos tracos agy"
conferir "caso 42b: papel e pedido apos -- com agy" [ "$(codigo)" = 0 ]

# 24b. Os dois perfis padrão (JANGADA_DELEGAR=agy): leitor e redator vão ao
# Ollama com --destino local; falha local fica local, sem agy nem envio remoto.
for papel_perfil in leitor redator; do
  : >"$ollama_reqs"
  DELEGAR=agy OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local "$papel_perfil" "pedido" --arquivos "$tmp/projeto/doc1.txt"
  conferir "perfis: $papel_perfil local sob JANGADA_DELEGAR=agy chega ao Ollama" \
    bash -c '[ "$1" = 0 ] && [ -s "$2" ] && [ ! -e "$3" ]' _ "$(codigo)" "$ollama_reqs" "$tmp/falso/agy.args"
done
for falha_local in modelo fora; do
  : >"$ollama_reqs"
  : >"$reg"
  if [[ "$falha_local" == modelo ]]; then
    DELEGAR=agy LOCAL_MODELO=modelo_inexistente OLLAMA_URL="http://127.0.0.1:$porta_ollama" \
      delegar --destino local leitor "pedido" --arquivos "$tmp/projeto/doc1.txt"
  else
    DELEGAR=agy OLLAMA_URL="http://127.0.0.1:1" delegar --destino local leitor "pedido" --arquivos "$tmp/projeto/doc1.txt"
  fi
  conferir "perfis: falha local ($falha_local) recusa com código 4 sem chamar o agy" \
    bash -c '[ "$1" = 4 ] && [ ! -e "$2" ]' _ "$(codigo)" "$tmp/falso/agy.args"
  conferir "perfis: falha local ($falha_local) fica registrada no destino local, sem tentativa remota" \
    jqok -se 'length == 1 and .[0].destino == "local" and .[0].codigo_saida == 4 and .[0].recusa == true' "$reg"
done
for papel_remoto in explorador pesquisador verificador auditor arquiteto designer otimizador supervisor; do
  : >"$ollama_reqs"
  DELEGAR=agy OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local "$papel_remoto" "pedido" --arquivos "$tmp/projeto/doc1.txt"
  conferir "perfis: $papel_remoto não vai ao destino local" \
    bash -c '[ "$1" = 4 ] && [ ! -s "$2" ] && [ ! -e "$3" ]' _ "$(codigo)" "$ollama_reqs" "$tmp/falso/agy.args"
done
: >"$ollama_reqs"
DELEGAR=agy OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "pedido" --arquivos "$tmp/projeto/doc1.txt"
conferir "perfis: sem --destino nem autorização, nem agy nem Ollama recebem a fonte" \
  bash -c '[ "$1" = 4 ] && [ ! -s "$2" ] && [ ! -e "$3" ]' _ "$(codigo)" "$ollama_reqs" "$tmp/falso/agy.args"
DELEGAR=agy delegar --destino agy explorador "mapeie" --arquivos "$tmp/projeto/doc1.txt"
conferir "perfis: agy explícito sem --permitir-remoto recusa antes de enviar" \
  bash -c '[ "$1" = 4 ] && [ ! -e "$2" ]' _ "$(codigo)" "$tmp/falso/agy.args"
DELEGAR=agy delegar --destino agy --permitir-remoto explorador "mapeie" --arquivos "$tmp/projeto/doc1.txt"
conferir "perfis: agy explícito com autorização das fontes atende" \
  bash -c '[ "$1" = 0 ] && [ -e "$2" ]' _ "$(codigo)" "$tmp/falso/agy.args"
DELEGAR=agy delegar --destino agy --permitir-remoto designer "avalie interface" --arquivos "$tmp/projeto/doc1.txt"
conferir "designer: agy explícito com autorização atende" \
  bash -c '[ "$1" = 0 ] && grep -qx -- designer "$2"' _ "$(codigo)" "$tmp/falso/agy.args"

# 25. Marca de jogo ativo no estado
mkdir -p "$tmp/home/.local/state/jangada/marcas"
# 25a. Fora do isolamento a marca é ignorada
printf '%s\n' "$(date +%s)" >"$tmp/home/.local/state/jangada/marcas/jogo-ativo"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 43a: marca jogo-ativo fora do isolamento é ignorada" [ "$(codigo)" = 0 ]

# 25b. Na sessão isolada com marca recente recusa com código 4
ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 43b: marca jogo-ativo recente no isolamento recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 43b: erro indica jogo aberto" grep -q "jogo aberto detectado" "$tmp/erro"

# 25c. Na sessão isolada com marca expirada (>120s) a marca é ignorada
printf '%s\n' "$(( $(date +%s) - 300 ))" >"$tmp/home/.local/state/jangada/marcas/jogo-ativo"
ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 43c: marca jogo-ativo expirada no isolamento é ignorada" [ "$(codigo)" = 0 ]

# 25d. Na sessão isolada com marca malformada recusa por segurança (código 4)
printf 'invalido\n' >"$tmp/home/.local/state/jangada/marcas/jogo-ativo"
ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 43d: marca jogo-ativo malformada no isolamento recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 43d: erro indica jogo aberto" grep -q "jogo aberto detectado" "$tmp/erro"
rm -f "$tmp/home/.local/state/jangada/marcas/jogo-ativo"

# 26. Marca de VRAM livre gravada pelo host no estado
# 26a. Na sessão isolada com marca recente permite chamada sem nvidia-smi
printf '6000 %s\n' "$(date +%s)" >"$tmp/home/.local/state/jangada/marcas/vram-livre"
SEM_VRAM=1 ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 44a: marca vram-livre recente permite medicao no isolamento" [ "$(codigo)" = 0 ]

SEM_VRAM=2 ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 44a2: erro do nvidia-smi na saída padrão usa marca recente" [ "$(codigo)" = 0 ]
printf '1000 %s\n' "$(date +%s)" >"$tmp/home/.local/state/jangada/marcas/vram-livre"
SEM_VRAM=2 ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 44a3: erro do nvidia-smi não ignora limite de memória" [ "$(codigo)" = 4 ]
conferir "caso 44a3: informa memória insuficiente medida pelo host" grep -q 'memória de vídeo livre insuficiente: 1000 MiB' "$tmp/erro"

# 26b. Na sessão isolada com marca expirada (>120s) recusa
printf '6000 %s\n' "$(( $(date +%s) - 300 ))" >"$tmp/home/.local/state/jangada/marcas/vram-livre"
SEM_VRAM=2 ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 44b: marca vram-livre expirada no isolamento recusa com código 4" [ "$(codigo)" = 4 ]
conferir "caso 44b: erro indica vram nao verificada" grep -q "não pôde ser verificada na sessão isolada" "$tmp/erro"

# 26c. Na sessão isolada com marca malformada recusa com código 4
printf '6000 invalido\n' >"$tmp/home/.local/state/jangada/marcas/vram-livre"
SEM_VRAM=1 ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 44c: marca vram-livre com timestamp invalido recusa" [ "$(codigo)" = 4 ]
rm -f "$tmp/home/.local/state/jangada/marcas/vram-livre"

# 27. Sessão isolada sem medição de VRAM e sem modelo residente recusa
SEM_VRAM=1 ISOLADO=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 45: sessao isolada sem medicao de vram recusa" [ "$(codigo)" = 4 ]
conferir "caso 45: erro indica vram nao verificada" grep -q "não pôde ser verificada na sessão isolada" "$tmp/erro"

# 28. JANGADA_LOCAL_IGNORAR_VRAM=1 ignora checagem na sessão isolada
SEM_VRAM=1 ISOLADO=1 LOCAL_IGNORAR_VRAM=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar --destino local leitor "leia" --arquivos "$tmp/projeto/doc1.txt"
conferir "caso 46: JANGADA_LOCAL_IGNORAR_VRAM=1 libera chamada" [ "$(codigo)" = 0 ]

# 29. Protocolo de delegação local presente e referenciado
conferir "caso 47: arquivo protocolo-delegar-local.md existe e legivel" test -r "$repo_jangada/agentes/perfis/protocolo-delegar-local.md"
conferir "caso 47: protocolo contém instrução de delegação local" grep -q "delegação local" "$repo_jangada/agentes/perfis/protocolo-delegar-local.md"

# Cotas antigas ou inválidas nunca autorizam uma chamada.
cache_cota="$tmp/home/.cache/jangada/agy-usage.json"
delegar --permitir-remoto explorador "leia"
touch -d '10 minutes ago' "$cache_cota"
USAGE_FALHA=1 delegar --permitir-remoto explorador "leia" --json
conferir "cota expirada: falha de atualização recusa antes do pedido" test ! -e "$tmp/falso/agy.args"
conferir "cota expirada: motivo estruturado" jqok -e '.motivo_codigo == "cota_desconhecida"' "$tmp/saida"
rm -f "$cache_cota"
COTA='"invalida"' delegar --permitir-remoto explorador "leia" --json
conferir "cota textual: recusa estruturada" jqok -e '.motivo_codigo == "cota_desconhecida"' "$tmp/saida"
COTA=1.5 delegar --permitir-remoto explorador "leia" --json
conferir "cota fora da faixa: recusa" [ "$(codigo)" = 4 ]
COTA=0 delegar --permitir-remoto explorador "leia" --json
conferir "cota zero: insuficiente" jqok -e '.motivo_codigo == "cota_insuficiente"' "$tmp/saida"
rm -f "$cache_cota"
AGENTE=codex DELEGAR=local delegar --destino agy leitor "leia"
conferir "recusa no Codex: orienta continuar na sessão" grep -q "nesta sessão do Codex" "$tmp/saida"
conferir "recusa no Codex: não recomenda Claude" bash -c '! grep -q Claude "$1"' _ "$tmp/saida"

# A lista de compatibilidade precisa de estado privado distinto por tentativa.
rm -f "$cache_cota"
ISOLADO=1 COTA=0.9 SEMANAL=0.9 TERCEIROS=0.8 ESGOTADO=gemini-3.8-flash-high RESPOSTA='doc1.txt:1 trecho' \
  delegar leitor "leia" --destino agy --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "compatibilidade: cota esgotada usa outra cópia privada" jqok -e \
  '.codigo_saida == 0 and .modelo == "claude-sonnet-5-5-high" and (.cotas_modelos | length) == 2' "$tmp/saida"
rm -f "$cache_cota"

# Política nova, sem configuração pessoal: nenhuma chamada local automática.
: >"$ollama_reqs"
for autor in claude codex; do
  for papel_padrao in leitor redator; do
    AGENTE="$autor" RESPOSTA='Relatório em doc1.txt:1' delegar --permitir-remoto "$papel_padrao" "leia ou revise" \
      --json --arquivos "$tmp/projeto/doc1.txt"
    conferir "padrão $autor/$papel_padrao: agy sem perfil" jqok -e \
      '.destino == "agy" and .codigo_saida == 0' "$tmp/saida"
    conferir "padrão $autor/$papel_padrao: fonte entregue" grep -qx "$tmp/projeto/doc1.txt" "$tmp/falso/agy.args"
  done
  AGENTE="$autor" delegar leitor "leia" --json --arquivos "$tmp/projeto/doc1.txt"
  conferir "padrão $autor: falta de autorização bloqueia" jqok -e \
    '.motivo_codigo == "destino_proibido" and .chamadas_executor == 0' "$tmp/saida"
  conferir "padrão $autor: sem autorização não chama agy" test ! -e "$tmp/falso/agy.args"
done
for capacidade_padrao in leitura_documental resumo_curto analise_documental; do
  RESPOSTA='Relatório em doc1.txt:1' delegar leitor "compare" --capacidade "$capacidade_padrao" \
    --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
  conferir "padrão $capacidade_padrao: somente agy" jqok -e \
    '.destino == "agy" and .codigo_saida == 0 and (.tentativas | length) == 1' "$tmp/saida"
  delegar leitor "compare" --capacidade "$capacidade_padrao" --json --arquivos "$tmp/projeto/doc1.txt"
  conferir "padrão $capacidade_padrao: sem autorização bloqueia" jqok -e \
    '.motivo_codigo == "sem_executor" and .tentativas[0].motivo_codigo == "destino_proibido"' "$tmp/saida"
  rm -f "$cache_cota"
  COTA=0.1 delegar leitor "compare" --capacidade "$capacidade_padrao" --permitir-remoto --json \
    --arquivos "$tmp/projeto/doc1.txt"
  conferir "padrão $capacidade_padrao: cota baixa sem alternativa local" jqok -e \
    '.motivo_codigo == "sem_executor" and (.tentativas | length) == 1
      and .tentativas[0].destino == "agy" and .tentativas[0].motivo_codigo == "cota_insuficiente"' "$tmp/saida"
  rm -f "$cache_cota"
done
USAGE_FALHA=1 delegar leitor "compare" --capacidade resumo_curto --permitir-remoto --json \
  --arquivos "$tmp/projeto/doc1.txt"
conferir "padrão: cota desconhecida sem alternativa local" jqok -e \
  '.motivo_codigo == "sem_executor" and .tentativas[0].motivo_codigo == "cota_desconhecida"
    and (.tentativas | length) == 1' "$tmp/saida"
cp "$conf_agy" "$tmp/confianca-copia.json"
printf '{"trustedWorkspaces":[]}\n' >"$conf_agy"
delegar leitor "compare" --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "padrão: falta de confiança não chama agy" test ! -e "$tmp/falso/agy.args"
conferir "padrão: confiança bloqueada e rastreável" jqok -e \
  '.tentativas[0].motivo_codigo == "destino_proibido" and .chamadas_executor == 0' "$tmp/saida"
mv "$tmp/confianca-copia.json" "$conf_agy"
conferir "padrão: Ollama não recebeu nenhuma chamada" test ! -s "$ollama_reqs"

# Compatibilidade: somente uma política pessoal explícita habilita a ordem antiga.
mkdir -p "$tmp/home/.config/jangada"
politica_local() {
  printf '{"leitura_documental":["local","agy"],"resumo_curto":["local","agy"],"analise_documental":["agy","local"]}\n' \
    >"$tmp/home/.config/jangada/delegacao.json"
}
politica_local
# Roteamento documental usa os mesmos executores falsos dos casos anteriores.
printf 'Relatório em doc1.txt:1\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade resumo_curto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: seleciona local e valida referência" jqok -e \
  '.destino == "local" and .capacidade == "resumo_curto" and .verificacao == "referencias_validas"
    and .decisao == "ordem_configurada_por_capacidade" and .chamadas_executor == 1' "$tmp/saida"
conferir "capacidade: mantém medidas por chamada local" jqok -e '.chamadas_local | length == 1' "$tmp/saida"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade leitura_documental --conta principal --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "conta por capacidade: candidato local antes do agy pode concluir" jqok -e \
  '.destino == "local" and .codigo_saida == 0 and .tentativas[0].destino == "local"' "$tmp/saida"
DELEGAR=local OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade leitura_documental --conta principal --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "conta por capacidade: destino padrão local não rejeita a conta do candidato agy" jqok -e \
  '.destino == "local" and .codigo_saida == 0' "$tmp/saida"
RESPOSTA='Relatório em doc1.txt:1' delegar leitor "compare" --capacidade analise_documental \
  --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: agy normal" jqok -e '.destino == "agy" and .verificacao == "referencias_validas"' "$tmp/saida"
conferir "capacidade: agy recebe fonte explícita" grep -qx "$tmp/projeto/doc1.txt" "$tmp/falso/agy.args"

rm -f "$cache_cota"
COTA=0.1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "compare" \
  --capacidade analise_documental --conta principal --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: cota baixa troca agy por local" jqok -e \
  '.destino == "local" and (.tentativas | length) == 2
    and .tentativas[0].motivo_codigo == "cota_insuficiente"' "$tmp/saida"
conferir "capacidade: tentativas compartilham identificação" jqok -se \
  '.[-1].roteamento_id == .[-2].roteamento_id' "$reg"
rm -f "$cache_cota"
USAGE_FALHA=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "compare" \
  --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: cota desconhecida tenta local" jqok -e \
  '.destino == "local" and .tentativas[0].motivo_codigo == "cota_desconhecida"' "$tmp/saida"

OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "compare" \
  --capacidade analise_documental --json --arquivos "$tmp/projeto/doc1.txt"
conferir "privacidade: sem autorização remota descarta agy" jqok -e \
  '.destino == "local" and .tentativas[0].motivo_codigo == "destino_proibido"' "$tmp/saida"
conferir "privacidade: agy não recebe pedido" test ! -e "$tmp/falso/agy.args"
DELEGAR=local OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "compare" \
  --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "perfil local: autorização da tarefa não amplia perfil" test ! -e "$tmp/falso/agy.args"

printf 'Relatório sem referência\n' >"$ollama_resp"
RESPOSTA='Relatório em doc1.txt:1' OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "qualidade: saída inválida tenta outro executor" jqok -e \
  '.destino == "agy" and .tentativas[0].motivo_codigo == "saida_invalida"' "$tmp/saida"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade resumo_curto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "privacidade: falha local não autoriza nuvem" test ! -e "$tmp/falso/agy.args"
conferir "sem executor: recusa explicável" jqok -e \
  '.motivo_codigo == "sem_executor" and .tentativas[0].motivo_codigo == "saida_invalida"' "$tmp/saida"
printf 'Relatório em doc1.txt:99\n' >"$ollama_resp"
printf 'original\n' >"$tmp/preservar.md"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" --destino local \
  --capacidade resumo_curto --json --arquivo "$tmp/preservar.md" --arquivos "$tmp/projeto/doc1.txt"
conferir "qualidade: linha inexistente reprova" [ "$(codigo)" = 4 ]
conferir "qualidade: saída reprovada preserva arquivo" grep -qx original "$tmp/preservar.md"
conferir "destino explícito: não troca executor" jqok -e \
  '.tentativas | map(select(.destino == "agy")) | length == 0' "$tmp/saida"

RESPOSTA='Relatório em doc1.txt:1' CHAMADAS_MAX=1 OLLAMA_URL="http://127.0.0.1:$porta_ollama" \
  delegar leitor "resuma" --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "limite: não chama segundo executor" test ! -e "$tmp/falso/agy.args"
conferir "limite: registra esgotamento" jqok -e '.motivo_codigo == "limite_chamadas"' "$tmp/saida"
TEMPO_TOTAL=3 ESPERA_AGY=5 RESPOSTA='Relatório em doc1.txt:1' delegar leitor "compare" \
  --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "tempo total: executor começou antes do prazo" test -f "$tmp/falso/agy.args"
conferir "tempo total: interrompe executor" jqok -e \
  '.motivo_codigo == "limite_tempo" and .chamadas_executor == null' "$tmp/saida"
ISOLADO=1 TEMPO_TOTAL=3 ESPERA_AGY=5 RESPOSTA='Relatório em doc1.txt:1' delegar leitor "compare" \
  --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "tempo total privado: marcador do modelo pertence à chamada interrompida" test -f "$tmp/falso/agy.args"
conferir "tempo total privado: a interrupção continua explícita" jqok -e \
  '.motivo_codigo == "limite_tempo" and .chamadas_executor == null' "$tmp/saida"

mkdir -p "$tmp/home/.config/jangada"
printf '{"resumo_curto":["agy","local"]}\n' >"$tmp/home/.config/jangada/delegacao.json"
RESPOSTA='Relatório em doc1.txt:1' delegar leitor "resuma" --capacidade resumo_curto \
  --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "política: ordem do usuário prevalece" jqok -e '.destino == "agy"' "$tmp/saida"
printf '{"resumo_curto":["claude"]}\n' >"$tmp/home/.config/jangada/delegacao.json"
delegar leitor "resuma" --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "política: rejeita executor não integrado" jqok -e '.motivo_codigo == "politica_invalida"' "$tmp/saida"
conferir "política: não executa agy" test ! -e "$tmp/falso/agy.args"
rm -f "$tmp/home/.config/jangada/delegacao.json"
politica_local

# Negação de ferramenta e restrição de perfil não são falhas recuperáveis.
NEGADO=ReadUrlContent RESPOSTA='Relatório em doc1.txt:1' OLLAMA_URL="http://127.0.0.1:$porta_ollama" \
  delegar leitor "compare" --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "permissão: negação não dispara troca" jqok -e \
  '.tentativas[0].motivo_codigo == "destino_proibido"
    and (.tentativas | map(select(.destino == "local")) | length == 0)' "$tmp/saida"
DELEGAR=claude delegar leitor "resuma" --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "perfil Claude: não delega a outro executor" test ! -e "$tmp/falso/agy.args"
delegar explorador "resuma" --capacidade resumo_curto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: papel incompatível recusa" jqok -e '.motivo_codigo == "capacidade_incompativel"' "$tmp/saida"
delegar redator "resuma" --capacidade resumo_curto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: redator não substitui leitor" jqok -e '.motivo_codigo == "capacidade_incompativel"' "$tmp/saida"
delegar leitor "resuma" --capacidade inexistente --arquivos "$tmp/projeto/doc1.txt"
conferir "capacidade: desconhecida é erro de uso" [ "$(codigo)" = 2 ]

printf 'Relatório em doc1.txt:1\n' >"$ollama_resp"
printf 'outra fonte\n' >"$tmp/projeto/doc2.txt"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" --destino local --capacidade resumo_curto \
  --json --arquivos "$tmp/projeto/doc1.txt" "$tmp/projeto/doc2.txt"
conferir "qualidade: fonte omitida reprova" [ "$(codigo)" = 4 ]
OLLAMA_URL="http://127.0.0.1:1" delegar leitor "resuma" --capacidade resumo_curto \
  --json --arquivos "$tmp/projeto/doc1.txt"
conferir "sem executor: indisponibilidade registrada" jqok -e \
  '.motivo_codigo == "sem_executor" and .tentativas[0].motivo_codigo == "indisponivel"' "$tmp/saida"

CHAMADAS_MAX=1 LOCAL_CTX=2100 LOCAL_FATIAS_MAX=5 OLLAMA_URL="http://127.0.0.1:$porta_ollama" \
  delegar leitor "resuma" --destino local --capacidade resumo_curto --json --arquivos "$doc_grande"
conferir "limite: reserva consolidação antes de consumir chamadas" jqok -e \
  '.tentativas[0].motivo_codigo == "limite_chamadas" and .tentativas[0].chamadas == 0' "$tmp/saida"

printf '## Destino\nUse o modelo local para ler os documentos. doc1.txt:1\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia a regra" \
  --capacidade leitura_documental --requisito Destino --json --arquivos "$tmp/projeto/doc1.txt"
conferir "completude: explica requisito com referência" jqok -e \
  '.verificacao == "referencias_e_requisitos_validos" and .codigo_saida == 0
    and .requisitos == ["Destino"]' "$tmp/saida"
conferir "geração: desativa raciocínio e limita saída" jqok -se \
  'last | .think == false and .options.num_predict == 1024
    and (.messages[1].content | endswith("/no_think"))' "$ollama_reqs"
printf '{"destino":{"valor":"local","referencia":"doc1.txt:1"}}\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia o destino" --destino local \
  --capacidade leitura_documental --extrair destino:texto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: confere estrutura e referência" jqok -e \
  '.verificacao == "estrutura_e_referencias_validas" and (.relatorio | fromjson | .destino.valor == "local")' "$tmp/saida"
conferir "extração: formato obrigatório enviado ao Ollama" jqok -se \
  'last | .format.required == ["destino"] and .format.additionalProperties == false
    and .format.properties.destino.properties.valor.type == ["string","null"]' "$ollama_reqs"

fonte_citacao="$pasta_longa/README.md"
printf 'Contexto.\n\n\n\nMarcador reservado.\n\nItens 37.\n' >"$fonte_citacao"
printf '{"marcador":{"valor":"reservado","referencia":"README.md:5"},"itens":{"valor":37,"referencia":"README.md:7"}}\n' >"$ollama_resp"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia marcador e itens" --destino local \
  --capacidade leitura_documental --extrair marcador:texto --extrair itens:inteiro --json --arquivos "$fonte_citacao"
conferir "citação: resposta curta é aceita e canonizada sem alterar valores" jqok -e --arg fonte "$fonte_citacao" \
  '.codigo_saida == 0 and (.relatorio | fromjson |
    .marcador == {valor:"reservado",referencia:($fonte + ":5")} and .itens == {valor:37,referencia:($fonte + ":7")})' "$tmp/saida"
conferir "citação: exemplos efetivos são dados válidos da fatia, sem gabarito" exemplos_validos
conferir "citação: prefere nome curto e orienta preservar barra inicial" jqok -se \
  'last | (.messages[0].content | contains("barra inicial")) and
    (.messages[1].content | split("Exemplos de referência deste trecho (dados):\n")[1] |
      split("\n/no_think")[0] | fromjson | map(.referencia) == ["README.md:1"])' "$ollama_reqs"

referencia_sem_barra="${fonte_citacao#/}:5"
jq -nc --arg ref "$referencia_sem_barra" '{marcador:{valor:"reservado",referencia:$ref}}' >"$ollama_resp"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia marcador" --destino local \
  --capacidade leitura_documental --extrair marcador:texto --json --arquivos "$fonte_citacao"
conferir "citação: retirar barra inicial mantém código 4" [ "$(codigo)" = 4 ]
conferir "citação: diagnóstico existente identifica o caminho recebido sem barra" \
  grep -Fq "referência \"${referencia_sem_barra:0:12}…${referencia_sem_barra: -20}\" (fora do trecho)" "$tmp/erro"
conferir "citação: falha não repete geração nem tenta outro destino" jqok -e \
  '(.tentativas | length) == 1 and .tentativas[0].chamadas == 1 and .tentativas[0].motivo_codigo == "saida_invalida"
    and .tentativas[0].destino == "local"' "$tmp/saida"
conferir "citação: servidor falso recebeu uma única geração" jqok -se 'length == 1' "$ollama_reqs"

mkdir -p "$tmp/projeto/outra"
printf 'Outro contexto.\n' >"$tmp/projeto/outra/README.md"
jq -nc --arg ref "$fonte_citacao:5" '{marcador:{valor:"reservado",referencia:$ref}}' >"$ollama_resp"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia marcador" --destino local \
  --capacidade leitura_documental --extrair marcador:texto --json \
  --arquivos "$fonte_citacao" "$tmp/projeto/outra/README.md"
conferir "citação: caminho absoluto correto continua aceito com homônimos" [ "$(codigo)" = 0 ]
conferir "citação: exemplos de homônimos são válidos" exemplos_validos
conferir "citação: homônimos recebem somente caminhos exatos" jqok -se \
  'last | .messages[1].content | split("Exemplos de referência deste trecho (dados):\n")[1] |
    split("\n/no_think")[0] | fromjson | length == 2 and all(.[]; .referencia == .rotulo and (.referencia | startswith("/")))' "$ollama_reqs"

printf '{"pagina":{"valor":"teste","referencia":"documento.pdf, p. 2"}}\n' >"$ollama_resp"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia pagina" --destino local \
  --capacidade leitura_documental --extrair pagina:texto --json --arquivos "$tmp/projeto/documento.pdf"
conferir "citação PDF: referência de página aceita e canonizada" jqok -e --arg ref "$tmp/projeto/documento.pdf, p. 2" \
  '.codigo_saida == 0 and (.relatorio | fromjson | .pagina.referencia == $ref)' "$tmp/saida"
conferir "citação PDF: exemplos usam página real da fatia" exemplos_validos
conferir "citação PDF: exemplo curto sem número interno de linha" jqok -se \
  'last | .messages[1].content | split("Exemplos de referência deste trecho (dados):\n")[1] |
    split("\n/no_think")[0] | fromjson | map(.referencia) == ["documento.pdf, p. 1"]' "$ollama_reqs"

python_real="$(command -v python3)"
cat >"$tmp/bin/python3" <<EOF
#!/bin/sh
if [ "\${2:-}" = exemplos ]; then
  echo 'falha simulada na preparação dos exemplos' >&2
  exit 1
fi
exec "$python_real" "\$@"
EOF
chmod +x "$tmp/bin/python3"
: >"$ollama_reqs"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia o destino" --destino local \
  --capacidade leitura_documental --extrair destino:texto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "exemplos: falha de preparação recusa com código 4" [ "$(codigo)" = 4 ]
conferir "exemplos: falha de preparação devolve tentativa estruturada sem geração" jqok -e \
  '(.tentativas | length) == 1 and .tentativas[0].destino == "local"
    and .tentativas[0].motivo_codigo == "saida_invalida" and .tentativas[0].chamadas == 0' "$tmp/saida"
conferir "exemplos: recusa é registrada sem contar chamada ao Ollama" jqok -se \
  'map(select(.destino == "local")) | last | .codigo_saida == 4 and .motivo_codigo == "saida_invalida"
    and .chamadas_executor == 0 and (.chamadas_local | length) == 0' "$reg"
conferir "exemplos: falha não transporta pedido ao servidor falso" test ! -s "$ollama_reqs"
conferir "exemplos: erro explica a falha de preparação" grep -Fq 'não foi possível preparar os exemplos de referência' "$tmp/erro"
rm "$tmp/bin/python3"

printf '{"destino":{"valor":"local","referencia":"doc1.txt:99"}}\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia o destino" --destino local \
  --capacidade leitura_documental --extrair destino:texto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: referência inexistente recusa" jqok -e \
  '.tentativas[0].motivo_codigo == "saida_invalida"' "$tmp/saida"
conferir "extração: referência inválida mantém código 4" [ "$(codigo)" = 4 ]
conferir "extração: stderr identifica referência fora do trecho" grep -Fq 'referência "doc1.txt:99" (fora do trecho)' "$tmp/erro"
python3 - "$repo_jangada/delegacao/extracao.py" "$tmp/projeto/doc1.txt" <<'PY'
import json, pathlib, subprocess, sys
modulo, fonte = sys.argv[1:]
absoluto = str(pathlib.Path(fonte).resolve())
def conferir(referencia, documento):
    resposta = json.dumps({'destino': {'valor': 'local', 'referencia': referencia}})
    dados = json.dumps({'resposta': resposta, 'fonte': documento})
    return subprocess.run([sys.executable, modulo, 'conferir', 'destino:texto'], input=dados, text=True, capture_output=True)
assert conferir('doc1.txt:1', 'doc1.txt:1: fonte\n').returncode == 0
assert conferir(f'{absoluto}:1', f'{absoluto}:1: fonte\n').returncode == 0
for referencia, estado, documento in [
    ('doc1.txt:999', 'fora do trecho', 'doc1.txt:1: fonte\n'),
    ('doc1.txt:1:', 'fora do trecho', 'doc1.txt:1: fonte\n'),
    ('doc1.txt:2', 'ambígua', 'a/doc1.txt:2: A\nb/doc1.txt:2: B\n'),
    (None, 'ausente', 'doc1.txt:1: fonte\n'),
]:
    resultado = conferir(referencia, documento)
    assert resultado.returncode != 0 and f'({estado})' in resultado.stderr
for hostil, visivel, oculto in [
    (['segredo', {'x': 'conteúdo'}], 'list, 2 itens', 'segredo'),
    ('\x1b[31m' + 'x' * 20000 + 'arquivo.txt:98765', 'arquivo.txt:98765', '\x1b'),
]:
    resultado = conferir(hostil, 'doc1.txt:1: fonte\n')
    assert resultado.returncode != 0 and len(resultado.stderr.encode()) < 350
    assert visivel in resultado.stderr and oculto not in resultado.stderr
print('matriz sintética de referências aprovada')
PY
conferir "extração: matriz sintética de referência" [ "$?" = 0 ]
printf '{"destino":{"valor":null,"referencia":null}}\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia o destino" --destino local \
  --capacidade leitura_documental --extrair destino:texto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: permite ausência sem inventar citação" jqok -e \
  '.codigo_saida == 0 and (.relatorio | fromjson | .destino.valor == null)' "$tmp/saida"
delegar leitor "extraia" --destino agy --capacidade leitura_documental --extrair destino:texto --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: exige destino local explícito" [ "$(codigo)" = 2 ]
delegar leitor "extraia" --destino local --capacidade leitura_documental --extrair destino:numero --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: tipo desconhecido é erro de uso" [ "$(codigo)" = 2 ]
delegar leitor "extraia" --destino local --capacidade leitura_documental --extrair destino:texto --extrair destino:texto --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: campo repetido é erro de uso" [ "$(codigo)" = 2 ]
delegar leitor "extraia" --destino local --capacidade leitura_documental --extrair destino:texto \
  --requisito Destino --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: requisito textual é incompatível" [ "$(codigo)" = 2 ]
delegar redator "extraia" --destino local --capacidade leitura_documental --extrair destino:texto \
  --arquivos "$tmp/projeto/doc1.txt"
conferir "extração: papel diferente de leitor é incompatível" [ "$(codigo)" = 2 ]
python3 - "$curto/extracao.txt" "$ollama_resp.sequencia" <<'PY'
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text('Destino local.\n' + ('Contexto sem novos fatos. ' * 8 + '\n') * 20 + 'Responsável Helena.\n')
partes = [
    {'destino': {'valor': 'local', 'referencia': 'extracao.txt:1'}, 'responsavel': {'valor': None, 'referencia': None}},
    {'destino': {'valor': None, 'referencia': None}, 'responsavel': {'valor': 'Helena', 'referencia': 'extracao.txt:22'}},
]
pathlib.Path(sys.argv[2]).write_text(json.dumps(partes))
PY
: >"$ollama_reqs"
CHAMADAS_MAX=2 LOCAL_CTX=3000 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia fatos" --destino local \
  --capacidade leitura_documental --extrair destino:texto --extrair responsavel:texto --json --arquivos "$curto/extracao.txt"
conferir "extração: consolida sem apagar fatos e sem chamada adicional" jqok -e \
  '.codigo_saida == 0 and .consolidacao == "deterministica" and .chamadas_executor == 2
    and (.relatorio | fromjson | .destino.valor == "local" and .responsavel.valor == "Helena")' "$tmp/saida"
conferir "extração: somente as partes são chamadas" jqok -se 'length == 2' "$ollama_reqs"
conferir "citação: cada parte recebe exemplos do próprio trecho" exemplos_validos
printf '[{"destino":{"valor":"local","referencia":"extracao.txt:22"},"responsavel":{"valor":null,"referencia":null}}]\n' >"$ollama_resp.sequencia"
: >"$ollama_reqs"
CHAMADAS_MAX=2 LOCAL_CTX=3000 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia fatos" --destino local \
  --capacidade leitura_documental --extrair destino:texto --extrair responsavel:texto --json --arquivos "$curto/extracao.txt"
conferir "citação: referência de outra fatia mantém código 4" [ "$(codigo)" = 4 ]
conferir "citação: recusa fora da fatia antes da segunda chamada" jqok -se 'length == 1' "$ollama_reqs"
conferir "citação: diagnóstico informa referência de outra fatia" grep -Fq 'referência "extracao.txt:22" (fora do trecho)' "$tmp/erro"
python3 - "$curto/extracao.txt" "$ollama_resp.sequencia" <<'PY'
import json, pathlib, sys
fonte = pathlib.Path(sys.argv[1])
linhas = fonte.read_text().splitlines()
linhas[-1] = 'Destino remoto. Responsável Helena.'
fonte.write_text('\n'.join(linhas) + '\n')
partes = [
    {'destino': {'valor': 'local', 'referencia': 'extracao.txt:1'}, 'responsavel': {'valor': None, 'referencia': None}},
    {'destino': {'valor': 'remoto', 'referencia': 'extracao.txt:22'}, 'responsavel': {'valor': 'Helena', 'referencia': 'extracao.txt:22'}},
]
pathlib.Path(sys.argv[2]).write_text(json.dumps(partes))
PY
printf 'preservar\n' >"$tmp/extracao-anterior.json"
CHAMADAS_MAX=2 LOCAL_CTX=3000 OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia fatos" --destino local \
  --capacidade leitura_documental --extrair destino:texto --extrair responsavel:texto --json \
  --arquivo "$tmp/extracao-anterior.json" --arquivos "$curto/extracao.txt"
conferir "extração: conflito recusa sem escolher um fato" jqok -e \
  '.tentativas[0].motivo_codigo == "saida_invalida" and .tentativas[0].chamadas == 2' "$tmp/saida"
conferir "extração: recusa preserva arquivo anterior" grep -qx preservar "$tmp/extracao-anterior.json"
rm "$ollama_resp.sequencia"
printf '## Destino\ndoc1.txt:1\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia a regra" \
  --capacidade leitura_documental --requisito Destino --json --arquivos "$tmp/projeto/doc1.txt"
conferir "completude: localizador sozinho reprova" jqok -e \
  '.tentativas[0].motivo_codigo == "saida_invalida"' "$tmp/saida"
artefato_reprovado="$(jq -rs 'map(select(.destino == "local")) | last | .artefato' "$reg")"
conferir "completude: preserva relatório reprovado para diagnóstico" grep -q doc1.txt:1 "$artefato_reprovado"
touch "$ollama_resp.limite"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "extraia a regra" \
  --capacidade leitura_documental --json --arquivos "$tmp/projeto/doc1.txt"
conferir "geração: relatório cortado pelo limite reprova" jqok -e \
  '.tentativas[0].motivo_codigo == "saida_invalida"' "$tmp/saida"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar redator "revise" --destino local \
  --arquivos "$tmp/projeto/doc1.txt"
conferir "compatibilidade: saída longa sem capacidade mantém contrato" [ "$(codigo)" = 0 ]
conferir "compatibilidade: não altera opções antigas de geração" jqok -se \
  'last | (has("think") | not) and (.options | has("num_predict") | not)
    and (.messages[1].content | endswith("/no_think") | not)' "$ollama_reqs"
rm "$ollama_resp.limite"
printf 'Regra explicada com referência válida em doc1.txt:1\n' >"$ollama_resp"
LOCAL_MODELO=modelo-simples OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "leia" \
  --capacidade leitura_documental --json --arquivos "$tmp/projeto/doc1.txt"
conferir "geração: outros modelos não recebem controle Qwen3" jqok -se \
  'last | .model == "modelo-simples" and (.messages[1].content | endswith("/no_think") | not)' "$ollama_reqs"
delegar leitor "leia" --requisito Destino --arquivos "$tmp/projeto/doc1.txt"
conferir "uso: requisito exige capacidade" [ "$(codigo)" = 2 ]
delegar leitor "leia" --capacidade leitura_documental --requisito -Foo --arquivos "$tmp/projeto/doc1.txt"
conferir "uso: requisito começando com hífen é recusado" [ "$(codigo)" = 2 ]
conferir "uso: ajuda apresenta requisito" grep -q -- --requisito "$tmp/erro"
printf 'doc_grande.txt:1: resumo completo com fonte.\n' >"$ollama_resp"
: >"$ollama_reqs"
CHAMADAS_MAX="$chamadas_fatiadas" LOCAL_CTX=2100 LOCAL_FATIAS_MAX=5 OLLAMA_URL="http://127.0.0.1:$porta_ollama" \
  delegar leitor "resuma" --capacidade resumo_curto --json --arquivos "$doc_grande"
conferir "limite: orçamento exato inclui consolidação" jqok -e --argjson total "$chamadas_fatiadas" \
  '.codigo_saida == 0 and .chamadas_executor == $total and .chamadas_local[-1].fase == "consolidacao"' "$tmp/saida"
RESPOSTA='Resposta sem referências' CHAMADAS_MAX="$chamadas_fatiadas" LOCAL_CTX=2100 \
  OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" --capacidade analise_documental \
  --permitir-remoto --json --arquivos "$doc_grande"
conferir "limite: desconta chamada anterior antes das partes locais" jqok -e \
  '.tentativas[0].destino == "agy" and .tentativas[0].chamadas == 1
    and .tentativas[1].destino == "local" and .tentativas[1].chamadas == 0
    and .tentativas[1].motivo_codigo == "limite_chamadas"' "$tmp/saida"

# A prévia cortada declara que a verificação vale para o arquivo completo.
python3 -c 'print("palavra " * 610 + "doc1.txt:1")' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" --capacidade resumo_curto \
  --json --arquivo "$tmp/completo.md" --arquivos "$tmp/projeto/doc1.txt"
conferir "arquivo: roteamento bem-sucedido grava relatório completo" grep -q doc1.txt:1 "$tmp/completo.md"
conferir "prévia: escopo da verificação é explícito" jqok -e \
  '.relatorio_cortado and .verificacao_escopo == "relatorio_completo"
    and .artefato != "" and (.relatorio | contains("doc1.txt:1") | not)' "$tmp/saida"

# O pai limpa temporários mesmo quando o executor ignora SIGTERM.
TEMPO_TOTAL=1 ESPERA_AGY=5 IGNORAR_TERM=1 RESPOSTA='Relatório em doc1.txt:1' delegar leitor "compare" \
  --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "encerramento forçado: recusa estruturada" jqok -e '.motivo_codigo == "limite_tempo"' "$tmp/saida"
conferir "encerramento forçado: diretório dos temporários removido" \
  test ! -d "$(cat "$tmp/falso/temporario")"
# O agy roda em namespace de PID próprio, e o número que ele vê não vale fora.
# Os processos da chamada se reconhecem pelo ambiente que herdaram dela.
restam_do_falso() {
  # Fora de uma sessão há processos de outros usuários: o grep sai com 2 por
  # não poder lê-los, e só o resultado do último comando interessa.
  (set +o pipefail
   grep -lsaF "FALSO_DIR=$tmp/falso" /proc/[0-9]*/environ | xargs -r grep -lsaF "FALSO_IGNORAR_TERM=$1" | grep -q .)
}
nao() { ! "$@"; }
FALSO_DIR="$tmp/falso" FALSO_IGNORAR_TERM=sonda sleep 5 &
sonda_pid=$!
# O /proc só mostra o ambiente novo depois que o filho troca de programa.
for _ in 1 2 3 4 5 6 7 8 9 10; do restam_do_falso sonda && break; sleep 0.1; done
conferir "encerramento forçado: a busca enxerga um processo vivo" restam_do_falso sonda
kill "$sonda_pid" 2>/dev/null; wait "$sonda_pid" 2>/dev/null
conferir "encerramento forçado: agy e filho não continuam executando" nao restam_do_falso 1
rm -f "$cache_cota"
TEMPO_TOTAL=1 ESPERA_USAGE=5 delegar leitor "compare" --capacidade analise_documental \
  --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "consulta interrompida: recusa estruturada" jqok -e '.motivo_codigo == "limite_tempo"' "$tmp/saida"
conferir "consulta interrompida: temporário ao lado do cache removido" \
  bash -c '! compgen -G "$1.*" >/dev/null' _ "$cache_cota"

# Um executor sem resultado JSON não pode produzir uma entrega aceita.
cat >"$tmp/bin/bash" <<'EOF'
#!/bin/sh
if [ -n "${JANGADA_DELEGAR_ROTEAMENTO_ID:-}" ]; then
  echo 'resultado sem JSON'
  exit 0
fi
exec /usr/bin/bash "$@"
EOF
chmod +x "$tmp/bin/bash"
delegar leitor "resuma" --capacidade resumo_curto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "executor: resultado não JSON recusa" jqok -e \
  '.motivo_codigo == "erro_execucao" and .tentativas[0].destino == "local"
    and .tentativas[0].chamadas == null' "$tmp/saida"
rm -f "$tmp/bin/bash"

printf '\377\n' >"$tmp/projeto/binario.txt"
printf 'Referência em binario.txt:1\n' >"$ollama_resp"
OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" --capacidade resumo_curto \
  --json --arquivos "$tmp/projeto/binario.txt"
conferir "fonte: codificação inválida reprova saída" jqok -e \
  '.tentativas[0].motivo_codigo == "saida_invalida"' "$tmp/saida"

if command -v pdftotext >/dev/null; then
  python3 - "$tmp/projeto/fonte.pdf" <<'PY'
import pathlib
import sys

conteudo = b"BT /F1 12 Tf 72 720 Td (Fonte de teste.) Tj ET"
objetos = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"\nendstream",
]
pdf = b"%PDF-1.4\n"
posicoes = [0]
for i, objeto in enumerate(objetos, 1):
    posicoes.append(len(pdf))
    pdf += f"{i} 0 obj\n".encode() + objeto + b"\nendobj\n"
xref = len(pdf)
pdf += f"xref\n0 {len(posicoes)}\n0000000000 65535 f \n".encode()
pdf += b"".join(f"{p:010d} 00000 n \n".encode() for p in posicoes[1:])
pdf += f"trailer\n<< /Size {len(posicoes)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
pathlib.Path(sys.argv[1]).write_bytes(pdf)
PY
  printf 'Referência em fonte.pdf, p. 1\n' >"$ollama_resp"
  OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" --capacidade resumo_curto \
    --json --arquivos "$tmp/projeto/fonte.pdf"
  conferir "PDF: extrai e valida página no fluxo completo" jqok -e '.verificacao == "referencias_validas"' "$tmp/saida"
else
  echo "pulado PDF no fluxo completo: pdftotext ausente"
fi

# A contagem é por registro, mas o consumo não duplica o histórico.
printf 'Relatório sem referência\n' >"$ollama_resp"
RESPOSTA='Relatório em doc1.txt:1' OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
id_roteamento="$(jq -r '.roteamento_id' "$tmp/saida")"
jq -c --arg id "$id_roteamento" 'select(.roteamento_id == $id)' "$reg" >"$tmp/roteamento.jsonl"
registros_roteamento() {
  jq -s --argjson n "$1" 'length == $n and (map(.roteamento_id) | unique | length) == 1' \
    "$tmp/roteamento.jsonl" >/dev/null
}
conferir "roteamento: troca de executor grava duas entradas com o mesmo roteamento_id" registros_roteamento 2
RESPOSTA='Relatório sem referência' OLLAMA_URL="http://127.0.0.1:$porta_ollama" delegar leitor "resuma" \
  --capacidade resumo_curto --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
id_roteamento="$(jq -r '.roteamento_id' "$tmp/saida")"
jq -c --arg id "$id_roteamento" 'select(.roteamento_id == $id)' "$reg" >"$tmp/roteamento.jsonl"
conferir "roteamento: falha total grava executores e recusa final com o mesmo roteamento_id" registros_roteamento 3

parecer_supervisor="$(jq -cn --arg fonte "A informação foi conferida na fonte $tmp/projeto/doc1.txt:1" \
  '{task_id:"S1",relatorio_sha256:("0" * 64),decisao:"APPROVED",
    criterios:{fidelidade:{resultado:"PASS",justificativa:$fonte},
               completude:{resultado:"PASS",justificativa:$fonte},
               extrapolacoes:{resultado:"PASS",justificativa:$fonte}},observacoes:[]}')"
AGENTES=supervisor RESPOSTA="$parecer_supervisor" delegar supervisor "compare as fontes" \
  --destino agy --capacidade analise_documental --permitir-remoto --json \
  --arquivo "$tmp/parecer-supervisor.json" --arquivos "$tmp/projeto/doc1.txt"
conferir "supervisor agy: JSON puro passa pelo comando real e pelo gate de referências" [ "$(codigo)" = 0 ]
conferir "supervisor agy: relatório completo continua JSON" jqok -e '.decisao == "APPROVED"' "$tmp/parecer-supervisor.json"
AGENTES=leitor delegar supervisor "compare as fontes" --destino agy \
  --capacidade analise_documental --permitir-remoto --json --arquivos "$tmp/projeto/doc1.txt"
conferir "supervisor ausente do catálogo: recusa antes da geração" [ "$(codigo)" = 4 ]
conferir "supervisor ausente do catálogo: não usa agente padrão" test ! -e "$tmp/falso/agy.args"

echo
if ((falhas)); then
  echo "$falhas teste(s) falharam"
  exit 1
fi
echo "todos os testes do jangada-delegar passaram"
