# Continuação com modelos reais autorizados

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

O usuário autorizou Codex executor e Claude revisor, somente dados sintéticos e configurações existentes. Ainda não há resultado de execução real; scripts foram preparados, não executados nesta sessão com sockets restritos.

1. No terminal compatível: `python3 scripts/preparar_modelos_reais.py --chamar-provedores`. Cria /tmp/jreal-*, código exato, aplicações copiadas, HOME e XDG próprios. Copia somente auth.json do Codex e .credentials.json do Claude, quando existentes, com permissão 0600. Históricos, extensões, instruções pessoais e configurações globais não são copiados. Credenciais continuam privadas no HOME temporário, fora de qualquer manifesto ou pacote de evidências. Não compartilhar esse HOME. Variáveis de autenticação selecionadas são usadas somente em memória. As originais não são alteradas.

2. O Jangada confirma ocultação da casa real antes de chamadas remotas. Duas chamadas curtas, ferramentas desativadas, respostas fixas e prazo de 180 segundos cada. Autenticação ausente, modelo incompatível ou comunicação inválida impedem avançar. O teste usa jangada-isolar e jangada-codex originais; não constitui execução ou revisão de atividade econômica.

3. Se ambos passarem, abrir tarefa: `python3 scripts/iniciar_atividade_real.py /tmp/jreal-RAIZ_REGISTRADA`. Cadastra projeto, atividade e critérios pelo backend e abre sessão Codex via jangada-agente nativo, em worktree e tmux próprios. Apenas primeira rodada e contrato público são entregues; gabarito e segunda rodada não são copiados. A sessão é interativa para observar confiança e supervisão. Nenhuma integração ou encerramento automático. Desanexar com Ctrl-b d após o executor parar preserva estado.

4. Conferir artefatos, realizar revisão protegida pelo controlador, comparar oráculo privado, conduzir correções, segunda rodada e encerramento com recuperação. Essas etapas permanecem pendentes. Uma revisão dentro do isolamento do executor não deve ser usada como autoridade de aprovação final.

Os scripts não alteram produção nem configuram provedores novos. O modelo Codex é obtido somente do campo model da configuração existente; provedor personalizado exige inspeção e bloqueia a suposição de OpenAI. Claude solicita sonnet pelo mecanismo existente. Ainda será necessário registrar a identidade efetivamente retornada pela execução real.


## Substituição autorizada do revisor

Codex real respondeu corretamente no ensaio jreal-z0ziv6zp. Claude retornou erro 429 de cota semanal, sem tokens processados; não é evidência de falha do Jangada. Usuário autorizou usar agy em seu lugar. Verificação específica preparada em `scripts/verificar_agy_real.py`, reutilizando apenas a raiz sintética do Codex.

O agy depende do chaveiro. A sonda usa proxy efêmero com GetSecret limitado a itens cujo atributo service identifica agy/Antigravity. Não concede CreateItem, SetSecret, Delete, Unlock ou acesso em lote a segredos. Não copia conversas ou configurações pessoais. Sem identificação inequívoca, chaveiro desbloqueado e token válido, bloqueia e registra motivo. Nenhum serviço permanente é criado. Resultado real do agy ainda pendente; não declarar conectividade ou revisão realizada.
