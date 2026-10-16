8. Subagentes (delegação local):
   - Para ler documento longo ou revisar redação (papéis `leitor` e `redator`),
     use `jangada-delegar PAPEL "pedido" --destino local --arquivos ARQUIVOS`.
     Ele roda um modelo local no Ollama, sem terminal, Git nem escrita, sem
     gastar cota externa nem expor dados.
   - Os demais papéis (explorador, pesquisador, verificador, auditor,
     arquiteto, otimizador, supervisor) ficam nesta sessão: com
     `JANGADA_DELEGAR=local` o agy está bloqueado e não há subagente do Claude.
   - Se o comando recusar (Ollama fora, modelo ausente, jogo aberto, memória,
     limite de contexto, fatias, vaga ou tempo), registre o motivo, informe o
     usuário e continue nesta sessão. Nunca reencaminhe ao agy, ao Claude nem
     ao Codex por conta própria.
