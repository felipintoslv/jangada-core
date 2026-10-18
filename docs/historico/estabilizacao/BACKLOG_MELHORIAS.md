# Melhorias e impedimentos

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

| Prioridade | Evidência | Próximo passo |
|---|---|---|
| P1 | Sandbox recusa namespace sem rede e comunicação por soquetes locais. Testes reais de validação R, D-Bus, Central, painel HTTP e serviços sintéticos não completam. | Rodar as suítes em máquina compatível ou no CI existente. Não alterar o host desta missão. |
| P1 | Provedor real e sessão Hyprland não executados. | Ensaio supervisionado com projeto sintético, sem dados privados. |
| P1 | Integração automática bloqueada por falta de publicação segura contra processos externos concorrentes. | Projeto separado para publicação isolada e protocolo de exclusão efetiva. Sem reativação na baseline. |
| P1 | Exceções manuais de isolamento, trabalho direto e descarte existem. | Avaliar política de restrição no backend em trabalho separado; nesta baseline não usar esses modos. |
| P2 | Ajuda e mensagens legadas do validador ainda mencionam exceção do gitleaks e APROVADO_AUTORREVISAO. O backend já recusa essas aprovações. | Atualizar textos em revisão posterior; seguir a política desta baseline. |
| P2 | Consultas operacionais carregam histórico inteiro. | Medir com histórico sintético de 30 dias; limitar somente quando houver evidência de bloqueio. |
| P2 | Reprodução completa da instalação e restauração gráfica ainda pendente. | Ensaiar em instalação descartável, sem serviços globais no host atual. |
| P3 | Evoluções do painel e arquitetura de agentes. | Fora da missão; nenhuma implementação. |
