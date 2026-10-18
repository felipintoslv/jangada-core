# Relatório final P1

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

**P1 INCONCLUSIVA.** Todos os ensaios seguros deste plano executáveis no ambiente foram concluídos; a missão não demonstrou o fluxo com modelos reais nem a comunicação integrada. Não há evidência suficiente para aprovar 30 dias de utilização experimental ou congelamento.

## A. Integridade da plataforma

32 testes P0 passaram, incluindo Bubblewrap real, e três testes complementares passaram. Não houve falsificação aceita na amostra. Oito documentos foram reconstruídos integralmente apenas do arquivo histórico, com hashes verificados. Integração automática continua bloqueada. As três worktrees e os bytes do código exportado permanecem preservados, conforme `integridade-final.json`.

A marca de uma aprovação antiga permanece possível, mas o backend distingue sua versão da nova reprovada (`marca_atual=false`). Isso não foi classificado como ataque aceito. Não foram inventadas identidades ou decisões reais a partir de mocks.

## B. Funcionamento operacional

Cadastro e atividade sintéticos confirmados; tarefa ECON-P1 permanece QUEUED sem execução. Suítes de protocolos, supervisão, reservas, retomada e encerramento passaram. 63/67 testes Qt passaram; quatro ficaram bloqueados por sockets, com falhas brutas conservadas. Não houve execução de modelos, revisão independente real, reprovação/correção real, Shiny ou fluxo completo da Central. Acesso externo não previamente autorizado e restrições de sockets impediram os requisitos essenciais.

## C. Qualidade analítica

Oráculo independente Python/R concordou nas duas sementes. Foram executadas 16 entregas R artificiais com oito classes de defeitos, todas aprovadas pelos testes estruturais públicos e confrontadas com controles privados. Detecções pertencem ao auditor, não aos modelos. Segunda rodada determinística passou; segunda rodada cega de IA não foi executada. Referências textuais e código executável não comprovam validade metodológica ou corroboram resultados empíricos.

## O que permanece pendente

Modelos reais de famílias distintas com acesso previamente autorizado; tarefa econômica completa com gráficos e Shiny; pareceres cegos, divergências, correções e nova revisão; testes privados da entrega final; aprovação protegida e recuperação do histórico integral dessa atividade; comunicação e interface em ambiente compatível. A solução avaliada não pode ser declarada capaz de distinguir erros semânticos de revisores apenas pelos resultados deste ensaio.

## Próxima etapa

Repetir o ciclo real em ambiente com isolamento preservado e sockets permitidos, credenciais de teste autorizadas e duas famílias de modelos. Conservar critérios e gabarito privados, executar a segunda rodada cega e recuperar as evidências após encerramento. Não modificar produção para favorecer aprovação. Não iniciar o período de 30 dias como versão validada antes dessa verificação.

Os onze relatórios, scripts, dados artificiais e logs estão fora da versão avaliada. Nenhum commit de produção, push, merge ou tag foi produzido nesta missão.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.


## Reexecução no terminal local

Logs recebidos e hashes conferidos em `evidencias/jangada-p1-comunicacao-833nd0if/`: interface 66/67 PASSOU, um FALHOU em `QLocalServer.listen`; P0 32/32 PASSOU. Os quatro bloqueios anteriores não devem mais ser tratados como indisponibilidade geral neste terminal. A falha restante está em investigação; possível limite do comprimento do caminho, ainda sem confirmação. A reprodução seguinte usa caminhos menores e sonda de erro Qt, sem mudar produção. O ciclo com modelos reais permanece pendente e a classificação geral continua P1 INCONCLUSIVA.


## Resultado atualizado: interface 67/67

Execução no terminal local, logs e hashes conferidos em `evidencias/jp1-pio6_bdi/`: 67/67 testes de interface PASSOU, em 7,031 segundos segundo unittest. Os 32 testes P0 passaram na execução local anterior. Os quatro bloqueios de sockets estão superados para essas suítes no terminal local. Isso não comprova interface gráfica completa com modelos reais.

A falha anterior não se repetiu após encurtar caminhos sintéticos. O comprimento do socket permanece hipótese de causa, pois a sonda complementar do auditor falhou por erro de sintaxe. Esse erro está preservado em `sonda-qt.stderr.log`, pertence ao experimento e não invalida os 67 testes efetivamente executados. O script de diagnóstico foi corrigido sem mudar produção; o diagnóstico corrigido ainda não foi executado no terminal local. Não é necessário repetir a suíte aprovada apenas para esse diagnóstico.

Classificação P1: INCONCLUSIVA enquanto execução real, revisão independente, correção e aprovação econômica não forem demonstradas. Não há autorização registrada para chamadas remotas do ensaio.


Continuação autorizada: usuário autorizou Codex executor e Claude revisor, com dados sintéticos. Scripts e condições estão em `EXPERIMENTO_REAL.md`. Nenhuma chamada real ocorreu ainda nesta sessão; aguardam execução no terminal compatível.


## Conferência independente executada no terminal local

PASSOU: commit bb3ad6b4b2bb8f3032e28efb7af5f1a5c4abb9bb, código SHA-256 fe56b11787d68b0fb9497e10d0176915a1a15f05e04fc7e30b3be1e75508c74c. Sete cenários com 42 verificações cada, total 294. Condição normal, alteração de outro ano, município com total zero, setor com total zero, ausência pontual, todas as observações ausentes e ordem invertida concordaram com referência Python. Execução R em Bubblewrap sem rede, somente código e dados públicos montados; gabarito Python fora das montagens.

Registro conferido: evidencias/jctrl-jt5vmx8p/resumo.json; insumos e saídas sintéticos preservados no mesmo diretório. Nenhuma chamada de modelo nesse ensaio. Isso valida os indicadores na amostra e segundo a política explícita de propagação de ausências; não valida a atividade econômica extensa, generalização universal ou causalidade.

Pendentes: revisão protegida pelo controlador, parecer metodológico fundamentado, aprovação autorizada e reconstrução histórica do ciclo real após encerramento. Preparação independente original não foi demonstrada. P1 permanece INCONCLUSIVA.


## Identidade da versão do ensaio nativo

O campo comando do registro da sessão par-cobaia--tarefa-9c1ba243388f aponta para ~/.local/share/jangada/bin/jangada-isolar e jangada-codex. Conferência somente de leitura constatou que agente, validar, isolar e agente-fim instalados diferem da P0; default/orquestracao/confianca.py não existe na instalação. Evidências em versao-ensaio-nativo.json. O commit da instalação não foi identificado só pelos hashes.

O ensaio demonstra comportamento da instalação utilizada e do artefato bb3ad6b, não execução do ciclo real pela versão P0. Os 32 testes P0 e os 67 testes Qt anteriores continuam associados ao código exportado do commit 17178ded. É necessário repetir o ciclo real com executáveis explicitamente da cópia P0 e estado independente. Não alterar ou encerrar a sessão existente para tentar certificar outra versão. Classificação permanece P1 INCONCLUSIVA.


## Encerramento desta etapa

A pedido do usuário, a investigação foi interrompida e os resultados registrados em commit local no repositório externo de resultados. O ciclo completo permanece não validado. A última sonda de chaveiro retornou NoReply antes de OpenSession. A sonda seguinte foi preparada e compilada, mas não executada no terminal compatível. Classificação final desta etapa: P1 INCONCLUSIVA. Não há recomendação de congelamento com base nessa validação.
