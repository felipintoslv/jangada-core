# Regras automáticas

O jangada confere algumas regras de texto e de código em dois momentos: ao
gravar um arquivo numa sessão de agente (aviso) e no `jangada-validar`
(reprovação). Também lembra o coordenador de registrar decisões e, nos
projetos de pesquisa, as regras de escrita e de figura.

## Aviso ao gravar

`bin/jangada-hook-regras gravacao` roda depois de cada gravação. A
conferência desta seção só age quando `JANGADA_SESSAO` está definida; fora de
sessão de agente, só o lembrete de pesquisa (seção seguinte) age. O aviso
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

## Regras dos projetos de pesquisa

O mesmo `jangada-hook-regras gravacao` lembra ao agente as regras de escrita
e de figura do dono quando ele grava num projeto de pesquisa. Vale com e sem
`JANGADA_SESSAO`: o dono escreve nesses projetos também com o Claude comum.

- **Marca:** um arquivo `.jangada/pesquisa`, que pode ser vazio, na pasta do
  projeto. O hook resolve links e `..` do caminho gravado e procura a marca
  na pasta do arquivo e nas de cima, até a raiz do Git. Sem a marca, nada
  acontece.
- **Repositório do jangada:** a pasta que tem `bin/jangada-hook-regras` (a
  cópia instalada, a de desenvolvimento e os worktrees) fica de fora, com ou
  sem marca.
- **Escrita:** ao gravar `.md`, `.qmd`, `.Rmd`, `.tex` ou `.docx`.
- **Figura:** ao gravar `.R` ou `.py` que gera gráfico (ggplot2, matplotlib,
  seaborn, plotly, `savefig`, `salvar_figura`, `plot(`, `png(` e afins).
- **Uma vez por conversa e por tipo:** a marca do aviso dado é uma pasta
  vazia `$JANGADA_ESTADO/agentes/avisos-pesquisa/<session_id>.<tipo>`, a
  única pasta do estado gravável no isolamento. Pastas com mais de 7 dias são
  apagadas na gravação seguinte num projeto de pesquisa. Se `agentes/` ou
  `avisos-pesquisa` for link, a marca não é gravada. Sem `session_id` no
  evento, ou sem poder gravar a marca, o lembrete vai a cada gravação.
- **Texto:** sai das seções `## Escrita` e `## Figuras` de
  `agentes/regras-pesquisa.md`, a fonte única. O lembrete não traz nome nem
  conteúdo do arquivo gravado.

As skills `relatorio-academico`, `graficos`, `conferir-citacao`,
`conferir-referencias` e `fichamento` detalham essas regras.

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

`install/50-agentes.sh` mescla os novos hooks no `settings.json` do Claude e
liga as skills. O `jangada-update` não roda esse passo; numa instalação
existente, a migração `202610171200-ligar-hooks-e-skills-do-claude.sh`
reaplica as duas ligações com as mesmas funções de `install/lib.sh`. O Codex
não precisa de mudança.
