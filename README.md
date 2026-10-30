# jangada-core

Camada do jangada para abrir, acompanhar, isolar e revisar sessões de agentes
de IA: sessões de autor e revisor em tmux, isolamento com bubblewrap,
validação cruzada entre modelos, delegação a modelos locais e ao agy, fila
persistente de tarefas e registro de provedores.

O Core funciona sozinho. O [jangada-shell](https://github.com/felipintoslv/jangada)
(área de trabalho) e o painel da Central são opcionais: o Core procura os
comandos deles no PATH e segue sem erro quando não os acha. Os indicadores
locais ficam no comando `jangada-indicadores`.

Última versão: v1.0.0, de 18/10/2026, com tag publicada. O `main` seguiu com
correções sem tag nova; `jangada-versao` mostra a distância (por exemplo,
`1.0.0-87-gc874caa`). A [página da versão](docs/versao-1.0.0.md) separa o
estado atual, os limites conhecidos e o histórico do lançamento.

## Dependências

`bash`, `python3`, `sqlite3`, `bwrap` (bubblewrap), `tmux`, `git` e `jq`. R com
o pacote `lintr` é opcional e habilita a verificação de código R na validação.
Os clientes de agente (Claude Code, Codex, agy) e o Ollama são usados quando
instalados.

## Instalação

```sh
git clone https://github.com/felipintoslv/jangada-core.git ~/.local/share/jangada-core
cd ~/.local/share/jangada-core
JANGADA_SIMULAR=1 ./install.sh
./install.sh
```

Confira a simulação antes de aplicar. A instalação recusa worktrees e a cópia
de desenvolvimento, que são graváveis pelo agente. Depois, rode
`testes/verificar.sh`. Detalhes em [instalação e uso](docs/instalacao-e-uso.md).

Configuração em `~/.config/jangada`, estado em `~/.local/state/jangada`.

## Comandos principais

| Comando | Função |
|---|---|
| `jangada-agente` | abre um agente numa sessão tmux isolada, em worktree próprio |
| `jangada-agentes` | lista, abre e encerra as sessões de agentes |
| `jangada-coordenador` | abre o coordenador do projeto no tmux do jangada, sem isolamento |
| `jangada-agente-fim` | encerra a sessão e integra a entrega após aprovação e testes |
| `jangada-validar` | manda a entrega ao outro modelo para revisão |
| `jangada-indicadores` | resume consumo, procedência dos revisores e destinos de delegação |
| `jangada-isolar` | roda um comando no bubblewrap |
| `jangada-delegar` | delega leitura a um modelo local ou ao agy |
| `jangada-fila`, `jangada-executar`, `jangada-task` | fila persistente de tarefas |
| `jangada-router`, `jangada-provedor` | estado e controle dos provedores |
| `jangada-assinar` | assina os commits da cópia de trabalho |
| `jangada-versao` | versões e registro de mudanças |

A lista completa está em [comandos](docs/comandos.md).

## Documentação

Leia as regras do [AGENTS.md](AGENTS.md) e o guia do assunto da tarefa.

| Assunto | Documento |
|---|---|
| Instalação, várias máquinas e assinatura | [Instalação e uso](docs/instalacao-e-uso.md) |
| Entrega e lançamento da v1.0.0 | [Core 1.0.0](docs/versao-1.0.0.md) |
| Comandos | [Comandos](docs/comandos.md) |
| Abertura, revisão e encerramento | [Ciclo da tarefa](docs/ciclo-da-tarefa.md) |
| Permissões, credenciais e modelo de ameaça | [Isolamento](docs/isolamento.md) |
| Papéis, Ollama, agy e fila | [Subagentes e delegação](docs/subagentes-e-delegacao.md) |
| Codex como executor e revisor | [Codex](docs/codex.md) |
| Registro de provedores | [Provedores](docs/provedores.md) |
| Indicadores de tarefas | [Indicadores](docs/indicadores.md) |
| Atualização e migrações | [Atualização e migrações](docs/atualizacao-e-migracoes.md) |
| Campos e limites dos registros | [Registros](docs/registros.md) |
| Código, testes, textos e commits | [Boas práticas](docs/boas-praticas.md) |
| Avisos ao gravar e regras do validar | [Regras automáticas](docs/regras-automaticas.md) |
| Divisão em módulos e contratos (histórico) | [Modularização 3.0](docs/modularizacao-3.0/README.md) |
| Coordenação e consultas entre módulos | [Coordenação central](docs/coordenacao-central/README.md) |
| Evolução 2.0 (histórico) | [Evolução 2.0](docs/evolucao-2.0/00-indice.md) |
| Registros encerrados: estabilização, Inspector (nome anterior da proposta Vigia) e o antigo LEIAME do `core/` | [Histórico](docs/historico/README.md) |
