# Mapa dos registros

Levantamento feito em 26/09/2026 nesta máquina, para o `jangada-painel`.
Cada seção diz onde o registro fica, quem escreve, o formato, desde quando
existe, se é sobrescrito ou acumulado e quem apaga. Os números de linha são
do repositório em 26/09/2026. Os exemplos são reais, resumidos, com textos
trocados por `...`.

Desde a modularização 3.0, os comandos citados como `bin/jangada-*` são
links de compatibilidade: o arquivo mora em `bin/`, `shell/bin/` ou
`monitor/bin/`, e `default/painel/` mora em `monitor/painel/`. Só o
`jangada-config` e outros seis comandos compartilhados continuam em `bin/`.
O mapa das pastas está na seção Estrutura do [README](../README.md).

Caminhos usados abaixo:

- `$JANGADA_ESTADO` = `~/.local/state/jangada` (`bin/jangada-config:8`).
- `$JANGADA_WORKTREES` = `~/.local/share/jangada-worktrees`
  (`bin/jangada-config:23`, repetido em `~/.config/jangada/jangada.conf`).
  O nome da pasta é `jangada-worktrees`, sem barra entre as palavras.
- `$JANGADA_PROJETOS` = `~/Projetos`.

## Consultas de terminal e Monitor

O terminal consulta por sessão ou árvore de trabalho através de
`jangada-agentes --contexto-json` e `--sessao-worktree-json`, ambos versão 1.
O Monitor recebe filas, consumos, métricas e provedores por
`nucleo.consultas.consultar_filas`, sem descobrir bancos ou receber conexões.
O [contrato M1.2](coordenacao-central/11-consultas-modulos.md) define campos,
limites, seleção e erros. Os registros abaixo permanecem inalterados.
Texto repassado não é autorização; a consulta nunca inclui `revisoes/`.
`jangada-agentes --rodadas-json` lista as rodadas da seção 1 por sessão; em `revisoes/`, abre só o `validar.jsonl`.
`jangada-agentes --coordenadores-json` lista os coordenadores da seção 7 e
as tarefas de cada um, lidas das cópias `revisoes/SESSAO.json`.

## 1. validar.jsonl

Desde a Fase 4 da evolução 2.0, `execucao` é opcional nos eventos de sessão,
delegações e validações. Identifica a reserva da fila ou a execução da
sessão; registros antigos permanecem sem vínculo. `projeto.json`,
`atividades` e `execucoes` ficam no estado do projeto. As revisões da fila
registram hash do artefato, identidades e critérios no evento `revisada`.
Campos não medidos são nulos. Esses registros são observações; não
substituem a marca protegida que autoriza integração.

- **Caminho:** `$JANGADA_ESTADO/validar.jsonl`.
- **Quem escreve:** `bin/jangada-validar`, função `registrar` (linhas 80 a
  103). Chamada em quatro pontos: limite de rodadas (linha 346), reprovação
  na verificação local (linha 709), falha do revisor (linha 770) e parecer
  do revisor (linha 791). Registro criado no commit ed62434, de 26/09/2026.
- **Formato:** JSON Lines, uma linha por rodada, gravada com `>>`.
- **Exemplo:**

  ```json
  {"data":"2026-09-26T22:56:45-03:00","projeto":"jangada","rotulo":"jangada","rodada":1,"resultado":"revisar","etapa":"revisor","revisor":"agy","modelo":"","autor":"claude","arquivos":3,"mais":120,"menos":10,"itens":3,"segundos":180}
  ```

- **Campos:**
  - `data`: `date -Iseconds`, com fuso.
  - `projeto`: nome da pasta do repositório principal, tirado do
    `--git-common-dir`. Num worktree dá o nome real do repositório (por
    exemplo `Demanda CEBRAP`), não o nome da tarefa nem o slug.
  - `rotulo`: nome da sessão (`JANGADA_SESSAO`); fora de sessão, nome da
    pasta. Caracteres fora de `[A-Za-z0-9_.-]` viram `-`. Não é único no
    tempo: uma sessão nova com o mesmo nome repete o rótulo.
  - `rodada`: rodada da entrega atual. Recomeça em 1 depois de um APROVADO.
    Não é o N do arquivo `validacao-*-rN.md`, que só cresce.
  - `resultado`: `aprovado`, `revisar`, `erro` ou `limite`.
  - `etapa`: `revisor`, `local` (barrado pela verificação determinística)
    ou vazio (no `limite`).
  - `revisor`: `claude`, `agy` ou `codex`.
  - `modelo`: modelo pedido ao revisor. Fica vazio quando o revisor é o agy
    sem `--modelo`: o agy usa o padrão dele e o nome não é gravado. Com o
    Claude, o padrão é `sonnet`. Com Codex sem `--modelo`, o campo fica
    vazio e vale o padrão do CLI, sem a configuração do usuário.
  - `autor`: primeira palavra de `.agente` do `SESSAO.json`. Vazio fora de
    sessão.
  - `independente`: falso na autorrevisão (revisor igual ao autor ou
    `mesmo`) e quando a autoria não é confiável (autor vazio, ou revisão de
    fora do isolamento sem a cópia da sessão em `revisoes/`).
  - `execucao`: o `.execucao` do `SESSAO.json`; `null` sem vínculo.
  - `arquivos`, `mais`, `menos`: tamanho do diff (arquivo novo conta as
    linhas inteiras).
  - `itens`: linhas do parecer que começam por `N.`. É 0 no `limite` e no
    `erro`, que não têm parecer.
  - `segundos`: `$SECONDS` do script, do início ao registro.
  - `resposta` (opcional): classificação de `--resposta`, gravada apenas com
    parecer `aprovado` ou `revisar` na etapa `revisor`. Contém os inteiros
    `corrigidos`, `rejeitados` e `sem_classificar`. Registros antigos sem esse
    campo não têm classificação conhecida.
  - `responde_a` (opcional): `rodada`, `revisor` e `modelo` do último parecer
    registrado na rodada imediatamente anterior, com o mesmo `rotulo` e
    `execucao`. Ignora erros e outras etapas; vale `null` quando não encontrado.
  - `subagentes` (opcional, a partir de 27/09/2026): resumo dos subagentes
    e delegações da entrega, dado por `jangada-subagentes --entrega`, comando opcional, fora do Core por ora. Conta
    o que rodou na pasta desde a última aprovação (mtime do
    `validacao-*.aprovado`), desde a criação da sessão (`.desde` do
    arquivo da sessão) ou desde a data do commit base. Campos: `n`
    (subagentes mais delegações atendidas), `claude` (`n`, `tokens`;
    `principal` e `principal_cache_lido`, tokens da conversa principal na
    pasta, sem e com o cache lido), `agy` (`n`, `passos`), `delegadas_agy`
    (delegações atendidas), `codex_economico` (`n`), `local` (`n`,
    `atendidas`, `recusas`, `tokens_entrada`, `tokens_saida`,
    `medidas_entrada`, `medidas_saida`, `ferramentas_disponiveis`),
    `papeis` (contagem por papel),
    `retorno_tokens`, `edicoes`, `autorrevisao` e `recusas`. Falta nas
    linhas antigas, sem python3 e quando a leitura falha.
  - `subagentes_erro` (opcional, a partir de 27/09/2026): motivo de o
    resumo não ter sido gravado (código de saída do `jangada-subagentes`, comando opcional fora do Core por ora,
    tempo esgotado ou saída que não é um objeto JSON). O `jangada-validar`
    também o mostra no stderr.
- **Desde:** 26/09/2026 21:29 (primeira linha). Em 26/09/2026 havia 11
  linhas, todas do projeto jangada, revisor agy, autor claude, modelo vazio:
  7 aprovado e 4 revisar.
- **Acumulado.** Ninguém apaga. O `bin/jangada-isolar` libera a escrita
  desse arquivo para o agente isolado.

## 2. Pareceres em agentes/

Pasta `$JANGADA_ESTADO/agentes/`. Em 26/09/2026 havia 41 arquivos.

| Arquivo | Qtd. | Período (mtime) | Quem escreve | Quem apaga |
|---|---|---|---|---|
| `validacao-SESSAO-rN.md` | 16 | 26/09 20:54 a 23:37 | `bin/jangada-validar:773` (e a reprovação local, linhas 690 a 709) | `bin/jangada-agente-fim:261` a `:264`, ao encerrar a sessão |
| `validacao-SESSAO.aprovado` | 1 | 26/09 | `bin/jangada-validar:794` | `bin/jangada-agente-fim:264` |
| `validacao-SESSAO-rN.contexto.json`, `validacao-SESSAO-rN.verificacoes.tsv`, `validacao-SESSAO-rN.md.log` | não medido | não medido | `bin/jangada-validar`, a cada rodada: identidade e pedido da revisão (`:618` a `:627`), estado de cada verificação local (`:667`) e registro do revisor (`:1053`) | ninguém: `bin/jangada-agente-fim:268` a `:272` só apaga `-rN.md` e `.aprovado` |
| `parecer-SESSAO-rN.md` | 12 | 20/09 a 21/09 | antigo `bin/jangada-par` (removido no commit 411d273, 22/09) | ninguém |
| `avaliacao-SESSAO-rN.md` | 2 | 21/09 | antigo `bin/jangada-par` (avaliação do Claude sobre o parecer, não é revisão) | ninguém |
| `revisao-SESSAO-rN.log` | 5 | 20/09 a 21/09 | antigo `bin/jangada-par` (erro do agy, vários vazios) | ninguém |
| `revisao-claude-*.md` | 1 | 22/09 | revisão feita à mão | ninguém |
| `fim-SESSAO.log` | 2 | 22/09 e 25/09 | `bin/jangada-agente-fim:271` (saída do encerramento pela própria sessão) | sobrescrito no próximo fim da mesma sessão |

- **Primeira linha:** `STATUS: APROVADO` ou `STATUS: REVISAR`. O
  `jangada-validar` lê só a primeira linha não vazia, para um apontamento
  que cita o diff não aprovar a entrega, e aceita marcação de Markdown
  (`## STATUS:`, `**STATUS:**`) com a expressão da linha 756:
  `^[#[:space:]*]*STATUS:[[:space:]*]*APROVADO`. Exceções encontradas:
  `parecer-demanda-cebrap-r1.md` traz o STATUS na linha 3, depois de um
  título; os dois `avaliacao-*` começam com a mensagem de limite de sessão
  do Claude. Procure o STATUS nas primeiras linhas, não só na primeira, e
  deixe `avaliacao-*` e `revisao-*` fora da contagem de pareceres.
- **Conteúdo do `.aprovado`:** um objeto JSON (desde 05/10/2026) com
  `cabeca` (commit do ramo), `num` (último parecer), `limpo` (falso quando o
  worktree tinha alteração sem commit), `base`, `base_sha`, `ponto`,
  `candidate_sha`, `candidate_tree` (o que o revisor leu), `reviewer`,
  `model`, `author`, `local_verified` (verdadeiro quando a verificação local
  rodou inteira) e `independent` (falso na autorrevisão). Antes era uma
  linha `COMMIT N limpo|sujo`, que ainda é lida para o ponto de comparação e
  que o `--integrar` não aceita. Marca com `limpo` falso não move o ponto de
  comparação da próxima entrega. Esta pasta é gravável pelo
  agente isolado; a marca que o `--integrar` aceita fica na seção 2b.
- **O que dá para recuperar:**
  - sessão, do nome: `validacao-<rotulo>-rN.md` e `parecer-<sessao>-rN.md`;
  - projeto e tarefa: a sessão é `slug-do-repo` ou `slug-do-repo--tarefa`
    (`bin/jangada-agente:261`). O projeto sai como slug, não como nome real;
  - N do arquivo: número sequencial na sessão, não a rodada da entrega. A
    rodada se reconstrói pela sequência: recomeça depois de cada APROVADO
    (conferido: r6 a r16 batem com as rodadas do validar.jsonl);
  - resultado: pela linha do STATUS;
  - itens: linhas `N.` do parecer, como faz o `registrar`;
  - data: só pelo mtime. Não é confiável nos antigos:
    `parecer-cadeia_produtiva--fatores-r1.md` tem mtime depois do r2;
  - revisor e autor: não estão no arquivo. No `parecer-*` (jangada-par) o
    autor era o Claude e o revisor o agy. No `validacao-*`, só pelo
    `SESSAO.json`, enquanto a sessão existir.
  - Não há tamanho de diff nem duração.
- **Como não contar duas vezes:** a data do validar.jsonl e o mtime do
  parecer caem no mesmo segundo (conferido em r6 a r16). Um parecer entra
  na conta só se não houver linha do validar.jsonl com o mesmo `rotulo` e
  diferença de até 60 segundos entre `data` e mtime. Em 26/09/2026 isso
  deixa de fora r6 a r16 e recupera r1 a r5 da sessão jangada e os 12
  `parecer-*` do jangada-par. O `limite` e o `erro` não geram arquivo; esses
  só existem no validar.jsonl.
- **Perda:** os `validacao-*` de 22/09 a 26/09 de sessões já encerradas
  foram apagados pelo `jangada-agente-fim`. Não há como recuperá-los.

## 2b. Revisões feitas fora do isolamento (revisoes/)

Pasta `$JANGADA_ESTADO/revisoes/`, modo 700, criada a partir de 28/09/2026.
O `jangada-isolar` a oculta, então o agente isolado não lê nem grava ali.

| Arquivo | Quem escreve | Quem apaga |
|---|---|---|
| `SESSAO.json` | `bin/jangada-agente`, fora do isolamento, ao abrir a sessão: `sessao`, `raiz`, `worktree`, `ramo`, `base`, `agente`, `desde`, `tarefa`, `inicio`, `revisor` | `bin/jangada-agente-fim`, ao encerrar |
| `validacao-SESSAO-rN.md` | `bin/jangada-validar` rodado fora do isolamento, em geral pelo `--integrar` | `bin/jangada-agente-fim`, ao encerrar |
| `validacao-SESSAO.aprovado` | idem, no APROVADO: `COMMIT N limpo` ou `COMMIT N sujo` | `bin/jangada-agente-fim`, ao encerrar |
| `validar.jsonl` | idem, uma linha por rodada, no formato da seção 1 | ninguém |

- O `jangada-validar --metricas` lê os dois `validar.jsonl` e diz quantas
  aprovações vieram de fora.
- O painel marca a origem `revisoes` e forma entregas próprias
  (`ROTULO#fora-N`), sem somá-las às taxas das rodadas da sessão.
- Sessão aberta antes de 28/09/2026 não tem a cópia `SESSAO.json`; o
  `jangada-validar` avisa que base, tarefa e revisor vêm do estado gravável.
- Sessão aberta com `--sem-isolar` alcança esta pasta: nela a revisão de fora
  não protege nada.

## 3. Conversas do Claude Code

- **Caminho:** `~/.claude/projects/PASTA/SESSAO.jsonl` e, para subagentes,
  `~/.claude/projects/PASTA/SESSAO/subagents/agent-ID.jsonl` com
  `agent-ID.meta.json` ao lado. Na mesma pasta ficam `tool-results/`
  (saídas grandes de ferramenta, em `.txt`) e `memory/` (`.md`).
- **Quem escreve:** o Claude Code, a cada mensagem.
- **Tamanho em 26/09/2026:** 115 arquivos `.jsonl` (104 conversas e 11
  subagentes), 275,6 MB, o maior com 33,5 MB, em 30 pastas.
- **Datas:** linha mais antiga em 28/08/2026 10:29 UTC; mais recente em
  27/09/2026 02:42 UTC (26/09 23:42 no fuso local).
- **Acumulado dentro do arquivo, mas apagado por idade.** O
  `~/.claude/settings.json` não define `cleanupPeriodDays`, então vale o
  padrão de 30 dias. Evidência: o `stats-cache.json` registra a primeira
  sessão em 24/08/2026, e nenhuma linha anterior a 28/08 sobrou. A última
  limpeza está em `~/.claude/.last-cleanup` (26/09/2026 22:56 UTC).
- **Nome da pasta e cwd:** a pasta é o cwd do início da conversa com todo
  caractere fora de `[A-Za-z0-9]` trocado por `-`
  (`/home/u/.local/share/jangada-worktrees/cadeia_produtiva/mapa` vira
  `-home-u--local-share-jangada-worktrees-cadeia-produtiva-mapa`;
  `Construção` vira `Constru--o`). A troca perde informação: use o `cwd`
  das linhas, não a pasta. O `cwd` muda dentro da conversa quando o agente
  entra em subpastas (até 5 valores numa conversa, 96 na pasta `~`).
- **Projeto a partir do cwd:**
  1. Se começa por `$JANGADA_WORKTREES/`, o componente seguinte é o slug do
     repositório e o outro é a tarefa
     (`~/.local/share/jangada-worktrees/cadeia_produtiva/mapa/fontes` dá
     `cadeia_produtiva`, tarefa `mapa`).
  2. Se começa por `$JANGADA_PROJETOS/`, o componente seguinte é o nome
     real (`Demanda CEBRAP`).
  3. `/tmp/claude-1000/...` são testes aninhados em pastas temporárias;
     `~` e o resto ficam como "outros".
  O validar.jsonl e o eventos-agentes.jsonl gravam o nome real; o worktree e
  o nome da sessão usam o slug (`bin/jangada-agente:133`: minúsculas,
  transliteração ASCII, `[^a-z0-9_-]` vira `-`). Para cruzar, passe todos
  pelo mesmo slug.

### Tipos de linha

Contagem em 26/09/2026 (conversas principais; subagentes entre parênteses):
`assistant` 13.817 (775), `attachment` 10.654 (685), `user` 7.763 (455),
`atis-latch` 2.671, `last-prompt` 2.646, `ai-title` 2.190, `mode` 2.175,
`permission-mode` 2.172, `system` 1.087 (3), `bridge-session` 847,
`file-history-snapshot` 560, `queue-operation` 495, `agent-name` 130,
`cost-state` 109, `file-history-delta` 95, `frame-link` 94,
`agent-setting` 13, `artifact-autoreact-ledger` 6,
`artifact-comment-monitor` 4, `continued-in` 2.

### Linhas `assistant`

Campos de topo usados: `timestamp` (UTC, com `Z`), `cwd`, `sessionId`,
`requestId`, `uuid`, `parentUuid`, `isSidechain`, `agentId` (subagente),
`entrypoint`, `gitBranch`, `version`, `sessionKind` (`bg` em tarefa de
fundo), `quotaLimits` (raro, ver abaixo).

`entrypoint` separa a origem: `cli` (terminal), `sdk-cli` (`claude -p`,
como a revisão do `jangada-validar` com o Claude e o antigo jangada-par) e
`claude-vscode`.

`message`: `id`, `model`, `content`, `stop_reason`, `usage` e outros.

Modelos vistos: `claude-opus-5` (12.312 linhas), `claude-opus-5-5` (1.968),
`claude-sonnet-5` (275), `claude-haiku-4-5-20251001` (16),
`claude-opus-4-8` (5) e `<synthetic>` (16, mensagem gerada pelo próprio
Claude Code, sem consumo; descarte).

`message.usage`, com exemplo:

```json
{"input_tokens": 2, "cache_creation_input_tokens": 31930, "cache_read_input_tokens": 0,
 "output_tokens": 590, "output_tokens_details": {"thinking_tokens": 330},
 "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
 "service_tier": "standard",
 "cache_creation": {"ephemeral_1h_input_tokens": 31930, "ephemeral_5m_input_tokens": 0},
 "inference_geo": "not_available", "iterations": [{"input_tokens": 2, "output_tokens": 590, "...": "..."}],
 "speed": "standard"}
```

- `input_tokens`, `output_tokens`, `cache_creation_input_tokens` e
  `cache_read_input_tokens` estão em todas as 14.592 linhas.
- `output_tokens_details.thinking_tokens` existe em 13.830 linhas (95%);
  é maior que zero em 11.588. Faz parte de `output_tokens` (no exemplo,
  330 de 590): não some os dois. Em 7 linhas passa de `output_tokens`,
  provavelmente linhas parciais. As linhas antigas não têm o campo.
- O texto do raciocínio não fica guardado: 5.346 dos 5.585 blocos
  `thinking` estão vazios.
- `iterations` repete o consumo por iteração. Use os campos de cima, não
  some `iterations`.

**Repetição:** a mesma resposta aparece em várias linhas, uma por bloco de
conteúdo (texto, raciocínio, cada `tool_use`). Foram 14.592 linhas para
7.183 respostas distintas por `(message.id, requestId)`. Além disso, 99
respostas aparecem em mais de um arquivo (conversa retomada ou continuada),
então a chave vale para o conjunto todo, não por arquivo. Em 10 respostas o
`usage` difere entre as linhas: a primeira traz `output_tokens` parcial
(por exemplo 16) e a última o valor final (250). O `jangada-consumo`, do Core,
guarda a primeira linha vista e conta a menos nesses casos. O coletor deve
ficar com a linha de maior `output_tokens` de cada chave.

**Limite de uso:** `quotaLimits` aparece em 15 linhas, só quando o limite
foi atingido: `{"status": "rejected", "rateLimitType": "five_hour",
"resetsAt": 1789875600, ...}`. Mostra os blocos que bateram no limite, não
os que chegaram perto.

### Blocos `tool_use` (em `message.content` das linhas `assistant`)

`{"type": "tool_use", "id": "toolu_...", "name": "Bash", "input": {"command": "...", "description": "..."}}`

- Contagem: Bash 6.135, Read 539, Edit 149, Write 98, Grep 96, WebSearch
  59, Glob 48, AskUserQuestion 33, ToolSearch 28, WebFetch 27, Agent 11,
  Skill 10 e outros.
- Alvo: `input.file_path` em Read, Edit e Write; `input.notebook_path` no
  NotebookEdit (nenhum visto); `input.command` no Bash;
  `input.run_in_background` no Bash em segundo plano.
- Capacidades para o espaço de ferramentas: `input.skill` no `Skill`
  (jangada, dataviz, artifact-design, run), `input.subagent_type` no
  `Agent` (só `general-purpose`), nome `mcp__SERVIDOR__FERRAMENTA` nas
  ferramentas MCP (nenhuma chamada registrada até 26/09/2026).

### Resultado de ferramenta (linhas `user`)

Em `message.content` vem
`{"type": "tool_result", "tool_use_id": "toolu_...", "content": "...", "is_error": true}`.
O nome da ferramenta não vem no resultado: ligue pelo `tool_use_id` ao
`tool_use.id` da linha `assistant` anterior. `content` é texto ou lista de
blocos `{"type": "text", "text": ...}`. `is_error` falta em 1.156 dos 7.299
resultados; trate ausência como falso.

A linha `user` traz também `toolUseResult`. No Bash que terminou com código
zero é um objeto com `stdout`, `stderr`, `interrupted`, `isImage`,
`noOutputExpected` e, às vezes, `returnCodeInterpretation`. No Bash com
erro vira texto: `"Error: Exit code 1\n..."`.

**Falha de Bash:** `is_error` verdadeiro e `content` começando por
`Exit code N` (210 casos). Não existe campo numérico com o código de saída.
Outros `is_error` do Bash não são falha de teste e devem ficar de fora:
`Permission for this action was denied` (10), `The user doesn't want to
proceed` (9), `<tool_use_error>Blocked: ...` (6), `This Bash command contains
multiple operations` (2), `Interrupted` (1). O `returnCodeInterpretation`
(`No matches found` em 81, `Files differ` em 4) marca código 1 que o Claude
Code não trata como erro (grep sem resultado, diff com diferença); esses
vêm com `is_error` falso. `interrupted` nunca foi verdadeiro. Bash em
segundo plano devolve só o id da tarefa; a falha dele não aparece no
resultado.

### Subagentes

- `agent-ID.jsonl`: mesmo formato; `sessionId` é o da conversa mãe,
  `agentId` o do subagente, `isSidechain` verdadeiro. O `cwd` pode ser outro
  (dois subagentes rodaram na pasta de memória).
- `agent-ID.meta.json`: `{"agentType": "general-purpose", "description":
  "...", "toolUseId": "toolu_...", "spawnDepth": 1, "requestShape":
  "background", "requestNonInteractive": true}`. O `toolUseId` liga ao
  `tool_use` do `Agent` na conversa mãe.
- 11 subagentes em 26/09/2026. O `find -name '*.jsonl'` do
  `jangada-consumo` (Core) já entra nessas pastas.
- **Totais na conversa mãe.** No primeiro plano, o `tool_result` do `Agent`
  traz `toolUseResult.totalTokens`, `totalDurationMs`, `totalToolUseCount`
  e o texto devolvido. No segundo plano, o `tool_result` só diz
  `status: async_launched`; os totais vêm depois numa linha `attachment`
  de tipo `queued_command`, com `attachment.usage` (`totalTokens`,
  `toolUses`, `durationMs`) e um `prompt` com `<task-notification>`,
  `<task-id>ID</task-id>` e `<status>completed</status>` (ou `killed`). O
  relatório chega à parte, numa mensagem que começa por "Another Claude
  session sent a message:" com `<agent-message from="ID">`.
- **`totalTokens` é o contexto do último turno** (entrada, cache criado,
  cache lido e saída), não a soma dos turnos. Sem linha na mãe (conversa
  antiga ou subagente morto), o `jangada-subagentes` (comando opcional, fora do Core por ora) usa a mesma conta no
  último turno do `agent-ID.jsonl`.

### Outras linhas úteis

- `cost-state` (109 linhas): totais da conversa calculados pelo Claude Code:
  `totalCostUSD`, `totalAPIDuration`, `totalToolDuration`,
  `totalDuration`, `totalLinesAdded`, `totalLinesRemoved`, `startTime` (ms)
  e `modelUsage` por modelo. É cumulativo; use só a última linha de cada
  sessão, se usar.
- `ai-title`: título da conversa.
- `continued-in`: `continuedInSessionId`, a conversa que continuou esta.

## 4. SESSAO.json

- **Caminho:** `$JANGADA_ESTADO/agentes/SESSAO.json`.
- **Quem escreve:** `bin/jangada-agente:499` a `:516` cria;
  `bin/jangada-hook-claude` (linha 82), `bin/jangada-hook-agy` e
  `bin/jangada-hook-codex` atualizam `estado`, `mensagem`, `atualizado` e
  `conversa`;
  `bin/jangada-validar:704` e `:786` gravam `validacao`; `bin/jangada-agentes` marca
  `interrompido` (função `marcar`).
- **Exemplo:**

  ```json
  {"sessao": "jangada", "dir": "~/Projetos/jangada", "raiz": "~/Projetos/jangada",
   "worktree": "", "ramo": "", "base": "", "agente": "claude", "comando": "claude",
   "isolar": true, "estado": "trabalhando", "mensagem": "...",
   "desde": "2026-09-26T18:01:48-03:00", "atualizado": "2026-09-26T23:41:38-03:00",
   "inicio": "fbaec5e...", "revisor": "agy",
   "conversa": "bf9108eb-a715-46b6-8a8f-0b090376baa5", "validacao": "r1: APROVADO (agy)",
   "delegar": "agy", "coordenador": "dono"}
  ```

- **Campos:** `sessao`, `dir`, `raiz`, `worktree`, `ramo`, `base`,
  `agente`, `comando`, `isolar`, `estado` (`iniciado`, `trabalhando`,
  `aguardando`, `concluido`, `interrompido`), `mensagem`, `desde`,
  `atualizado`, `execucao` (sempre gravado: o identificador devolvido por
  `jangada-projeto sessao-iniciar`), e quando houver `tarefa`, `perfil`,
  `atividade` e `tarefa_id` (vínculos dados por `--atividade` e
  `--tarefa-id`), `inicio` (commit),
  `revisor`, `conversa`, `validacao`, `delegar` (sempre gravado),
  `coordenador` (sempre gravado), `coordenador_sessao` e
  `pid` (só o antigo par; nenhum script grava hoje, e o
  `jangada-agente-fim` não o lê nem mata processo por ele).
- `jangada-agente-fim` (função `conferir_estado`) recusa, sem alterar nada,
  o estado cujo `ramo` não seja `agente/NOME`, cujo `worktree` não seja
  `$JANGADA_WORKTREES/REPO/NOME` (sem link simbólico e registrado como
  worktree da `raiz`, com o mesmo diretório git comum), cuja `raiz` não seja
  a raiz de um repositório ou cuja `base` não seja nome de ramo. O
  `--limpar-concluidos` de `bin/jangada-agentes` mostra as sessões marcadas
  como `concluido` e só encerra depois de confirmação.
- `comando` e `isolar` são só para consulta. A pasta `agentes/` é gravável
  de dentro do `jangada-isolar`, então a restauração (`restaurar` em
  `bin/jangada-agentes:244`) não executa o `comando` nem respeita o
  `isolar`: recompõe o comando a partir de `agente`, `dir`, `perfil`,
  `conversa` e `revisor` validados, e só `JANGADA_AGENTE_ISOLAR=0` na
  configuração tira o isolamento.
- `coordenador` é declarado na abertura por `--coordenador` do
  `jangada-agente`. Sem a opção, vale `JANGADA_COORDENADOR`; sem os dois,
  vale `"dono"`. Hooks e `jangada-validar` não o alteram. Serve só para
  exibição na Central e no painel: nenhuma permissão, revisão ou integração
  depende dele.
- `coordenador_sessao` é gravado a partir de 17/10/2026 só quando a tarefa
  é aberta de dentro de uma sessão do `jangada-coordenador`: vale
  `JANGADA_COORDENADOR` quando há registro em `coordenadores/` com esse
  nome. Vai também para a cópia em `revisoes/`.
- `conversa` é o `sessionId` do Claude (nome do `.jsonl`) ou o
  `conversationId` do agy (nome do `.db`). É o único lugar que liga a sessão
  do jangada à conversa.
- **Sobrescrito** a cada evento. Não tem histórico.
- **Quem apaga:** `bin/jangada-agente-fim:264`, ao encerrar;
  `limpar_orfaos` em `bin/jangada-agentes:133` a `:159`, quando a sessão
  tmux não existe mais: estado `concluido` ou `aguardando` fica 24 horas
  (`JANGADA_AGENTES_GUARDAR`), `interrompido` fica 168 horas; sessão sem
  pid em andamento vira `interrompido` em vez de sumir.
- **Desde:** um arquivo por sessão viva. Em 26/09/2026 só havia
  `jangada.json`.

## 5. foco.historico

- **Caminho:** `$JANGADA_ESTADO/agentes/foco.historico`.
- **Quem escreve:** `registrar_foco` em `bin/jangada-agentes:350` a `:356`,
  chamada por `focar`.
- **Formato:** uma sessão por linha, a mais recente no fim, sem repetição
  seguida. Sem horário. Exemplo: `jangada`, `tcc1`, `jangada`.
- **Sobrescrito:** reescrito inteiro a cada troca, com as últimas 20
  linhas. Em 26/09/2026 tinha 5 linhas.
- Serve para o `--anterior`, não para medir. O horário da troca passa a ir
  para o eventos-agentes.jsonl (seção 8).

## 6. agy (Antigravity)

### conversations/*.db

- **Caminho:** `~/.gemini/antigravity-cli/conversations/ID.db`, um SQLite
  por conversa, incluídas as conversas de subagente e as revisões feitas
  pelo `jangada-validar` com `agy -p`.
- **Tamanho em 26/09/2026:** 104 arquivos, 294 MB. Mais antigo em
  19/09/2026, dia da instalação do agy (`installation_id`). Nada foi
  apagado até agora; não achei regra de limpeza no `settings.json` do agy.
- **Abrir só para leitura:** `sqlite3.connect("file:ARQ?mode=ro", uri=True)`.
- **Tabelas:**
  - `trajectory_meta(trajectory_id, cascade_id, trajectory_type, source)`:
    uma linha; `cascade_id` é o nome do arquivo.
  - `steps(idx, step_type, status, has_subtrajectory, metadata,
    error_details, permissions, task_details, render_info, step_payload,
    step_format)`: um passo por linha; colunas em protobuf.
  - `gen_metadata(idx, data, size)`: uma linha por chamada ao modelo,
    protobuf.
  - `executor_metadata(idx, data)`, `parent_references(idx, data)`,
    `battle_mode_infos(idx, data)`: protobuf.
  - `trajectory_metadata_blob(id, data)`: uma linha, protobuf.
- **Datas:** `google.protobuf.Timestamp` (`{1: segundos, 2: nanos}`) no
  campo 1 de `steps.metadata` (criação do passo) e no campo 2 de
  `trajectory_metadata_blob.data` (início).
- **Pasta:** `trajectory_metadata_blob.data`, campo 1.1, em URI
  (`file:///home/u/Projetos/jangada`); 1.3 traz o remoto git e 1.4 o ramo.
- **Tokens:** não há esquema publicado. O que se vê decodificando o
  protobuf sem o `.proto`:
  - `gen_metadata.data`, campo 1.19: nome do modelo (`gemini-3.8-flash` em
    5.187 das 5.197 chamadas);
  - campo 1.4: inteiros nos campos 1, 2, 3, 5, 6, 9 e 10. Em 5.182 chamadas
    vale 3 = 9 + 10, o que sugere saída total = raciocínio + resposta. O
    campo 1 fica constante na conversa, o 5 cresce como cache lido, o 2
    varia. O mesmo bloco se repete em `steps.metadata`, campo 9;
  - campo 1.9.10: um número que cresce (contexto?) e 256000 (janela?).
  Nenhum desses significados foi conferido com um valor que o agy mostre.
  **Conclusão:** não há contagem de tokens confiável. O agy fica fora do
  consumo, e o painel diz isso.

### conversation_summaries.db

`~/.gemini/antigravity-cli/conversation_summaries.db`, tabela
`conversation_summaries`, em colunas SQL legíveis: `conversation_id`,
`title`, `step_count`, `last_modified_time`, `workspace_uris` (lista JSON,
às vezes vazia), `status`, `parent_conversation_id`, `nesting_depth` (0 ou
1 para subagente), `last_user_input_time`, entre outras. 105 linhas, de
19/09/2026 a 26/09/2026. Serve para contar conversas e passos por pasta sem
decodificar protobuf. É sobrescrita por conversa.

### Subagentes do agy

`~/.gemini/antigravity-cli/brain/CONVERSA/.system_generated/subagents/ID.json`:
`{"conversationId": "...", "subagentDescriptor": {"typeName": "research",
"role": "..."}, "state": "SUBAGENT_STATE_ALIVE", "spawnStepIndex": 48,
"workspaceUris": ["file:///home/u/Projetos/jangada"]}`. 10 arquivos, de
22/09 a 25/09/2026. Sem data no conteúdo (só mtime). A conversa do
subagente tem `.db` próprio.

## 7. Outros registros

- `~/.cache/jangada/consumo.json`: cache do `jangada-consumo` (Core),
  sobrescrito a cada 60 segundos. Campos `ativo`, `inicio`, `fim`,
  `mensagens`, `entrada`, `saida`, `cache_criado`, `cache_lido`, `total`.
  Só o bloco de 5 horas atual; sem histórico.
- `$JANGADA_ESTADO/migracoes/`: marcas de migrações aplicadas, gravadas
  pelo repositório jangada-shell. Fora do Core.
- `$JANGADA_ESTADO/tarefas/*.md`: especificações de tarefa escritas à mão.
- `$JANGADA_ESTADO/coordenadores/SESSAO.json` (pasta modo 700, a partir de
  17/10/2026): um por coordenador aberto pelo `jangada-coordenador`. Campos
  `sessao`, `projeto` (raiz absoluta), `provedor`, `estado` (`iniciado`,
  `trabalhando`, `aguardando`, `concluido`, `encerrado`), `ultima_linha`
  (até 200 caracteres, sem caracteres de controle), `desde`, `atualizado` e,
  depois do `--fim`, `encerrado` (data). O comando cria; os hooks do Claude e
  do Codex atualizam `estado`, `ultima_linha` e `atualizado` só com
  `JANGADA_COORDENADOR` definido, por arquivo temporário e `mv`. Ninguém
  apaga: o `--fim` só marca.
- `~/.claude/history.jsonl`: um pedido digitado por linha, `display`,
  `pastedContents`, `timestamp` (ms), `project` (cwd), `sessionId`. 2.617
  linhas desde 02/05/2026; não é apagado pela limpeza de 30 dias. Serve
  para contar pedidos por projeto e dia fora da janela das conversas.
- `~/.claude/stats-cache.json`: resumo do próprio Claude Code, de
  24/08/2026 a 21/09/2026 (`lastComputedDate`): `dailyActivity` (mensagens,
  sessões e ferramentas por dia), `dailyModelTokens` (total de tokens por
  modelo e dia, sem separar tipo), `modelUsage`, `hourCounts`. Sobrescrito;
  cobre dias que as conversas já perderam.
- `~/.gemini/antigravity-cli/history.jsonl`: pedidos ao agy, `display`,
  `timestamp` (ms), `workspace`, `conversationId`. 187 linhas desde
  19/09/2026.
- `~/.gemini/antigravity-cli/log/cli-DATA.log`: log do agy no formato glog,
  um por execução, 104 arquivos (6,2 MB) desde 19/09/2026. Não traz
  consumo; serve para achar erros do revisor.
- `~/.config/jangada/eventos.json`: agenda do `jangada-calendario`, sem
  relação com os agentes.

## 8. eventos-agentes.jsonl (novo, a partir de 26/09/2026)

- **Caminho:** `$JANGADA_ESTADO/eventos-agentes.jsonl`.
- **Quem escreve:** a função `jangada_registrar_evento` em
  `bin/jangada-config`, chamada por `bin/jangada-hook-claude` (mudança de
  estado, início e fim), `bin/jangada-hook-agy` (mudança de estado) e
  `bin/jangada-agentes`, função `focar` (troca de foco).
- **Formato:** uma linha por mudança de estado:

  ```json
  {"data": "2026-09-26T23:50:00-03:00", "sessao": "jangada--tarefa", "projeto": "jangada", "agente": "claude", "estado": "aguardando"}
  ```

  - `data`: ISO com fuso (`jangada_data_iso`).
  - `projeto`: último componente de `.raiz` (ou `.dir`) do `SESSAO.json`,
    nome real, não slug.
  - `agente`: `claude` ou `agy`.
  - `estado`: `inicio`, `trabalhando`, `aguardando`, `concluido`, `fim` ou
    `foco`. O `SESSAO.json` grava `iniciado`; aqui o valor é `inicio`.
  - `execucao`: o `.execucao` do `SESSAO.json`, quando tem a forma `exe-`
    mais 16 hexadecimais; senão `null`. Presente em toda linha nova.
- **Subagentes do Claude:** com o hook de subagentes do Claude Code
  (SubagentStart e SubagentStop), o `eventos-agentes.jsonl` ganha linhas
  com estado `subagente-inicio` e `subagente-fim`. Elas trazem três campos
  opcionais a mais: `subagente_id` (o `agent_id`, igual ao `agent-ID` de
  `subagents/` da conversa), `subagente_tipo` (o `agent_type`) e `conversa`
  (o `session_id`). Essas linhas não mudam o estado da sessão. Quem mede
  tempo por estado deve ignorá-las, como ignora `foco`.
- **Acumulado.** Ninguém apaga; o painel não depende de apagar.
- **Limites do registro:**
  - só sessões abertas pelo `jangada-agente` (com `JANGADA_SESSAO`);
  - o agy não tem evento de início, fim nem pedido de permissão: só
    `trabalhando` e `concluido`. Um agy parado numa pergunta conta como
    trabalhando;
  - no Claude, o aviso `idle_prompt` vira `concluido`, e o `SessionEnd`
    do `/clear` não gera linha;
  - os hooks rodam da cópia instalada em `~/.local/share/jangada-core/bin`
    (`~/.claude/settings.json`, `~/.gemini/config/hooks.json`). O registro
    só começa depois de instalar a versão nova.

## 9. delegacoes.jsonl (novo, a partir de 27/09/2026)

- **Caminho:** `$JANGADA_ESTADO/delegacoes.jsonl`.
- **Quem escreve:** `bin/jangada-delegar`, função `registrar`, uma linha
  por chamada, atendida ou recusada. O `bin/jangada-isolar` libera a
  escrita para o agente isolado.
- **Exemplo:**

  ```json
  {"data":"2026-09-27T09:10:00-03:00","sessao":"jangada","projeto":"jangada","pasta":"/home/u/Projetos/jangada","papel":"explorador","destino":"agy","modelo":"gemini-3.8-flash-low","segundos":41,"codigo_saida":0,"palavras":250,"tokens_retorno":420,"passos":18,"tokens_agy":61000,"cota_antes":93.87,"cota_depois":93.87,"recusa":false,"motivo":"","conversa":"..."}
  ```

- **Campos:**
  - `pasta`: raiz git da pasta atual; é por ela que o validar liga a
    delegação à entrega.
  - `destino`: `agy`, `claude` (perfil sem agy; recusa), `local` (Ollama local)
    ou `codex-economico` (modelo explicitamente configurado).
    `nativo` identifica recusa numa sessão antiga do agy restaurada.
    Vazio quando a seleção por capacidade termina sem executor.
  - `modelo`: Flash com o esforço do papel (no agy) ou modelo local (ex.: `qwen3:4b`).
  - `codigo_saida`: 0 atendida, 4 recusada.
  - `versao_registro`: 3 nos registros com seleção por capacidade e recusas
    estruturadas; campos anteriores continuam disponíveis.
  - `delegacao_id`: UUID da chamada. Sem seleção em andamento, o
    `roteamento_id` repete esse valor.
  - `roteamento_id`: identifica as tentativas da mesma seleção.
  - `execucao`: `JANGADA_EXECUCAO` da sessão; `null` fora dela.
  - `capacidade`: capacidade documental solicitada, ou vazio na chamada antiga.
  - `decisao`: ordem por capacidade, destino explícito ou configuração anterior.
  - `motivo_codigo`: motivo estável da recusa; vazio no sucesso.
  - `verificacao`: `nao_exigida`, `reprovada`, `referencias_validas` ou
    `referencias_e_requisitos_validos`, com explicações e referências por requisito.
    Extração tipada usa `estrutura_e_referencias_validas`: campos, tipos,
    pares nulos e posições presentes no trecho, sem conferência semântica.
    Referências válidas não comprovam a interpretação do conteúdo.
  - `requisitos`: lista dos itens exigidos por `--requisito`; vazia sem essa opção.
  - `campos_extracao`: declarações `campo:tipo` de `--extrair`; vazia sem essa opção.
  - `consolidacao`: `deterministica` quando a extração uniu partes sem geração;
    vazio nos demais casos. A união recusa valores conflitantes.
  - `verificacao_escopo`: `relatorio_completo` na seleção documental;
    `nenhum` nas chamadas anteriores. A prévia cortada pode omitir referências.
  - `artefato`: arquivo completo gravado, ou vazio quando não foi gravado.
  - `relatorio_cortado`: indica se o relatório devolvido é uma prévia.
  - `chamadas_executor`: chamadas ao modelo neste executor, incluindo partes
    locais; `null` se a interrupção impedir conhecer o total.
  - `tentativas`: destinos descartados ou executados até esse registro, um
    objeto por destino com `destino`, `motivo_codigo`, `motivo`,
    `codigo_saida` e `chamadas` (`null` quando o executor não informou). O
    registro seguinte pode repetir o histórico; não some novamente essas
    contagens.
  - `chamadas_local`: lista com a medida de cada chamada ao Ollama; `null`
    quando o destino não é `local`. Cada medida tem `id` (`delegacao_id`,
    dois pontos e a ordem da chamada), `modelo`, `fase` (`documento`,
    `fatia` ou `consolidacao`), `indice`, `codigo_transporte` (saída do
    curl), `tokens_entrada`, `tokens_saida`, `cache_lido` e `tempos_ms`
    (`total`, `carregamento`, `entrada`, `geracao`, em milissegundos),
    com `null` no que a API não informou.
  - `documento_chars`, `contexto`: caracteres do documento lido e janela de
    contexto (`JANGADA_LOCAL_CTX`) na delegação local; `null` nas demais.
  - `ferramentas_disponiveis`: `false` nos destinos `local` e
    `codex-economico`; `null` nos demais.
  - `palavras`, `tokens_retorno`: tamanho do que voltou ao Claude
    (caracteres impressos divididos por 4, relatório cortado em 600
    palavras).
  - `retorno_chars`: os mesmos caracteres impressos, sem a divisão.
  - `passos`: linhas da tabela `steps` do `.db` da conversa do agy.
  - `tokens_agy`: `usage.total_tokens` da saída JSON do agy.
  - `tokens_codex_entrada`, `tokens_codex_saida` (opcionais): consumo informado
    pelo evento `turn.completed` do executor Codex. Ausência permanece `null`.
  - `tokens_local_entrada` (opcional): tokens de prompt avaliados pelo Ollama
    (`prompt_eval_count`).
  - `tokens_local_saida` (opcional): tokens de resposta gerados pelo Ollama
    (`eval_count`).
  - `sem_fonte` (opcional): linhas do relatório com 25 caracteres ou mais,
    fora de título, código, tabela e citação, sem caminho:linha, URL,
    página ou célula. Aproxima as afirmações sem fonte.
  - `cota_antes`, `cota_depois`: `remaining_fraction` do balde `gemini-5h`
    do `/usage`, em porcentagem com duas casas. O antes pode vir do cache
    de 5 minutos. Uma delegação pequena não move esse número.
  - `recusa`, `motivo`: por que não delegou (cota abaixo de 20%, agy
    falhou, agente não achado, ação negada sem resposta, perfil, Ollama
    fora do ar, modelo ausente, memória insuficiente ou jogo aberto).
  - Campos numéricos sem valor ficam `null`.

## 10. Cache incremental e cobertura do Codex

Arquivos derivados em `$JANGADA_ESTADO/painel/`, criados pelo adaptador
`default/painel/metricas.py`, a partir de 01/10/2026:

| Arquivo | Conteúdo | Atualização |
|---|---|---|
| `codex-jangada.json` | posições e metadados das conversas geridas pela Jangada | troca de nome depois de ler a fonte sem erro |
| `codex-interface_externa.json` | posições e metadados do histórico externo | mesma regra, com origem separada |
| `cobertura.json` | situação e data da coleta de cada fonte | publicado pelo coletor junto às métricas |

Os caches Codex têm `versao`, `raiz`, `limite` de retenção e `arquivos`. Cada arquivo guarda
posição em bytes, inode, dispositivo, tamanho, data de alteração, assinatura
das bordas consumidas, contexto, contadores e registros normalizados dentro
da retenção. Não guarda mensagens, argumentos,
resultados textuais de ferramentas ou credenciais. Cache ausente ou com JSON
inválido é reconstruído; arquivos truncados ou substituídos são relidos.

Na cobertura, `atualizado` é a última coleta válida e `ultima_tentativa` é
a chamada mais recente, mesmo com falha. `ultimo_dado` informa a data do
registro mais recente dentro da retenção. `dados_preservados` identifica
registros conservados após erro; nesse caso, as contagens continuam sendo
as do cache preservado. `erro` registra somente a classe da exceção, sem
conteúdo externo. Nas fontes Codex, `arquivos_lidos`, `bytes_lidos` e
`linhas_lidas` medem a leitura dos registros na chamada, não consumo de tokens.
Os bytes incluem o trecho final incompleto, relido até receber a quebra de
linha. A contagem de linhas inclui apenas registros completos. A leitura das
bordas para conferir assinaturas não entra nessas contagens.

## 11. consumo-tarefas.jsonl

- **Caminho:** `$JANGADA_ESTADO/consumo-tarefas.jsonl`.
- **Quem escreve:** `bin/jangada-agente-fim`, função `registrar_consumo_tarefa`,
  após parar a sessão e preservar as evidências, antes de remover a pasta de trabalho.
- **Formato:** JSON Lines, uma linha por sessão e execução, acrescentada sob trava.
- **Campos:**
  - `sessao`: nome da sessão encerrada.
  - `projeto`: nome da pasta do repositório principal; `null` quando a cópia
    protegida da sessão está ausente ou inválida, ou quando a raiz protegida
    é inválida.
  - `execucao`: identificador da execução; `null` sem vínculo.
  - `autor`: provedor do agente da sessão; vazio quando a cópia protegida
    está ausente ou inválida, ou quando o provedor não é reconhecido.
  - `modelo`: modelo encontrado nos registros do autor; `null` quando ausente.
  - `tokens`: `entrada`, `saida` e `cache_lido`, inteiros ou `null` quando não medidos.
  - `motivo`: motivo da medição ausente; `null` quando medida.
  - `inicio`: data de criação da sessão, com fuso; `null` quando ausente.
  - `fim`: data da medição após parar o agente, com fuso.
  - `contexto_inicial` (desde 17/10/2026): tokens lidos pela primeira resposta
    do autor, somando entrada, cache criado e cache lido. Claude: primeira
    resposta do registro da conversa após o início. Codex: primeiro
    `token_count` com uso no rollout, cujo `input_tokens` já inclui o cache.
    `null` quando não medido.
  - `motivo_contexto` (desde 17/10/2026): motivo de `contexto_inicial` nulo;
    `null` quando medido. Linhas anteriores não têm os dois campos.
- **Acúmulo e limpeza:** não é sobrescrito nem apagado no encerramento.
  Uma medição ausente não bloqueia a limpeza da sessão. O consumo do revisor
  fica fora deste registro. Consulte o [contrato dos indicadores](indicadores.md).

## Indicadores e registros

| Grupo | Indicador | Registros | Observação |
|---|---|---|---|
| A | Aprovação na 1ª rodada | 1; 2 para o histórico anterior | rodada dos pareceres reconstruída pela sequência |
| A | Rodadas até a aprovação | 1; 2 | par autor e revisor só no 1 (e no `parecer-*`, sempre claude e agy) |
| A | Entregas no limite de rodadas | 1 | o limite não gera arquivo; só existe desde 26/09 |
| A | Itens por REVISAR, tempo de revisão | 1 (`itens`, `segundos`); 2 só para itens | |
| A | Diff das aprovadas de primeira e das reprovadas | 1 (`arquivos`, `mais`, `menos`) | sem equivalente nos pareceres |
| B | Tokens por dia e projeto, por tipo | 3 (`usage`, `cwd`) | raciocínio dentro da saída; dias antes de 28/08 só no `stats-cache.json`, sem tipo |
| B | Blocos de 5 horas por semana | 3 | regra do `jangada-consumo` (Core); `quotaLimits` marca os que bateram no limite |
| B | Tokens por entrega aprovada | 3 com 1, ligados por 4 (`conversa`) ou por pasta e horário | o 4 some no fim da sessão |
| B | Uso por modelo | 3 (`message.model`) | agy fora |
| C | Tempo em "aguardando" por dia | 8 | só a partir da instalação do registro novo |
| C | Sessões simultâneas por hora | 8; 3 como aproximação (timestamps por sessionId) | |
| C | Trocas de foco por dia | 8 (`foco`) | 5 não tem horário |
| C | Sessões abertas sem entrega aprovada há mais de 3 dias | 4 com 1 e 8 | |
| D | Ciclos de retrabalho | 3 (`tool_use`, `tool_result`) | falha = `is_error` com `Exit code N` |
| D | Pontos quentes sessão × arquivo | 3 (Edit, Write, NotebookEdit); 1 e 2 para REVISAR | 1 não lista arquivos, só a contagem |
| D | Espaço de ferramentas | 3 (`name`, `Skill`, `Agent`, `mcp__*`); agy só pelo `steps`, sem decodificar | exploratório |
| E | Tokens do Claude por entrega, com e sem agy | 1 (`subagentes`) | só entregas validadas a partir de 27/09; por tercil do diff |
| E | Fração ao agy e recusas por motivo | 9; 3 e agy para os subagentes | |
| E | Compressão (tokens do subagente por token de retorno) | 3; 9 para o agy (passos por mil tokens) | séries separadas: o agy não dá tokens por passo |
| E | Cota do agy por delegação e por semana | 9 (`cota_antes`, `cota_depois`) | uma delegação pequena fica abaixo da resolução |
| E | Aprovação na 1ª rodada com e sem verificador ou agy | 1 (`subagentes.papeis`, `delegadas_agy`) | |
| E | Afirmações sem fonte | 3 e 9 (`sem_fonte`) | desmentidos pelo revisor não são detectáveis |
| E | Desvios do protocolo | 3, agy, 9 | edição, autorrevisão, `general-purpose`, Claude sem recusa antes |
| E | Árvore pasta, conversa e subagentes | 3, agy, 9 | aba Subagentes do painel |

## Lacunas

- **validar.jsonl só desde 26/09/2026 21:29.** Antes disso só há pareceres,
  e os `validacao-*` das sessões encerradas foram apagados.
- **Pareceres sem autor, revisor, diff nem duração.** A data vem do mtime,
  que não é confiável nos arquivos antigos.
- **Modelo vazio** no validar.jsonl quando o revisor é o agy com o modelo
  padrão.
- **Autor vazio** no validar.jsonl fora de sessão do jangada; `autor` é o
  nome do comando, não o modelo.
- **Projeto com nomes diferentes:** nome real no validar.jsonl e no
  eventos-agentes.jsonl, slug no nome da sessão e no worktree, pasta
  codificada no Claude. Normalizar pelo slug.
- **Conversas do Claude apagadas depois de 30 dias** (`cleanupPeriodDays`
  padrão). O coletor precisa guardar o que já leu no próprio cache, senão o
  histórico encolhe.
- **Contagem a menos no jangada-consumo** em respostas repetidas com
  `usage` diferente (fica a primeira linha, não a final).
- **Raciocínio só como número.** `thinking_tokens` falta nas linhas antigas
  e o texto do raciocínio não é guardado.
- **Código de saída do Bash só no texto** (`Exit code N`); Bash em segundo
  plano não mostra a falha.
- **agy sem tokens confiáveis:** fica fora do consumo.
- **SESSAO.json sem histórico** e apagado no fim da sessão: a ligação
  sessão → conversa (`conversa`) se perde, e o validar.jsonl não grava a
  conversa.
- **foco.historico sem horário** e limitado a 20 linhas; horário só no
  eventos-agentes.jsonl, que começa em 26/09/2026.
- **agy sem estado "aguardando"**: o tempo de espera do agy não é medido.
- **Sessões fora do jangada-agente** (Claude aberto direto no terminal ou
  no VS Code) não geram eventos nem SESSAO.json; só aparecem nas conversas.

## Registros do piloto de implementação

`modelos_tarefa` registra modelo, esforço e provedor de autor e revisor,
com cópia protegida em `revisoes/SESSAO.json`. Artefatos da implementação
ficam em `$JANGADA_ESTADO/agentes/implementacoes/CHAVE/ID`, sem autoridade de aprovação.
O contrato e a entrega são vinculados por hash, tarefa e base exata.
Veja o [contrato do piloto](coordenacao-central/10-executor-agy.md).
