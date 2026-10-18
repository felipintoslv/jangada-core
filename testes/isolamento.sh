# shellcheck shell=bash
# Ajudante dos testes que também rodam dentro do jangada-isolar, numa sessão
# de agente. Ali a marca /tmp/.jangada-sem-autoridade faz o Core recusar o que
# exige o controlador de fora: registrar o início da sessão e preparar o
# isolamento do revisor, do lintr e do .jangada/validar.sh. Fora dela nenhum
# caso é pulado.
#
# Uso: source testes/isolamento.sh

sem_autoridade() {
  awk '$5 == "/tmp/.jangada-sem-autoridade" { a = 1 } END { exit !a }' /proc/self/mountinfo 2>/dev/null
}

# Uma linha por caso pulado. O verificar.sh soma as linhas de todos os testes
# pelo arquivo de JANGADA_TESTES_PULADOS.
pulado_no_isolamento() {
  printf 'pulado no isolamento: %s\n' "$1"
  [[ -z "${JANGADA_TESTES_PULADOS:-}" ]] || printf '%s\n' "$1" >>"$JANGADA_TESTES_PULADOS"
}

# O que o Core e o jangada-update dizem ao recusar dentro do isolamento.
RECUSAS_DO_ISOLAMENTO='AUTORIZACAO_RECUSADA|exige controlador fora do isolamento|atualização exige terminal externo ao agente isolado'
_sem_autoridade=0
sem_autoridade && _sem_autoridade=1

# Primeira recusa do isolamento no que o último comando gravou em PASTA. O
# último comando começa no novo_comando do invólucro do teste; sem invólucro,
# na última conferência que passou. Do arquivo que cresceu sem mudar o começo,
# como o registro de delegações, que guarda recusas antigas, só conta o que
# veio depois; o arquivo regravado, mesmo com o conteúdo igual, conta inteiro.
# A marca .conferencia só existe dentro do isolamento.
_recusa_nova() {
  local pasta="$1" marca="$1/.conferencia" arq tamanho hash inicio linha
  local -A tamanho_marcado=() hash_marcado=()
  local -a novos=()
  if [[ -e $marca ]]; then
    novos=(-newer "$marca")
    while IFS=$'\t' read -r tamanho hash arq; do
      tamanho_marcado[$arq]=$tamanho
      hash_marcado[$arq]=$hash
    done <"$marca"
  fi
  while IFS=$'\t' read -r -d '' tamanho arq; do
    inicio=0
    if [[ -n ${tamanho_marcado[$arq]:-} ]] && ((tamanho > tamanho_marcado[$arq])) &&
      [[ "$(head -c "${tamanho_marcado[$arq]}" "$arq" | md5sum)" == "${hash_marcado[$arq]}" ]]; then
      inicio=${tamanho_marcado[$arq]}
    fi
    linha="$(tail -c "+$((inicio + 1))" "$arq" 2>/dev/null | grep -soE "($RECUSAS_DO_ISOLAMENTO).*" | head -n 1)"
    [[ -n $linha ]] && printf '%s\n' "$linha" && return 0
  done < <(find "$pasta" -type f "${novos[@]}" ! -name .conferencia ! -name '.conferencia.*' \
    ! -name .por-comando -printf '%s\t%p\0' 2>/dev/null)
  return 1
}

# Uso: pulado_se_recusado PASTA DESCRICAO
# Dentro do isolamento, pula o caso quando o último comando foi recusado.
pulado_se_recusado() {
  ((_sem_autoridade)) && [[ -d $1 ]] || return 1
  local recusa
  recusa="$(_recusa_nova "$1")" || return 1
  pulado_no_isolamento "$2 (recusa: $recusa)"
}

# Uso: guardar_recusa PASTA NOME, logo depois do comando que cria o que
# conferências adiante usam. Dentro do isolamento, guarda a recusa desse
# comando. repetir_recusa PASTA NOME a devolve ao último comando, para as
# conferências que dependem do que o comando recusado não criou.
guardar_recusa() {
  ((_sem_autoridade)) && [[ -d $1 ]] || return 0
  _recusa_nova "$1" >"$1/.recusa-$2" || rm -f "$1/.recusa-$2"
}
repetir_recusa() {
  ((_sem_autoridade)) && [[ -f $1/.recusa-$2 ]] || return 0
  cat "$1/.recusa-$2" >>"$1/.recusa-repetida"
}

# Guarda tamanho e hash dos arquivos da pasta que já têm recusa, para a
# próxima conferência saber se cresceram ou foram regravados.
_marcar_conferencia() {
  local arq tamanho
  grep -rlsE --exclude=.conferencia --exclude='.conferencia.*' --exclude=.por-comando \
    "$RECUSAS_DO_ISOLAMENTO" "$1" | while IFS= read -r arq; do
    tamanho="$(stat -c %s "$arq")"
    printf '%s\t%s\t%s\n' "$tamanho" "$(head -c "$tamanho" "$arq" | md5sum)" "$arq"
  done >"$1/.conferencia.$$"
  mv -f "$1/.conferencia.$$" "$1/.conferencia"
}

# Uso: novo_comando PASTA, no invólucro que roda o comando conferido. Depois
# dele, uma conferência que passa não esconde a recusa das seguintes, como
# "termina com erro" diante de um comando recusado.
novo_comando() {
  ((_sem_autoridade)) && [[ -d ${1:-} ]] || return 0
  : >"$1/.por-comando"
  _marcar_conferencia "$1"
}

# Fecha a conferência que passou, nos testes sem novo_comando.
conferencia_feita() {
  ((_sem_autoridade)) && [[ -d ${1:-} && ! -e $1/.por-comando ]] || return 0
  _marcar_conferencia "$1"
}

# Uso: erros_dos_pulados PASTA
# Dentro do isolamento, o stderr do teste vai para PASTA/erros-no-isolamento.log:
# os casos pulados deixam erros em cascata, como ler um arquivo que o caso não
# chegou a gravar, e a recusa que um processo de fundo imprime passa a ser
# vista pelo pulado_se_recusado. Fora dele nada muda.
erros_dos_pulados() {
  ((_sem_autoridade)) || return 0
  exec 2>>"$1/erros-no-isolamento.log"
}
