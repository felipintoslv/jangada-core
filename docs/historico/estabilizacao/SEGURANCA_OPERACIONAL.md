# Segurança operacional

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

`jangada-agente-fim --integrar` está bloqueado no backend. A recusa mantém sessão, ramo e worktree. Não existe variável para liberar o fluxo. Uma tentativa interrompida ou repetida não autoriza publicação. Uma integração já feita manualmente não autoriza limpeza automática por esse comando.

Use worktree isolada, revisão independente fora do isolamento e testes antes de integrar. Faça cópia dos projetos e de seus arquivos ignorados antes do primeiro uso. Confirme pessoalmente os SHA da base, do candidato e da árvore registrada, a origem da marca em `revisoes/`, `local_verified=true` e `independent=true`. Se a base mudar, revise novamente. O parecer de um provedor sintético só serve para teste.

Para integração manual, encerre a execução do agente sem remover a worktree e suspenda editores, formatadores e outras operações Git no projeto. Confira o estado de todas as worktrees e execute `git fsck --full`. Prepare primeiro uma worktree separada da base, faça a mescla com ganchos e monitor de arquivos desligados e execute os testes no isolamento. Confira alterações e objetos antes de publicar. A publicação final e a recuperação são operações humanas, com cópia prévia e conferência do worktree principal. Não trate `update-ref` como publicação completa.

Uma falha antes de publicar mantém o principal intocado. Depois de publicação parcial, pare: registre HEAD, índice, estado e erro; preserve cópias e não repita a operação até esclarecer o estado. Não use reset destrutivo ou stash invisível para recuperar.

## Proteções efetivas e limites

O backend congela a entrega revisada, separa marcas protegidas, blinda Git fora do isolamento e exige isolamento para scripts de validação. A baseline bloqueia publicação e reversão automáticas perigosas. Falta de ferramenta aplicável e validação pulada não aprovam.

As opções de trabalho direto, validação com rede e o comando manual `reverter` ainda existem. O desligamento do isolamento foi bloqueado: `--sem-isolar` e `JANGADA_AGENTE_ISOLAR=0` geram aviso e a sessão abre, retoma e executa isolada. As opções que restam são exceções deliberadas da ferramenta, não proteções da baseline. Não as use durante os 30 dias. `reverter` mostra e confirma descarte, mas seu ramo de cópia não preserva alterações sem commit nem arquivos novos. Encerrar com descarte também exige decisão humana. Nunca confirme descarte sem cópia verificável.

O isolamento de agente permite rede para o provedor configurado e não elimina todo risco de envio de informações. Não coloque credenciais ou dados privados nos arquivos acessíveis ao agente. Revise `.worktreeinclude` e `.jangada/links`. Configurações executáveis do projeto só devem rodar no isolamento. Não forneça uma instalação modificável ao agente.

Sem Bubblewrap funcional no perfil exigido, interrompa a validação; não substitua por execução direta. Registre falhas e guarde entregas reprovadas. Painel, Central e consultas não substituem conferência de Git e arquivos.
