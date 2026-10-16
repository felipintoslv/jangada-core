# shellcheck shell=bash
# Etapa 20: grava em ~/.local/bin um invólucro para cada comando de bin/.
# Não é link simbólico: os comandos acham a própria pasta por
# dirname "${BASH_SOURCE[0]}", que num link apontaria para ~/.local/bin.
# Arquivo alheio com o mesmo nome fica como está, com aviso; no fim a etapa
# sai com erro listando os conflitos. Invólucro com a marca cujo comando saiu
# de bin/ é removido.

_marca="# gerado pelo jangada-core; não edite"
_destino="$HOME/.local/bin"
_conflitos=()

# Grava o invólucro de NOME em DESTINO por arquivo temporário e mv.
_gravar_involucro() {
  local nome="$1" arquivo="$2" novo
  mkdir -p "$(dirname "$arquivo")" || return 1
  novo="$(mktemp "$arquivo.jangada-XXXXXX")" || return 1
  if printf '#!/usr/bin/env bash\n%s\n%s\n' "$_marca" "$(_linha_exec "$nome")" >"$novo" \
    && chmod 755 "$novo" && mv -f "$novo" "$arquivo"; then
    return 0
  fi
  rm -f "$novo"
  return 1
}

# Linha que executa o comando; %q protege caminho com espaço ou aspas.
_linha_exec() { printf 'exec %q "$@"' "$JANGADA_CORE_PATH/bin/$1"; }

_tem_marca() { [[ -f "$1" ]] && grep -qxF "$_marca" "$1"; }

for _arq in "$JANGADA_CORE_PATH"/bin/jangada*; do
  [[ -f "$_arq" && -x "$_arq" ]] || continue
  _nome="${_arq##*/}"
  _alvo="$_destino/$_nome"
  if [[ -e "$_alvo" || -L "$_alvo" ]] && ! _tem_marca "$_alvo"; then
    aviso "$_alvo já existe e não é invólucro do jangada-core; mantido"
    _conflitos+=("$_alvo")
    continue
  fi
  if _tem_marca "$_alvo" && [[ "$(sed -n '3p' "$_alvo")" == "$(_linha_exec "$_nome")" ]]; then
    ok "invólucro já gravado: $_alvo"
    continue
  fi
  executar _gravar_involucro "$_nome" "$_alvo" || { _conflitos+=("$_alvo"); continue; }
  simulando || ok "invólucro gravado: $_alvo"
done

for _alvo in "$_destino"/jangada*; do
  [[ -f "$_alvo" ]] || continue
  _tem_marca "$_alvo" || continue
  [[ -x "$JANGADA_CORE_PATH/bin/${_alvo##*/}" ]] && continue
  executar rm -f "$_alvo"
  info "invólucro órfão removido: $_alvo"
done

if ((${#_conflitos[@]})); then
  morrer "invólucros não gravados (arquivo alheio ou falha de gravação): ${_conflitos[*]}"
fi
unset _marca _destino _conflitos _arq _nome _alvo
unset -f _gravar_involucro _linha_exec _tem_marca
