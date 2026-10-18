# Auditoria P1 do jangada

**P1 INCONCLUSIVA.** O ensaio avaliou o commit `17178de`.
A correção P0 foi depois incorporada em `main`, no commit `19f5569`;
veja a [prova e o estado atual](../README.md).

Os testes de proteção P0 e de interface passaram nos ensaios registrados.
O ciclo econômico completo com execução, revisão independente, aprovação
protegida e reconstrução histórica não foi demonstrado.
A autenticação do agy no ambiente sintético falhou; a última sonda retornou
NoReply antes de OpenSession.

- [Relatório final](relatorios/RELATORIO_FINAL.md).
- [Execução de modelos](relatorios/EXECUCAO_MODELOS.md).
- [Ambiente isolado](relatorios/AMBIENTE_ISOLADO.md).
- [Indicadores econômicos](relatorios/RESULTADOS_ECONOMICOS.md).
- [Rastreabilidade](relatorios/RASTREABILIDADE.md).

Logs, dados artificiais, scripts e `SHA256SUMS` estão no ramo
`arquivo/evidencias`, commit `7a9d1e5`, em
`docs/estabilizacao/validacao-p1/`. Use `git show RAMO:CAMINHO` para consultar.
Os manifestos também citam gabaritos privados e dados externos que nunca
foram copiados para este repositório; não incluem credenciais ou o HOME sintético.
