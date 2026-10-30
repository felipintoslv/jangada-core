# Core 1.1.0

Notas e roteiro de lançamento da versão 1.1.0 do jangada-core. O registro
completo de mudanças está no [CHANGELOG](../CHANGELOG.md), gerado por
`jangada-versao`.

## Situação

Preparada em 30/10/2026. Até o dono executar o [roteiro](#roteiro-do-dono):

- a tag `v1.1.0` não existe;
- o `main` local está 3 commits à frente do publicado (`d95a267`): a
  correção do agy órfão, a documentação dela e o `chore(versao): 1.1.0`,
  ainda sem assinatura;
- a cópia instalada está em `d95a267`, 92 commits depois da `v1.0.0`.

A versão reúne os 95 commits feitos depois da `v1.0.0` e o commit da própria
versão, que fica fora do registro.

## Mudanças principais

Cada item remete ao guia do assunto; a lista completa está no CHANGELOG.

| Área | Mudança | Guia |
|---|---|---|
| Isolamento | login só dos provedores concedidos, casa e ambiente mínimos, keyring fechado por padrão; conversas e memória do Claude e do agy em pasta própria de cada sessão | [Isolamento](isolamento.md) |
| Sessões | cada sessão trabalha num clone próprio, com os objetos da raiz pelo `alternates` somente leitura | [Ciclo da tarefa](ciclo-da-tarefa.md) |
| Contas e cotas | várias contas do agy, isoladas e escolhidas pelo maior saldo; `jangada-router cotas` junta agy, Codex e Claude num só `cotas.json` | [Provedores](provedores.md) |
| Delegação ao agy | cotas Flash e Argon separadas, fontes e pesquisa delimitadas, contrato e provas do Flash registrados | [Subagentes e delegação](subagentes-e-delegacao.md) |
| Coordenação | coordenador agy (Argon) com identidade persistente; hooks do Claude e do Codex declaram o próprio provedor e não alteram o registro de outro | [Ciclo da tarefa](ciclo-da-tarefa.md#coordenador) |
| Fila e execução | recuperação de reservas, descendentes encerrados depois de falhas, prazo global para execução e sondagens | [Subagentes e delegação](subagentes-e-delegacao.md#fila-persistente-de-projetos) |
| Atualização | retomada de atualização interrompida e volta à versão anterior documentadas e testadas | [Atualização e migrações](atualizacao-e-migracoes.md) |

Correções achadas nas homologações reais de 30/10/2026 com Claude, Codex e
agy:

- o coordenador reconhece o catálogo do agy 1.4.11, e a delegação feita de
  dentro de um coordenador agy abre;
- fechar a janela de um `jangada-delegar` com o agy em curso encerra a
  chamada, solta a trava e apaga a pasta da chamada. Antes, o agy seguia
  órfão até o prazo, com a trava livre e a pasta sobrando.

## Limites conhecidos

- Adaptador agy (versão 1.4.11): não há evento de pedido de permissão, então
  o coordenador agy nunca fica em `aguardando`. Esc, `/exit` e a pergunta de
  permissão não chegam ao hook.
- Estado `trabalhando` sem turno: Claude interrompido com Esc e Codex com turno
  encerrado por erro do provedor também não chamam hook. O registro fica em
  `trabalhando` até o próximo evento. A Central do Shell mostra há quanto
  tempo veio o último sinal, mas só o Shell publicado traz essa indicação.
- Delegação agy interrompida: com a janela fechada ou com SIGKILL, a
  delegação não entra em `delegacoes.jsonl`. Morto por SIGKILL, o
  `jangada-delegar` deixa o agy rodar até o prazo; a trava fica ocupada até
  ele sair e a pasta da chamada é apagada na próxima abertura de agente.
- Revisão independente na fila: só para intermediários de risco 1 com
  contexto `diff`
  ([detalhes](subagentes-e-delegacao.md#modelo-operacional-de-projetos)).
- O teste `test_trava_liberada_apos_interrupcao` de `testes/baseline.py` falha
  de vez em quando com a máquina carregada: na suíte completa e também na
  `1.0.0-92-gd95a267`, sem as mudanças desta versão (3 falhas em 24 rodadas
  paralelas). A espera de 5 s de `jangada_com_trava_dir` é a suspeita; não foi
  corrigida nesta versão.
- Os demais limites da [1.0.0](versao-1.0.0.md#limitações) continuam valendo.

## Verificação

- `testes/verificar.sh` completo no `main` preparado, fora do isolamento:
  código 0, 3281 verificações.
- Homologação real do agy em 30/10/2026, em projeto sintético, estado
  separado e teto de 6 chamadas, todas usadas: duas delegações simultâneas
  (a segunda recusada com `execucao_ocupada`), janela fechada com o agy em
  curso (nenhum processo sobra, trava livre, pasta apagada) e SIGKILL no
  `jangada-delegar` (o agy órfão mantém a trava e recusa outra execução até
  sair).
- Não foram verificados: a assinatura, a publicação e a instalação desta
  versão, a instalação em outras máquinas e a integração contínua do GitHub.

## Roteiro do dono

Rode num terminal comum, fora do isolamento e sem sessões de agentes abertas.
Um comando por bloco; só siga ao próximo com o resultado esperado. Troque
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

   Esperado: uma única linha `## main...origin/main [à frente 3]` (`[ahead 3]`
   com o git em inglês), sem arquivos listados. Com `atrás` (`behind`) na
   linha, a origem tem commits que o `main` não tem: pare.

   ```sh
   git -C ~/Projetos/migracao-jangada-core rev-parse 'main^{tree}'
   ```

   Esperado: um hash. Anote-o para o passo 4.

3. Assinar o repositório do Core.

   ```sh
   jangada-assinar ~/Projetos/migracao-jangada-core
   ```

   Esperado: a lista dos 3 commits a assinar, a pergunta `[s/N]` e, depois de
   `s`, a linha `assinados; confira com git log --show-signature e rode o push`.
   Qualquer outra mensagem de erro: pare.

4. Conferir assinaturas e conteúdo.

   ```sh
   git -C ~/Projetos/migracao-jangada-core -c gpg.ssh.allowedSignersFile="$HOME/.config/jangada/allowed_signers" -c gpg.ssh.program=ssh-keygen log --format='%G? %h %s' origin/main..main
   ```

   Esperado: três linhas, todas começando com `G`.

   ```sh
   git -C ~/Projetos/migracao-jangada-core rev-parse 'main^{tree}'
   ```

   Esperado: o mesmo hash anotado no passo 2.

5. Criar a tag anotada no `main` assinado.

   ```sh
   git -C ~/Projetos/migracao-jangada-core tag -a v1.1.0 -m "jangada 1.1.0" main
   ```

   Esperado: nenhuma saída. Com `fatal: tag 'v1.1.0' already exists`, pare.

   ```sh
   git -C ~/Projetos/migracao-jangada-core rev-parse 'v1.1.0^{commit}' main
   ```

   Esperado: duas linhas com o mesmo hash.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-versao -C ~/Projetos/migracao-jangada-core
   ```

   Esperado: `1.1.0`.

6. Publicar o `main`, sem forçar.

   ```sh
   git -C ~/Projetos/migracao-jangada-core push origin main
   ```

   Esperado: `main -> main` sem `forced update`. Se o servidor recusar, pare;
   não use `--force`.

7. Publicar a tag.

   ```sh
   git -C ~/Projetos/migracao-jangada-core push origin v1.1.0
   ```

   Esperado: `[new tag] v1.1.0 -> v1.1.0`.

   ```sh
   git -C ~/Projetos/migracao-jangada-core ls-remote origin refs/tags/v1.1.0 'refs/tags/v1.1.0^{}'
   ```

   Esperado: duas linhas; a segunda traz o hash do passo 5.

8. Atualizar só o Core instalado.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-update --so-core
   ```

   Esperado: a lista de commits e arquivos, a pergunta de confirmação e, depois
   de `s`, `jangada agora em 1.1.0`. O comando recusa com sessões de agentes
   abertas.

9. Conferir a instalação.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-versao -C ~/.local/share/jangada-core
   ```

   Esperado: `1.1.0`.

   ```sh
   ~/.local/share/jangada-core/bin/jangada-doctor
   ```

   Esperado: código de saída 0 e nenhuma falha no resumo.

Assinar, publicar e atualizar o Shell é um fluxo separado; esta sequência não
o toca.
