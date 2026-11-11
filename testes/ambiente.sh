# shellcheck shell=bash
# Ambiente fixo dos testes em bash: o resultado não depende do idioma nem da
# entrada padrão de quem chama. Caso que precisa de outro idioma ou de entrada
# própria passa isso ao subprocesso daquele caso.
#
# Uso, como primeiro comando depois do set:
#   # shellcheck source=testes/ambiente.sh
#   source "$(dirname "$0")/ambiente.sh"
# O testes/ambiente-fixo.py confere o uso em cada teste.

for _nome in $(compgen -v); do
  case $_nome in
    LANG | LANGUAGE | LC_*) unset "$_nome" ;;
  esac
done
unset _nome
export LC_ALL=C.UTF-8
exec </dev/null
