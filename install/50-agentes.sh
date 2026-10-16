# shellcheck shell=bash
# Etapa 50: camada de agentes (tmux isolado, hooks e skills do Claude Code, do agy e do Codex).

executar mkdir -p "$JANGADA_ESTADO/agentes"

# Hooks do Claude Code: acrescenta os hooks do jangada a ~/.claude/settings.json
# sem apagar hooks existentes. Só age se o Claude Code estiver instalado.
if tem_comando claude || [[ -d "$HOME/.claude" ]]; then
  mesclar_hooks_claude
  # Skills de agentes/claude/skills: regras e pegadinhas do jangada e os
  # protocolos de relatório técnico e acadêmico.
  ligar_skill_claude
  # Papéis de subagente, incluindo o supervisor de relatórios intermediários.
  ligar_agentes_claude
else
  aviso "Claude Code não encontrado; hooks e skills não instalados (rode ./install.sh 50 depois de instalar)"
fi

# Hooks do Antigravity (agy): estado da sessão na barra, como no Claude Code.
# As mesmas skills vão para ~/.gemini/config/skills.
if tem_comando agy || [[ -d "$HOME/.gemini" ]]; then
  mesclar_hooks_agy
  ligar_skill_agy
  mesclar_agentes_agy
fi

# Codex: só a skill coordenador, para a sessão comum que coordena tarefas.
if tem_comando codex || [[ -d "${CODEX_HOME:-$HOME/.codex}" ]]; then
  ligar_skill_codex
fi
