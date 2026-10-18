# Resultados econômicos

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

CONFIRMADO: cálculo reprodutível das quatro tabelas de referência nas duas implementações e sementes. Dados públicos e entregas sintéticas preservados em `artefatos/`; referências em `privado/`. Não há análise de municípios brasileiros reais ou resultados empíricos.

A mudança apenas de 2025 no setor S001 alterou 36.000 QLs históricos na solução A7 em cada rodada, enquanto o controle correto alterou zero. Evidências `metamorfismo-1.json` e `metamorfismo-2.json`. Demonstra vazamento temporal das entregas artificiais.

Todos os defeitos artificiais conservam plausibilidade estrutural suficiente para passar nos testes públicos. A concordância formal ou a ausência de erro R não estabelece validade metodológica. `referencias-formais.json` mostra aceitação de oito referências textuais ao LEIA-ME, sem comprovar suas conclusões. O verificador nativo de referências não substitui o oráculo ou julgamento metodológico autorizado.

Segunda rodada determinística: PASSOU sob os mesmos critérios. Segunda rodada cega com modelos reais: BLOQUEADO. Generalização da solução de IA não foi avaliada. Aplicação Shiny, visualizações e entrega final aprovada por modelos: BLOQUEADO.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.


## Conferência independente executada no terminal local

PASSOU: commit bb3ad6b4b2bb8f3032e28efb7af5f1a5c4abb9bb, código SHA-256 fe56b11787d68b0fb9497e10d0176915a1a15f05e04fc7e30b3be1e75508c74c. Sete cenários com 42 verificações cada, total 294. Condição normal, alteração de outro ano, município com total zero, setor com total zero, ausência pontual, todas as observações ausentes e ordem invertida concordaram com referência Python. Execução R em Bubblewrap sem rede, somente código e dados públicos montados; gabarito Python fora das montagens.

Registro conferido: evidencias/jctrl-jt5vmx8p/resumo.json; insumos e saídas sintéticos preservados no mesmo diretório. Nenhuma chamada de modelo nesse ensaio. Isso valida os indicadores na amostra e segundo a política explícita de propagação de ausências; não valida a atividade econômica extensa, generalização universal ou causalidade.

Pendentes: revisão protegida pelo controlador, parecer metodológico fundamentado, aprovação autorizada e reconstrução histórica do ciclo real após encerramento. Preparação independente original não foi demonstrada. P1 permanece INCONCLUSIVA.
