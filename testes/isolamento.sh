# shellcheck shell=bash
# Ajudante dos testes que também rodam dentro do jangada-isolar, numa sessão
# de agente. Ali a marca /tmp/.jangada-sem-autoridade faz o Core recusar o que
# exige o controlador de fora: registrar o início da sessão e preparar o
# isolamento do revisor, do lintr e do .jangada/validar.sh. Fora dela nenhum
# caso é pulado.
#
# A recusa só conta quando sai do próprio comando conferido: o último comando
# rodado pelo executar terminou com o código da recusa e a escreveu no stdout
# ou no stderr. Texto de recusa em outro arquivo da pasta não conta. Qualquer
# comando do nível de cima do teste entre esse passo e a conferência, fora o
# conferir e o rc=$?, anula o registro.
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
# orquestracao/confianca.py, o jangada-validar e o jangada-update saem com 1;
# o orquestracao/cli.py (jangada-fila e afins), com 2; o jangada-delegar, com 4.
CODIGOS_DA_RECUSA='1 2 4'
_sem_autoridade=0
_comandos=0

# Conta os comandos do nível de cima do teste. Não contam o conferir, o
# rc=$?, o guardar_recusa nem o cabeçalho do for e do case. O trap DEBUG não
# entra nas funções nem nos subshells: o executar dentro do rodar ou de um
# $(...) vê a contagem do comando que o chamou.
_contar_comando() {
  case $BASH_COMMAND in
    conferir* | guardar_recusa* | 'for '* | 'case '*) ;;
    *) [[ $BASH_COMMAND =~ ^[A-Za-z_]+=\$\?$ ]] || _comandos=$((_comandos + 1)) ;;
  esac
}
vigiar_comandos() {
  _sem_autoridade=1
  trap _contar_comando DEBUG
}
sem_autoridade && vigiar_comandos

# Uso: executar PASTA COMANDO..., no invólucro que roda o comando conferido.
# Dentro do isolamento, guarda o stdout, o stderr e o código do comando em
# PASTA/.comando.*, devolve a saída a quem chamou e sai com o mesmo código.
# Fora dele só roda o comando.
executar() {
  local pasta="$1" rc
  shift
  if ! ((_sem_autoridade)) || [[ ! -d $pasta ]]; then
    "$@"
    return
  fi
  rm -f "$pasta/.comando.rc"
  "$@" >"$pasta/.comando.saida" 2>"$pasta/.comando.erro"
  rc=$?
  printf '%s\n' "$rc" >"$pasta/.comando.rc"
  printf '%s\n' "$_comandos" >"$pasta/.comando.n"
  cat "$pasta/.comando.saida"
  cat "$pasta/.comando.erro" >&2
  return "$rc"
}

# Uso: registrar_comando PASTA CODIGO SAIDA ERRO, quando o comando conferido
# rodou dentro de outro e gravou o código, o stdout e o stderr à parte.
registrar_comando() {
  ((_sem_autoridade)) && [[ -d $1 ]] || return 0
  cat "$3" >"$1/.comando.saida" 2>/dev/null
  cat "$4" >"$1/.comando.erro" 2>/dev/null
  printf '%s\n' "$2" >"$1/.comando.rc"
  printf '%s\n' "$_comandos" >"$1/.comando.n"
}

# Uso: novo_comando PASTA, antes de um comando conferido rodado sem o
# executar. Apaga o registro do anterior.
novo_comando() {
  [[ -n ${1:-} ]] || return 0
  rm -f "$1/.comando.rc"
}

# Uso: recusa_do_comando PASTA [REGISTRO]. Imprime a primeira recusa do
# último comando registrado em PASTA, se ele saiu com o código da recusa;
# senão falha. Não olha a marca do isolamento, para ser testada fora dele.
recusa_do_comando() {
  local registro="$1/.${2:-comando}" codigo
  [[ -f $registro.rc ]] || return 1
  codigo="$(<"$registro.rc")"
  [[ " $CODIGOS_DA_RECUSA " == *" $codigo "* ]] || return 1
  cat "$registro.saida" "$registro.erro" 2>/dev/null | grep -m 1 -oE "($RECUSAS_DO_ISOLAMENTO).*"
}

# Uso: pulado_se_recusado PASTA DESCRICAO
# Dentro do isolamento, pula o caso quando o último comando foi recusado e
# nenhum outro rodou depois dele.
pulado_se_recusado() {
  ((_sem_autoridade)) && [[ -d ${1:-} ]] || return 1
  [[ -f $1/.comando.n && "$(<"$1/.comando.n")" == "$_comandos" ]] || return 1
  local recusa
  recusa="$(recusa_do_comando "$1")" || return 1
  pulado_no_isolamento "$2 (recusa: $recusa)"
}

# Uso: guardar_recusa PASTA NOME, logo depois do passo que cria o que
# conferências adiante exigem. Dentro do isolamento, guarda o registro desse
# passo, se ele foi recusado.
guardar_recusa() {
  ((_sem_autoridade)) && [[ -d $1 ]] || return 0
  local parte
  rm -f "$1/.recusa-$2".*
  recusa_do_comando "$1" >/dev/null || return 0
  for parte in saida erro rc; do
    cp "$1/.comando.$parte" "$1/.recusa-$2.$parte" 2>/dev/null
  done
}

# Uso: pulado_sem_o_passo PASTA NOME DESCRICAO, na conferência que só vale
# com o que o passo guardado como NOME criaria. Dentro do isolamento, pula
# quando esse passo foi recusado. Não olha o último comando: a falha própria
# dele fica com as conferências dele.
pulado_sem_o_passo() {
  ((_sem_autoridade)) && [[ -d ${1:-} ]] || return 1
  local recusa
  recusa="$(recusa_do_comando "$1" "recusa-$2")" || return 1
  pulado_no_isolamento "$3 (recusa de $2: $recusa)"
}

# Uso: erros_dos_pulados PASTA
# Dentro do isolamento, o stderr do teste vai para PASTA/erros-no-isolamento.log:
# os casos pulados deixam erros em cascata, como ler um arquivo que o caso não
# chegou a gravar. Fora dele nada muda.
erros_dos_pulados() {
  ((_sem_autoridade)) || return 0
  exec 2>>"$1/erros-no-isolamento.log"
}
