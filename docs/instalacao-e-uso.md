# Instalação e uso em várias máquinas

## Instalação

```sh
git clone <url> ~/.local/share/jangada-core
cd ~/.local/share/jangada-core
JANGADA_SIMULAR=1 ./install.sh   # confere o que será feito
./install.sh                     # aplica
```

O `install.sh` executa as etapas de `install/` em ordem: verificações (00),
pacotes (10), comandos (20) e agentes (50). Para rodar só algumas, passe o prefixo
(`./install.sh 10 50`). O `install.sh` recusa rodar da cópia de trabalho
(`JANGADA_REPO`), de um worktree, de `JANGADA_WORKTREES` ou de qualquer pasta
dentro de `JANGADA_PROJETOS` (onde fica a cópia de trabalho do Core): essas
pastas são graváveis de dentro do isolamento, e a pasta da instalação vira o
`JANGADA_CORE_PATH` dos hooks e da sessão. Nelas só a simulação roda.

A etapa 20 grava em `~/.local/bin` um invólucro para cada comando de `bin/`.
Ela não sobrescreve um arquivo alheio com o mesmo nome: avisa e termina com
erro, listando os conflitos. O Core ignora o `JANGADA_PATH` que o Shell exporta
na sessão e só lê o `JANGADA_CORE_PATH`.

Depois, rode `testes/verificar.sh` para conferir a instalação.

Use `jangada doctor` para consultar o ambiente, ou
`jangada doctor --json` para obter o relatório estruturado. O resumo separa
falhas, avisos e consultas não verificáveis. Saída 1 indica falha; saída 0
pode conter avisos e itens não verificáveis. O comando não corrige o ambiente,
não renova login nem cotas e não aplica migrações. A conferência Git usa e remove
uma cópia temporária na pasta de estado existente. Veja os
[limites das consultas](comandos.md#diagnóstico-do-ambiente).

## Várias máquinas

O repositório é o mesmo em todas as máquinas; o que muda de uma para outra
fica só em `~/.config/jangada`. Nenhum arquivo do repositório cita usuário ou
caminho de uma máquina específica.

| O que muda por máquina | Onde fica |
|---|---|
| Pastas de projetos (`JANGADA_PROJETOS`, `JANGADA_REPO`) | `~/.config/jangada/jangada.conf` |
| Agente, delegação e revisor padrão | `~/.config/jangada/jangada.conf` |
| Perfis de agente e ganchos | `~/.config/jangada/agentes/`, `~/.config/jangada/ganchos/` |

Roteiro para uma máquina nova:

1. Clonar em `~/.local/share/jangada-core` a partir do remoto compartilhado.
2. `JANGADA_SIMULAR=1 ./install.sh`, conferir, e `./install.sh`.
3. Ajustar `~/.config/jangada/jangada.conf`.
4. Rodar `testes/verificar.sh`.

### Atualização

A cópia instalada só recebe avanço rápido. Em um terminal comum, busque a
origem, confira os commits e aplique:

```sh
git -C ~/.local/share/jangada-core fetch
git -C ~/.local/share/jangada-core log --oneline HEAD..@{u}
git -C ~/.local/share/jangada-core merge --ff-only @{u}
```

A cópia instalada não é editada: a edição acontece na cópia de trabalho.

### Commits assinados

Com `~/.config/jangada/allowed_signers`, só se aplicam commits assinados por
uma chave desse arquivo. O arquivo fica fora da cópia de trabalho e é
somente leitura para o agente isolado, que também não vê a chave. Os commits
dos agentes chegam sem assinatura. Antes do envio ao remoto, rode
`jangada-assinar` fora do isolamento. Para habilitar a conferência, num
terminal comum:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519   # se ainda não houver chave
echo "$(git config user.email) namespaces=\"git\" $(cat ~/.ssh/id_ed25519.pub)" \
  >~/.config/jangada/allowed_signers
jangada-assinar          # antes do envio ao remoto
```

Outra chave vai em `JANGADA_ASSINATURA_CHAVE` no `jangada.conf`.

### Versões

As versões seguem o formato `vX.Y.Z`, em tags anotadas do git (`v0.1.0`,
`v0.2.0`, `v1.0.0`). O `CHANGELOG.md` é
gerado das mensagens de commit pelo `jangada-versao --lancar X.Y.Z`: o que
começa com `feat` entra em Novidades, o que começa com `fix` em Correções e o
resto em Outras mudanças. `jangada-versao` mostra a versão instalada.

O `--lancar` grava o `CHANGELOG.md`, faz o commit dele e cria a tag no estado
atual do ramo. O `jangada-assinar` refaz commits e não move tags: uma tag criada
antes da assinatura fica apontando para o commit sem assinatura. Com commits
ainda sem assinatura, rode o `--lancar` numa cópia temporária privada do
repositório, aproveite só o `CHANGELOG.md` gerado e crie a tag anotada à mão,
no commit já assinado, antes de publicá-la. A sequência usada na `v1.0.0`, com
os resultados esperados, está registrada em
[Core 1.0.0](versao-1.0.0.md#roteiro-do-dono) e serve de modelo para a próxima.
