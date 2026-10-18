# Interface e comunicação

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

A suíte `testes/tarefas.py` executou 67 casos: 63 passaram e quatro falharam nas condições de comunicação local. Os quatro são classificados BLOQUEADO para a auditoria operacional, com resultado bruto FALHOU preservado em `interface-67.stderr.log`. AF_UNIX bind e AF_INET socket produzem EPERM nas sondagens independentes. Não se removeram proteções para contornar o ambiente.

Suítes backend passaram: orquestração 30, executor 42, supervisão 26, operacional 36, determinístico 26, acompanhamento 12 e painel-orquestração três. Cadastro/atividade real no backend sintético também observado. Isso não comprova atualização completa da Central, comunicação local ou recuperação gráfica integrada.

`testes/fim.sh` e `testes/restaurar.sh` passaram. Sessões, tmux e provedores são fixtures nesses testes. Qt offscreen não substitui experiência gráfica real. A versão avaliada mantém os bloqueios ambientais anteriores; nenhuma regressão crítica foi confirmada por esta amostra.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.


## Reexecução no terminal local

Logs recebidos e hashes conferidos em `evidencias/jangada-p1-comunicacao-833nd0if/`: interface 66/67 PASSOU, um FALHOU em `QLocalServer.listen`; P0 32/32 PASSOU. Os quatro bloqueios anteriores não devem mais ser tratados como indisponibilidade geral neste terminal. A falha restante está em investigação; possível limite do comprimento do caminho, ainda sem confirmação. A reprodução seguinte usa caminhos menores e sonda de erro Qt, sem mudar produção. O ciclo com modelos reais permanece pendente e a classificação geral continua P1 INCONCLUSIVA.


## Resultado atualizado: interface 67/67

Execução no terminal local, logs e hashes conferidos em `evidencias/jp1-pio6_bdi/`: 67/67 testes de interface PASSOU, em 7,031 segundos segundo unittest. Os 32 testes P0 passaram na execução local anterior. Os quatro bloqueios de sockets estão superados para essas suítes no terminal local. Isso não comprova interface gráfica completa com modelos reais.

A falha anterior não se repetiu após encurtar caminhos sintéticos. O comprimento do socket permanece hipótese de causa, pois a sonda complementar do auditor falhou por erro de sintaxe. Esse erro está preservado em `sonda-qt.stderr.log`, pertence ao experimento e não invalida os 67 testes efetivamente executados. O script de diagnóstico foi corrigido sem mudar produção; o diagnóstico corrigido ainda não foi executado no terminal local. Não é necessário repetir a suíte aprovada apenas para esse diagnóstico.

Classificação P1: INCONCLUSIVA enquanto execução real, revisão independente, correção e aprovação econômica não forem demonstradas. Não há autorização registrada para chamadas remotas do ensaio.
