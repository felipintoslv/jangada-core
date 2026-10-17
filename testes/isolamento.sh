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
