# Atualização e migrações

O Core roda de uma cópia instalada em `~/.local/share/jangada-core`
(`JANGADA_CORE_PATH`), que só avança pelo `jangada-update` e só depois de você ver
e aceitar os commits novos. Mudança que exige ajuste numa instalação
existente chega por uma migração do Core, aplicada uma única vez pelo
`jangada-migrar`. O sistema (pacotes, snapshots, recarga da sessão) é do
`jangada-sistema-update`, do jangada-shell, que o `jangada-update` chama no
fim quando ele está no PATH.

## Instalação inicial

```mermaid
flowchart TD
    A[./install.sh ETAPAS] --> B{usuário root?}
    B -- sim --> X[recusa]
    B -- não --> B2{cópia de trabalho, worktree,<br>JANGADA_WORKTREES ou JANGADA_PROJETOS?}
    B2 -- sim, sem simulação --> X
    B2 -- não, ou simulação --> C[install/NN-*.sh em ordem numérica]
    C --> D[00 verificações] --> E[10 pacotes] --> I[50 agentes]
```

- Com argumentos, roda só as etapas com esse prefixo: `./install.sh 10 50`.
- `JANGADA_SIMULAR=1 ./install.sh` mostra o que seria feito sem executar.
- A pasta de onde o `install.sh` roda vira o `JANGADA_CORE_PATH`. A cópia de
  trabalho, os worktrees e tudo em `JANGADA_PROJETOS` são graváveis de dentro
  do isolamento, então instalar dali faria os hooks e a sessão rodarem o que o
  agente muda. Nelas só a simulação roda.

## Como escrever uma etapa ou migração

As duas usam as funções de `install/lib.sh`:

| Função | Uso |
|---|---|
| `executar CMD...` | roda o comando, ou só o mostra com `JANGADA_SIMULAR=1` |
| `como_root CMD...` | o mesmo, com `sudo` quando não é root |
| `copia_seguranca ARQ` | cópia `.jangada-DATA.bak` antes de alterar um arquivo existente |
| `copiar_se_ausente ORIGEM DESTINO` | cria o arquivo do usuário só se ele não existir |
| `simulando` | verdadeiro com `JANGADA_SIMULAR=1` |

Regras de uma migração (`migrations/README.md`):

1. Nome `AAAAMMDDHHMM-descricao.sh`; a ordem de aplicação é a do nome.
2. Pode rodar de novo sem estragar nada: uma falha no meio faz ela ser
   tentada outra vez.
3. Nunca apaga arquivo do usuário; move para `.bak` com data.
4. Explica no topo o que mudou e por quê.
5. O padrão correspondente é corrigido também, para a instalação nova.

## jangada-update

```mermaid
flowchart TD
    A[jangada-update] --> G0{fora do isolamento,<br>sem sessões nem processos<br>da instalação?}
    G0 -- não --> X[recusa, código 1]
    G0 -- sim --> B{cópia instalada limpa?}
    B -- não --> S[avisa e segue]
    B -- sim --> C[git fetch origin]
    C --> D{no ramo JANGADA_CANAL?}
    D -- não --> D1[troca de ramo,<br>com confirmação se vier da origem]
    D -- sim --> E
    D1 --> E{origem à frente<br>em linha reta?}
    E -- não --> S
    E -- sim --> F0{com allowed_signers,<br>todos assinados?}
    F0 -- não --> S
    F0 -- sim, ou sem o arquivo --> F[confirmar_novidades:<br>commits, arquivos e aviso<br>de migrations, install, bin]
    F -- não ou sem terminal --> S
    F -- s --> G[merge --ff-only]
    G --> M[jangada-migrar]
    M --> P{--so-core?}
    S --> P
    P -- sim --> Z[fim]
    P -- não --> Q{jangada-sistema-update<br>no PATH?}
    Q -- sim --> R[roda sem argumentos<br>e repassa o código de saída]
    Q -- não --> Z
```

- **Confirmação.** A origem da cópia instalada é a cópia de trabalho, cujas
  refs um agente isolado pode gravar. Por isso nada que chega por ela roda
  sem você ver: `confirmar_novidades` mostra os commits, os arquivos e um
  aviso quando mudam `migrations/`, `install/` ou `bin/`. Os textos passam
  por um filtro de caracteres de controle, para que uma sequência de escape
  não disfarce a lista. Sem terminal, a resposta é não.
- **Assinaturas.** Com `~/.config/jangada/allowed_signers`, todo commit que
  chegaria precisa de assinatura válida por esse arquivo, conferida commit a
  commit (o `--verify-signatures` do merge só olharia o último); se algum
  não tem, nada é aplicado. O arquivo fica fora da cópia de trabalho e
  somente leitura no isolamento, então um agente não inclui nele uma chave
  própria. Os agentes fazem commit sem a chave, que o isolamento oculta: o
  `jangada-assinar`, num terminal comum, mostra os commits ainda não
  enviados e sem assinatura válida e os assina com `JANGADA_ASSINATURA_CHAVE`
  depois da confirmação, a partir do primeiro sem assinatura, para não
  reescrever o que a cópia instalada já aplicou. Commit enviado sem
  assinatura e ainda não aplicado fica fora do que ele reescreve e dentro do
  que o `jangada-update` confere: o `jangada-assinar` avisa e mostra o
  comando que avança a cópia instalada à mão, depois de você conferir esses
  commits. Os merges do `jangada-agente-fim --integrar` são refeitos e
  assinados junto, e o próprio `--integrar` chama o `jangada-assinar` depois
  de apagar o ramo, quando a raiz é a cópia de trabalho do jangada; chamado
  de dentro da própria sessão, ele só avisa, porque a limpeza segue sem
  terminal. Refazer um merge perde o que foi resolvido ou alterado nele à
  mão: com conflito, o rebase para e `git rebase --abort` desfaz; sem
  conflito, o comando nota a diferença, volta o ramo ao que era e não assina
  nada. O `jangada-update` e o `jangada-assinar` fixam o `gpg.ssh.program`
  em `ssh-keygen`, porque o da configuração do repositório rodaria fora do
  isolamento.
- **Avanço rápido.** Só `--ff-only`: origem que não avança em linha reta
  não é aplicada.
- **Canal.** `JANGADA_CANAL` (`main` ou `estavel`) escolhe o ramo que a cópia
  instalada acompanha.
- **Guardas.** O comando recusa rodar dentro do isolamento, com sessões de
  agentes abertas no tmux do Jangada ou com processos que usam a instalação.
  Interrompa os executores e preserve os registros antes de atualizar. Não há
  simulação: `JANGADA_SIMULAR=1` é recusado, e as migrações se conferem com
  `JANGADA_SIMULAR=1 jangada-migrar`.
- **Git sem ganchos.** Todo git sobre a cópia instalada passa por
  `jangada_git_seguro`, sem fsmonitor nem ganchos da configuração do
  repositório.
- **Sistema.** Sem `--so-core`, e se `jangada-sistema-update` existir no
  PATH, ele roda no fim, sem argumentos, e o código de saída dele é o do
  comando. Pacotes, AUR, Hyprland, snapshots, initramfs, NVIDIA, recarga da
  sessão e ganchos `pos-update` ficam com o Shell. Código recusado não
  impede o sistema, mas o comando termina com erro.

## jangada-migrar

```mermaid
flowchart TD
    A[jangada-migrar] --> B[flock na pasta de marcas, 60 s]
    B -- ocupada --> X[outra migração em andamento, código 1]
    B -- ok --> C[migrations/*.sh em ordem de nome,<br>pasta sem scripts: nada a fazer]
    C --> D{marca em<br>estado/migracoes/NOME?}
    D -- sim --> C
    D -- não --> E[bash MIGRAÇÃO]
    E -- falhou --> X2[para a sequência, código 1]
    E -- ok --> F{JANGADA_SIMULAR=1?}
    F -- não --> G[grava a marca]
    F -- sim --> C
    G --> C
```

Em simulação a marca não é gravada: gravar faria a execução seguinte, a de
verdade, pular uma migração que nunca foi aplicada.

A pasta `migrations/` começa vazia no Core. As migrações anteriores à
separação ficam no histórico do monorepo, e as marcas delas em
`$JANGADA_ESTADO/migracoes/` impedem que sejam reaplicadas.

### Padrões do isolamento de 30/10/2026

A migração `202610301200-avisar-isolamento-credenciais.sh` não grava nada:
ela mostra, uma vez, o que muda na configuração de quem atualiza. Os novos
padrões do `jangada-isolar` valem para quem não definiu as variáveis no
`jangada.conf`:

| Antes | Agora | Para voltar ao modo antigo |
|---|---|---|
| pasta pessoal inteira legível | casa mínima | `JANGADA_ISOLAR_CASA=inteira` |
| ambiente herdado, menos a lista fixa | lista base, sem nomes de credencial | `JANGADA_ISOLAR_AMBIENTE=herdado` |
| keyring inteiro sem `JANGADA_ISOLAR_KEYRING_ITEM` | keyring fechado | `JANGADA_ISOLAR_KEYRING=servico` |
| login dos três provedores no perfil `agente` | só o do principal e o do destino da delegação | `JANGADA_ISOLAR_PROVEDORES=claude:codex:agy` |

O modo antigo avisa no terminal a cada abertura. Valor fora da lista é
recusado, em vez de cair calado num modo sem proteção. O ajuste fino, sem
voltar ao modo antigo, é `JANGADA_ISOLAR_CASA_LER` para caminhos e
`JANGADA_ISOLAR_AMBIENTE_MANTER` para variáveis. Uma sessão aberta antes da
atualização segue com o modo antigo até ser reaberta. Detalhes em
[isolamento](isolamento.md).

## Testes

| Arquivo | O que cobre |
|---|---|
| `testes/update.sh` | resposta `n` e sem terminal não aplicam; `s` avança, roda a migração e grava a marca; filtro de caracteres de controle; origem reescrita recusada; com `allowed_signers`, commit sem assinatura ou com chave de fora não é aplicado; `gpg.ssh.program`, fsmonitor e ganchos da cópia instalada não rodam; canal `estavel`; `jangada-migrar` com a pasta vazia, em simulação e com falha; `--so-core` não chama o `jangada-sistema-update`, e sem ele o comando é chamado e o código de saída repassado |
| `testes/update-codigo.py` | em clones descartáveis e com bubblewrap: recusa com árvore suja, sessão ativa, processo da instalação, isolamento e simulação, sem chamar pacote nem migração |
| `testes/consumo.sh` | `jangada-consumo` com registros sintéticos e a dica da barra |
| `testes/hooks.sh` | `mesclar_hooks_claude` e `mesclar_hooks_agy` com o arquivo vazio gravam os hooks (o vazio conta como `{}`); com JSON inválido, avisam e não gravam; o `jangada-verificar` aponta o arquivo vazio ou inválido |
|| `.github/workflows/verificar.yml` | a CI simula a instalação como usuário sem sudo e confere que nada foi escrito |

Veja também as [boas práticas](boas-praticas.md) e o ciclo de versão no
README (`jangada-versao`).

### Git separado de 30/10/2026

Sessão nova do `jangada-agente` deixou de ser `git worktree` e passou a ser
um clone com `.git` próprio em `JANGADA_WORKTREES`. Refs, índice e objetos
novos ficam no clone; os objetos da raiz entram pelo
`objects/info/alternates`, sem cópia. O ramo `agente/NOME` é criado também na
raiz ao abrir, e o `jangada-agente-fim` leva os commits do clone para ele por
`fetch` com conferência de cada objeto, antes de apagar o clone. Na
integração, a entrega passa pelo espelho em `revisoes/espelhos` e só avança a
base pelo commit exato aprovado.

A migração `202610301300-avisar-git-separado.sh` não grava nada: lista as
sessões antigas. Elas não são convertidas. Uma sessão aberta antes da
atualização segue em worktree, com aviso ao ser reaberta, até o
`jangada-agente-fim`, que a encerra pelo caminho antigo. Enquanto houver
sessão antiga, os objetos e as refs `agente/` da raiz continuam graváveis de
dentro dela; a proteção nova vale inteira quando a última for encerrada.

O clone depende dos objetos da raiz. Um `git gc --prune=now` na raiz depois
de reescrever a história dela (por exemplo, `reset` para trás seguido de
`gc`) pode apagar um objeto que o clone ainda usa. Não há outra alternativa
silenciosa: sem `jangada.raiz` no config, uma pasta com `.git` próprio não é
aceita como sessão pelo `jangada-agente-fim`.
