# Regressões e compatibilidade

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Suites diretas cobrem projetos/cadastro, atividades, artefatos, fila, reservas, retomada, supervisão, validação determinística, encerramento e consultas. Comandos/tempos estão em evidencias/resultados.json; saídas integrais em .log.

Mudanças deliberadas: identidade igual não demonstra independência; rótulo sem execução não aprova; dependência adulterada é bloqueada antes da chamada; configuração antiga não desativa isolamento. Os casos existentes foram preservados.

Regressão temporária corrigida: consulta somente leitura do painel não inicializava o caminho necessário aos recibos. Os três testes de painel-orquestracao.py passaram após correção.

Quatro falhas de tarefas.py dependem de sockets locais negados. Monitoramento e conversa têm restrição semelhante. Logs não foram transformados em aprovação. Agregado limitado não comprova ausência de regressão nos grupos restantes.

Integração automática permanece RESTRITA. Sessão sem ramo próprio agora não é limpa implicitamente por --integrar; revisão e artefatos ficam preservados.

Principal e baseline permanecem com HEAD/estado conferidos em evidencias/estado-repositorios.json. Nenhum comando desta missão alterou instalação ativa. Não houve inventário integral dos arquivos do sistema operacional.
