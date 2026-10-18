# Execução dos modelos

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

BLOQUEADO: fluxo real, revisão por segunda família, terceira revisão adversarial, confrontação cega dos pareceres, correção e nova revisão. Nenhum modelo executor ou revisor foi chamado. Executáveis encontrados não foram tratados como prova de disponibilidade. Não foram copiadas credenciais ou sondadas APIs autenticadas. Acesso remoto não foi previamente autorizado para este ensaio e a infraestrutura local de sockets é restrita.

CONFIRMADO no backend: cadastro de projeto sintético, criação de atividade com oito critérios explícitos e importação da tarefa ECON-P1. `evidencias/backend-cadastro.json` registra atividade, especificação, status QUEUED, zero tentativas, zero execuções e ausência de artefato. Não se atribuiu identidade inventada a uma execução.

Protocolos de execução, supervisão, reservas e retomada passaram nas suítes locais com fixtures. Provedores falsos nesses testes são explicitamente simulações. Eles não validam execução multimodelo real. R econômico e controles foram escritos pelo auditor, não pelo executor. Gráficos, aplicação Shiny e documentação produzidos por IA não foram realizados.

O ciclo de 15 etapas não foi completado: cadastro observado; execução, revisão, correção, aprovação e histórico de atividade econômica real estão bloqueados. Encerramento e recuperação foram testados separadamente com sessões sintéticas.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.


Continuação autorizada: usuário autorizou Codex executor e Claude revisor, com dados sintéticos. Scripts e condições estão em `EXPERIMENTO_REAL.md`. Nenhuma chamada real ocorreu ainda nesta sessão; aguardam execução no terminal compatível.


## Substituição autorizada do revisor

Codex real respondeu corretamente no ensaio jreal-z0ziv6zp. Claude retornou erro 429 de cota semanal, sem tokens processados; não é evidência de falha do Jangada. Usuário autorizou usar agy em seu lugar. Verificação específica preparada em `scripts/verificar_agy_real.py`, reutilizando apenas a raiz sintética do Codex.

O agy depende do chaveiro. A sonda usa proxy efêmero com GetSecret limitado a itens cujo atributo service identifica agy/Antigravity. Não concede CreateItem, SetSecret, Delete, Unlock ou acesso em lote a segredos. Não copia conversas ou configurações pessoais. Sem identificação inequívoca, chaveiro desbloqueado e token válido, bloqueia e registra motivo. Nenhum serviço permanente é criado. Resultado real do agy ainda pendente; não declarar conectividade ou revisão realizada.


## Identificação do serviço usado pelo agy

O diagnóstico fornecido encontrou um item com campos service e username, cujo SHA-256 do serviço é 5d72436256ada53828b51895a94bb8489e9f1ac4fe937a8024ef1594e7045ff6. A análise estática do executável instalado identificou a constante `gemini` na rotina `codeassistclient.(*KeyringTokenStorage).LoadStoredToken`, endereço 0x7846e80. A chamada passa o endereço 0x5088215 e comprimento 6 ao armazenamento de chaveiro. Os bytes desse endereço são `gemini`, com hash correspondente. Não houve leitura de segredos nem chamada de modelo nessa análise. Evidências: evidencias/agy-autenticacao-estatica/.

O script de ensaio agora seleciona esse serviço somente com campo username e verifica o SHA-256 do executável contra a análise. O proxy continua sem autorização de escrita ou desbloqueio do chaveiro. Isso corrige a seleção do ensaio, não demonstra autenticação efetiva nem revisão. A chamada real com essa seleção aguarda execução no terminal com D-Bus disponível. Nenhum código de produção foi alterado.


## Falha de autenticação e ponte temporária

A chamada real posterior selecionou o serviço correto, mas retornou ERROR após 60,855 segundos: authentication failed or timed out, zero turnos e zero tokens. O agy pediu login interativo. Isso não comprova execução de modelo. A rotina secretServiceProvider.Get do binário chama Unlock antes de GetSecret; o proxy anterior bloqueia esse método. Essa é uma hipótese fundamentada para a falha, ainda sem observação de tráfego que a confirme.

Preparado scripts/ponte_agy_privada.py: barramento D-Bus efêmero em runtime sintético, seleção única por service=gemini e username, origem necessariamente já desbloqueada, atributos mantidos apenas em memória. Unlock é respondido no barramento sintético; nunca encaminhado à origem. Apenas SearchItems, leitura de propriedades, OpenSession/GetSecret do item selecionado e Close são usados na origem. Não há métodos de escrita implementados na ponte. O segredo é encaminhado em memória ao provedor autorizado, sem gravação nos registros. Contagens de leitura e Unlock sintético são registradas. O processo e o barramento terminam após o teste. A ponte não faz parte da produção e seu funcionamento efetivo ainda requer ensaio no terminal com sockets.


## Segunda tentativa: ponte sem acesso à credencial

A ponte privada foi executada no terminal: agy retornou erro de autenticação após 60,839 segundos, com zero leituras de segredo, zero Unlock sintético e zero escritas na origem. Portanto, não há confirmação de que o bloqueio anterior de Unlock causou a falha. A tentativa não validou o modelo. Acrescentados contadores de métodos sem argumentos pessoais e sonda local `ponte_agy_privada.py RAIZ --diagnosticar`. Ela testa OpenSession plain, consulta de coleções, busca do item, Unlock sintético e Close pelo mesmo isolamento nativo, sem GetSecret ou chamada ao modelo. A execução da sonda permanece pendente no terminal compatível. Registros existentes passam a ser copiados para tentativas-agy antes de cada tentativa.


## Sonda: NoReply antes de OpenSession

Resultado recebido: barramento presente, erro org.freedesktop.DBus.Error.NoReply; ponte registrou SearchItems=2 e Properties.Get=1, mas zero OpenSession, Unlock e GetSecret. Não há evidência de falha do token. A sonda inicial usava introspecção automática de dbus-python, que pode requerer métodos não autorizados pelos proxies; portanto, a própria sonda pode influenciar a falha. A sonda seguinte desativa introspecção e fornece assinaturas explícitas, com prazo de cinco segundos por chamada. Compara o barramento privado direto, o proxy externo e o isolamento nativo, sem leitura de segredo e sem chamada remota. Resultados efetivos dessa comparação ainda pendentes. Nenhum controle de produção foi relaxado.
