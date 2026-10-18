#!/usr/bin/env bash
# Prova consultas, validação e percurso R sem módulos de apresentação.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
marca="${JANGADA_MARCA_ISOLADO:-/tmp/.jangada-isolado}"
if ! awk -v m="$marca" '$5 == m { a = 1 } END { exit !a }' /proc/self/mountinfo; then
  pasta_marca="$(mktemp -d)"
  JANGADA_MARCA_ISOLADO="$pasta_marca/marca" \
    bwrap --dev-bind / / --ro-bind /dev/null "$pasta_marca/marca" -- bash "$0"
  rc=$?
  rm -rf "$pasta_marca"
  exit "$rc"
fi
unset JANGADA_VALIDAR_REVISOR JANGADA_DELEGAR
# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
falhas=0
# Dentro do isolamento, a parte com R real fica pulada: o jangada-isolar do
# lintr exige o controlador, e a saída do jangada-validar só diz que o lintr
# falhou.
pulo_fixo=''
conferir() {
  local descricao="$1"; shift
  if [[ -n $pulo_fixo ]]; then pulado_no_isolamento "$descricao ($pulo_fixo)"
  elif "$@"; then printf 'ok    %s\n' "$descricao"
  elif ! pulado_se_recusado "${tmp:-}" "$descricao"; then
    printf 'FALHA %s\n' "$descricao"; falhas=$((falhas + 1))
  fi
}
tmp="$(mktemp -d)"
erros_dos_pulados "$tmp"
trap 'rm -rf "$tmp"' EXIT
copia="$tmp/jangada"
mkdir -p "$copia/bin" "$tmp/bin" "$tmp/falso" \
  "$tmp/config/jangada" "$tmp/estado/jangada/agentes" "$tmp/projeto"
cp -a bin/jangada-config bin/jangada-gancho "$copia/bin/"
for comando in jangada-validar jangada-isolar; do
  cp -a "bin/$comando" "$copia/bin/"
done
for recurso in nucleo orquestracao provedores delegacao validacao; do
  cp -a "$recurso" "$copia/"
done
conferir 'Shell físico ausente' test ! -e "$copia/shell"
conferir 'Monitor físico ausente' test ! -e "$copia/monitor"
# Comandos do Shell e do Monitor, mesmo instalados na máquina, ficam fora do PATH.
path_limpo() {
  local d out="" IFS=:
  for d in $PATH; do
    [[ -x "$d/jangada-consumo" || -x "$d/jangada-subagentes" || -x "$d/jangada-snapshot" ]] || out+="${out:+:}$d"
  done
  printf '%s' "$out"
}
PATH="$(path_limpo)"
PYTHONPATH="$copia" python3 -B - "$tmp/consulta" <<'PY'
import json
from pathlib import Path
import sys
from nucleo import acoes, consultas
import delegacao
import orquestracao

estado = Path(sys.argv[1])
(estado / 'agentes').mkdir(parents=True)
sessao = estado / 'agentes/sintetica.json'
sessao.write_text(json.dumps({'sessao': 'sintetica', 'raiz': str(estado), 'estado': 'trabalhando'}))
antes = {str(p): p.read_bytes() for p in estado.rglob('*') if p.is_file()}
dados = consultas.consultar(estado)
assert dados['erros'] == [], dados['erros']
assert dados['sessoes'][0]['estado'] == 'Executando', dados
assert antes == {str(p): p.read_bytes() for p in estado.rglob('*') if p.is_file()}
PY
conferir 'importações Core e consulta sintética sem Monitor, sem escrita na origem' test "$?" = 0
conferir 'fachada copiada resolve para o Core copiado' \
  test "$(realpath "$copia/bin/jangada-validar")" = "$copia/bin/jangada-validar"
conferir 'padrão do lintr existe na cópia mínima' test -e "$copia/validacao/lintr"
cat >"$tmp/bin/claude" <<'FALSO'
#!/usr/bin/env bash
cat >"$FALSO_DIR/pedido"
printf 'STATUS: APROVADO\n'
FALSO
chmod +x "$tmp/bin/claude"
export PATH="$tmp/bin:$PATH" FALSO_DIR="$tmp/falso"
export JANGADA_ISOLAR_ESCRITA="$tmp/falso"
export XDG_STATE_HOME="$tmp/estado" XDG_CONFIG_HOME="$tmp/config"
# Fora do isolamento, onde o atendente do jangada-isolar roda a revisão.
export JANGADA_CORE_PATH="$copia" JANGADA_SESSAO=s
unset JANGADA_ISOLADO
git -C "$tmp/projeto" init -q -b main
printf 'x <- 1\n' >"$tmp/projeto/exemplo.R"
git -C "$tmp/projeto" add exemplo.R
git -C "$tmp/projeto" -c user.name=t -c user.email=t@t commit -qm inicio
git -C "$tmp/projeto" checkout -qb agente/x
nova_sessao() {
  rm -f "$tmp/estado/jangada/revisoes/validacao-s"* "$tmp/falso/pedido"
  printf '{"sessao":"s","agente":"codex","revisor":"claude","base":"main","tarefa":"R sintético"}\n' \
    >"$tmp/estado/jangada/agentes/s.json"
  mkdir -p "$tmp/estado/jangada/revisoes"
  cp "$tmp/estado/jangada/agentes/s.json" "$tmp/estado/jangada/revisoes/s.json"
}
validar() {
  executar "$tmp" "$copia/bin/jangada-validar" --revisor claude "$tmp/projeto" >"$tmp/saida" 2>&1
}
printf 'conteúdo sintético\n' >"$tmp/projeto/exemplo.txt"
git -C "$tmp/projeto" add exemplo.txt
nova_sessao
validar; rc=$?
conferir 'validação sem R e sem Monitor chama revisão' test "$rc" = 0
conferir 'revisão sem diagnóstico foi chamada' test -s "$tmp/falso/pedido"
conferir 'resumo opcional ausente registrado explicitamente' \
  grep -q 'resumo de subagentes não gravado' "$tmp/saida"
printf '#!/bin/bash\nif then\n' >"$tmp/projeto/exemplo.sh"
git -C "$tmp/projeto" add exemplo.sh
nova_sessao
validar; rc=$?
conferir 'sem Monitor a sintaxe inválida continua reprovando' test "$rc" = 3
conferir 'erro obrigatório não chega ao revisor' test ! -e "$tmp/falso/pedido"
rm "$tmp/projeto/exemplo.sh"
git -C "$tmp/projeto" add -u
if ((falhas)); then cat "$tmp/saida"; exit 1; fi
if ! Rscript --vanilla -e 'stopifnot(requireNamespace("lintr", quietly = TRUE))' >/dev/null 2>&1; then
  echo 'UNAVAILABLE: prova R do Core independente não executada; exige R e lintr reais' >&2
  exit 77
fi
sem_autoridade && pulo_fixo='o jangada-isolar do lintr exige o controlador'
printf 'cat("novo\\n")\n' >>"$tmp/projeto/exemplo.R"
nova_sessao
validar; rc=$?
conferir 'sem .lintr da base: aprovação com R real' test "$rc" = 0
conferir 'padrão Core gera aviso na linha nova' \
  grep -q 'exemplo.R:2: \[undesirable_function_linter\]' "$tmp/saida"
conferir 'achado do padrão é aviso' grep -q 'aviso do lintr (padrão do jangada' "$tmp/saida"
conferir 'revisão falsa chamada' test -s "$tmp/falso/pedido"

nova_sessao
printf 'linters: file.create("%s")\n' "$tmp/regra-executada" >"$tmp/projeto/.lintr"
printf 'invisible(file.create("%s"))\n' "$tmp/perfil-executado" >"$tmp/projeto/.Rprofile"
validar; rc=$?
conferir 'regra nova e perfil do worktree não impedem validação' test "$rc" = 0
conferir 'regra gravável não executada' test ! -e "$tmp/regra-executada"
conferir 'perfil gravável não executado' test ! -e "$tmp/perfil-executado"
conferir 'regra nova ignorada explicitamente' grep -q 'não está na base' "$tmp/saida"
conferir 'padrão Core ainda aplicado' grep -q 'exemplo.R:2: \[undesirable_function_linter\]' "$tmp/saida"
conferir 'revisão chamada com regra nova ignorada' test -s "$tmp/falso/pedido"

# A regra da base difere do padrão: só ela proíbe message(). O worktree tenta
# desativá-la. Assim, reprovar comprova também a prioridade da base.
git -C "$tmp/projeto" checkout -q main
printf 'linters: list(undesirable_function_linter(fun = c(message = "regra da base")))\n' >"$tmp/projeto/.lintr"
git -C "$tmp/projeto" add .lintr
git -C "$tmp/projeto" -c user.name=t -c user.email=t@t commit -qm regras
git -C "$tmp/projeto" checkout -q agente/x
git -C "$tmp/projeto" -c user.name=t -c user.email=t@t merge -q main
printf 'linters: list()\n' >"$tmp/projeto/.lintr"
printf 'message("novo")\n' >>"$tmp/projeto/exemplo.R"
nova_sessao
validar; rc=$?
conferir 'regra da base reprova com código 3' test "$rc" = 3
conferir 'regra da base aponta violação nova' grep -q 'exemplo.R:3:.*regra da base' "$tmp/saida"
conferir 'revisor poupado na reprovação local' test ! -e "$tmp/falso/pedido"
conferir 'perfil continua sem executar' test ! -e "$tmp/perfil-executado"

# A falta do recurso obrigatório não pode ser confundida com nenhum achado.
nova_sessao
git -C "$tmp/projeto" checkout -q -- .lintr
git -C "$tmp/projeto" checkout -q agente/x~1
mv "$copia/validacao/lintr" "$tmp/padrao"
validar; rc=$?
conferir 'padrão indisponível reprova' test "$rc" = 3
conferir 'falha do lintr explícita' grep -q 'FAILED: lintr falhou' "$tmp/saida"
conferir 'sem padrão não chama revisor' test ! -e "$tmp/falso/pedido"
((falhas == 0)) || cat "$tmp/saida"
exit $((falhas > 0))
