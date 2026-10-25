# Ciclo de uma tarefa com agentes

Uma tarefa passa por três comandos: `jangada-agente` abre a sessão,
`jangada-validar` manda a entrega ao revisor configurado e
`jangada-agente-fim` encerra e limpa. Com `--integrar`, ele avança a base
até o commit aprovado, depois de confirmação humana, e mantém a sessão.
Veja a [segurança operacional](historico/estabilizacao/SEGURANCA_OPERACIONAL.md), registro histórico. O estado de cada sessão fica em
`~/.local/state/jangada/agentes/SESSAO.json`, com o contrato descrito em
`agentes/claude/skills/jangada/agentes.md`.

Os comandos deste ciclo moram em `bin/` e a skill em
`agentes/claude/skills/jangada/`. O README traz os comandos principais.

Os perfis padrão são `claude-codex` (Claude implementa, Codex revisa) e
`codex-claude` (Codex implementa, Claude revisa), os dois com delegação ao
agy para todos os papéis, inclusive leitor e redator. O agy só atende em
pasta marcada como confiável nele; uma recusa registra bloqueio do apoio.
A sessão principal pode continuar a investigação. A seção Confiança do agy,
abaixo, descreve como a tarefa recebe essa confiança.
As diferenças de protocolo, hooks e revisão estão em [Codex](codex.md).

```mermaid
flowchart LR
    A[jangada-agente] --> B[agente trabalha<br>no worktree]
    B --> D[commit]
    D --> C[jangada-validar]
    C -- REVISAR --> B
    C -- APROVADO --> E{mais uma entrega?}
    E -- sim --> B
    E -- não --> F[jangada-agente-fim --integrar:<br>confirmação, suíte e avanço rápido]
    F --> H[encerramento após conferência]
    C -- limite --> G[usuário decide:<br>--forcar ou reverter]
```

O fluxograma recomenda commit antes da revisão, para que a aprovação
identifique uma entrega limpa. O comando também revisa alterações sem commit,
mas registra a aprovação como `sujo`, sem avançar o ponto da próxima entrega.

## Coordenador

A skill `coordenador` define o papel da sessão que conversa com o dono,
explora problemas e alternativas, transforma decisões autorizadas em tarefas,
acompanha e confere a entrega antes de integrar; explorar não autoriza implementar.
O coordenador pode ser Claude, Codex ou agy com Argon. A skill vale para qualquer
projeto e roda numa sessão comum, fora do isolamento, aberta na pasta do
projeto. No Codex, abrir tarefa, ler o estado, verificar e integrar passam
pela aprovação do dono na tela. O texto fica em
`agentes/claude/skills/coordenador/SKILL.md`; só a descrição entra no contexto
até a skill ser chamada.

- Claude Code: `/coordenador`, ou pedir para coordenar as tarefas do projeto.
- Codex: `$coordenador` na mensagem, ou o mesmo pedido em texto. Conferido
  no Codex 0.162.1, que lê `~/.codex/skills/coordenador/SKILL.md` pelo link.

Ao abrir uma tarefa, a skill passa `--coordenador claude`,
`--coordenador codex` ou `--coordenador agy` ao `jangada-agente`, que grava o nome no campo
`coordenador` do registro da sessão. Sem a opção, vale `JANGADA_COORDENADOR`
e, sem ela, "dono"; registro sem o campo é lido como "dono". O nome é só o
que foi declarado: a Central de Tarefas e o grafo do painel o mostram ao lado
do autor e do revisor, e ele não muda nenhuma permissão.

O `jangada-coordenador --projeto PASTA --provedor claude|codex|agy` mantém um
coordenador por projeto. Novas sessões usam explicitamente o modelo forte:
Claude `opus`, Codex `gpt-6-astra`, agy `gemini-4-argon-high`.
A escolha econômica de autor e revisor não altera o coordenador. O comando
não substitui silenciosamente o modelo. Claude e Codex não consultam a rede
na abertura. O adaptador agy consulta catálogo e cota antes de criar sessão.

No agy, `--modelo` só aceita `gemini-4-argon-high`; qualquer outro nome recusa.
O catálogo precisa informar esse identificador numa linha inteira. Saída desconhecida
ou consulta sem sucesso recusa antes de alterar a atuação. `/usage` precisa
informar cota válida de pelo menos 20% em todas as janelas `gemini-argon-*`;
a cota Flash não entra nessa decisão. Cota desconhecida, inválida ou insuficiente
recusa sem créditos nem outro modelo. Isso confere disponibilidade declarada,
não comprova a execução do modelo. Erro posterior do cliente permanece no painel.
A função `coordenador` do registro é separada de `principal`; adicionar agy
não libera autor agy no `jangada-agente`.

A skill e o texto inicial são os mesmos para os três provedores. O agy recebe
`--model gemini-4-argon-high --prompt-interactive TEXTO`, sem retomar conversa
global nem retirar confirmações do cliente. Instalação e troca da sessão atual
continuam ações do dono. A atualização do produto só prepara a ligação da skill
e os hooks; não altera a instalação durante os testes.

**Aceite real pendente da MOD-02:** os ensaios usam clientes falsos, tmux privado
e estado separado. Em 23/10/2026 a consulta delimitada de `/usage` confirmou
cota Argon de 0%, com renovação em `2026-10-24T00:02:15Z`. Nenhuma execução real Argon foi feita nessa condição.
O bloqueio Flash por agrupamento de cota foi corrigido na MOD-03.
O apoio arquiteto foi feito na retomada da MOD-02 após a renovação:
uma chamada, sem mudança de produto.

A paridade de permissões e coexistência ainda não está demonstrada. A documentação
do cliente não oferece `PermissionRequest`: o adaptador não inventa `aguardando`
a partir de `PreToolUse`. A pergunta continua no terminal, sem observação fiel
pelo Core. Isso bloqueia o aceite de paridade até uma solução verificável.
Não se deve usar este adaptador como capacidade já aceita para coordenar produção.

A origem também tem uma lacuna: o hook agy declara seu provedor, mas os hooks
Claude e Codex herdam `JANGADA_COORDENADOR_PROVEDOR`. Se chamados diretamente
dentro da atuação agy, podem atualizar o registro do pai. A identidade preservada
não distingue esses clientes. Corrigir `bin/jangada-hook-claude` e
`bin/jangada-hook-codex` exige autorização adicional, pois estão fora do escopo
da MOD-02. Os testes provam recusa de origem divergente explícita, sem comprovar
que os três hooks declaram a própria origem.

A abertura não toma `.agy-execucao.lock`; tampouco os hooks a retêm até Stop.
Os filhos continuam disputando a trava do delegador. Isso evita o impasse
pai esperando filho, mas não comprova coexistência na mesma conta. A prova real
exige projeto sintético, estado separado, cota disponível e teto previamente aprovado:
Argon ocioso com Flash, Argon delegando, dois Flash concorrentes, interrupção
com filho, saída abrupta, liberação e retomada. Cota baixa, resultado parcial
e consumo desconhecido devem permanecer visíveis. Não interrompa sessões existentes.

Se a sessão tmux estiver viva com registro regular válido do mesmo projeto
e provedor, o comando informa e foca a sessão atual. Outro provedor recebe
erro de uso e a orientação de encerramento voluntário pelo dono, sem foco,
reescrita do registro ou nova sessão. Registro inconsistente preserva a sessão
e recebe erro; projetos homônimos continuam recusados. A presença real no tmux
é conferida sob a trava, que também serializa chamadas concorrentes.

A passagem é manual. O coordenador atual atualiza `.jangada/estado.md` e
`.jangada/coordenacao.md` com decisões, autorizações e pendências e informa
que a passagem está pronta. O dono encerra voluntariamente a sessão anterior.
Nas sessões novas, a saída normal do cliente termina o painel e, se ele era
o último, a sessão. Se o processo falhar, a opção `remain-on-exit failed`,
local à janela nova, mantém o painel morto com a mensagem para conferência.
A abertura ainda informa o nome da sessão criada; isso não atesta que o
cliente iniciou sem erro. O dono confere a mensagem e fecha a janela pelo
tmux (`Ctrl+b &`, com confirmação) antes de abrir outro provedor.

Em sessões de versões anteriores, sair do cliente pode deixar o shell aberto.
Nesse caso, saia também desse shell. Janelas e painéis adicionais criados pelo
dono também precisam terminar. Desanexar do tmux não encerra a sessão.
Só depois abra o provedor escolhido na pasta do projeto pelo mesmo comando.
Sem sessão tmux viva, o mesmo comando retoma a atuação aberta, preservando
`atuacao_id`, `desde`, tarefas, decisões e autorizações, inclusive ao trocar
de provedor. Registro inválido ou de projeto homônimo é preservado e recusado.
O `--fim` conserva sua semântica existente e não participa dessa passagem.

A atuação tem `ciclo=aberta|encerrada`, independente do estado dos hooks.
Resposta concluída, Stop, Interrupt, SessionEnd e reinício não encerram o
ciclo. Retome pelo comando de abertura; o botão Retomar da Central atende Claude e Codex.
O suporte agy na Central depende da MOD-05.
não há serviço de login ou início automático. A consulta versão 1 acrescenta
`ciclo`, `atuacao_id` e `retomavel`, verdadeiro para ciclo aberto sem sessão
viva. A consulta não migra registros. Legado sem data `encerrado` válida
continua aberto, mesmo com `estado=encerrado` de hook antigo; identidade
ausente fica nula até a abertura. Data de encerramento legítima indica fim explícito.

O processo novo recebe um texto inicial pelo argumento do cliente, identificando
o papel e pedindo a leitura da skill, das regras e dos registros. Não há texto
colado em agente aberto nem conteúdo de arquivo interpolado em código shell.
O sucessor lê `.jangada/regras-do-dono.md`, `.jangada/estado.md`,
`.jangada/armadilhas.md`, o diário e `.jangada/coordenacao.md`, quando presentes;
confere sessões reais, ramos e worktrees e apresenta resumo antes de abrir
tarefas já autorizadas. Autorizações registradas ainda válidas continuam sem
reconfirmação; arquivos ausentes não autorizam inventar decisões.
O estado fica fora do controle de versão; a identidade da atuação é
persistente, sem memória global nem importação automática de históricos.

Após integração aceita, o coordenador limpa imediatamente tarefas concluídas
com `jangada-agente-fim SESSAO` e exclui só o ramo integrado com
`git branch -d RAMO`. Isso inclui tarefas herdadas de outros coordenadores:
confira vínculo real com o projeto pelo Git e registro protegido, parecer
exigido da cabeça, integração e árvore limpa. As evidências ficam preservadas.
`concluido` de hook e fim de turno não comprovam conclusão. Preserve e relate
tarefa com pendências ou sem integração; não há exclusão em massa.

Para encerrar a atuação, atualize `.jangada/estado.md` e o diário
`.jangada/coordenacao.md`, limpe concluídas aceitas e relate pendências e
ações do dono. Saia voluntariamente; então use
`jangada-coordenador --finalizar SESSAO`, ou a ação correspondente da Central.
O comando recusa sessão ainda viva, pedindo salvar estado/diário e sair;
não mata processos nem grava documentos no projeto. Sem sessão viva, marca
o ciclo encerrado com data e salva checkpoint em
`$JANGADA_ESTADO/coordenadores/historico/ATUACAO_ID.json`, preservando o
registro e referências das tarefas pendentes lidas de `revisoes/`.
Informa quantas restam; não executa estado salvo nem importa credenciais ou
históricos de provedores. Repetir é idempotente. Antes de criar outra atuação,
o registro anterior deve estar arquivado. Checkpoint válido é conferido e
reutilizado antes de nova varredura de pendências. Sem checkpoint, as cópias
protegidas precisam ser legíveis. Histórico ou pendências necessários inválidos
recusam antes de alterar o registro ou de `--fim` matar a sessão.
Falha ao publicar checkpoint novo mantém o registro encerrado para nova
tentativa; histórico inválido ou simbólico não é sobrescrito.
Outra atuação recebe nova identidade e conserva as pendências visíveis.
`--fim` também marca o encerramento explícito, mantendo a compatibilidade
de matar a sessão. Nunca o use para simular interrupção ou retomada.
Hooks atrasados não reabrem ciclo encerrado nem alteram uma atuação nova.
Veja [exploração e exemplos](coordenacao-central/02-coordenador-contextos.md#exploração-antes-de-abrir-tarefas)
e [M2.0](coordenacao-central/05-plano-incremental.md#fase-2-coordenador-mínimo-preservando-sessões).

## Abertura da sessão

```mermaid
flowchart TD
    A[jangada-agente] --> B[projeto: --projeto ou<br>seletor com zoxide e JANGADA_PROJETOS]
    B --> C[nome da tarefa e slug]
    C --> D{--direto?}
    D -- sim --> H[pasta = repositório]
    D -- não --> E{ramo agente/NOME existe?}
    E -- não --> F[git worktree add -b]
    E -- já integrado --> F
    E -- não integrado --> G[retomar, outro nome<br>ou cancelar]
    G --> F
    F --> P[jangada-worktree-preparar]
    P --> I
    H --> I[agente, perfil, revisor,<br>destino dos subagentes, isolar]
    I --> Q{delega ou revisa<br>pelo agy?}
    Q -- sim --> S[confere a confiança do agy]
    Q -- não --> J
    S --> J[protocolo: protocolo.md<br>+ protocolo-delegar-*.md<br>+ protocolo-r.md se houver R]
    J --> K[sessão tmux]
    K --> L[estado: iniciado]
```

- `slug` em `bin/jangada-agente` tira acentos e caracteres especiais do nome;
  o ramo é `agente/NOME` e o worktree fica em `JANGADA_WORKTREES`.
- `bin/jangada-worktree-preparar` leva ao worktree o que o git não leva: o que
  casa com `.worktreeinclude` e é ignorado pelo git é copiado, o que está em
  `.jangada/links` vira link e `.jangada/preparar.sh` roda por último.
- Só o worktree recém-criado passa pela preparação completa, chamada com
  `--sem-confianca`: a confiança do agy fica para a conferência adiante. No
  reaproveitado e na sessão retomada nada é copiado nem executado: roda só a
  conferência da confiança do agy.
- Revisor: `--revisor`, depois o `JANGADA_VALIDAR_REVISOR` do perfil, depois o
  da configuração; sem nenhum, Codex revisa Claude e Claude revisa Codex.
  Fora de sessão e nas sessões antigas do agy, o padrão é Claude.
- O protocolo vai ao Claude por `--append-system-prompt`, ao agy por `-i`
  junto com a tarefa e ao Codex por `developer_instructions`. O item de
  subagentes depende do destino; veja
  [subagentes e delegação](subagentes-e-delegacao.md).
- Com isolamento, o comando começa por `jangada-isolar --`; veja
  [isolamento](isolamento.md).
### Confiança do agy

A confiança do agy vale para o caminho exato da pasta. Quem autoriza a raiz
do projeto é o proprietário, na pergunta do próprio agy. O jangada só estende
essa autorização ao worktree da tarefa.

- Quando confere: ao abrir a tarefa, ao reaproveitar o worktree, ao anexar a
  uma sessão que já existe e ao restaurar (`jangada-agentes --restaurar` e
  `--focar`). Só quando a delegação ou o revisor da tarefa é o agy; numa
  sessão que já existe, valem os provedores, a raiz e o worktree do registro
  protegido dela, não os da chamada.
- Projetos homônimos: duas raízes com o mesmo nome de pasta e a mesma tarefa
  dão o mesmo identificador de sessão. A chamada feita pelo segundo projeto
  anexa à sessão do primeiro e recebe o aviso com a raiz dela. Anexar não cria
  worktree, não copia arquivos, não roda `.jangada/preparar.sh` e, nesse caso,
  não sincroniza nada.
- Registro protegido ausente, ilegível, com campo de tipo errado ou com
  worktree que não existe mais: a abertura, a restauração e o
  `jangada-agentes --confianca SESSAO` avisam e não conferem nem sincronizam;
  a opção explícita devolve erro. A sessão abre ou volta do mesmo jeito.
- Raiz autorizada: o `jangada-worktree-preparar --so-confianca RAIZ WORKTREE`
  confirma pelo Git que o worktree é registrado no repositório da raiz
  (`git worktree list` lido na raiz e a pasta `.git` comum lida no worktree,
  com os caminhos resolvidos), grava o worktree em `trustedWorkspaces` e relê
  o arquivo para confirmar. Repetir não duplica a entrada.
- Raiz sem autorização: o `jangada-agente` informa a raiz. Com terminal e
  sessão nova, pergunta se abre o agy nela. Você responde à pergunta de
  confiança dentro do agy e sai; o jangada relê o `settings.json` e sincroniza
  o worktree se a raiz estiver lá. Fechar o agy sem responder não autoriza
  nada.
- Pendência: sem terminal, sem o agy instalado, com a oferta recusada ou com a
  pergunta sem resposta, a tarefa abre do mesmo jeito. O `jangada-delegar`
  recusa o agy nela e a sessão principal faz o trabalho.
- Para retomar depois, numa tarefa já aberta: abra o agy na raiz do projeto,
  responda à pergunta e rode `jangada-agentes --confianca SESSAO` num terminal
  fora da sessão do agente. O comando não recria a tarefa, não copia arquivos
  e não roda `.jangada/preparar.sh`.
- O que o jangada não faz: gravar a raiz, confiar em pasta que o Git não
  aponta como worktree da raiz autorizada, ler a raiz ou o worktree do estado
  da sessão (gravável pelo agente; vale a cópia em `revisoes/`) e sincronizar
  de dentro do isolamento.

Os estados do ciclo são:

| Estado | Quando aparece |
|---|---|
| `iniciado` | abertura ou restauração da sessão |
| `trabalhando` | execução acompanhada pelos hooks |
| `aguardando` | pedido de resposta ou permissão; o agy não informa esse estado |
| `concluido` | fim de uma resposta ou encerramento informado pelo agente |
| `interrompido` | tmux desapareceu, mas a pasta permite restaurar a sessão |

Na Central de Tarefas v0.1, `concluido` aparece como **Pronto para conferir**,
sem afirmar que a tarefa foi concluída. Cada sessão representa uma tarefa.
A central acompanha estados e mensagens a cada dois segundos; mudanças
observadas ficam em memória durante a janela. Perguntas e permissões
continuam no terminal. Na tarefa selecionada, `Alt+I` abre a integração,
que mantém a sessão; `Ctrl+X` abre o encerramento sem integração. Ambos usam
`jangada-agente-fim`, preservando suas conferências e confirmações.
Veja instalação e reversão (documentadas no jangada-shell).

Cada mudança registrada vira uma linha em `eventos-agentes.jsonl`
([registros](registros.md)).

## Validação da entrega

```mermaid
flowchart TD
    A[jangada-validar] --> B[revisor e base<br>da sessão ou das opções]
    B --> C[ponto de comparação:<br>merge-base, início da sessão<br>ou último commit aprovado]
    C --> D{há diff?}
    D -- não --> X1[código 1: nada a revisar]
    D -- sim --> E{rodada > JANGADA_VALIDAR_RODADAS<br>e sem --forcar?}
    E -- sim --> R{--reverter-se-limite?}
    R -- sim --> R1[reversão automática bloqueada,<br>preserva arquivos e commits]
    R -- não --> R2[pede para parar e<br>descrever o pendente]
    R1 --> X4[registra limite, código 4]
    R2 --> X4
    E -- não --> F{--pular-local?}
    F -- não --> G[verificar_local]
    G -- falhou --> X3[parecer REVISAR sem<br>chamar o revisor, código 3]
    G -- passou --> H
    F -- sim --> H[monta o pedido: regras da base,<br>commits, diff, parecer anterior<br>e resposta do agente]
    H --> I{revisor}
    I -- claude --> J[revisar_claude:<br>só ferramentas de leitura]
    I -- agy --> K[revisar_agy: agente revisor,<br>--sandbox]
    I -- codex --> O[revisar_codex:<br>pedido completo, sem ferramentas]
    J --> L[lê STATUS da primeira linha]
    K --> L
    O --> L
    L -- APROVADO --> P{verificação local completa<br>e revisão independente?}
    P -- sim --> M[grava .aprovado<br>registra, código 0]
    P -- não --> N
    L -- REVISAR --> N[registra, código 3]
```

- **Dentro do isolamento.** Numa sessão de agente, o `jangada-validar` não
  revisa ali: manda o sha do `HEAD` e a `--resposta`, se houver, ao atendente que o
  `jangada-isolar` mantém fora do bwrap, e o fluxo acima roda fora, com a
  base, o revisor e o limite de rodadas de `revisoes/SESSAO.json` e de fora.
  O parecer volta pelo terminal; o registro, a marca e a contagem ficam em
  `revisoes/`. Antes de pedir, faça commit: pasta com alteração sem commit é
  recusada. As opções que mudam o critério (`--forcar`, `--pular-local`,
  `--revisor`, `--modelo`, `--esforco`, `--base`,
  `--reverter-se-limite`) saem com código 1 dentro. Sem atendente, o
  comando sai com 1 e pede o coordenador; depois de 3 erros seguidos do
  revisor, também. Detalhes em
  [isolamento](isolamento.md#o-atendente-da-revisão).
- **Ponto de comparação.** Parte do `merge-base` entre a base e o `HEAD`.
  Direto no ramo base, vale o commit `inicio` gravado na abertura. Depois de
  um APROVADO, a próxima chamada é outra entrega: a revisão parte do commit
  aprovado (`validacao-ROTULO.aprovado`) e as rodadas recomeçam, somente
  com marca protegida, validação local completa, independência, árvore e base
  conferidas. Marcas graváveis pelo agente não encurtam o diff.
- **Foto da entrega.** Antes de qualquer conferência, o worktree é
  congelado: o commit do agente, os arquivos rastreados e os novos viram
  árvores do git, e uma cópia temporária é montada a partir delas. O portão
  local, o diff e o revisor leem só essa cópia, então o que o agente altera
  durante a revisão fica fora do parecer e da aprovação. Fora do isolamento,
  a cópia fica em `fotos/` do estado, pasta privada que o isolamento oculta,
  e não em `revisoes/`, porque leva os links versionados da entrega. Os
  objetos passam antes por `git fetch` para um espelho em `revisoes/espelhos/`,
  que recalcula cada hash: o agente grava em `.git/objects`, e o git não
  reconfere um objeto solto ao ler. A integração confere os objetos com o
  mesmo espelho e faz o avanço lendo só os objetos dele. Uma divergência
  posterior ao avanço só gera aviso: não autoriza rollback destrutivo na
  cópia principal.
  A trava do Jangada não impede alterações do editor.
- **Diff.** Entram os arquivos rastreados e os novos não rastreados. Nome de
  arquivo com quebra de linha reprova na verificação local, porque escaparia
  das listas.
- **Verificação local** (`verificar_local`), antes de gastar o revisor:
  marcadores de conflito, script com byte nulo, sintaxe dos scripts
  alterados, `lintr` nas linhas R tocadas, segredos com o `gitleaks` só nas
  linhas acrescentadas, aviso de `Co-Authored-By` e, por último, o
  `.jangada/validar.sh` do projeto. As regras vêm da base, para a entrega não
  afrouxar o critério que a avalia. O R roda sem o `.Rprofile`, o `.Renviron`
  e o `.lintr` do worktree, que são código do repositório avaliado. O
  `.lintr` da base também é código R, e depois de um APROVADO a base da
  comparação é um commit do agente: por isso o `lintr` e o
  `.jangada/validar.sh` rodam pelo `jangada-isolar`, que numa sessão isolada
  roda direto e fora dela abre o bwrap. Com `.lintr` no projeto, o `lintr`
  que falha ou está ausente reprova a entrega. Sem configuração própria,
  achados do padrão continuam como aviso, mas a execução é obrigatória.
  ShellCheck e luac ausentes também reprovam arquivos aos quais se aplicam.
  O estado das verificações acompanha o parecer em `.verificacoes.tsv`.
  `.jangada/validar.sh` tem prazo de 300 segundos; lintr, 120 segundos.
- **Revisor.** O hook do revisor fica desligado, para o Stop dele não marcar
  a sessão como concluída. Pedido acima de 126.000 bytes leva o diff num
  arquivo que o agy lê. Sem o agente `revisor` instalado, o agy cairia no
  agente padrão, com todas as ferramentas; por isso o agy não é chamado.
  Quando a chamada ao revisor falha (sem cota, fora do ar, sem o agente
  `revisor`), a revisão passa aos outros modelos instalados, na ordem
  `claude`, `agy`, `codex`, e por último ao modelo do autor, com o aviso de
  revisão pelo mesmo modelo no pedido. Cada falha vira uma linha `erro` no
  `validar.jsonl`, e o estado registra quem deu o parecer. O Codex fica fora
  da troca quando o diff não cabe no pedido. Com `--revisor`, vale só o
  revisor pedido.
  Cada chamada ao revisor tem prazo de `JANGADA_VALIDAR_PRAZO` segundos
  (540): vencido, o revisor e o que ele abriu são encerrados, e a rodada sai
  com código 1 e sem parecer, sem passar a outro modelo. Como as rodadas são contadas pelos pareceres,
  essa chamada não gasta uma das rodadas da entrega.
  O diff acima de `JANGADA_VALIDAR_DIFF_MAX` bytes (150.000) vai cortado, com
  a lista do que ficou de fora para o revisor ler. O Codex revisa sem
  ferramentas: com diff cortado ou arquivo novo acima de 50 KB, a validação
  recusa a chamada com código 1, antes de gastar a rodada.
- **Registro.** Cada rodada grava `validacao-ROTULO-rN.md` e uma linha em
  `validar.jsonl` (`registrar`), e atualiza o campo `validacao` do estado.
  Dentro do isolamento, isso vai para `agentes/` e para o `validar.jsonl` do
  estado, que o agente pode alterar. Fora dele (sem `JANGADA_ISOLADO`), vai
  para `revisoes/`, que o `jangada-isolar` oculta, e a base, a tarefa e o
  revisor saem da cópia `revisoes/SESSAO.json` que o `jangada-agente` grava
  ao abrir a sessão. O `.aprovado` é um JSON que prende a aprovação ao que
  foi lido: commit e árvore do candidato, ponta da base, revisor, autor e
  `independent`. Com `limpo` falso (worktree com alteração sem commit), o
  commit sozinho não foi o que o revisor viu.
- **Parecer.** Só vale a primeira linha não vazia, e ela tem de ser
  exatamente `STATUS: APROVADO` ou `STATUS: REVISAR`, em maiúsculas. Outra
  forma conta como REVISAR. Parecer aprovado sem verificação local completa
  ou produzido pelo autor vira REVISAR e não gera marca de aprovação. Fora
  do isolamento, autoria sem cópia protegida da sessão também não aprova.

| Código | Significado |
|---|---|
| 0 | APROVADO |
| 3 | REVISAR (do revisor ou da verificação local) |
| 4 | limite de rodadas |
| 1 | erro: sem diff, nenhum revisor respondeu, prazo vencido, opção desconhecida |

## Fim da sessão

O `conferir_estado` recusa caracteres de controle, caminhos relativos, ramo
fora de `agente/NOME`, worktree fora de `JANGADA_WORKTREES` e worktree de
outro repositório. O estado gravável pelo agente não autoriza operação fora
da sessão.

Com `--integrar`, uma sessão com ramo próprio é integrada à base por avanço
rápido, fora do isolamento. O comando não chama o revisor e `--sem-revisao`
não libera. As etapas, na ordem:

1. O estado da sessão tem de ser igual à cópia protegida em
   `revisoes/SESSAO.json`. A worktree da tarefa tem de estar limpa, e a
   cópia principal, na base e sem alterações, inclusive arquivos novos e
   submódulos. A configuração local da cópia principal, com o
   `config.worktree` e o que entra por include, não pode definir chave
   `filter.*`: o comando recusa antes de qualquer `git status` e de novo sob
   a trava, porque o filtro rodaria comando ao gravar os arquivos.
2. Se a base andou, o ramo é refeito sobre ela com `git rebase` na worktree
   da tarefa. O commit muda, e o comando recusa pedindo
   `jangada-validar` para o commit novo. Um conflito deixa o rebase parado na
   worktree.
3. A marca `revisoes/validacao-SESSAO.aprovado` tem de registrar revisão
   independente, verificação local, worktree limpo e o commit, a árvore e a
   base exatos.
4. O usuário confirma: a resposta `s` no terminal (`Alt+I`) ou o botão da
   Central, que passa em `--confirmacao` os dois commits exibidos.
5. `testes/verificar.sh` roda numa cópia do commit tirada do espelho, em
   `integracoes/` do estado, e tem de sair com 0. O registro fica em
   `revisoes/verificar-SESSAO.log`. Projeto sem esse arquivo na base e no
   candidato segue com aviso.
6. Sob a trava do repositório, tudo é conferido de novo e a base avança com
   `git merge --ff-only`, lendo os objetos do espelho em `revisoes/espelhos/`,
   não os de `.git/objects`, que o agente grava.

A recusa por base alterada ou cópia principal alterada vale até a última
conferência, sob a trava. A trava não impede um Git de fora do jangada: se
ele mover a base para um ancestral do candidato entre essa conferência e o
merge, o `--ff-only` aceita. Essa janela é só detectada: depois do avanço,
o comando lê no reflog o valor anterior da base e, se não for o conferido,
avisa e sai com erro, sem desfazer. Uma recusa anterior ao avanço deixa
arquivos, índice e HEAD da cópia principal como estavam. Se, depois do
avanço, os arquivos da cópia principal não conferem com o espelho, a base
fica avançada, o comando sai com erro e pede conferência manual. Não há `merge --no-ff`, `reset --hard`, `git clean` nem outro
comando de descarte. O comando não envia ao remoto, não assina, não atualiza a
cópia instalada e mantém sessão, ramo e worktree. O encerramento é outro
gesto: `Ctrl+X` ou `jangada-agente-fim SESSAO`.

Sem `--integrar`, o encerramento conserva a conferência de alterações
pendentes e a confirmação humana antes de remover a worktree. O ramo fica.
Uma confirmação de descarte perde arquivos sem commit: faça cópia antes.
Chamado de dentro da própria sessão, o `limpar` roda em segundo plano, com
registro, porque fechar o tmux encerraria o próprio comando.

## Sessões órfãs

As consultas `jangada-agentes --lista`, `--lista-atualizada` e `--waybar`
só leem o estado em `~/.local/state/jangada/agentes`. A limpeza é a ação
explícita `jangada-agentes --limpar-orfaos` (contrato K4 em
`docs/modularizacao-3.0/03-contratos.md`). Ela remove o estado de sessão sem
tmux e sem processo vivo. Ficam o `concluido` e o `aguardando` dentro de
`JANGADA_AGENTES_GUARDAR` horas (padrão 24) e o `interrompido` dentro de 7
dias. Sessão de agente sem processo e com a pasta no disco vira
`interrompido` em vez de sair.

Até a barra chamar a limpeza antes da consulta (tarefa M3-06), nada a chama
sozinho e as órfãs acumulam na pasta. Elas não aparecem na lista nem no
contador; a sessão que dá para restaurar aparece como `interrompido` sem
prazo para sair.

## Testes

| Arquivo | O que cobre |
|---|---|
| `testes/validar.sh` | veredito, rodadas, limite, ponto de comparação, verificação local, pareceres e métricas, com claude e agy falsos |
| `testes/fim.sh` | estado adulterado; integração por avanço rápido com parecer do commit final, recusa por parecer inválido, base alterada, cópia principal alterada, suíte com falha e objeto forjado; preservação de arquivos, índice, HEAD, sessão, ramo e worktree, inclusive com trabalho concorrente e chamadas simultâneas |
| `testes/baseline.py` | reprodução do rollback antigo, conflito, repetição após publicação manual, interrupção da trava, ferramentas ausentes, marcas inválidas e recuperação sintética |
| `testes/update.sh` | a integração não mexe na cópia instalada, não envia ao remoto, não assina nem roda ganchos; atualização e assinatura continuam ensaiadas com Git sintético |
| `testes/eventos.sh` | histórico de estados gravado pelos hooks e pela troca de foco |
| `testes/restaurar.sh` | volta de uma sessão interrompida |
| `testes/confianca-agy-fluxo.sh` | confiança do agy na abertura, no reaproveitamento e na retomada |
| `testes/contratos-consulta.sh` | consultas de `jangada-agentes` sem gravar no estado e limpeza explícita das órfãs |

## Implementador opcional

É possível selecionar autor e revisor por tarefa. O autor padrão escreve. O
coordenador pode ligar no pedido a delegação de uma atividade com arquivos
exatos ao implementador agy, só em tarefa pequena e bem especificada. Sem a
opção no pedido, o autor não chama o implementador. O autor inspeciona, aceita
pelo hash e testa; o revisor independente continua obrigatório.

O teto é de 3 chamadas por tarefa, e a chamada com `saida_invalida` conta no
teto. Acabado o teto, o autor termina à mão e registra no corpo do commit
quais linhas são dele. Voltar atrás é parar de ligar a opção nos pedidos:
nenhum padrão foi trocado e o MOD-04 fica parado. Os números do piloto MOD-06
estão no [contrato](coordenacao-central/10-executor-agy.md).

## Worktrees dos agentes

O `jangada-agente` cria cada worktree a partir do último
commit, então arquivos fora do git (`.Renviron`, `.env`, dados locais) ficam
para trás. Ao criar um worktree novo, o `jangada-worktree-preparar` lê três
arquivos opcionais na raiz do projeto:

| Arquivo | Efeito |
|---|---|
| `.worktreeinclude` | padrões no formato do `.gitignore`; o que casar e for ignorado pelo git é copiado (mesmo formato do `--worktree` do Claude Code) |
| `.jangada/links` | um caminho por linha; vira link simbólico para a pasta da raiz, sem cópia |
| `.jangada/preparar.sh` | roda dentro do worktree por último, com `JANGADA_RAIZ` e `JANGADA_WORKTREE` no ambiente |

A cópia usa `--reflink=auto`: em btrfs, na mesma partição, não ocupa espaço.
Fora disso, uma cópia maior que `JANGADA_WORKTREE_COPIA_MAX` megabytes (padrão
500) é recusada com aviso. Um link só é mantido se o git do worktree o ignorar;
para pastas, escreva `/dados` no `.gitignore`, sem a barra final, porque o
padrão `dados/` não cobre um link. Um worktree reaproveitado não é preparado de
novo.

## Skills do Claude Code, do agy e do Codex

A etapa de agentes liga cada pasta de `agentes/claude/skills` em
`~/.claude/skills/<nome>` e, se o agy estiver instalado, em
`~/.gemini/config/skills/<nome>`. Os dois agentes carregam a skill quando a
tarefa combina com a descrição dela, mesmo abertos em outro projeto:

- `jangada`: regras do projeto e pegadinhas já resolvidas (`hyprctl dispatch`
  só com Lua, hypridle que ignora `-c`, on-click da waybar com `setsid -f`,
  agy sem terminal).
- `relatorio-tecnico`: investigação, postmortem, RFC, ADR e relatório formal
  (NBR 10719), com a estrutura de cada tipo e o checklist de entrega.
- `relatorio-academico`: artigo, monografia e tese, com o que levantar antes
  de redigir, `[FALTA: ...]` no lugar de dado ou citação sem origem e o
  checklist de entrega.
- `revisao-academica`: revisão de TCC, artigo ou dissertação como orientador,
  com comentários curtos inseridos no PDF ou DOCX. Conduz as etapas do projeto
  `jangada-academic-review` (revisores, critical gate, anotação e QA) e
  mantém o estado e a rastreabilidade.
- `graficos`: gráfico para relatório em R (ggplot2) ou Python (matplotlib),
  com a escolha do tipo pela relação a mostrar, o tema padrão (`tema_dv.R` e
  `tema_dv.py`, copiados para o projeto), título e fonte em comentário fora
  da imagem e a checklist de 41 itens.
- `coordenador`: papel da sessão que abre, acompanha e confere tarefas de
  agentes em qualquer projeto. Também vai para o agy; é a única ligada ao Codex,
  em `~/.codex/skills/coordenador`. Veja
  [docs/ciclo-da-tarefa.md](ciclo-da-tarefa.md#coordenador).

O agy e o Codex leem o mesmo `SKILL.md`, sem ajuste no frontmatter. Uma pasta
ou link alheio com o mesmo nome nessas pastas fica como está, com aviso.

## Perfis e protocolo no uso diário

O seletor calcula as descrições a partir do executor, revisor e delegação
efetivos. `DESCRICAO` em perfis antigos continua sendo lida, mas não
substitui esses valores. Os perfis ficam em `~/.config/jangada/agentes/NOME.conf`;
o modelo está em `agentes/perfis/exemplo.conf`. Fila e orçamento são
configurados separadamente.

O agy não abre sessão principal. `jangada-agente` recusa `--agente agy` e
perfis com `COMANDO=agy`; sessões antigas ainda podem ser restauradas.
Sem terminal, `jangada-agente` exige `--nome`, `--prompt` ou `--direto`.
O seletor recusa executor ausente antes de criar sessão. Revisor ausente
mantém protocolo e testes, mas deixa a entrega sem aprovação.

`JANGADA_AGENTE_PROTOCOLO=0` desliga o protocolo. Em projetos com arquivos R
até dois níveis abaixo da raiz, também entram as regras de
`agentes/perfis/protocolo-r.md`. O Codex usa o worktree e o tmux do jangada,
sem criar outro worktree nem conectar ao servidor compartilhado do programa.

Ganchos pessoais ficam em `~/.config/jangada/ganchos/EVENTO` ou `EVENTO.d/`.
Os eventos são `pos-update`, `pos-tema`, `pos-agente-fim` (sessão, raiz e
indicação de integração) e `pos-validar` (sessão e estado).
`pos-tema` pode chamar `jangada-sddm aplicar` para atualizar o tema do login.

## Detalhes da conferência local e das métricas

O `lintr` usa `.lintr` da base; sem configuração própria, usa
`validacao/lintr`. Do `object_usage_linter`, só considera variável sem uso;
o aviso de variável global em colunas do dplyr é descartado.
Achados do padrão geram aviso; configuração própria torna o achado impeditivo.
Ausência ou falha da ferramenta aplicável não aprova a entrega.

O `gitleaks` lê `.gitleaks.toml` e `.gitleaksignore` da base.
Um falso positivo pode receber `gitleaks:allow` num comentário da linha.
`JANGADA_VALIDAR_SEM_GITLEAKS=1` registra a conferência ausente como
`SKIPPED`; essa opção não produz aprovação com verificação local completa.

`jangada-validar --metricas` resume rodadas, apontamentos e duração por
projeto e revisor a partir de `validar.jsonl`. Os estados de sessão usam
`flock` na pasta `~/.local/state/jangada/agentes`, aberta só para leitura,
pois os hooks rodam em paralelo. Uma trava aberta para escrita poderia
seguir um link criado pelo agente e truncar um arquivo fora do isolamento.
