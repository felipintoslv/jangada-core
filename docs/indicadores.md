# Indicadores

`jangada-indicadores` lê os registros em `$JANGADA_ESTADO` e não altera arquivos.
Use `--projeto NOME` e `--desde AAAA-MM-DD` para filtrar. `--json` imprime o
contrato consumido pela Central.

Sem `--json`, a saída é um resumo em texto. Cada bloco começa pelos totais:
tokens, rodadas e tempo de revisão das tarefas; pareceres, procedentes,
rejeitados e taxa dos revisores, separados por origem; chamadas, sucessos e
recusas do local e do agy. Depois vêm as linhas de cada grupo. Das tarefas, só
as 10 mais recentes, pela data de encerramento ou da última rodada protegida;
`--todas` lista todas. Valor nulo aparece como "sem dado".

O objeto JSON tem `versao: 1` e três listas:

- `tarefas`: uma entrada por sessão e execução, com `sessao`, `autor`, `tokens`
  (`entrada`, `saida`, `cache_lido`, `modelo` e `motivo`), `rodadas`,
  `rodadas_sessao`, `ultimo_resultado`, `delegacoes`, `segundos_revisao`,
  `contexto_inicial` e `motivo_contexto`.
  Sessões abertas só aparecem com rodadas protegidas e têm tokens nulos até o
  encerramento. Sessões encerradas usam `consumo-tarefas.jsonl`.
  `contexto_inicial` é o total de tokens que a primeira resposta do autor leu:
  entrada, cache criado e cache lido. No Claude vem da primeira resposta do
  registro da conversa; no Codex, do primeiro `token_count` com uso (o
  `input_tokens` do Codex já inclui o cache). Quando não há medição, o campo é
  `null` e `motivo_contexto` diz por quê; linhas gravadas antes da medição
  trazem `registro anterior à medição do contexto inicial`.
- `revisores`: uma entrada por revisor, modelo e origem (`sessao` ou
  `protegida`), com `pareceres`, `apontamentos`,
  `procedentes`, `rejeitados`, `sem_classificacao`, `casos`, `casos_taxa` e
  `taxa_procedencia`. A taxa divide procedentes por procedentes mais rejeitados.
  `null` indica que não há casos classificados. Linhas antigas sem `resposta`
  não entram nos totais de classificação.
- `local_vs_agy`: uma entrada por papel e destino, com `chamadas`, `sucesso`,
  `recusas`, `segundos_medianos`, `tokens_entrada`, `tokens_saida`,
  `mudancas_local` e `origem: "sessao"`. Tokens sem divisão por entrada e saída
  ficam `null`; o total conhecido do agy aparece como `tokens_agy` nas delegações
  da tarefa. A mudança conta tentativas que passaram pelo destino local e
  terminaram em outro destino. As delegações da tarefa também têm
  `origem: "sessao"`, pois vêm de registro gravável pelo agente.

O medidor usa o último total do Codex e respostas únicas do Claude, identificadas
por mensagem e pedido. Uma medição ausente retorna tokens e modelo nulos com
`motivo`. Os tokens do revisor são medidos à parte, em `tokens_revisor` de
cada rodada do `validar.jsonl` e da linha de `consumo-tarefas.jsonl`
([registros](registros.md), seções 1 e 11). O `--json` ainda não os mostra.
O medidor do Claude considera apenas respostas a partir do início da sessão e
exige um worktree para separar as conversas do projeto. Se o autor e o revisor
forem Claude e usarem o mesmo worktree, os tokens da revisão podem entrar na
conta do autor, pois os registros não permitem separá-los.

As métricas identificam a origem: `sessao` para `validar.jsonl` e `protegida`
para `revisoes/validar.jsonl`. `revisores` agrupa por revisor, modelo e origem.
Nas tarefas, `rodadas`, `ultimo_resultado` e `segundos_revisao` usam somente a
origem protegida; `rodadas_sessao` mostra à parte as rodadas graváveis pelo
agente. Tarefas abertas aparecem apenas com rodadas protegidas e têm tokens
nulos enquanto a cópia protegida confirma a mesma sessão e execução; caso
contrário, usam o motivo `consumo não registrado no encerramento`. Tarefas
encerradas usam somente `consumo-tarefas.jsonl`, gravado com dados de
`revisoes/SESSAO.json`; sem cópia protegida, o projeto e os tokens ficam nulos
com o motivo. O indicador não lê
`agentes/` nem chama o medidor para tarefas abertas. Nomes de sessão são
conferidos antes de formar caminhos. A leitura de JSONL tolera bytes inválidos
e ignora linhas inválidas ou que não sejam objetos.

Após parar o agente e preservar as evidências, o Core mede e grava o consumo em
`$JANGADA_ESTADO/consumo-tarefas.jsonl`, antes de remover a pasta de trabalho.
A linha inclui sessão, projeto, execução, autor, modelo, tokens, motivo, início,
fim, `contexto_inicial`, `motivo_contexto` e `tokens_revisor`. Falha de medição
não impede o encerramento.
