#!/usr/bin/env bash
# Testa o contrato K9 (docs/modularizacao-3.0/03-contratos.md): o Core não
# cita pastas nem comandos de outras aplicações fora das exceções registradas.
#   Os arquivos de bin/, agentes/, nucleo/, orquestracao/, delegacao/,
#   provedores/, validacao/ e install/ não citam shell/, monitor/,
#   default/painel, default/tarefas, default/hypr, default/waybar, hyprctl,
#   waybar nem notify-send, e não chamam comando do jangada-shell nem do
#   jangada-monitor (lista em testes/contratos/modulos.txt).
# Comando de outra aplicação só é procurado no PATH, com command -v, e a
# ausência é tratada sem erro; essas chamadas ficam na lista de exceções.
#
# Não contam: comentário, corpo de "cat <<" (texto de ajuda; sem aspas no
# delimitador, o que vem a partir de $( ou ` conta), docstring do
# Python e arquivo .md. Comando conta só quando é chamado: pelo caminho
# (.../jangada-x), como texto exato entre aspas ('jangada-x', forma de argv)
# ou, em script de shell, na posição de comando; citado no meio de uma frase,
# não conta. A opção --waybar é da fachada (K1) e não conta como Waybar; o
# pkill que avisa a barra conta pela palavra waybar, e pkill -P de processo
# filho não conta.
#
# Limites conhecidos: a leitura usa expressões regulares, linha a linha,
# e não interpreta o shell. O teste detecta acoplamento acidental, não código
# escrito para escapar dele. Em "cat <<" sem aspas no delimitador, não
# acompanha uma substituição aberta numa linha e fechada em outra. O texto
# após uma substituição na mesma linha é conferido junto e pode ser apontado
# demais. Chamadas montadas em variável ou construídas por eval podem escapar
# quando o nome do comando não aparece numa das formas reconhecidas.
#
# Exceções em testes/contratos/fronteiras-excecoes.txt, no formato
# CONTRATO ARQUIVO TRECHO, em que TRECHO é a linha do código sem os espaços
# das pontas. A lista é igual aos acoplamentos: acoplamento fora dela falha, e
# exceção sem acoplamento correspondente também falha (retire-a da lista).
# A lista só diminui: o teto de cada contrato, abaixo, é a contagem de quando
# a lista foi criada (M3-03), e só sobe com mudança neste arquivo. A marca
# "permanente" reúne as exceções que ficam por decisão (D8), cada uma com o
# motivo na lista; o teto dela é o número decidido.
#
# Uso: testes/fronteiras.sh
set -uo pipefail
export LC_ALL=C
cd "$(dirname "$0")/.." || exit 1
repo_jangada="$PWD"
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

declare -A teto=([K3]=8 [K6]=7 [permanente]=0)

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fim_nome='([^[:alnum:]_-]|$)'
aspas="[\"']"
# Comando NOMES (ERE) chamado pelo caminho ou por system() e system2().
chamada() { printf '/(%s)%s|system2?\\([[:space:]]*%s(%s)%s' "$1" "$fim_nome" "$aspas" "$1" "$fim_nome"; }
# Comando NOMES como texto exato entre aspas, a forma de argv do Python.
chamada_py() { printf '%s(%s)%s' "$aspas" "$1" "$aspas"; }
# Comando NOMES na posição de comando de um script de shell: início da linha,
# depois de operador ou de substituição, com ou sem palavra reservada,
# prefixo, atribuição, opção ou número antes ("if", "env", "VAR=1",
# "timeout 5"). Palavra reservada solta numa frase ("saída do jangada-x") não
# conta.
chamada_sh() {
  local prefixo='exec|command|builtin|env|nohup|setsid|nice|timeout|if|then|else|elif|do|while|until|time|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*|-[[:alnum:]-]+|[0-9]+[smhd]?'
  printf '(^|[|&;!`]|\\$\\()[[:space:]]*((%s)[[:space:]]+)*(%s)%s' "$prefixo" "$1" "$fim_nome"
}

# Linhas de código dos arquivos dados que casam com FRONTEIRA_PADRAO ou, em
# script de shell e em Python, com FRONTEIRA_PADRAO_SH e FRONTEIRA_PADRAO_PY
# (vazio não casa). Saída: ARQUIVO<TAB>LINHA<TAB>TRECHO.
varrer() {
  awk '
    # Corta o comentário de fim de linha: # fora de aspas, depois de espaço.
    function sem_comentario(l,   i, ch, q) {
      q = ""
      for (i = 1; i <= length(l); i++) {
        ch = substr(l, i, 1)
        if (q == "") {
          if (ch == "#" && (i == 1 || substr(l, i - 1, 1) ~ /[[:space:]]/)) return substr(l, 1, i - 1)
          if (ch == "\"" || ch == "\047") q = ch
        } else if (ch == "\\" && (q == "\"" || tipo != "sh")) i++
        else if (ch == q) q = ""
      }
      return l
    }
    BEGIN { aspas3["\"\"\""]; aspas3["\047\047\047"] }
    FNR == 1 {
      tipo = "texto"; aberto = ""; fim = ""
      if (FILENAME ~ /\.py$/) tipo = "py"
      else if (FILENAME ~ /\.lua$/) tipo = "lua"
      else if (FILENAME ~ /\.sh$/ || $0 ~ /^#!.*sh([[:space:]]|$)/) tipo = "sh"
    }
    fim != "" {
      t = $0; if (tab) sub(/^\t+/, "", t)
      if (t == fim) { fim = ""; next }
      if (expande && match(t, /\$\(|`/)) { l = substr(t, RSTART); tipo_corpo = 1 } else next
    }
    {
      if (tipo_corpo) tipo_corpo = 0
      else l = $0
      if (tipo == "py") {
        if (aberto != "") {
          p = pular
          if (index(l, aberto)) aberto = ""
          if (p) next
        } else if (match(l, /^[[:space:]]*[rRbBuUfF]*("""|\047\047\047)/)) {
          q = substr(l, RSTART + RLENGTH - 3, 3)
          if (!index(substr(l, RSTART + RLENGTH), q)) { aberto = q; pular = 1 }
          next
        } else {
          for (q in aspas3) { c = l; if (gsub(q, "", c) % 2) { aberto = q; pular = 0 } }
        }
      }
      if (tipo == "lua") {
        if (l ~ /^[[:space:]]*--/) next
      } else {
        if (l ~ /^[[:space:]]*#/) next
        l = sem_comentario(l)
      }
      if (tipo == "sh" && match(l, /(^|[^[:alnum:]_])cat[^<]*<<-?[[:space:]]*["\047]?[A-Za-z_]+/)) {
        d = substr(l, RSTART, RLENGTH); tab = (d ~ /<<-/); expande = (d !~ /<<-?[[:space:]]*["\047]/)
        sub(/.*<<-?[[:space:]]*["\047]?/, "", d); fim = d
      }
      extra = (tipo == "sh" || tipo == "py") ? ENVIRON["FRONTEIRA_PADRAO_" toupper(tipo)] : ""
      if (l ~ ENVIRON["FRONTEIRA_PADRAO"] || (extra != "" && l ~ extra)) {
        t = $0; sub(/^[[:space:]]+/, "", t); sub(/[[:space:]]+$/, "", t)
        print FILENAME "\t" FNR "\t" t
      }
    }' "$@"
}

# Arquivos de texto do Core, sem .md.
arquivos_core() {
  find bin agentes nucleo orquestracao delegacao provedores validacao install install.sh \
    -type f ! -path '*/__pycache__/*' ! -name '*.md' | sort | xargs -r -d '\n' grep -Il ''
}

# Um problema por linha; sem saída, a árvore de RAIZ cumpre o contrato.
problemas() {
  local raiz="$1"
  (
    cd "$raiz" || exit 1
    local modulos=testes/contratos/modulos.txt excecoes=testes/contratos/fronteiras-excecoes.txt
    local cmd_sm achados lista c n

    cmd_sm="$(awk '!/^#/ && NF { print $2 }' "$modulos" | paste -sd'|')"
    achados="$(
      mapfile -t lista < <(arquivos_core)
      FRONTEIRA_PADRAO="(^|[^[:alnum:]_.-])(shell|monitor)/|default/(painel|tarefas|hypr|waybar)$fim_nome|(^|[^[:alnum:]_-])(hyprctl|waybar|notify-send)$fim_nome|$(chamada "$cmd_sm")" \
        FRONTEIRA_PADRAO_SH="$(chamada_sh "$cmd_sm")" FRONTEIRA_PADRAO_PY="$(chamada_py "$cmd_sm")" varrer "${lista[@]}"
    )"

    awk '!/^#/ && NF && NF < 3 { print "exceção incompleta na linha " FNR ": " $0 }' "$excecoes"
    awk '!/^#/ && NF >= 3 { print $1 }' "$excecoes" | sort | uniq -c |
      while read -r n c; do
        if [[ -z "${teto[$c]+x}" ]]; then echo "contrato desconhecido na lista de exceções: $c"
        elif ((n > teto[$c])); then echo "teto excedido: $c tem $n exceções, o teto é ${teto[$c]}"
        fi
      done
    # Comparação como multiconjunto de ARQUIVO<TAB>TRECHO: linhas idênticas no mesmo arquivo contam uma a uma.
    awk '!/^#/ && NF >= 3 { a = $2; sub(/^[[:space:]]*[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+/, ""); sub(/[[:space:]]+$/, ""); print a "\t" $0 }' "$excecoes" |
      sort >"$tmp/excecoes"
    [[ -n "$achados" ]] && cut -f1,3 <<<"$achados" | sort >"$tmp/achados" || : >"$tmp/achados"
    comm -23 "$tmp/achados" "$tmp/excecoes" | awk -F'\t' 'NR == FNR { novo[$1 "\t" $2]; next } ($1 "\t" $3) in novo { print "fora da lista: " $1 ":" $2 ": " $3 }' - <(printf '%s\n' "$achados")
    comm -13 "$tmp/achados" "$tmp/excecoes" | awk -F'\t' '{ print "exceção sem acoplamento: " $1 ": " $2 }'
  )
}

conferir "teto de cada contrato definido" [ "${#teto[@]}" -eq 3 ]
achados="$(problemas "$repo_jangada")"
conferir "nenhum acoplamento entre módulos fora da lista de exceções" [ -z "$achados" ]
[[ -n "$achados" ]] && printf '      %s\n' "$achados"

# O teste precisa falhar quando a fronteira é cruzada: prova em cópias.
copia() {
  rm -rf "$tmp/copia"
  mkdir -p "$tmp/copia/testes"
  cp -a "$repo_jangada"/{bin,agentes,nucleo,orquestracao,delegacao,provedores,validacao,install,install.sh} "$tmp/copia/"
  cp -a "$repo_jangada/testes/contratos" "$tmp/copia/testes/"
}
acrescentar() { printf '%s\n' "$2" >>"$tmp/copia/$1"; }
apontado() { grep -qxF -- "$1" <<<"$(problemas "$tmp/copia")"; }

copia
conferir "cópia intacta passa" [ -z "$(problemas "$tmp/copia")" ]
acrescentar bin/jangada-fila 'hyprctl dispatch exit'
conferir "hyprctl novo em arquivo do Core é apontado" \
  apontado "fora da lista: bin/jangada-fila:$(wc -l <"$tmp/copia/bin/jangada-fila"): hyprctl dispatch exit"
# Exceções novas até passar do teto, qualquer que seja a contagem atual.
for ((i = $(grep -c '^K3 ' "$tmp/copia/testes/contratos/fronteiras-excecoes.txt"); i <= teto[K3]; i++)); do
  acrescentar testes/contratos/fronteiras-excecoes.txt 'K3 bin/jangada-fila hyprctl dispatch exit'
done
conferir "exceção nova na lista estoura o teto do contrato" \
  apontado "teto excedido: K3 tem $((teto[K3] + 1)) exceções, o teto é ${teto[K3]}"

copia
acrescentar bin/jangada-fila '# hyprctl e waybar citados em comentário
x=1 # notify-send no fim da linha
cat <<EOF
uso: rode hyprctl reload e "$JANGADA_CORE_PATH/bin/jangada-tarefas"
EOF
echo "abra o jangada-painel para ver"'
acrescentar nucleo/acoes.py '

def _exemplo():
    """Avisa a waybar.

    Chama hyprctl, notify-send e "$JANGADA_CORE_PATH/bin/jangada-tarefas".
    """'
conferir "comentário, texto de ajuda e docstring do Core não são apontados" [ -z "$(problemas "$tmp/copia")" ]

copia
for linha in 'if jangada-painel; then :; fi' 'command jangada-tarefas --nova' \
  "printf '%s\\n' ' # exemplo'; hyprctl dispatch exit" 'VAR=1 jangada-painel' 'env jangada-tarefas --nova' \
  'cat <<EOF' 'uso: $(hyprctl dispatch exit)' 'EOF'; do
  acrescentar bin/jangada-fila "$linha"
  [[ "$linha" == *EOF ]] && continue
  conferir "chamada escondida no Core é apontada: $linha" \
    apontado "fora da lista: bin/jangada-fila:$(wc -l <"$tmp/copia/bin/jangada-fila"): $linha"
done

copia
acrescentar bin/jangada-fila 'pkill -RTMIN+10 -x waybar 2>/dev/null || true'
acrescentar testes/contratos/fronteiras-excecoes.txt 'K3 bin/jangada-fila pkill -RTMIN+10 -x waybar 2>/dev/null || true'
sed -i '/pkill -RTMIN+10 -x waybar/d' "$tmp/copia/bin/jangada-fila"
conferir "acoplamento retirado com a exceção ainda na lista é apontado" \
  apontado "exceção sem acoplamento: bin/jangada-fila: pkill -RTMIN+10 -x waybar 2>/dev/null || true"
sed -i '\|^K3 bin/jangada-fila |d' "$tmp/copia/testes/contratos/fronteiras-excecoes.txt"
conferir "lista menor que o teto passa" [ -z "$(problemas "$tmp/copia")" ]

((falhas == 0)) && echo "tudo certo" || echo "$falhas falha(s)"
exit $((falhas > 0))
