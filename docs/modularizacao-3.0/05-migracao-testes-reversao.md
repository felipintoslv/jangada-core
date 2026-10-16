# 7 e 8. Migração incremental, testes e reversão

## 7. Plano de migração incremental

### Princípios

1. Contrato antes de pasta. A Onda A desfaz os acoplamentos com o código
   ainda no lugar. Se a migração parar depois dela, o repositório já fica
   melhor e nada mudou de caminho.
2. Um commit por mudança de pasta, com o link de compatibilidade no mesmo
   commit. Não existe estado intermediário em que um caminho antigo falte.
3. Mover não é editar. Cada tarefa da Onda C mostra só renomeações em
   `git diff -M -B --stat`. Correção de conteúdo é outra tarefa.
4. O jangada instalado segue na versão anterior enquanto o usuário quiser.
   O desenvolvimento usa `JANGADA_CORE_PATH=$PWD` na worktree. A cópia instalada
   só avança por `jangada-update`, confirmado no terminal.
5. Nenhuma migração de `migrations/` é necessária enquanto os links
   existirem. Migração que reescreva caminhos do usuário só entra se D7
   decidir retirar os links, e exige autorização própria.

### Etapas

| Etapa | Tarefas | O que muda para quem usa | Portão |
|---|---|---|---|
| 0 | este plano | nada | aprovação do usuário |
| A | M3-01 a M3-10, M3-10a, M3-10b e M3-10c | nada visível; uma opção nova (`--limpar-orfaos`) | `verificar.sh` 0 e revisão cruzada por tarefa |
| B | M3-11 | pastas novas vazias | aprovação do usuário |
| B1 | M3-11a | restaura integração pelo botão e por alt+i, depois do portão da M3-11 e antes da M3-12 | revisão cruzada, `verificar.sh` 0 fora do isolamento e confirmação humana por entrega |
| C1 | M3-12 a M3-15 | arquivos do Shell mudam de pasta; caminhos antigos seguem | teste em Hyprland aninhado; aprovação antes da primeira |
| C2 | M3-16, M3-17 | pacotes Python, perfis e painel mudam de pasta | ciclo em estado temporário |
| C3 | M3-18 | comandos do Core mudam de pasta | ciclo completo em repositório de teste |
| D | M3-19, M3-20 | documentação | leitura final do usuário |

Ordem dentro da Onda C: o Shell vai primeiro porque tem menos importações
entre arquivos e porque um defeito aparece na hora (a sessão aninhada não
sobe). O Core vai por último porque é a ferramenta que conduz a migração.

Decisão do usuário em 10/10/2026 (D11): as linhas C1 e C2 da tabela agrupam
as tarefas por módulo, não por ordem no tempo. A execução corre em duas
frentes:

1. M3-12 sozinha, com a aprovação do usuário e o teste em Hyprland aninhado
   antes de integrar.
2. M3-13 e M3-16 em paralelo.
3. M3-14 e M3-17 em paralelo.
4. M3-15, depois M3-18.

Os portões de cada linha da tabela continuam valendo para as tarefas dela.
A integração segue uma tarefa por vez. Em cada par, a segunda tarefa faz
`git rebase` sobre o `main` na própria worktree e roda `testes/verificar.sh`
de novo fora do isolamento antes de integrar; o restante da regra está em
[04-backlog.md](04-backlog.md#onda-c-migração-fase-4).

Divergência registrada, sem ajuste: o parágrafo acima diz que o Shell vai
primeiro e o Core por último. Com a D11, isso vale para a M3-12 e para a
M3-18. A M3-16 integra antes da etapa da M3-14 e da M3-17, e a M3-17 integra
antes da M3-15. Dentro de cada par, a ordem de integração não está fixada.

### Atualização da cópia instalada

Recomendação: rodar `jangada-update` em três momentos, não a cada tarefa.

1. Depois da Onda A, com alguns dias de uso.
2. Depois de C1, com a sessão gráfica testada antes em modo aninhado.
3. Depois de M3-20.

Divergência registrada, sem ajuste: com a D11, quando C1 termina (M3-15
integrada), a M3-16 e a M3-17 já estão no `main`. A atualização do momento
2 leva junto as mudanças de C2, e o portão de C2 (ciclo em estado
temporário) precisa estar cumprido antes dela. O usuário não decidiu se o
momento 2 muda.

Na M3-10a, a conferência de processos do `jangada-update` passa a procurar
`core/`, `shell/` e `monitor/` sob `JANGADA_CORE_PATH`, além de `default/` e
`bin/jangada-*`. A aceitação usa processos em uma instalação falsa e
confere a recusa antes de atualizar.

Antes de cada um: cópia de segurança conforme
`docs/estabilizacao/BACKUP_RECUPERACAO.md` e anotação do commit instalado.

## 8. Plano de testes e reversão

### Camadas de teste

| Camada | O que confere | Quando roda |
|---|---|---|
| Linha de base | `testes/verificar.sh` com saída 0, como em `ad30fdd` | toda tarefa |
| Contratos | `testes/contratos-*` (K1, K2, K3, K4, K7) e `testes/fronteiras.sh` (K9) | toda tarefa a partir de M3-01 e M3-03 |
| Módulo | testes do módulo, conforme inventário 1.6 | tarefa do módulo |
| Integração | ciclo `jangada-agente`, `jangada-validar`, `jangada-agente-fim` em repositório de teste com `JANGADA_CORE_PATH` da worktree e estado em pasta temporária | M3-04, M3-08, M3-16, M3-18 |
| Sessão gráfica | Hyprland aninhado (guia `hyprland.md` da skill), sem sair da sessão em uso | M3-12 a M3-15 |
| Isolamento | trabalho `sandbox-e2e` da integração contínua | M3-16, M3-18, M3-20 |
| Instalação | `install.sh` com `JANGADA_SIMULAR=1` em `HOME` vazio | M3-11 em diante |
| Remoção | testes do Core em cópia temporária sem `shell/` e `monitor/` | M3-20 |

Critério de regressão: qualquer grupo do `verificar.sh` que passe em
`ad30fdd` e falhe depois. A linha de base é saída 0, sem grupo tolerado.

Os testes de integração usam `JANGADA_ESTADO` e `HOME` temporários. Nenhum
teste abre os bancos da instalação ativa.

`testes/contratos-fachada.sh` e `testes/fronteiras.sh` copiam só parte do
repositório. Na tarefa de estrutura M3-11, passam a copiar também `core/`,
`shell/` e `monitor/`, para que os links da fachada resolvam nas cópias de
teste. `testes/contratos/modulos.txt` muda junto com cada mudança de pasta
na Onda C; K9 deve passar com a lista atualizada no mesmo commit.

### Revisão

| Passo | Quem | Regra |
|---|---|---|
| Conferência local | subagente `verificador` na própria sessão | só lista problemas, não aprova |
| Parecer | `jangada-validar` com o modelo cruzado | primeira linha `STATUS: APROVADO`; `REVISAR` volta ao autor |
| Integração | usuário | uma tarefa por vez, com assinatura por `jangada-assinar`; até a M3-11a, manual; depois, pelo botão ou por alt+i, com as conferências da M3-11a |

Uma tarefa com três pareceres `REVISAR` seguidos para e volta ao
Coordenador, que a redivide ou a devolve ao usuário.

### Reversão

| Situação | Procedimento |
|---|---|
| Tarefa reprovada antes de integrar | o ramo `agente/m3-NN` fica como está; nada a desfazer no `main` |
| Tarefa integrada com defeito | `git revert <commit>` no `main`, novo commit, sem reescrever histórico |
| Cópia instalada com defeito depois de `jangada-update` | com autorização do usuário: `git -C ~/.local/share/jangada switch --detach <commit anotado antes>`; voltar ao `main` quando o `revert` estiver disponível |
| Sessão gráfica não sobe | entrar por TTY ou por outra sessão do SDDM, aplicar a linha acima; o relatório de falha fica em `~/.cache/hyprland/hyprlandCrashReport*.txt` |
| Estado suspeito | restaurar a cópia de segurança em pasta nova, conforme `BACKUP_RECUPERACAO.md`; nunca por cima do estado em uso |
| Abandono da modularização | `main` volta a `jangada-pre-modularizacao-3.0` por uma série de `git revert`; as tarefas da Onda A podem ficar, porque não dependem das pastas novas |

Não entram em nenhum procedimento: `git reset --hard`, `git clean -fd`,
remoção de worktree existente, reinício automático da sessão gráfica,
edição direta da cópia instalada.

### Critérios de aceitação da especificação

| Critério | Como se confere |
|---|---|
| Três pastas reais no monorepositório | M3-11 e Onda C |
| Core independente do Shell e do Monitor | K9 sem exceção `sem-contrato`, só as exceções permanentes da D8, e teste de remoção em M3-20 |
| Monitor por contratos definidos | K5 e K7 |
| Comandos `jangada-*` preservados | K1 em toda tarefa |
| `shell/` existente não sobrescrito | `sha256sum` dos dois arquivos em M3-11 e na Onda C |
| Sistema atual operacional durante o processo | cópia instalada na versão anterior até cada `jangada-update` |
| Nenhum agente aprova a própria alteração | revisão cruzada por `jangada-validar` |
| Integração supervisionada | confirmação humana por entrega; até a M3-11a, manual; depois, botão ou alt+i com as conferências da M3-11a |
