# Métricas

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

| Métrica | Resultado e escopo |
| --- | --- |
| Modelos reais / revisões reais | 0 / 0; fluxo BLOQUEADO |
| Testes Python de regressão e P0 | 274 executados, 270 passaram, quatro bloqueados por sockets |
| Ensaios complementares finais | 3/3 passaram |
| Entregas deliberadamente defeituosas | 16, duas sementes |
| Testes públicos nessas entregas | 96/96 passaram; não prova correção |
| Classes numéricas detectadas pelo auditor | 12 ocorrências em seis classes |
| Casos metodológicos adjudicados | 4, composição e causalidade |
| Erros identificados por revisor real | Não mensurável: nenhum revisor executado |
| Falsos positivos de revisor real | Não mensurável |
| Comparações Python/R | 181.050 linhas por rodada, duas rodadas PASSOU |
| Controles corretos do auditor | Dois, conferidos contra referência |
| Documentos históricos recuperados | 8/8, conteúdo completo e SHA-256 |
| Falsificações aceitas | 0 nos cenários executados; alcance limitado às fixtures |
| Rodadas de correção por IA | 0; não executadas |
| Intervenções humanas no fluxo IA | Não mensurável: fluxo não iniciado |

Tempo dos subprocessos: `comandos-consolidados.json` registra segundos por execução; somar subprocessos não representa duração total humana, revisão ou geração completa. Tempo de execução/revisão de modelos reais é indisponível. Falhas exploratórias dos testes complementares constam separadamente e não se contam como regressões do produto.

Sem estimativa estatística de confiabilidade geral. Testes privados de uma entrega final de IA não têm taxa calculável porque essa entrega não existe. Infraestrutura, experimento e erros do modelo permanecem separados.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.


## Reexecução no terminal local

Logs recebidos e hashes conferidos em `evidencias/jangada-p1-comunicacao-833nd0if/`: interface 66/67 PASSOU, um FALHOU em `QLocalServer.listen`; P0 32/32 PASSOU. Os quatro bloqueios anteriores não devem mais ser tratados como indisponibilidade geral neste terminal. A falha restante está em investigação; possível limite do comprimento do caminho, ainda sem confirmação. A reprodução seguinte usa caminhos menores e sonda de erro Qt, sem mudar produção. O ciclo com modelos reais permanece pendente e a classificação geral continua P1 INCONCLUSIVA.


## Resultado atualizado: interface 67/67

Execução no terminal local, logs e hashes conferidos em `evidencias/jp1-pio6_bdi/`: 67/67 testes de interface PASSOU, em 7,031 segundos segundo unittest. Os 32 testes P0 passaram na execução local anterior. Os quatro bloqueios de sockets estão superados para essas suítes no terminal local. Isso não comprova interface gráfica completa com modelos reais.

A falha anterior não se repetiu após encurtar caminhos sintéticos. O comprimento do socket permanece hipótese de causa, pois a sonda complementar do auditor falhou por erro de sintaxe. Esse erro está preservado em `sonda-qt.stderr.log`, pertence ao experimento e não invalida os 67 testes efetivamente executados. O script de diagnóstico foi corrigido sem mudar produção; o diagnóstico corrigido ainda não foi executado no terminal local. Não é necessário repetir a suíte aprovada apenas para esse diagnóstico.

Classificação P1: INCONCLUSIVA enquanto execução real, revisão independente, correção e aprovação econômica não forem demonstradas. Não há autorização registrada para chamadas remotas do ensaio.


## Conferência independente executada no terminal local

PASSOU: commit bb3ad6b4b2bb8f3032e28efb7af5f1a5c4abb9bb, código SHA-256 fe56b11787d68b0fb9497e10d0176915a1a15f05e04fc7e30b3be1e75508c74c. Sete cenários com 42 verificações cada, total 294. Condição normal, alteração de outro ano, município com total zero, setor com total zero, ausência pontual, todas as observações ausentes e ordem invertida concordaram com referência Python. Execução R em Bubblewrap sem rede, somente código e dados públicos montados; gabarito Python fora das montagens.

Registro conferido: evidencias/jctrl-jt5vmx8p/resumo.json; insumos e saídas sintéticos preservados no mesmo diretório. Nenhuma chamada de modelo nesse ensaio. Isso valida os indicadores na amostra e segundo a política explícita de propagação de ausências; não valida a atividade econômica extensa, generalização universal ou causalidade.

Pendentes: revisão protegida pelo controlador, parecer metodológico fundamentado, aprovação autorizada e reconstrução histórica do ciclo real após encerramento. Preparação independente original não foi demonstrada. P1 permanece INCONCLUSIVA.
