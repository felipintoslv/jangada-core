# Modelo de ameaças

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

O executor é potencialmente hostil: pode alterar sua worktree, saída, JSON, metadados operacionais e variáveis, executar comandos e explorar caminho alternativoes ou descritores herdados. O controlador fora do Bubblewrap, seu código, configuração e conta do usuário são a autoridade. Não há promessa contra controle irrestrito da conta, administrador, kernel comprometido ou executável de provedor substituído pelo usuário.

| Componente | Acesso e autoridade |
|---|---|
| Controlador: CLI, executor, projetos e supervisão | Escrita em SQLite, artefatos, decisões e histórico; exige execução fora do isolamento |
| Agente interativo e agy delegado | Bubblewrap obrigatório; agentes/projetos somente leitura; revisoes e chave do painel ocultas |
| Revisores Git Claude/agy/Codex | Bubblewrap; Claude/agy recebem somente a foto congelada em leitura; saída coletada pelo controlador |
| Modelo local | Dados e texto via cliente; não recebe interface de escrita autoritativa |
| Central, painel e consultas | Conferem recibo e digest antes de apresentar COMPLETED ou liberar dependências |

Autoridade reside em `$JANGADA_ESTADO/agentes/projetos/<chave>/` e `$JANGADA_ESTADO/revisoes/`. Montagens opcionais precedem a proteção obrigatória, inclusive código e configuração somente leitura. Executáveis temporários do PATH são reexpostos em leitura antes das proteções finais.

A decisão legítima é emitida pelo controlador após verificar reserva, política, artefato e revisão aplicável. Recibo protegido inclui linha integral da tarefa, especificação, resultado, digest e instante. COMPLETED isolado não basta. Revisão humana nunca recebe independência de modelo e só aprova políticas que a permitem.

Supervisão intermediária exige comprovante em memória emitido após processo executado, parecer estruturado, referências, tarefa/digest e identidades distintas. JSON não reconstitui o comprovante. Isso comprova execução controlada, não verdade do parecer ou atestado criptográfico do fornecedor.

A conferência anterior ao lançamento recusa ligações simbólicas, ligações físicas e canais especiais no estado protegido. Os três descritores padrões não podem expor arquivos protegidos ou sockets; os adicionais são fechados. A guarda verifica marca física de montagem mesmo sem variável de ambiente. Runtime privado oculta sockets da Central/tmux. Não há serviço novo de aprovação acessível ao agente. D-Bus mantém as restrições existentes.

Negação de serviço, crescimento do histórico e resultados falsos continuam possíveis. Aprovação não garante verdade científica. Serviços e credenciais reais não foram usados.
