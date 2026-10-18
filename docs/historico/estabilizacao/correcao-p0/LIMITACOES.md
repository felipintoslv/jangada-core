# Limitações

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

- Modelos reais: NÃO EXECUTADO. Provedores simulados, Bubblewrap/Git reais. Bloqueio de escrita não comprova verdade semântica ou disponibilidade comercial.
- Identidades são observadas pelo controlador no protocolo/configuração; não há atestado criptográfico do fornecedor nem independência intelectual garantida.
- Revisão independente final não pode usar o antigo comando de rótulo sem execução. Revisão Git e supervisão intermediária não são a aprovação final de tarefa. Nenhuma API nova foi criada.
- Controle irrestrito da conta, administrador e kernel ficam fora do modelo de ameaça. Hashes locais não protegem contra esse usuário.
- Sockets e D-Bus restritos impedem alguns testes integrados. Logs crus com falha ficam disponíveis; não houve remoção de proteções ou instalação de dependências.
- Verificação integral contém comandos proibidos e foi limitada em tempo. Grupos bloqueados não são aprovados. Casos seguros são executados separadamente quando possível.
- Conferência anterior ao lançamento registra recusa no stderr; processos iniciados com falha recebem registro protegido de código. Não se promete registrar toda tentativa silenciosa absorvida pelo próprio executor.
- Fila permanece legível ao agente, sem escrita. Não há segregação de leitura entre projetos; J comprova bloqueio de alteração de outro projeto.
- Guarda existente do Codex documental exige isolamento. Execução real e consulta real de cota continuam sem validação nova; nenhum serviço é declarado disponível.
- Falha de arquivo pode deixar sessão parada com originais preservados. Recuperação é supervisionada; não remove dados para liberar espaço.
- Correção computacional, metodologia e evidência científica continuam exigindo verificação externa. COMPLETED autorizado não é prova de verdade.

Esta missão não instala a correção, altera o canal estável ou autoriza congelamento. Próxima auditoria deve verificar ciclo completo com modelos reais autorizados e ambiente compatível.
