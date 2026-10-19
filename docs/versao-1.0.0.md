# Core 1.0.0

Notas da entrega e roteiro de lançamento da versão 1.0.0 estável do
jangada-core. O registro completo de mudanças está no
[CHANGELOG](../CHANGELOG.md), gerado por `jangada-versao`.

## Situação

Esta versão está preparada, não lançada. Enquanto o dono não executar o
[roteiro](#roteiro-do-dono), a tag `v1.0.0` não existe, os commits não estão
assinados nem publicados e a cópia instalada continua na versão anterior.

## O que o Core entrega

O Core funciona sozinho. Cada item remete ao guia do assunto.

| Área | Entrega | Guia |
|---|---|---|
| Sessões | `jangada-agente` abre autor e revisor em tmux, cada tarefa em worktree próprio; `jangada-agentes` lista, restaura e encerra | [Ciclo da tarefa](ciclo-da-tarefa.md) |
| Isolamento | `jangada-isolar` roda o agente no bubblewrap, obrigatório em todas as sessões; o agente é tratado como possivelmente hostil | [Isolamento](isolamento.md) |
| Validação cruzada | `jangada-validar` confere conflitos, sintaxe, segredos e testes do projeto e manda o diff ao revisor de outro modelo; perfis `claude-codex` e `codex-claude` | [Ciclo da tarefa](ciclo-da-tarefa.md), [Codex](codex.md) |
| Integração | `jangada-agente-fim --integrar` exige aprovação independente, confirmação humana e testes; avança só em linha reta | [Ciclo da tarefa](ciclo-da-tarefa.md#fim-da-sessão) |
| Delegação | `jangada-delegar` com destino e fontes explícitos: Ollama local ou agy; falha do destino é registrada e não troca de destino sozinha | [Subagentes e delegação](subagentes-e-delegacao.md) |
| Fila e provedores | fila persistente de tarefas, registro de provedores, estado e cota | [Subagentes e delegação](subagentes-e-delegacao.md#fila-persistente-de-projetos), [Provedores](provedores.md) |
| Coordenação | `jangada-coordenador` mantém uma atuação por projeto; ela persiste até o encerramento explícito (`--finalizar`) e pode ser retomada, inclusive em outro provedor depois da saída voluntária do anterior; a passagem entre provedores é manual | [Ciclo da tarefa](ciclo-da-tarefa.md#coordenador) |
| Diagnóstico | `jangada doctor` consulta o ambiente sem alterá-lo e separa falhas, avisos e itens não verificáveis | [Comandos](comandos.md#diagnóstico-do-ambiente) |
| Indicadores | `jangada-indicadores` resume consumo, procedência dos revisores e destinos de delegação | [Indicadores](indicadores.md) |
| Versão e atualização | `jangada-versao`, `jangada-assinar`, `jangada-update` e `jangada-migrar`; com `allowed_signers`, só entram commits assinados | [Instalação e uso](instalacao-e-uso.md#versões), [Atualização e migrações](atualizacao-e-migracoes.md) |

Quem vem de uma instalação anterior à separação dos módulos encontra a raiz do
Core em `JANGADA_CORE_PATH` (antes `JANGADA_PATH`); o Core ignora o
`JANGADA_PATH` que o Shell exporta na sessão.

## Dependências

`bash`, `python3`, `sqlite3`, `bwrap`, `tmux`, `git` e `jq`. R com `lintr`
é opcional. Claude Code, Codex, agy e Ollama são usados quando instalados.
Detalhes no [README](../README.md#dependências).

## Fronteira com o Shell

O Shell (área de trabalho e Central de Tarefas) e o Monitor são opcionais e
ficam em outros repositórios. O Core procura os comandos deles no PATH e segue
sem erro quando não os acha; o `testes/fronteiras.sh` confere que ele não os
chama por `JANGADA_CORE_PATH`.

- O Core 1.0.0 oferece a consulta e os comandos de coordenação que a Central
  usa. Os botões novos da Central, como Retomar, dependem de publicar e
  atualizar também o Shell, em fluxo separado do dono. Sem isso, a retomada
  continua disponível pelo comando `jangada-coordenador`.
- `jangada-update --so-core` não chama o `jangada-sistema-update` do Shell.
  Sem a opção, o comando o chama quando ele está no PATH.

## Limitações

- Assinar, publicar, criar a tag e atualizar a instalação são ações do dono,
  fora do isolamento. O agente não assina: a chave fica oculta nele.
- Não há serviço de login nem início automático da coordenação. A retomada é
  pelo comando de abertura ou pelo botão da Central.
- Queda abrupta do processo ou da máquina durante a gravação do histórico de
  uma atuação pode deixar um arquivo que o comando recusa. A recusa preserva
  os dados, e a conferência pode ser manual. Não há promessa de que isso nunca
  ocorra.
- O doctor não consulta login no servidor nem saldo do Claude, e o teste de
  bubblewrap não comprova as montagens de cada provedor. Os itens que ele não
  consegue conferir aparecem como não verificáveis, não como aprovados.
- O isolamento tem [limites conhecidos](isolamento.md#limites-conhecidos): as
  conversas e a memória em `~/.claude/projects` e o `settings.json` do agy
  continuam graváveis pelo agente.
- A delegação local depende do Ollama, do modelo, da memória e de não haver
  jogo aberto. Quando falha, o apoio não é concluído e nada é reenviado a
  serviço remoto sem autorização.
- Os testes usam simuladores do tmux e dos clientes de agente. O uso com cada
  provedor real depende de login, cota e versão do cliente instalado.

## Critérios de aceitação

Uma preparação só é integrada com todos estes itens:

1. Revisão independente por `jangada-validar` com `STATUS: APROVADO` na
   cabeça final.
2. `testes/verificar.sh` completo, rodado pelo coordenador fora do isolamento
   na cabeça final, com código 0 e sem pulos.
3. Escopo conferido: apenas `CHANGELOG.md`, `docs/versao-1.0.0.md`,
   `docs/instalacao-e-uso.md` e `README.md`, sobre a base atual do `main`.
4. `CHANGELOG.md` produzido por `jangada-versao --lancar 1.0.0` numa cópia
   temporária, sem edição à mão, e com as seções 0.2.0 e 0.1.0 inalteradas.
5. Tag `v1.0.0` ausente do repositório compartilhado.
6. Links novos e alterados resolvem.

Conferido antes desta preparação, com revisão independente e suíte externa em
cada entrega: o diagnóstico do ambiente, a passagem manual, o ciclo
persistente da coordenação e o respectivo contrato com a Central. Em
18/10/2026, o doctor lido em modo leitura sobre a instalação real deu 42 itens
ok, 0 avisos, 0 falhas e 8 não verificáveis (código 0).

Não foram verificados: a assinatura e a publicação desta versão, a instalação
ou atualização da cópia instalada para a 1.0.0, a instalação em outras
máquinas, a integração contínua do GitHub nesta versão e todos os provedores
reais.

## Roteiro do dono

Comece depois que o coordenador integrar a preparação no `main`. Rode num
terminal comum, fora do isolamento e sem sessões de agentes abertas. Um comando
por bloco; só siga ao próximo com o resultado esperado. Troque
`~/Projetos/migracao-jangada-core` pelo caminho da cópia de trabalho do Core,
a que está no ramo `main`.

O `jangada-assinar` refaz os commits ainda não publicados e não move tags.
Por isso a tag só nasce no passo 5, sobre o commit já assinado.

1. Atualizar a referência da origem.

   ```sh
   git -C ~/Projetos/migracao-jangada-core fetch origin
   ```

   Esperado: sem erro.

2. Conferir o estado e guardar a árvore de arquivos.

   ```sh
   git -C ~/Projetos/migracao-jangada-core status --short --branch
   ```

   Esperado: uma única linha `## main...origin/main [ahead N]`, sem arquivos
   listados. Com `behind` na linha, a origem tem commits que o `main` não tem:
   pare.

   ```sh
   git -C ~/Projetos/migracao-jangada-core rev-parse 'main^{tree}'
   ```

   Esperado: um hash. Anote-o para o passo 4.

3. Assinar o repositório do Core.

   ```sh
   jangada-assinar ~/Projetos/migracao-jangada-core
   ```

   Esperado: a lista dos commits a assinar, a pergunta `[s/N]` e, depois de
   `s`, a linha `assinados; confira com git log --show-signature e rode o push`.
   Se aparecer `nada a assinar`, os commits já têm assinatura. Qualquer outra
   mensagem de erro ou o aviso de commits já enviados sem assinatura: pare.

4. Conferir assinaturas e conteúdo.

   ```sh
   git -C ~/Projetos/migracao-jangada-core -c gpg.ssh.allowedSignersFile="$HOME/.config/jangada/allowed_signers" -c gpg.ssh.program=ssh-keygen log --format='%G? %h %s' origin/main..main
   ```

   Esperado: toda linha começa com `G`.

   ```sh
   git -C ~/Projetos/migracao-jangada-core rev-parse 'main^{tree}'
   ```

   Esperado: o mesmo hash anotado no passo 2.

5. Criar a tag anotada no `main` assinado.

   ```sh
   git -C ~/Projetos/migracao-jangada-core tag -a v1.0.0 -m "jangada 1.0.0" main
   ```

   Esperado: nenhuma saída. A tag não pode existir antes: com
   `fatal: tag 'v1.0.0' already exists`, pare.

   ```sh
   git -C ~/Projetos/migracao-jangada-core rev-parse 'v1.0.0^{commit}' main
   ```

   Esperado: duas linhas com o mesmo hash.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-versao -C ~/Projetos/migracao-jangada-core
   ```

   Esperado: `1.0.0`.

6. Publicar o `main`, sem forçar.

   ```sh
   git -C ~/Projetos/migracao-jangada-core push origin main
   ```

   Esperado: `main -> main` sem `forced update`. Se o servidor recusar, pare;
   não use `--force`.

7. Publicar a tag.

   ```sh
   git -C ~/Projetos/migracao-jangada-core push origin v1.0.0
   ```

   Esperado: `[new tag] v1.0.0 -> v1.0.0`.

   ```sh
   git -C ~/Projetos/migracao-jangada-core ls-remote origin refs/tags/v1.0.0 'refs/tags/v1.0.0^{}'
   ```

   Esperado: duas linhas; a segunda traz o hash do passo 5.

8. Atualizar só o Core instalado.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-update --so-core
   ```

   Esperado: a lista de commits e arquivos, a pergunta de confirmação e, depois
   de `s`, `jangada agora em 1.0.0`. O comando recusa com sessões de agentes
   abertas, e a opção `--so-core` não chama o `jangada-sistema-update`.

9. Conferir a instalação.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-versao -C ~/.local/share/jangada-core
   ```

   Esperado: `1.0.0`. O `-C` é necessário: sem ele o programa consulta o
   repositório da pasta atual, não a instalação.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-doctor
   ```

   Esperado: código de saída 0 e nenhuma falha no resumo.

Assinar, publicar e atualizar o Shell, que traz os botões novos da Central,
é um fluxo separado; esta sequência não o toca.
