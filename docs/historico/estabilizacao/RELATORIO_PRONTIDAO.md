# Relatório de prontidão

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

**APTA para congelamento da baseline de 30 dias.** Em 09/10/2026 as quatro condições estão atendidas. A tag `jangada-baseline-2026-10` é criada pelo usuário sobre a `main` assinada; a integração automática segue bloqueada durante o período. As seções a partir de "Avaliação original" descrevem o código `5816c76` e ficam como histórico.

## Situação em 09/10/2026

Código conferido: `db0ee931acd251c647f7665a780f6232efe0b164`, na instalação ativa (versão `0.2.0-277`), com commits assinados e 0 migrações pendentes. A `main` está à frente da instalação só em `docs/`. A atualização foi de somente código; nenhum pacote do sistema foi alterado.

| Condição | Estado | Evidência |
|---|---|---|
| Suíte completa sem falhas em ambiente compatível | Atendida | `testes/verificar.sh` no terminal do host, fora das sessões: 1.514 verificações `ok`, 0 falhas. |
| Ensaio gráfico com agente e revisor reais em projeto sintético | Atendida | Projeto `teste-central`, sessão `teste-central--tarefa-ba2e86f7c899`: agente Claude, commit `a0d0231`, revisão do Codex aprovada na rodada 2, com contexto e marca gravados. Alt+I recusou a integração automática e manteve sessão, ramo e worktree. Ctrl+X encerrou a sessão, removeu a worktree e manteve o ramo; a `main` do projeto não mudou. |
| Backup completo e recuperação conferidos | Atendida, com uma exceção | Backup de 09/10 às 18:56 em `~/jangada-baseline-backup-20261009-185618`, feito com sessões, Central e painel parados: instalação, configuração, estado, worktrees e `~/Projetos`. O `diff -rq` entre origem e cópia deu 0 diferenças nos quatro primeiros e 1 em projetos: a pasta `CNPJ/pgdata`, de outro usuário do sistema, não foi lida e ficou fora. O `repo.bundle` clona, passa no `git fsck` e confere com a `main`; os 5 bancos passam no `integrity_check`; o manifesto SHA-256 lista 59.852 arquivos. A recuperação foi ensaiada com o backup das 18:43, restaurado em pasta descartável: bundle, instalação limpa, configuração idêntica e bancos íntegros. |
| Uso supervisionado com integração manual aprovado | Atendida | Aprovado pelo usuário em 09/10/2026, com o bloqueio da integração automática mantido. Uma integração pelo atalho e pelo botão, com conferências e confirmação humana, fica para depois da tag, em ramo separado. |

O ensaio gráfico revelou um defeito, corrigido em `db0ee93`: a limpeza de sessões órfãs da barra apagava o contexto da rodada (`validacao-<sessão>-rN.contexto.json`) cerca de 1 s depois de gravado, e o `jangada-validar` dentro da sessão falhava ao registrar a decisão. A rodada 1 do ensaio falhou por isso; a rodada 2, já com a correção instalada, passou.

Não conferido neste ensaio: o arquivo da revisão em `revisoes/arquivo`, que a sessão isolada usada na conferência não enxerga. Depois do encerramento, contextos, registros e verificações das rodadas permanecem em `agentes/`; só os pareceres e a marca saem.

## Avaliação original

Esta seção e as seguintes valem para o código `5816c76`.

O risco prioritário de perda de edições concorrentes foi efetivamente bloqueado. A integração automática não publica nem recupera o principal e conserva sessão, ramo e worktree. A reversão automática ao atingir limite também foi bloqueada. Validação indisponível, pulada, autorrevisão e autoria externa sem cópia protegida não geram aprovação. As marcas e a prévia conferem identidade da entrega.

Há evidência positiva dos ensaios de preservação, aprovação, encerramento, atualização, backup e recuperação sintéticos e das duas suítes R do painel. A suíte completa foi executada, mas não passou: o sandbox impede comunicação local e o perfil de isolamento sem rede. Foram 7 grupos reprovados, descritos em `TESTES_BASELINE.md` e `EVIDENCIAS.json`; isso não significa apenas 7 asserções individuais. Essas etapas não podem ser corrigidas alterando serviços ou permissões globais, nem por execução fora do isolamento, dentro dos limites desta missão.

## Disponível e restrito

Disponíveis na worktree de engenharia: comandos de projetos e tarefas, fila e persistência; execução em worktree e isolamento existente; revisão congelada; validação com recusa conservadora; encerramento após conferência; atualização e assinatura; componentes da Central e do painel. A aplicação cotidiana desses fluxos depende das verificações de ambiente pendentes.

Bloqueados no backend: integração automática com ramo próprio e reversão automática da validação. Restritos por falta de evidência: ponta a ponta gráfico, comunicação completa de serviços locais e validação sem rede neste sandbox. A execução sem isolamento também foi bloqueada: `--sem-isolar` e `JANGADA_AGENTE_ISOLAR=0` são ignorados com aviso. Os modos manuais de trabalho direto e descarte ainda existem; não compõem o plano de 30 dias.

## Condições para congelar

Executar a suíte completa sem falhas em ambiente compatível, incluindo isolamento real, D-Bus e serviços locais; concluir um ensaio gráfico com agente e revisor reais sobre projeto sintético; conferir backup completo e recuperação; aprovar uso supervisionado com integração manual. Até lá, conservar os commits para revisão e não criar `jangada-baseline-2026-10`.

Código conferido na avaliação original: `5816c76e81829569e9e4c9593ed176c53c4e69bc`.

O ramo de estabilização contém somente commits locais. `main`, `estavel`, instalação ativa, serviços e pacotes do host foram preservados. Nenhum push, merge em main, release ou tag foi executado. Os commits e seus testes estão registrados em `EVIDENCIAS.json`; o commit final de documentação é apresentado na entrega da missão.
