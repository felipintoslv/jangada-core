# Indicadores

`jangada-indicadores` lê os registros em `$JANGADA_ESTADO` e não altera arquivos.
Use `--projeto NOME` e `--desde AAAA-MM-DD` para filtrar. Sem opções, mostra
uma linha curta; `--json` imprime o contrato consumido pela Central.

O objeto JSON tem `versao: 1` e três listas:

- `tarefas`: uma entrada por sessão e execução, com `sessao`, `autor`, `tokens`
  (`entrada`, `saida`, `cache_lido`, `modelo` e `motivo`), `rodadas`,
  `ultimo_resultado`, `delegacoes` e `segundos_revisao`. Sessões abertas usam
uma medição atual; sessões encerradas usam `consumo-tarefas.jsonl`.
- `revisores`: uma entrada por revisor e modelo, com `pareceres`, `apontamentos`,
  `procedentes`, `rejeitados`, `sem_classificacao`, `casos`, `casos_taxa` e
  `taxa_procedencia`. A taxa divide procedentes por procedentes mais rejeitados.
  `null` indica que não há casos classificados. Linhas antigas sem `resposta`
  não entram nos totais de classificação.
- `local_vs_agy`: uma entrada por papel e destino, com `chamadas`, `sucesso`,
  `recusas`, `segundos_medianos`, `tokens_entrada`, `tokens_saida` e
  `mudancas_local`. Tokens sem divisão por entrada e saída ficam `null`; o total
  conhecido do agy aparece como `tokens_agy` nas delegações da tarefa. A mudança
  conta tentativas que passaram pelo destino local e terminaram em outro destino.

O medidor usa o último total do Codex e respostas únicas do Claude, identificadas
por mensagem e pedido. Uma medição ausente retorna tokens e modelo nulos com
`motivo`. Tokens do revisor não são medidos nesta versão; faltam registros de
uso vinculados à chamada do revisor, fora dos registros de consumo do autor.

O consumo por sessão é anexado a `$JANGADA_ESTADO/consumo-tarefas.jsonl` ao
encerrar. A linha inclui sessão, projeto, execução, autor, modelo, tokens,
motivo, início e fim. Falha de medição não impede o encerramento.
