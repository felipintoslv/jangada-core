# shellcheck shell=bash
# Etapa 10: instala os pacotes das listas em install/pacotes/.

mapfile -t _pacotes < <(
  for _lista in base ferramentas; do
    ler_lista "$JANGADA_CORE_PATH/install/pacotes/$_lista.txt"
  done
)
instalar_pacotes "${_pacotes[@]}"
unset _pacotes _lista
