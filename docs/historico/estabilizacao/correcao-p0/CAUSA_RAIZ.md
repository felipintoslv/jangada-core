# Causas-raiz

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Base: `1fa3d9cc16edaa9bba620b5f9cb81394dcecbb0d`, branch nova `correcao/confianca-p0-2026-10`. Principal e baseline auditada não receberam escrita ou ensaios.

P0-A: `jangada-isolar` tornava agentes gravável, incluindo SQLite, políticas e objetos. O backend aceitava COMPLETED sem evidência protegida; a revisão manual por nome de provedor podia declarar independência sem executar modelo. Ocultar o token do painel não protegia o banco.

A reprodução anterior em Bubblewrap real alterou o SQLite, registrou revisão inexistente e obteve aceitação do backend. Os quatro JSONs da auditoria, das versões original e baseline, foram conferidos contra seu manifesto e copiados em evidencias. `reproducoes-anteriores.json` registra origem e SHA-256. Essa reprodução verificável foi reutilizada, sem repetir comandos antigos proibidos.

Durante a correção, ataque adicional em banco descartável demonstrou escrita por descritor aberto antes da montagem somente leitura. Bubblewrap preservava esse descritor. Agora o lançador fecha os adicionais; o teste A exige EBADF e banco preservado. STDIN expondo o banco também é recusado.

P0-B: o encerramento removia parecer integral, marca, prompt, protocolo e JSONs local/protegido sem arquivar. Git e métricas resumidas não reconstruíam o parecer. Os registros baseline-encerramento.json e original-encerramento.json mostram seis categorias perdidas em ambas as versões.

A correção arquiva integralmente antes da limpeza, registra contexto por rodada e retém referências Git históricas. Falha impede remoção. JSONs anteriores são evidência de ensaio sintético, nunca aprovação atual. O manifesto verifica integridade, sem assinatura contra quem controla a conta.
