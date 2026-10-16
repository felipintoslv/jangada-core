# Jangada 3.0: modularização em core, shell e monitor

Situação em 10/10/2026: as Fases 3 e 4 foram executadas. O conteúdo está em
`core/`, `shell/` e `monitor/`, com links de compatibilidade nos caminhos
antigos. A conferência dos critérios de aceitação e as pendências para
depois da 3.0 estão em [06-validacao-final.md](06-validacao-final.md).

O texto abaixo é o planejamento das Fases 0, 1 e 2, escrito antes de
qualquer mudança de pasta e mantido como registro: onde ele diz que nenhum
código foi movido, descreve o estado daquela data.

| Documento | Entregável |
|---|---|
| Este arquivo | Linha de base (Fase 0), resumo, decisões em aberto |
| [01-inventario.md](01-inventario.md) | 1. Inventário e destino de cada arquivo |
| [02-arquitetura.md](02-arquitetura.md) | 2, 3 e 4. Arquitetura atual, proposta e matriz de dependências |
| [03-contratos.md](03-contratos.md) | 5. Contratos entre módulos e seus testes |
| [04-backlog.md](04-backlog.md) | 6. Backlog multiagentes |
| [05-migracao-testes-reversao.md](05-migracao-testes-reversao.md) | 7 e 8. Migração incremental, testes e reversão |
| [prova-links.md](prova-links.md) | Prova dos links simbólicos (M3-02, decisão D2) |
| [06-validacao-final.md](06-validacao-final.md) | Validação final (M3-20): critérios de aceitação, teste de remoção e pendências |

## Resumo

1. O repositório continua único. `core/`, `shell/` e `monitor/` passam a ser
   pastas reais na raiz, e `bin/` permanece como fachada pública: todo
   `jangada-*` continua em `$JANGADA_CORE_PATH/bin`.
2. Dos 59 comandos, 23 vão para o Core, 25 para o Shell, 4 para o Monitor e
   7 ficam compartilhados em `bin/`. Dos 127 arquivos de `default/`, 78 vão
   para o Core, 36 para o Shell, 10 para o Monitor e 3 ficam compartilhados.
3. A pasta `shell/` existente (integração com Bash e Zsh) não é sobrescrita.
   Os dois arquivos ficam onde estão e o módulo cresce ao redor deles.
4. Os caminhos antigos continuam válidos por links simbólicos relativos
   versionados (`bin/jangada-x`, `default/hypr` e semelhantes). Isso evita
   migração imediata dos arquivos do usuário que guardam caminho absoluto.
5. Dez contratos precisam existir antes de mover código (K10 entrou pela
   decisão D8). Cinco deles
   desfazem acoplamentos que hoje impedem a separação (Core que sinaliza a
   Waybar, painel que herda a classe de escrita do Core, consulta que limpa
   estado, entre outros).
6. O backlog tem 24 tarefas em quatro ondas. A primeira onda não move nada:
   cria os testes de contrato e desfaz os acoplamentos.

## Fase 0: linha de base

| Item | Valor |
|---|---|
| Repositório de desenvolvimento | `~/Projetos/jangada` (`JANGADA_REPO` confirmado pela variável de ambiente) |
| `main` e `origin/main` | `ad30fdd`, cópia de trabalho limpa |
| Cópia instalada | `~/.local/share/jangada` em `db0ee93`, três commits de documentação atrás; não foi tocada |
| Referência Git | etiqueta anotada local `jangada-pre-modularizacao-3.0` em `ad30fdd`, não enviada |
| Worktree de planejamento | `~/.local/share/jangada-worktrees/jangada/modularizacao-3-0-planejamento`, ramo `agente/modularizacao-3-0-planejamento` |
| Worktrees que já existiam | `tarefa-a57239626af5`, `~/Projetos/jangada-baseline-2026-10`, `~/Projetos/jangada-confianca-p0`; nenhum foi alterado |
| Suíte de testes | `JANGADA_CORE_PATH=$PWD testes/verificar.sh` em `ad30fdd`, em 09/10/2026: saída 0, "tudo certo", 3 min 43 s |

A execução anterior registrada em `docs/estabilizacao/TESTES_BASELINE.md`
(commit `5816c76e8182`) saiu com 1 e sete grupos falhos por limite do
ambiente em que rodou. A linha de base desta modularização é a execução de
hoje, com saída 0: qualquer grupo que falhe depois de uma tarefa é regressão.

Procedimentos já documentados e adotados sem mudança:

- Cópia de segurança e recuperação: `docs/estabilizacao/BACKUP_RECUPERACAO.md`
  (`cp -a` das pastas de configuração e estado, `backup()` do SQLite com WAL,
  restauração em pasta nova, `git worktree repair` só com supervisão).
- Testes: `testes/verificar.sh` e a integração contínua em
  `.github/workflows/verificar.yml` (trabalhos `verificar` e `sandbox-e2e`).
- Volta ao ponto de partida: `git switch main` e, se for preciso comparar,
  `git diff jangada-pre-modularizacao-3.0`. Nenhum comando de descarte é usado.

## Como o trabalho foi dividido

| Papel | Quem fez nesta execução | Entrega |
|---|---|---|
| Coordenador | sessão principal (Claude) | linha de base, consolidação, contagens por `git grep`, backlog |
| Agente Core | subagente `arquiteto` do jangada, só leitura | classificação de `bin/` e dos pacotes Python, acoplamentos do Core |
| Agente Shell | subagente `arquiteto`, só leitura | comandos de área de trabalho, funções de `shell/`, Waybar, instalação |
| Agente Monitor | subagente `arquiteto`, só leitura | painel, fontes de dados, formatos de registro |
| Transversal | subagente `explorador`, só leitura | testes, integração contínua, migrações |
| Agente Revisor | subagente diferente do autor | revisão deste conjunto (ver "Revisão" abaixo) |

A Central de Tarefas não foi usada nesta execução porque importar tarefas
grava nos bancos da instalação ativa, o que a especificação proíbe sem
autorização. A fila (`jangada-fila --importar`) também não serve para as
tarefas de implementação: ela atende delegações de leitura e redação. As
tarefas de escrita do backlog sobem por `jangada-agente`, uma worktree cada.

## Decisões em aberto

Os itens D1 a D7 trazem a recomendação adotada nos documentos. Mudar a
resposta muda o inventário, não o método. D8 a D11 registram decisões do
usuário.

| # | Decisão | Recomendação | Alternativa |
|---|---|---|---|
| D1 | Monorepositório ou três repositórios | Monorepositório, como pede esta especificação | Três projetos com Git próprio (ver "Conflito") |
| D2 | Como manter os caminhos antigos | Links simbólicos relativos versionados; a [prova dos links](prova-links.md) manteve D2 com ressalvas | Arquivos de repasse de duas linhas em `bin/` |
| D3 | Central de Tarefas e janela de conversa | Shell, porque mudam estado pelo Core; o Monitor fica só de leitura | Monitor, como classificou o agente Shell |
| D4 | Subpastas do esboço (`core/projetos`, `core/tarefas`, `monitor/historico` etc.) | Mover os pacotes Python inteiros e criar só as subpastas que correspondem a unidades existentes | Dividir os pacotes agora, o que obriga a reescrever importações |
| D5 | `testes/` ou `tests/`, e `scripts/` | Manter `testes/` (regra 7) e não criar `scripts/` | Renomear |
| D6 | Limpeza de sessões órfãs | Sai da consulta e vira ação explícita, chamada pelo próprio Shell | Manter como está e registrar exceção |
| D7 | Quando retirar os links de compatibilidade | Só em versão posterior, com migração própria e autorização | Nunca retirar |
| D8 | Destino dos 20 acoplamentos `sem-contrato` da M3-03, não retirados por K3 a K6 (ver situação em [04-backlog.md](04-backlog.md#m3-03-teste-de-fronteira)) | Decisão do usuário em 10/10/2026: 14 retirados por contrato, no mínimo (10 pelo K10 na M3-10b; 5 na M3-10c, 4 pelo caminho único de K5 e 1 pela consulta K4, ou 4 se o modo `--simular` precisar do padrão), e no máximo 6 exceções permanentes com motivo ([03-contratos.md](03-contratos.md#exceções-permanentes-de-k9)) | Mudança de módulo, não adotada |
| D9 | Integração pelo botão e por alt+i | Decisão do usuário em 09/10/2026: restaurar na M3-11a, logo depois do portão da M3-11 e antes da M3-12, com confirmação humana por entrega | Até a M3-11a, `--integrar` continua recusando |
| D10 | Autor e revisor das tarefas novas abertas por criação de agentes | Decisão do usuário em 10/10/2026: `claude` como autor e `codex` como revisor, o que mantém a revisão cruzada; M3-12 a M3-15 passam a Shell (`claude`), revisor `codex`; tarefas já integradas não mudam ([04-backlog.md](04-backlog.md#papéis-e-provedores)) | Shell (`codex`), revisor `claude`, como estava |
| D11 | Ordem da Onda C | Decisão do usuário em 10/10/2026: duas frentes. M3-12 sozinha, com portão humano e teste em Hyprland aninhado; M3-13 e M3-16 em paralelo; M3-14 e M3-17 em paralelo; M3-15 e depois M3-18. A M3-16 passa a depender também da M3-12 integrada. Até duas sessões de escrita ao mesmo tempo, as duas com `claude` como autor e `codex` como revisor. Em cada par, a segunda tarefa faz rebase sobre o `main` e roda `testes/verificar.sh` de novo fora do isolamento ([04-backlog.md](04-backlog.md#onda-c-migração-fase-4)) | Uma frente só, com uma sessão por provedor, como estava |

## Conflito a resolver antes da Fase 3

Há uma sessão do jangada em andamento,
`projeto--jangada3-0--tarefa-d20387ba5283`, na pasta
`~/Projetos/Projeto- Jangada3.0`, com uma versão anterior desta tarefa. Por
volta das 20h de 09/10/2026 ela recebeu a instrução "Opção 3, reescreva o
plano", que significa três projetos novos, cada um com seu Git. Esta
especificação diz o contrário ("Não criaria três repositórios nem três
aplicações totalmente separadas agora").

Este planejamento seguiu o monorepositório. A outra sessão não foi tocada.
O diagnóstico dela (`docs/arquitetura/modulos.md` e `dependencias.md`
naquela pasta) foi usado só como conferência cruzada: os achados de
acoplamento coincidem. Uma divergência foi resolvida: os formatos de
`SESSAO.json`, `eventos-agentes.jsonl` e `delegacoes.jsonl` já estão
documentados em `docs/registros.md` (seções 4, 8 e 9); o que falta é teste
de formato. Convém encerrar ou redirecionar uma das duas frentes.

## Revisão

O conjunto foi lido por um subagente `supervisor`, que não participou da
redação, com parecer `STATUS: REVISAR` e quatro achados:

| Achado | Tratamento |
|---|---|
| `default/` teria 126 arquivos, não 127 | não procede: `git ls-files default` e `find default -type f` dão 127 |
| `jangada-monitor --json` chama `default/nucleo/monitoramento.py` | procede; registrado no inventário 1.1 e ligado à M3-17 |
| A observação de `jangada-agentes` não dizia que a limpeza é o estado de hoje | procede; texto corrigido |
| Linhas dos hooks citadas de forma compacta | sem mudança |

O revisor conferiu por amostragem as linhas citadas, as contagens de `bin/`
e `testes/` e a sintaxe dos diagramas. Ele não conferiu a tabela de testes
por módulo arquivo a arquivo; isso segue como parte da M3-01. A revisão por
modelo cruzado (`jangada-validar` com `codex`) não foi feita, porque grava
no estado da instalação ativa; ela fica para a primeira tarefa aprovada.

## O que não foi feito

- Nenhum arquivo executável foi movido, criado ou alterado.
- Nada foi gravado na cópia instalada, em `~/.config`, nem nos bancos de
  estado.
- Nenhuma tarefa foi importada na fila e nenhuma sessão de agente com
  escrita foi aberta.
- Nada foi enviado ao remoto nem integrado ao `main`.
