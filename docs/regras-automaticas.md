# Regras automáticas

O jangada confere algumas regras de texto e de código em dois momentos: ao
gravar um arquivo numa sessão de agente (aviso) e no `jangada-validar`
(reprovação). Também lembra o coordenador de registrar decisões.

## Aviso ao gravar

`bin/jangada-hook-regras gravacao` roda depois de cada gravação, só quando
`JANGADA_SESSAO` está definida. Fora de sessão de agente não faz nada. O aviso
volta ao modelo como `additionalContext` e não bloqueia a ferramenta.

| Arquivo | Regra |
| --- | --- |
| Qualquer arquivo de texto | sem o valor de `$HOME`; use `~` ou caminho relativo |
| `.md` | sem travessão (U+2014) |
| `.sh` ou script com `#!` de bash | `shellcheck -x -S warning` |
| `.py` | sintaxe Python, sem gravar `__pycache__` |

Cada conferência tem 5 segundos; o hook lê até 4 MiB de entrada, confere até
20 arquivos de até 2 MiB e sai com 0 em silêncio em qualquer erro.
`JANGADA_HOOK_DESLIGADO=1` desliga o hook.

- **Claude Code:** `PostToolUse` com o filtro `Edit|Write|MultiEdit|NotebookEdit`
  em `agentes/claude/hooks.json`.
- **Codex:** o hook `PostToolUse` que já existe (`jangada-hook-codex
  trabalhando`) repassa a saída do `jangada-hook-regras`. Os caminhos vêm das
  linhas `*** Add File:`, `*** Update File:` e `*** Move to:` do
  `apply_patch`. A configuração dos hooks do Codex não muda, então a
  confiança gravada por hash continua válida.

## Reprovação no jangada-validar

A verificação `texto` reprova somente linhas acrescentadas pelo diff: o valor
de `$HOME` em arquivo de texto e o travessão em `.md`. Arquivos novos contam
inteiros. `CHANGELOG.md` fica de fora. Shellcheck e sintaxe Python continuam
nas verificações que já existiam.

## Lembrete ao coordenador

`bin/jangada-hook-regras coordenacao` roda no evento `SessionStart` do Claude
Code, com o filtro `startup|resume|compact`, só sem `JANGADA_SESSAO` e só
quando a pasta (ou a raiz do Git) tem `.jangada/coordenacao.md`. O hook não
grava nada no arquivo.

- `startup` e `resume`: pede que cada decisão seja registrada assim que for
  tomada, porque o resumo e o encerramento perdem o que não estiver no arquivo.
- `compact`: logo depois do resumo, pede que o modelo confira se as decisões
  anteriores estão no arquivo.

O `PreCompact` foi descartado porque não entrega texto ao modelo, e o fim da
sessão não tem resposta do modelo depois. Fonte: os esquemas de hook do Claude
Code 2.1.302 instalado (`SessionStart` aceita `additionalContext`; `PreCompact`
não).

## Instalação

`install/50-agentes.sh` mescla os novos hooks no `settings.json` do Claude.
O `jangada-update` não roda esse passo; uma instalação existente precisa
rodá-lo de novo ou de uma migração. O Codex não precisa de mudança.
