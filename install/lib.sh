#!/usr/bin/env bash
# Funções compartilhadas pelas etapas de instalação e pelos comandos jangada-*.
# Este arquivo é carregado com `source`; não executa nada sozinho.

JANGADA_CORE_PATH="${JANGADA_CORE_PATH:-$HOME/.local/share/jangada-core}"
JANGADA_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/jangada"
JANGADA_ESTADO="${XDG_STATE_HOME:-$HOME/.local/state}/jangada"
JANGADA_SIMULAR="${JANGADA_SIMULAR:-0}"

export JANGADA_CORE_PATH JANGADA_CONFIG JANGADA_ESTADO

if [[ -t 1 ]]; then
  _cor_info=$'\e[36m'; _cor_ok=$'\e[32m'; _cor_aviso=$'\e[33m'; _cor_erro=$'\e[31m'; _cor_fim=$'\e[0m'
else
  _cor_info=""; _cor_ok=""; _cor_aviso=""; _cor_erro=""; _cor_fim=""
fi

info()  { printf '%s==>%s %s\n' "$_cor_info" "$_cor_fim" "$*"; }
ok()    { printf '%s ok%s %s\n' "$_cor_ok" "$_cor_fim" "$*"; }
aviso() { printf '%s !!%s %s\n' "$_cor_aviso" "$_cor_fim" "$*" >&2; }
erro()  { printf '%sERRO%s %s\n' "$_cor_erro" "$_cor_fim" "$*" >&2; }
morrer() { erro "$*"; exit 1; }

simulando() { [[ "$JANGADA_SIMULAR" == "1" ]]; }

# Executa um comando, ou apenas o mostra quando JANGADA_SIMULAR=1.
executar() {
  if simulando; then
    printf '   [simulação] %q' "$1"; shift
    (($#)) && printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

# Executa como root. Na simulação, apenas mostra.
como_root() {
  if [[ $EUID -eq 0 ]]; then
    executar "$@"
  else
    executar sudo "$@"
  fi
}

tem_comando() { command -v "$1" >/dev/null 2>&1; }

# Pergunta sim ou não. Resposta padrão no segundo argumento (s ou n).
# Sem terminal interativo, assume o padrão.
confirmar() {
  local pergunta="$1" padrao="${2:-n}" resposta opcoes="[s/N]"
  [[ "$padrao" == "s" ]] && opcoes="[S/n]"
  if [[ ! -t 0 ]] || simulando; then
    [[ "$padrao" == "s" ]]
    return
  fi
  read -r -p "$pergunta $opcoes " resposta
  resposta="${resposta:-$padrao}"
  [[ "${resposta,,}" == s* ]]
}

# Cria cópia de segurança com data ao lado do arquivo, se ele existir.
copia_seguranca() {
  local arquivo="$1" destino
  [[ -e "$arquivo" ]] || return 0
  destino="$arquivo.jangada-$(date +%Y%m%d-%H%M%S).bak"
  if [[ -w "$(dirname "$arquivo")" ]]; then
    executar cp -a "$arquivo" "$destino"
  else
    como_root cp -a "$arquivo" "$destino"
  fi
  info "cópia de segurança: $destino"
}

# Troca o conteúdo de DESTINO pelo de ORIGEM com rename: uma interrupção deixa
# o arquivo antigo inteiro, nunca truncado. Segue link simbólico e mantém as
# permissões; sem poder renomear, regrava no lugar. Igual a
# jangada_gravar_atomico (bin/jangada-config), que esta lib não carrega.
gravar_atomico() {
  local origem="$1" destino novo
  destino="$(realpath "$2" 2>/dev/null)" || destino="$2"
  if novo="$(mktemp "$destino.jangada-XXXXXX" 2>/dev/null)"; then
    if cat "$origem" >"$novo" && chmod --reference="$destino" "$novo" 2>/dev/null \
      && mv -f "$novo" "$destino" 2>/dev/null; then
      return 0
    fi
    rm -f "$novo"
  fi
  cat "$origem" >"$destino"
}

# Copia um arquivo modelo para o destino apenas se o destino ainda não existe.
copiar_se_ausente() {
  local origem="$1" destino="$2"
  if [[ -e "$destino" ]]; then
    ok "mantido (já existe): $destino"
    return 0
  fi
  executar mkdir -p "$(dirname "$destino")"
  executar cp "$origem" "$destino"
  ok "criado: $destino"
}

# Lê uma lista de pacotes, ignorando comentários e linhas vazias.
ler_lista() {
  sed -e 's/#.*//' -e 's/[[:space:]]*$//' "$1" | awk 'NF'
}

# Detecta o ajudante do AUR disponível (paru ou yay).
ajudante_aur() {
  if tem_comando paru; then echo paru
  elif tem_comando yay; then echo yay
  fi
}

# Instala pacotes: os que existem nos repositórios oficiais vão pelo pacman,
# os demais pelo ajudante do AUR. Pacotes já instalados são ignorados.
# Pacotes que não existem em lugar nenhum são listados, sem interromper.
instalar_pacotes() {
  local -a oficiais=() aur=() ausentes=()
  local pacote aur_cmd
  aur_cmd="$(ajudante_aur)"

  for pacote in "$@"; do
    if pacman -Qq "$pacote" >/dev/null 2>&1; then
      continue
    elif pacman -Si "$pacote" >/dev/null 2>&1; then
      oficiais+=("$pacote")
    elif [[ -n "$aur_cmd" ]] && "$aur_cmd" -Si "$pacote" >/dev/null 2>&1; then
      aur+=("$pacote")
    else
      ausentes+=("$pacote")
    fi
  done

  if ((${#oficiais[@]})); then
    info "pacman: ${oficiais[*]}"
    como_root pacman -S --needed --noconfirm "${oficiais[@]}"
  fi
  if ((${#aur[@]})); then
    info "AUR ($aur_cmd): ${aur[*]}"
    executar "$aur_cmd" -S --needed "${aur[@]}"
  fi
  if ((${#ausentes[@]})); then
    aviso "não encontrados nos repositórios nem no AUR: ${ausentes[*]}"
    aviso "confira os nomes em install/pacotes/ e instale manualmente se necessário"
  fi
  return 0
}

# Sistema de arquivos da raiz.
fs_raiz() { findmnt -no FSTYPE / 2>/dev/null; }

# Carregador de boot detectado: limine, grub, systemd-boot ou desconhecido.
carregador_boot() {
  if [[ -f /boot/limine.conf || -f /boot/limine/limine.conf || -f /boot/EFI/limine/limine.conf ]] \
     || pacman -Qq limine >/dev/null 2>&1; then
    echo limine
  elif [[ -f /boot/grub/grub.cfg ]] || pacman -Qq grub >/dev/null 2>&1; then
    echo grub
  elif [[ -d /boot/loader/entries || -d /efi/loader/entries \
          || -d /boot/EFI/systemd || -d /efi/EFI/systemd ]] \
     || { tem_comando bootctl && bootctl is-installed >/dev/null 2>&1; }; then
    # O bootctl precisa de root para abrir a partição EFI e responde
    # "Permission denied" para usuário comum, por isso o teste no sistema
    # de arquivos vem antes.
    echo systemd-boot
  else
    echo desconhecido
  fi
}

# Liga cada skill de agentes/claude/skills (jangada, relatorio-tecnico,
# relatorio-academico) em <pasta>/<nome>, apontando para o repositório
# instalado: uma atualização do repositório as atualiza junto com o resto. Um link antigo do
# jangada (outro JANGADA_CORE_PATH) é trocado; uma pasta ou link alheio com o mesmo
# nome fica como está, com aviso. Também é do jangada o link do layout antigo
# (versão anterior à divisão), que termina em /default/claude/skills/<nome>. O filtro so:<nome> liga só essa skill e
# menos:<nome> liga todas as outras.
# Uso: ligar_skills <pasta> <agente> [filtro].
ligar_skills() {
  local pasta="$1" agente="$2" filtro="${3:-}" origem nome destino atual
  for origem in "$JANGADA_CORE_PATH"/agentes/claude/skills/*/; do
    origem="${origem%/}"
    [[ -f "$origem/SKILL.md" ]] || continue
    nome="${origem##*/}"
    case "$filtro" in
      so:*) [[ "$nome" == "${filtro#so:}" ]] || continue ;;
      menos:*) [[ "$nome" != "${filtro#menos:}" ]] || continue ;;
    esac
    destino="$pasta/$nome"
    if [[ -L "$destino" ]]; then
      atual="$(readlink "$destino")"
      if [[ "$atual" == "$origem" ]]; then
        ok "skill $nome do $agente já ligada: $destino"
        continue
      fi
      if [[ "$atual" != */agentes/claude/skills/"$nome" && "$atual" != */default/claude/skills/"$nome" ]]; then
        aviso "$destino aponta para $atual, que não é do jangada; mantido"
        continue
      fi
    elif [[ -e "$destino" ]]; then
      aviso "$destino já existe e não é um link do jangada; mantido"
      continue
    fi
    executar mkdir -p "$pasta"
    executar ln -sfn "$origem" "$destino"
    ok "skill $nome do $agente ligada: $destino -> $origem"
  done
}

# Skills no Claude Code: ~/.claude/skills/<nome>.
ligar_skill_claude() { ligar_skills "$HOME/.claude/skills" "Claude Code"; }

# Skills no Antigravity: ~/.gemini/config/skills/<nome>, a raiz global que o
# agy percorre em toda conversa (a mesma pasta do hooks.json). O agy aceita o
# link simbólico e o frontmatter do Claude Code como está. Inclui coordenador;
# essa skill não concede autoria de tarefas ao agy.
ligar_skill_agy() { ligar_skills "$HOME/.gemini/config/skills" "agy"; }

# Skill coordenador no Codex: skills/coordenador na pasta do Codex (CODEX_HOME
# ou ~/.codex). O Codex 0.162 segue o link simbólico e lê o mesmo SKILL.md,
# com name e description no frontmatter. As demais skills não são ligadas.
ligar_skill_codex() { ligar_skills "${CODEX_HOME:-$HOME/.codex}/skills" "Codex" so:coordenador; }

# Liga os papéis de subagente do Claude Code (agentes/claude/agents/*.md) em
# ~/.claude/agents/<papel>.md, com as mesmas regras de ligar_skills: link
# antigo do jangada é trocado (inclusive o do layout antigo default/, da versão
# anterior à divisão), arquivo alheio com o mesmo nome fica.
ligar_agentes_claude() {
  local pasta="$HOME/.claude/agents" origem nome destino atual
  for origem in "$JANGADA_CORE_PATH"/agentes/claude/agents/*.md; do
    [[ -f "$origem" ]] || continue
    nome="${origem##*/}"
    destino="$pasta/$nome"
    if [[ -L "$destino" ]]; then
      atual="$(readlink "$destino")"
      if [[ "$atual" == "$origem" ]]; then
        ok "subagente ${nome%.md} do Claude Code já ligado: $destino"
        continue
      fi
      if [[ "$atual" != */agentes/claude/agents/"$nome" && "$atual" != */default/claude/agents/"$nome" ]]; then
        aviso "$destino aponta para $atual, que não é do jangada; mantido"
        continue
      fi
    elif [[ -e "$destino" ]]; then
      aviso "$destino já existe e não é um link do jangada; mantido"
      continue
    fi
    executar mkdir -p "$pasta"
    executar ln -sfn "$origem" "$destino"
    ok "subagente ${nome%.md} do Claude Code ligado: $destino -> $origem"
  done
}

# Registra os papéis de subagente do agy (agentes/agy/agents/<papel>/agent.md)
# em ~/.gemini/config/agents.json, como uma entrada de pasta: o agy lê os
# agentes direto do repositório instalado, sem nada em .agents/ dos projetos.
# Uma entrada antiga do jangada (outro JANGADA_CORE_PATH) é trocada; as demais
# ficam como estão. A entrada do layout antigo default/ (versão anterior à
# divisão), que termina em /default/agy/agents, também é trocada.
mesclar_agentes_agy() {
  local cfg="$HOME/.gemini/config/agents.json" pasta="$JANGADA_CORE_PATH/agentes/agy/agents" tmp existia=0
  if simulando; then
    info "[simulação] registraria os subagentes do jangada em $cfg"
    return 0
  fi
  mkdir -p "$(dirname "$cfg")"
  if [[ -f "$cfg" ]]; then existia=1; else echo '{}' >"$cfg"; fi
  tmp="$(mktemp)"
  if ! jq --arg p "$pasta" '
      .entries = ([(.entries // [])[] | select((.path // "") | (endswith("/agentes/agy/agents") or endswith("/default/agy/agents")) | not)]
                  + [{path: $p}])' "$cfg" >"$tmp"; then
    rm -f "$tmp"
    aviso "não consegui ler $cfg; subagentes do agy não registrados"
    return 0
  fi
  if ((existia)) && [[ "$(jq -cS . "$tmp")" == "$(jq -cS . "$cfg")" ]]; then
    rm -f "$tmp"
    ok "subagentes do agy já registrados"
    return 0
  fi
  ((existia)) && copia_seguranca "$cfg"
  gravar_atomico "$tmp" "$cfg" && rm -f "$tmp"
  ok "subagentes do agy registrados em $cfg"
}

# Instala os hooks do jangada para o Antigravity (agentes/agy/hooks.json) em
# ~/.gemini/config/hooks.json, a pasta global que o agy lê em toda conversa. O
# arquivo é um objeto de hooks com nome; o do jangada fica na chave "jangada",
# substituída inteira, e os demais ficam como estão. Arquivo vazio conta como
# {} (o jq não devolve nada para uma entrada vazia, e a mescla dava os hooks
# por instalados sem gravar nada).
mesclar_hooks_agy() {
  local cfg="$HOME/.gemini/config/hooks.json" novos tmp existia=0
  novos="$(sed "s|@JANGADA_CORE_PATH@|$JANGADA_CORE_PATH|g" "$JANGADA_CORE_PATH/agentes/agy/hooks.json")"
  if simulando; then
    info "[simulação] instalaria os hooks do jangada em $cfg"
    return 0
  fi
  mkdir -p "$(dirname "$cfg")"
  if [[ -f "$cfg" ]]; then existia=1; else echo '{}' >"$cfg"; fi
  tmp="$(mktemp)"
  if ! jq -n --argjson novos "$novos" '(first(inputs) // {}) + $novos' "$cfg" >"$tmp"; then
    rm -f "$tmp"
    aviso "não consegui ler $cfg; hooks do agy não instalados"
    return 0
  fi
  if [[ "$(jq -cS . "$tmp")" == "$(jq -cS . "$cfg")" ]]; then
    rm -f "$tmp"
    ok "hooks do agy já instalados"
    return 0
  fi
  # Arquivo criado agora não precisa de cópia de segurança.
  ((existia)) && copia_seguranca "$cfg"
  gravar_atomico "$tmp" "$cfg" && rm -f "$tmp"
  ok "hooks do agy instalados em $cfg"
}

# Mescla os hooks do jangada (agentes/claude/hooks.json) em
# ~/.claude/settings.json, evento por evento. Um hook já presente, reconhecido
# pelo comando sem o caminho (a cópia instalada pode ter mudado de lugar), não
# é duplicado; hooks alheios ficam como estão. Rodar de novo não muda nada, e
# por isso a mesma função serve à instalação e às migrações que trazem hooks
# novos. Arquivo vazio conta como {}, como em mesclar_hooks_agy.
mesclar_hooks_claude() {
  local cfg="$HOME/.claude/settings.json" novos tmp
  executar mkdir -p "$HOME/.claude"
  [[ -f "$cfg" ]] || { simulando || echo '{}' >"$cfg"; }
  novos="$(sed "s|@JANGADA_CORE_PATH@|$JANGADA_CORE_PATH|g" "$JANGADA_CORE_PATH/agentes/claude/hooks.json")"
  if simulando; then
    info "[simulação] mesclaria os hooks do jangada em $cfg"
    return 0
  fi
  tmp="$(mktemp)"
  if ! jq -n --argjson novos "$novos" --arg path "$JANGADA_CORE_PATH" '
      def chave: (.command // "") | sub("^.*/bin/"; "");
      def comandos: [.[]?.hooks[]? | chave];
      (first(inputs) // {})
      | ((.hooks // {})
       | walk(if type == "object" and has("command") and ((.command // "") | test("/bin/jangada-hook-"))
              then .command |= sub("^.*/bin/"; ($path + "/bin/"))
              else . end)) as $atuais
      | .hooks = (
          reduce ($novos.hooks | keys[]) as $ev ($atuais;
            (.[$ev] // []) as $lista
            | .[$ev] = $lista + [
                $novos.hooks[$ev][]
                | select((.hooks | map(chave)) - ($lista | comandos) | length > 0)
              ])
        )' "$cfg" >"$tmp"; then
    rm -f "$tmp"
    aviso "não consegui ler $cfg; hooks não mesclados"
    return 0
  fi
  # Compara o conteúdo, não o texto: o jq reformata o arquivo inteiro.
  if [[ "$(jq -cS . "$tmp")" == "$(jq -cS . "$cfg")" ]]; then
    rm -f "$tmp"
    ok "hooks do Claude Code já instalados"
    return 0
  fi
  copia_seguranca "$cfg"
  gravar_atomico "$tmp" "$cfg" && rm -f "$tmp"
  ok "hooks do Claude Code mesclados em $cfg"
}
