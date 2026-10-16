---
name: jangada
description: >
  Use ao mexer no jangada-core, a camada de agentes: arquivos em
  ~/.config/jangada, ~/.local/share/jangada-core ou ~/.local/state/jangada;
  comandos jangada-*; sessões de agentes em tmux -L jangada, worktrees em
  ~/.local/share/jangada-worktrees, hooks do Claude Code e a revisão cruzada
  com o Antigravity (agy). Não use para configurar o niri, o Plasma ou
  ~/.config/hypr.
---

# jangada-core

Camada para lançar, acompanhar e encerrar agentes de IA: sessões de autor e
revisor, isolamento, validação cruzada, delegação e fila. A área de trabalho
(Hyprland, barra, temas) é do jangada-shell, e o painel e os indicadores são do
comandos opcionais fora do Core por ora; ambos são opcionais e o Core os acha pelo PATH. Cada assunto
tem um guia próprio nesta pasta; leia o que corresponde à tarefa antes de
alterar qualquer coisa:

| Assunto | Guia |
|---|---|
| Sessões de agentes, estado, hooks, worktrees, `jangada-validar` e agy | [agentes.md](agentes.md) |

## Onde cada coisa fica

| Papel | Caminho |
|---|---|
| Repositório de trabalho (editar e fazer commit aqui) | a cópia de trabalho do jangada-core |
| Cópia instalada (nunca editar) | `~/.local/share/jangada-core` (`$JANGADA_CORE_PATH` na sessão) |
| Ajustes do usuário | `~/.config/jangada` (`jangada.conf`) |
| Estado (sessões de agentes, pareceres) | `~/.local/state/jangada` |

Dentro do repositório: `bin/` (comandos), `agentes/` (`perfis`, `claude`,
`agy`, `tmux`), `nucleo/`, `orquestracao/`, `delegacao/`, `provedores/`,
`validacao/`, `testes/`, `install/` e `docs/`.

Pegadinhas:

- Comando chamado pelo caminho real acha o `jangada-config` ao lado do próprio
  arquivo. Pelo mesmo motivo, não passe `realpath` em caminho de comando.
- Para achar a raiz, use `JANGADA_CORE_PATH`; para importar o núcleo,
  `JANGADA_CORE_PY`, que no Core vale o mesmo que `JANGADA_CORE_PATH`.
- Cópia de só uma parte do repositório (`cp -a bin`) deixa o comando sem os
  pacotes Python. Um teste que monta árvore temporária copia `bin/` e as
  pastas que o comando usa.
- Comando do Shell ou do Monitor é procurado no PATH (`command -v`) e a
  ausência não é erro. O Core nunca chama outra aplicação por `$JANGADA_CORE_PATH`.

Atualizar a cópia instalada é buscar a origem e aplicar com
`git merge --ff-only` num terminal, depois de conferir os commits novos. Com
`~/.config/jangada/allowed_signers`, só se aplicam commits assinados; os do
agente saem sem assinatura, e o usuário os assina com `jangada-assinar` num
terminal comum. O `jangada-agente-fim --integrar` não assina nem atualiza a
cópia instalada. Git sobre pasta que um agente pode ter gravado roda com
`jangada_git_seguro` (`bin/jangada-config`), que desliga fsmonitor, hooks,
pager e `sshCommand` do repositório.

## Regras que não mudam

1. **Isolamento.** Nada do jangada escreve em `~/.config/hypr`, na
   configuração do niri ou em outra sessão. Ajustes do usuário ficam em
   `~/.config/jangada`.
2. **Antes de concluir**, rode `testes/verificar.sh` na cópia de trabalho.
3. **Testar a cópia de trabalho:** o shell da sessão herda `JANGADA_CORE_PATH`
   apontando para a cópia instalada. Rode com `JANGADA_CORE_PATH=$PWD bin/...`.
4. **Textos** em português, sem travessões, sem adjetivação desnecessária.
5. **Commits** sem linha `Co-Authored-By`.

## Diagnóstico rápido

- Sessão de agente que não sobe: veja `~/.local/state/jangada/agentes/` e o
  guia [agentes.md](agentes.md).
- `testes/verificar.sh` confere sintaxe, lint e contratos da cópia.
