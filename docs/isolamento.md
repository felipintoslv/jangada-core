# Isolamento dos agentes

O agente (Claude, agy ou Codex) roda dentro do bubblewrap pelo `bin/jangada-isolar`.
Ele grava só na pasta da tarefa e no que o jangada libera; o resto da casa
fica somente leitura, e os segredos ficam ocultos. O objetivo é que nada do
que o agente fizer rode depois fora do isolamento: um hook do git, um
`settings.json` do Claude, um clone do AUR compilado com sudo.

O `jangada-isolar` e o `jangada-agentes` moram em `bin/` e a skill em
`agentes/claude/skills/jangada/`.

No Codex, dados de execução próprios da sessão são montados sobre a pasta
global do CLI, com configuração e login somente leitura. O servidor
compartilhado fica desligado. Veja [Codex](codex.md).

## Modelo de ameaça

O agente é tratado como possivelmente hostil. Ele lê páginas, issues, logs e
documentos, e um texto preparado ali (injeção de prompt) faz um agente
comum agir contra o usuário. Por isso a pergunta que decide cada caso é: o
que o agente grava pode rodar depois fora do isolamento? Se pode, o jangada
confere antes (o `restaurar` recompõe o comando, o `jangada-validar` lê as
regras da base, a atualização manual mostra os commits) ou recusa (o
`install.sh` não instala da cópia de trabalho). O isolamento não protege
contra falha do próprio bubblewrap nem do kernel.

A proteção é contra escrita, não contra leitura. O isolamento não garante que
o agente só conheça os dados do projeto:

- **Arquivos.** O agente lê tudo o que o usuário lê e não está na lista de
  ocultos: documentos pessoais, o `.env` de outro projeto, o histórico do
  shell, o `~/.Renviron`. `JANGADA_ISOLAR_CASA=minima` fecha a pasta
  pessoal (veja Casa mínima); o resto do disco segue legível.
- **Rede.** Não há namespace de rede próprio: o agente fala com a internet e
  com os serviços locais da máquina. O que ele lê, pode enviar.
- **Ambiente.** As variáveis são herdadas. Saem as de sessão gráfica e as de
  credencial que correspondem aos ocultos (`GH_TOKEN`, `GITHUB_TOKEN`,
  `AWS_SECRET_ACCESS_KEY`, `VAULT_TOKEN` e as demais da lista no
  `jangada-isolar`). Outro segredo exportado no shell chega ao agente, a menos
  que `JANGADA_ISOLAR_AMBIENTE=minimo` esteja ligado (seção "Ambiente mínimo").
- **Keyring.** Com o agy instalado, o proxy do D-Bus libera o serviço
  `org.freedesktop.secrets` inteiro, porque o agy guarda o login ali: com o
  keyring destrancado, o agente alcança as outras senhas guardadas nele.
  `JANGADA_ISOLAR_KEYRING_ITEM` restringe a leitura a um item (seção "Keyring
  por item"). Sem o agy, o serviço não é liberado.

## Limites conhecidos

As conversas e a memória em `~/.claude/projects` continuam graváveis pelo
agente, assim como o `settings.json` do agy em `~/.gemini/antigravity-cli`.
Esse arquivo guarda permissões e pastas confiáveis.

Um repositório aninhado criado no worktree e registrado no índice leva
sua própria configuração. Um `git status` executado fora do isolamento
poderia carregá-la. Por isso os scripts do jangada usam `jangada_git_seguro`
para consultar pastas de agentes.

## Decisão de isolar

Desde a correção P0 o isolamento é obrigatório para todos os agentes:
`--sem-isolar` e `JANGADA_AGENTE_ISOLAR=0` são ignorados com aviso. Os
fluxogramas e a precedência abaixo descrevem o comportamento anterior, nos
ramos que desligam o isolamento.

```mermaid
flowchart TD
    A[jangada-agente] --> O{agente Codex?}
    O -- sim --> G[comando = jangada-isolar -- agente]
    O -- não --> B{--sem-isolar?}
    B -- sim --> N[isolar = 0]
    B -- não --> C{JANGADA_AGENTE_ISOLAR<br>no perfil?}
    C -- sim --> D[valor do perfil]
    C -- não --> E[valor do jangada.conf, padrão 1]
    D --> F{isolar != 0?}
    E --> F
    N --> F
    F -- sim --> G
    F -- não --> H[comando = agente]
    G --> I[sessão tmux]
    H --> I
```

Para Claude e agy, `--sem-isolar` tem precedência; sem ela, vale o
`JANGADA_AGENTE_ISOLAR` do perfil e, depois, o da configuração.
O Codex sempre passa pelo isolamento, inclusive com essas opções desligadas.
O prefixo `jangada-isolar --` entra no comando da sessão. O campo `.isolar` do estado
da sessão é só para consulta.

## O que o jangada-isolar monta

```mermaid
flowchart TD
    A[jangada-isolar -- COMANDO] --> B{ja_isolado?}
    B -- sim --> X[exec COMANDO direto]
    B -- não --> O{adaptador Codex?}
    O -- sim --> C{bwrap instalado?}
    O -- não --> P{JANGADA_AGENTE_ISOLAR = 0?}
    P -- sim --> X
    P -- não --> C
    C -- não --> F[recusa, código 1]
    C -- sim --> D[base: / somente leitura,<br>/tmp e PID próprios]
    D --> E[sockets de /run ocultos,<br>XDG_RUNTIME_DIR vazio,<br>D-Bus pelo proxy filtrado]
    E --> G[graváveis: pasta, ~/.claude,<br>agy, estado dos agentes,<br>JANGADA_ISOLAR_ESCRITA]
    G --> H[somente leitura por cima:<br>config do Claude, bin do agy,<br>config e hooks do git]
    H --> I[ocultos: .ssh, .gnupg,<br>chaves de nuvem, navegador,<br>keyring, cliphist]
    I --> J[remove TMUX, SSH_AUTH_SOCK,<br>HYPRLAND_*, WAYLAND_DISPLAY;<br>define JANGADA_ISOLADO=1]
    J --> K[exec bwrap]
```

A ordem importa: o bubblewrap aplica as montagens na sequência, e cada uma
vale por cima das anteriores. Por isso os graváveis vêm antes e o que precisa
ficar somente leitura dentro deles vem depois.

| Camada | O que entra | Por quê |
|---|---|---|
| Base | `/` somente leitura, `/dev`, `/proc`, `/tmp` próprio, `--unshare-pid`, `--die-with-parent` | um `rm` no `/tmp` não apaga os temporários do sistema; o agente não vê nem mata os processos da sessão, e o que ele deixou rodando morre com ele |
| `/run` | Docker, containerd, podman, tailscale, sshd local e D-Bus do sistema ocultos | esses sockets dão root ou mudam a máquina |
| `XDG_RUNTIME_DIR` | pasta vazia; o D-Bus da sessão volta pelo `xdg-dbus-proxy`, que só deixa falar com `org.freedesktop.Notifications` e, com o agy instalado, `org.freedesktop.secrets` | some o socket do Hyprland (`hyprctl dispatch` rodaria comando fora), do Wayland, do gpg-agent e do systemd do usuário; o agy lê o login do keyring e os hooks avisam pelo `notify-send` |
| Graváveis | pasta da tarefa, `~/.claude`, `~/.gemini/antigravity-cli`, `agentes/`, `validar.jsonl`, `eventos-agentes.jsonl` e `delegacoes.jsonl` do estado, e o que estiver em `JANGADA_ISOLAR_ESCRITA` | o resto do estado (barra, marcas das migrações) alimenta código que roda fora |
| Camada temporária | `~/.cache`; do Claude, `shell-snapshots`, `session-env` e `ide`; do agy, `bin` | o agente lê o conteúdo de fora, e o que grava some no fim (sobreposição do bwrap; sem suporte, o agente recebe uma pasta vazia em memória, e o `bin` do agy, somente leitura). O agy regrava o `agentapi` antes de cada comando, e o que ele regrava dentro não roda fora |
| Somente leitura | do Claude: `settings*.json`, `CLAUDE.md`, `commands`, `agents`, `skills`, `hooks`, `plugins`, scripts soltos; clones do AUR | tudo isso define comando ou instrução que valeria numa sessão aberta fora |
| Git | num worktree, o `.git` comum inteiro somente leitura, liberados `objects`, o gitdir do worktree e, das refs e dos `logs`, só a pasta do ramo da sessão (`refs/heads/agente`) e a das cópias do `reverter` (`refs/heads/backup`); direto no repositório, `config`, `hooks`, `commondir`, `worktrees` e `modules` somente leitura | `core.fsmonitor`, hooks e `commondir` rodariam fora no próximo `git status` |
| Ocultos | `.ssh`, `.gnupg`, `.password-store`, `.aws`, `.azure`, `.kube`, `.docker`, `.netrc`, `.git-credentials`, `gh`, `rclone`, `gcloud`, `op`, `sops`, Bitwarden, `.vault-token`, `.pgpass`, `.my.cnf`, `.pypirc`, perfis de navegador e do Thunderbird, keyrings, kwallet e o banco do `cliphist`; `JANGADA_ISOLAR_OCULTAR` troca a lista. A pasta `painel-chave` do estado, com o token do `jangada-painel`, a `revisoes`, com as revisões feitas fora do isolamento, e as `fotos` e `integracoes`, com as árvores da entrega que o `jangada-validar` e o `--integrar` extraem fora dele, ficam ocultas sempre; das fotos, só a escolhida em `JANGADA_ISOLAR_FOTO` volta ao revisor, somente leitura | segredos e o histórico da área de transferência; o painel responde a quem alcança a porta, e o agente isolado alcança; a aprovação que o `--integrar` aceita não pode ser escrita pelo agente revisado; as árvores da entrega trazem os links versionados dela e por isso ficam fora de `revisoes`, onde o `jangada-isolar` recusa link |

Para ver os argumentos sem abrir nada: `jangada-isolar --mostrar -- true`.

## A marca de isolamento

`ja_isolado` em `bin/jangada-isolar` só aceita a marca quando as duas coisas
valem: `JANGADA_ISOLADO` no ambiente e o ponto de montagem
`/tmp/.jangada-isolado` em `/proc/self/mountinfo`. Qualquer processo cria um
arquivo no `/tmp`, mas só quem monta cria um ponto de montagem; por isso a
variável herdada não basta para pular o isolamento.

## Perfis, rede e credenciais dos provedores

O `jangada-isolar` tem três perfis, escolhidos por `JANGADA_ISOLAR_PERFIL`:

| Perfil | Rede | Login e chaves dos provedores | Quem usa |
|---|---|---|---|
| `agente` (padrão) | a da máquina | visíveis | `jangada-agente`, `jangada-delegar`, revisores |
| `verificacao` | nenhuma (`--unshare-net`) | ocultos | `lintr` e `.jangada/validar.sh` no `jangada-validar` |
| `verificacao-rede` | a da máquina | ocultos | `.jangada/validar.sh` com `JANGADA_VALIDAR_REDE=1` |

Fora do perfil `agente` somem `~/.claude`, `~/.claude.json`, `~/.codex`,
`~/.gemini` e as variáveis `ANTHROPIC_*`, `OPENAI_*`, `GEMINI_*`, `GOOGLE_*`,
`CLAUDE_*`, `CODEX_*`, `AGY_*` e `ANTIGRAVITY_*`, e o D-Bus não é ligado.
Perfil desconhecido é recusado. Dentro de uma sessão já isolada, o perfil
`agente` roda direto. Os perfis de verificação criam outro isolamento para
retirar as credenciais e aplicar sua política de rede, mesmo com
`JANGADA_AGENTE_ISOLAR=0`.

No perfil `agente` não há política de rede nem intermediário de credenciais:
o agente fala com qualquer destino e lê o login do próprio provedor e dos
outros, porque delega e revisa por eles. Um agente desviado por injeção de
prompt consegue enviar para fora o que lê, inclusive esses logins. Um
intermediário (processo fora do isolamento que guarda as chaves e assina as
chamadas) fecharia isso, mas depende de cada cliente aceitar um endereço de
API próprio e fica fora do que o jangada faz hoje. Reduz o dano: usar login
de assinatura em vez de chave de API com cobrança por uso,
`JANGADA_ISOLAR_CASA=minima`, `JANGADA_ISOLAR_AMBIENTE=minimo` e
`JANGADA_ISOLAR_KEYRING_ITEM`.

## Refs do git

Num worktree, o agente grava só na pasta de refs do próprio ramo. Como todas
as sessões usam `refs/heads/agente/`, uma sessão consegue mover o ramo de
outra. O git cria o `.lock` ao lado da ref, então liberar um arquivo só não
funciona. A defesa fica na integração: o `--integrar` só aceita o commit e a
árvore que a revisão de fora aprovou, e um ramo movido volta a ser revisado.
Repositório com refs em reftable guarda tudo numa pasta só; ali o
`jangada-isolar` recusa abrir o worktree e mostra o comando de conversão.

## Casa mínima

Com `JANGADA_ISOLAR_CASA=minima` no `jangada.conf`, a pasta pessoal vira uma
pasta vazia em memória antes das outras montagens. Por cima dela voltam,
somente leitura:

- as pastas do `PATH` dentro da pasta pessoal, `~/.local/bin`, `~/.local/lib`,
  `~/.local/share/claude`, `~/.local/share/mise` e `~/.config/mise`;
- a cópia instalada, a configuração e o estado do jangada;
- `~/.gitconfig` e `~/.config/git`;
- `~/.claude.json`, `~/.gemini` e `~/.codex`;
- o que estiver em `JANGADA_ISOLAR_CASA_LER`, separado por `:`.

As regras de graváveis, somente leitura e ocultos valem como antes, por cima.
Documentos, outros projetos, o histórico do shell e o `~/.Renviron` deixam de
existir para o agente. O que ele grava solto na pasta pessoal fica em memória
e some no fim.

Os arquivos de início do shell (`.zshrc`, `.bashrc`, `.profile` e os demais)
ficam de fora desde 05/10/2026: é neles que se exporta token. Quem precisa
deles no agente acrescenta em `JANGADA_ISOLAR_CASA_LER`.

O padrão continua sendo a casa inteira legível. A lista cobre o que o jangada
conhece: bibliotecas de R em `~/R`, `~/.cargo`, `~/.nvm` ou dados que o
projeto alcança por link (`.jangada/links`) precisam entrar em
`JANGADA_ISOLAR_CASA_LER`. O que fica fora da pasta pessoal (`/etc`, `/mnt`,
outros discos) segue legível.

## Keyring por item

`JANGADA_ISOLAR_KEYRING_ITEM` recebe os atributos do item do agy no keyring,
em pares `atributo=valor` separados por espaço. Na abertura, fora do
isolamento, o `jangada-isolar` procura os itens com esses atributos e o proxy
passa a liberar só eles. O resto do serviço fica assim:

- leitura de outro item (`GetSecret`, propriedades) e leitura em lote
  (`Service.GetSecrets`): negadas;
- busca por atributos na coleção: liberada, devolve caminhos e não segredos;
- `CreateItem` na coleção: liberado, porque o agy regrava o token por ele.
  Com isso o agente ainda cria item e sobrescreve um item cujos atributos
  conheça, sem ler o valor antigo;
- destrancar a coleção e responder ao pedido de senha: liberados.

Um item criado durante a sessão só fica legível na abertura seguinte. Valor
fora do formato fecha a leitura do keyring e avisa no terminal.

Os atributos do item do agy não estão documentados. Para listar os de todos
os itens, sem os segredos, num terminal fora do isolamento:

```bash
for i in $(gdbus call --session --dest org.freedesktop.secrets \
    --object-path /org/freedesktop/secrets \
    --method org.freedesktop.Secret.Service.SearchItems '@a{ss} {}' \
    | grep -oE '/org/freedesktop/secrets/collection/[A-Za-z0-9_]+/[A-Za-z0-9_]+'); do
  gdbus call --session --dest org.freedesktop.secrets --object-path "$i" \
    --method org.freedesktop.DBus.Properties.Get org.freedesktop.Secret.Item Attributes
done
```

## Ambiente mínimo

Com `JANGADA_ISOLAR_AMBIENTE=minimo`, o agente recebe só as variáveis de uma
lista: as do sistema (`HOME`, `PATH`, `TERM`, `LANG`, `LC_*`, `XDG_*`, proxy e
certificados), as do jangada e do mise, e as dos agentes (`CLAUDE_*`,
`ANTHROPIC_*`, `CODEX_*`, `OPENAI_*`, `GEMINI_*`, `GOOGLE_*`, `AGY_*`,
`NODE_*`). As demais saem, inclusive as que o `~/.zshenv` exportou antes de o
jangada abrir. O que o projeto usa (`R_LIBS_USER`, `JAVA_HOME`) entra em
`JANGADA_ISOLAR_AMBIENTE_MANTER`, separado por `:`.

As variáveis de credencial conhecidas saem mesmo quando listadas ali. O shell
que o agente abre dentro do isolamento lê de novo os arquivos de início: o que
eles exportam volta, a menos que a casa mínima os deixe de fora.

## Falhas

- Sem `bwrap`: o `jangada-isolar` recusa com código 1 e nenhum agente abre;
  instale o pacote `bubblewrap`.
- Sem proxy do D-Bus (programa ausente ou sem resposta em 5 segundos): o
  agente abre sem D-Bus, e o agy não acha o login.
- Apagar ramo ou tag e o `git gc` falham dentro de um worktree, porque
  regravam o `packed-refs`, que fica na raiz somente leitura.
- Dentro de um worktree, o agente não move `main` nem outro ramo fora de
  `agente/` e `backup/`, e não cria tag, stash nem ref de remoto: `git stash`,
  `git tag`, `git fetch` e `git branch outro-nome` falham. Os ramos das outras
  sessões ficam na mesma pasta `agente/` e seguem ao alcance. Num repositório
  com `reftable`, todas as refs ficam numa pasta só e seguem graváveis.

## Restauração

```mermaid
flowchart TD
    A[jangada-agentes --restaurar] --> B[lê o estado da sessão]
    B --> C{campos conferidos?<br>agente, pasta, conversa,<br>perfil, revisor}
    C -- não --> R[recusa: nada foi executado]
    C -- sim --> D[monta o comando<br>dos campos conferidos]
    D --> O{agente Codex?}
    O -- sim --> F[prefixo jangada-isolar]
    O -- não --> E{JANGADA_AGENTE_ISOLAR<br>da configuração != 0?}
    E -- sim --> F
    E -- não --> G[sem prefixo]
    F --> H[refazer_protocolo]
    G --> H
    H --> I[sessão tmux]
```

`restaurar` em `bin/jangada-agentes` nunca executa o `.comando` nem lê o
`.isolar` do estado: o arquivo fica numa pasta que o agente grava, e um
agente poderia trocar o comando ou desligar o isolamento da próxima abertura.
O perfil também não desliga o isolamento na restauração. O Codex sempre
recebe o prefixo de isolamento, mesmo com a configuração global desligada.
O protocolo é refeito numa gravação por `mv -fT`, que não segue um link plantado.

## Testes

O processo externo também observa as gravações do arquivo de estado da
sessão com `inotifywait`. Apenas o nome de sessão conferido é observado;
o conteúdo do arquivo não é executado. Cada mudança avisa a Waybar com
o sinal 10. Isso permite atualização imediata, pois o hook isolado não
enxerga o processo da barra no namespace de PID do host. O observador
e o processo de `inotifywait` são encerrados junto com o isolamento.

| Arquivo | O que cobre |
|---|---|
| `testes/isolar.sh` | argumentos do bwrap (gravável, somente leitura, oculto, `/tmp`, marca), repositório direto, `JANGADA_AGENTE_ISOLAR=0`, variável sem marca não dispensa, recusa sem bwrap e um isolamento de verdade: gravação, commit, chave oculta, D-Bus restrito e PID próprio |
| `testes/restaurar.sh` | comando gravado e `.isolar: false` ignorados, `JANGADA_AGENTE_ISOLAR=0` abre fora, campos inválidos recusados, perfil não desliga o isolamento, protocolo refeito sem seguir link |

Dentro de uma sessão do agente, o `testes/isolar.sh` passa, mas pula o caso
do D-Bus (o endereço do barramento não entra no teste) e a leitura da casa
mínima (`/var/tmp` é somente leitura). A conferência completa é num terminal
comum.

Veja também o [ciclo da tarefa](ciclo-da-tarefa.md) e a seção de isolamento
da skill em `agentes/claude/skills/jangada/agentes.md`.

## Isolamento da implementação delimitada

O perfil `implementacao` sempre cria outro isolamento. Ele expõe fontes
copiadas e arquivos exatos, sem liberar worktree, Git ou estado persistente.
O estado do CLI é temporário e o keyring selecionado é somente leitura.
Veja o [contrato do piloto](coordenacao-central/10-executor-agy.md).

## Ajustes pessoais das montagens

`JANGADA_ISOLAR_ESCRITA` acrescenta pastas graváveis separadas por `:`, como
`~/dados:~/R`. `JANGADA_ISOLAR_OCULTAR` substitui a lista de ocultos;
definida vazia, remove os ocultos opcionais. Para acrescentar caminhos sem
perder a lista padrão, use `JANGADA_ISOLAR_OCULTAR_EXTRA`.
As pastas protegidas do controlador continuam ocultas independentemente dessas opções.
