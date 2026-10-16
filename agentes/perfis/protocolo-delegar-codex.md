8. Delegação no Codex (leitor e redator no Ollama, demais papéis no agy):
   - Todos os papéis de apoio, inclusive leitor e redator, têm destino
     explícito. Passe sempre `--destino`; o padrão do comando não decide.
   - `leitor` e `redator`, sobre texto ou PDF que caiba nas fatias:
     `jangada-delegar PAPEL "pedido" --destino local --arquivos FONTES`.
     Para trecho de arquivo grande, use a faixa `ARQUIVO:INI-FIM`. O modelo
     local roda no Ollama, sem terminal, Git nem escrita, e não envia dados
     para fora.
   - Os demais papéis (explorador, pesquisador, verificador, auditor,
     arquiteto, otimizador, supervisor):
     `jangada-delegar PAPEL "pedido" --destino agy --permitir-remoto`, com
     escopo e fontes autorizados nesta tarefa em `--arquivos`. A preferência
     global não autoriza compartilhar dados confidenciais.
   - Falha local (Ollama fora, modelo ausente, jogo aberto, memória, contexto,
     fatias, vaga ou tempo): registre o motivo e informe o usuário. Continue
     nesta sessão. Não reencaminhe ao agy nem ao Claude por conta própria;
     enviar essas fontes a um serviço remoto é decisão explícita, com
     autorização da tarefa para aquelas fontes.
   - Recusa do agy por acesso, confiança, cota ou autorização: registre e
     informe o bloqueio. A investigação pode continuar nesta sessão, mas o
     apoio não foi concluído. Não tente chamar subagentes do Claude a partir
     do Codex nem encaminhe ao Ollama.
   - Papel local só leitor ou redator; o modelo local nunca é revisor
     independente.
   - Com `JANGADA_DELEGAR=local` explicitamente escolhido, o agy fica
     bloqueado: leitor e redator usam `--destino local --arquivos ARQUIVOS`
     e os demais papéis ficam nesta sessão.
   - A seleção por `--capacidade` é opcional e documental, com o papel leitor
     e `--arquivos`. A política padrão seleciona somente agy; sem autorização,
     confiança, acesso ou cota, registra bloqueio sem alternativa local automática.
   - O papel `supervisor`, com `analise_documental`, confere somente relatórios
     intermediários autorizados. Não use o Ollama para emitir esse parecer
     nem substitua o `jangada-validar` por supervisão de conteúdo.

   - Exceção delimitada: `jangada-delegar implementador` edita somente cópia
     isolada, com base exata, fontes, arquivos permitidos e critérios. Modelo
     fixo `gemini-3.8-flash-high`, sem terminal ou alternativa automática.
     Inspecione e aceite pelo hash; teste antes da revisão independente.
     Especialistas de leitura continuam sem escrita; resultado não aprova.
