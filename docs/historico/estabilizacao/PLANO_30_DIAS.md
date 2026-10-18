# Plano de 30 dias

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

O período começa somente depois de completar as verificações pendentes em ambiente compatível e aprovar o congelamento. Nenhuma tag foi criada.

| Período | Operação |
|---|---|
| Antes do dia 1 | Executar CI completo, isolamento sem rede, D-Bus e sessão gráfica. Fazer e conferir backup. Escolher um projeto pequeno e sem dados privados. |
| Dias 1 a 3 | Uma tarefa por vez em worktree isolada. Revisão externa independente, validação completa e integração manual supervisionada. Conferir arquivos e estado após encerramento. |
| Dias 4 a 7 | Repetir em projeto real de baixo risco. Anotar falhas, prazos e tempo de consulta; não aumentar automação. |
| Dias 8 a 21 | Usar a versão congelada, preservando backups e conferência humana. Corrigir somente defeitos bloqueantes em ramo separado, com testes antes de substituir a versão. |
| Dias 22 a 30 | Ensaiar recuperação de uma cópia, conferir integridade e avaliar falhas acumuladas. Decidir continuidade com evidências. |

Interrompa o uso afetado diante de alteração inesperada no principal, segredo exposto, falha de isolamento, banco inconsistente ou estado de publicação desconhecido. Preserve dados e registros antes de investigar. Não use integração automática, reversão automática, trabalho direto ou execução sem isolamento. Não atualize o canal estável durante a avaliação.
