8. Subagentes (destino explícito por tarefa):
   - Todos os papéis de apoio, inclusive leitor e redator, têm destino
     explícito. Passe sempre `--destino`; o padrão do comando não decide.
   - `leitor` e `redator`, sobre texto ou PDF que caiba nas fatias:
     `jangada-delegar PAPEL "pedido" --destino local --arquivos FONTES`.
     Para trecho de arquivo grande, use a faixa `ARQUIVO:INI-FIM`. O modelo
     local roda no Ollama, sem terminal, Git nem escrita, e não envia dados
     para fora.
   - Com escolha remota explícita e fontes autorizadas nesta tarefa, leitor
     e redator podem usar `--destino agy --permitir-remoto --modelo
     gemini-3.8-flash-high --arquivos FONTES`. Recebem somente o texto extraído,
     sem ferramentas ou MCP. Falha local nunca autoriza essa escolha.
   - `pesquisador` usa `jangada-delegar pesquisador "pedido" --destino agy
     --permitir-remoto --modelo gemini-3.8-flash-high --url URL_OFICIAL`,
     sem `--arquivos`. Exija busca, abertura, URL, data e trecho sustentado.
   - `arquiteto` usa `--destino agy --permitir-remoto --arquivos FONTES`.
     Aceita somente arquivos regulares e faixas `ARQUIVO:INI-FIM`, sem
     ferramentas ou MCP. Pastas são recusadas.
     Pedido e fontes extraídas juntos têm limite de 96 KiB; delimite as fontes.
   - Os demais papéis (explorador, verificador, auditor,
     designer, otimizador, supervisor):
     `jangada-delegar PAPEL "pedido" --destino agy --permitir-remoto`, com
     escopo e fontes autorizados nesta tarefa em `--arquivos`. A preferência
     global não autoriza compartilhar dados confidenciais.
   - Chame `designer` em tarefas que mexem em tela, barra, Central ou textos
     que o usuário lê.
   - Falha local (Ollama fora, modelo ausente, jogo aberto, memória, contexto,
     fatias, vaga ou tempo): registre o motivo e informe o usuário. Continue
     nesta sessão. Não reencaminhe ao agy, ao Claude nem ao Codex por conta
     própria; enviar essas fontes a um serviço remoto é decisão explícita, com
     autorização da tarefa para aquelas fontes.
   - Recusa do agy por acesso, confiança, cota ou autorização: registre e
     informe o bloqueio. A investigação pode continuar nesta sessão, mas o
     apoio não foi concluído. Não encaminhe ao Ollama nem ao Claude.
   - Papel local só leitor ou redator; o modelo local nunca é revisor
     independente nem emite o parecer do supervisor.

   - Exceção delimitada, só com a opção ligada no pedido do coordenador e em
     tarefa pequena e bem especificada; sem a opção, não chame.
     `jangada-delegar implementador` edita somente cópia
     isolada, com base exata, fontes, arquivos permitidos e critérios. Modelo
     fixo `gemini-3.8-flash-high`, sem terminal ou alternativa automática.
     Teto de 3 chamadas por tarefa; `saida_invalida` conta no teto. Acabado o
     teto, termine à mão e registre no corpo do commit quais linhas são suas.
     Inspecione e aceite pelo hash; teste antes da revisão independente.
     Especialistas de leitura continuam sem escrita; resultado não aprova.
