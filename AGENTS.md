# Instruções para agentes de IA neste repositório

Este repositório é o **jangada-core**: a camada de sessões de agentes de IA
(isolamento, validação cruzada, delegação, fila e provedores). Antes de
alterar qualquer coisa, leia o [README.md](README.md) curto e o documento de
`docs/` sobre o assunto da tarefa, indicado na tabela do README.

## Regras

1. **Isolamento.** Nada do jangada pode escrever em `~/.config/hypr`, na
   configuração do niri ou em outra sessão existente. Tudo vai para
   `~/.config/jangada`, `~/.local/share/jangada-core` e `~/.local/state/jangada`.
   As únicas exceções são as de "Exceções à regra 1", abaixo; uma escrita
   nova fora dessas pastas entra na lista antes de entrar no código.
2. **Instalação repetível.** Cada etapa de `install/` precisa poder rodar de
   novo sem efeito colateral e respeitar `JANGADA_SIMULAR=1` (usar `executar`
   e `como_root` de `install/lib.sh` para todo comando que altera o sistema).
3. **Cópia antes de alterar.** Arquivos existentes só mudam depois de
   `copia_seguranca`. Arquivos do usuário são criados com `copiar_se_ausente`.
4. **Fronteira com as outras aplicações.** O Core nunca chama o Shell ou o
   Monitor por `$JANGADA_CORE_PATH`. Comandos deles são procurados no PATH com
   `command -v`, e a ausência não é erro. O `testes/fronteiras.sh` confere.
5. **Verificação.** Rode `testes/verificar.sh` antes de concluir qualquer mudança.
6. **Textos.** Documentação e mensagens em português, sem travessões, sem
   adjetivação desnecessária e sem estrangeirismos quando houver termo em
   português de uso corrente.
7. **Pegadinhas resolvidas.** Um comportamento inesperado de ferramenta que
   custou investigação (agy, tmux, bubblewrap) vai também para a skill em
   `agentes/claude/skills/jangada/`, no guia do assunto.
8. **Mensagens de commit.** Elas alimentam o `CHANGELOG.md`. Use
   `feat(área): ...` para novidade e `fix(área): ...` para correção. O
   `CHANGELOG.md` não se edita à mão: ele é gerado por
   `jangada-versao --lancar X.Y.Z`.
9. **Modelo de ameaça.** O agente é tratado como possivelmente hostil: ele lê
   conteúdo de fora, e uma injeção de prompt o faz agir contra o usuário.
   Nada que ele pode gravar (worktree, cópia de trabalho, estado das sessões)
   roda fora do isolamento sem conferência, e conteúdo de fora que chega a
   um agente (log, título de janela, página) vai como dado, não instrução.

## Exceções à regra 1

Escritas fora de `~/.config/jangada`, `~/.local/share/jangada-core` e
`~/.local/state/jangada`, cada uma com o motivo. O `testes/regra1.sh` confere
que todo caminho de fora escrito por extenso em `bin/`, `install/` e
`install.sh` está nesta lista ou na lista de caminhos só lidos do próprio
teste. Caminho montado em variável escapa da conferência e precisa entrar aqui
do mesmo jeito.

| Caminho | Quem grava | Para quê |
|---|---|---|
| `~/.claude/settings.json`, `~/.claude/skills`, `~/.claude/agents` | `install/50-agentes.sh` | hooks das sessões e links para as skills e os subagentes de `agentes/claude` |
| `~/.claude` (`settings.local.json`, `CLAUDE.md`, `commands`, `hooks`, `plugins`, `output-styles`, `shell-snapshots`, `session-env`, `ide`) | `jangada-isolar` | criados vazios quando faltam, para o bind do isolamento |
| `~/.claude` (`projects`, `file-history`, `sessions`, `todos`, `plans`, `paste-cache`, `jobs`, `logs`, `agent-memory`, `history.jsonl`), ou a pasta de `CLAUDE_CONFIG_DIR` | `jangada-isolar` | criados vazios quando faltam, para receber por cima os dados da sessão |
| `~/.gemini/config` (`hooks.json`, `agents.json`, `skills`) | `install/50-agentes.sh` | hooks, subagentes e skills do agy |
| `~/.codex/skills` (ou `skills` na pasta de `CODEX_HOME`) | `install/50-agentes.sh` | link para a skill `coordenador` |
| `~/.gemini/antigravity-cli` (`settings.json`, `bin`) | `jangada-worktree-preparar`, `jangada-agente-fim`, `jangada-isolar` | confiança do agy no worktree e pasta bin para montar isolada; o original fica em `settings.json.jangada-orig`; dentro do isolamento a pasta inteira vem dos dados da sessão |
| `~/.local/bin` | `install/20-comandos.sh` | invólucros `jangada*` que chamam os comandos de `bin/`; arquivo alheio com o mesmo nome não é sobrescrito |
| `~/.local/share/jangada-worktrees` | `jangada-agente` | worktrees das sessões de agente |
| Repositórios em `JANGADA_PROJETOS` | `jangada-agente`, `jangada-agente-fim` | ramos `agente/*`, registro dos worktrees e a integração que o usuário confirma |
| Pasta atual, com `--saida` | `jangada-avaliar-ollama` | fontes sintéticas e registros da avaliação local, em uma pasta nova por execução |
| `~/.cache/jangada` | `jangada-delegar` | cache da cota do agy |
| `~/.cache/cliphist` | `jangada-isolar` | pasta criada com 0700 para poder ocultá-la do agente |
| `$XDG_RUNTIME_DIR/jangada-isolar` | `jangada-isolar` | soquetes do proxy do D-Bus e, em `atendente-*`, o soquete do atendente da revisão |
| `$TMPDIR/jangada-consulta-*` (ou `/tmp/jangada-consulta-*`) | `nucleo/consultas.py` | cópia privada temporária do SQLite e WAL, removida ao fechar a consulta; evita gravar arquivos auxiliares na origem |

Pacotes, serviços do systemd e o estado dos serviços mudam pelos comandos do
próprio sistema (`pacman`, `systemctl`) e não entram na conta.
