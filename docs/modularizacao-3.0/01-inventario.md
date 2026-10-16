# 1. Inventário e destino dos arquivos

Base: `main` em `ad30fdd`. Contagens por `git ls-files`.

| Pasta | Arquivos | Papel hoje |
|---|---|---|
| `bin/` | 59 | comandos `jangada-*` (10.927 linhas) |
| `default/` | 127 | padrões: Hyprland, Waybar, temas, agentes, pacotes Python |
| `shell/` | 2 | integração com Bash e Zsh |
| `install/` | 12 | etapas da instalação e `lib.sh` |
| `migrations/` | 25 | 24 migrações e o README |
| `testes/` | 58 | suíte chamada por `testes/verificar.sh` |
| `config/` | 4 | modelos copiados para `~/.config/jangada` |
| `docs/` | 296 | documentação; nenhum código depende dela |

## 1.1 Comandos de `bin/`

O arquivo real vai para `<módulo>/bin/` e `bin/` guarda um link relativo com
o mesmo nome. Os compartilhados ficam como arquivos reais em `bin/`.

### Core (23), destino `core/bin/`

| Comando | Observação |
|---|---|
| `jangada-agente` | misto: usa `hyprctl` e terminal quando há sessão gráfica; sem ela faz `tmux attach` (linha 537) |
| `jangada-agente-fim` | `--integrar` segue bloqueado |
| `jangada-agentes` | misto: `hyprctl` (389, 416, 419, 460), `--waybar`, chama `jangada-consumo` (635) e hoje limpa órfãos na consulta (623, 630); K4 torna a limpeza explícita |
| `jangada-isolar` | sinaliza a Waybar (628) |
| `jangada-validar` | chama `jangada-subagentes --entrega` (159) |
| `jangada-delegar` | regra `sem_fonte` repetida (773 e 969) |
| `jangada-worktree-preparar` | |
| `jangada-hook-claude`, `jangada-hook-agy`, `jangada-hook-codex` | mistos: `pkill` da Waybar (118, 65, 41) e `notify-send` |
| `jangada-hook-leitor` | |
| `jangada-codex`, `jangada-codex-hooks` | adaptadores do Codex |
| `jangada-projeto`, `jangada-fila`, `jangada-task`, `jangada-executar`, `jangada-retomar`, `jangada-provedor`, `jangada-router`, `jangada-avaliar-ollama` | invólucros de 6 linhas sobre os pacotes Python |
| `jangada-mapa`, `jangada-filtrar` | utilitários de contexto para agentes; o agente Core os deixou como compartilhados, a consolidação os pôs no Core porque só agentes os usam |

### Shell (25), destino `shell/bin/`

`jangada-atalhos`, `jangada-atualizacoes`, `jangada-audio`, `jangada-barra`,
`jangada-bloquear`, `jangada-bluetooth`, `jangada-calendario`,
`jangada-captura`, `jangada-conversa`, `jangada-energia`, `jangada-importar`,
`jangada-interface-processos`, `jangada-logo`, `jangada-mapear`,
`jangada-menu`, `jangada-monitor`, `jangada-recarregar`, `jangada-rede`,
`jangada-sddm`, `jangada-sessao`, `jangada-shell`, `jangada-snapshot`,
`jangada-tarefas`, `jangada-tema`, `jangada-terminal`.

Observações:

- `jangada-monitor` abre o btop em janela flutuante. Apesar do nome, é Shell.
  A opção `--json` (linhas 8 a 10) repassa para
  `default/nucleo/monitoramento.py`, que é código de Monitor: na tarefa
  M3-17 essa opção passa a apontar para o caminho novo e entra na lista de
  exceções de K9 como chamada do Shell ao Monitor.
- `jangada-menu` tem 11 entradas de sistema e 6 de agentes e painel. Fica no
  Shell e chama só comandos públicos.
- `jangada-tarefas` e `jangada-conversa` abrem janelas Qt. Ver decisão D3.
- `jangada-tema` e `jangada-sddm` carregam `install/lib.sh`.
- `jangada-interface-processos` não é comando: é biblioteca sem permissão de
  execução (modo 644), carregada por `source` em `jangada-barra`,
  `jangada-tema` e `testes/interface.sh`. Dos 59 nomes de `bin/`, 58 são
  executáveis; o teste de K1 o marca como `carregado` na lista congelada.
- `jangada-sessao` monta o `PATH` da sessão gráfica (linha 6) e é o `Exec`
  de `/usr/share/wayland-sessions/jangada.desktop`. O caminho
  `bin/jangada-sessao` não pode deixar de existir.

### Monitor (4), destino `monitor/bin/`

| Comando | Observação |
|---|---|
| `jangada-painel` | painel de indicadores e módulo `--waybar` |
| `jangada-consumo` | grava só `~/.cache/jangada/consumo.json` |
| `jangada-subagentes` | misto: a opção `--entrega` é usada pelo Core |
| `jangada-verificar` | misto: área de trabalho (88 a 150, 193 a 197) e agentes (95, 152 a 191) |

### Compartilhados (7), ficam em `bin/`

| Comando | Motivo |
|---|---|
| `jangada` | despachante: resolve `"$dir/jangada-$1"` |
| `jangada-config` | carregado por 46 comandos; mistura funções dos três módulos (ver 1.5) |
| `jangada-gancho` | ganchos do usuário, chamado pelo Core e pelo Shell |
| `jangada-update`, `jangada-migrar`, `jangada-versao`, `jangada-assinar` | ciclo de vida do repositório inteiro |

## 1.2 Arquivos de `default/`

| Origem | Arquivos | Destino | Módulo |
|---|---|---|---|
| `default/agentes/` | 14 | `core/agentes/perfis/` | Core |
| `default/claude/` (subagentes, skills, hooks) | 25 | `core/agentes/claude/` | Core |
| `default/agy/` | 11 | `core/agentes/agy/` | Core |
| `default/tmux/` | 1 | `core/agentes/tmux/` | Core |
| `default/provedores/` | 4 | `core/provedores/` | Core |
| `default/nucleo/` | 6 | `core/nucleo/` | Core; `monitoramento.py` sai depois para o Monitor |
| `default/orquestracao/` | 12 | `core/orquestracao/` | Core |
| `default/delegacao/` | 5 | `core/delegacao/` | Core |
| `default/hypr/` | 9 | `shell/hyprland/` | Shell |
| `default/hypridle/` | 1 | `shell/hyprland/hypridle/` | Shell |
| `default/waybar/` | 3 | `shell/waybar/` | Shell |
| `default/matugen/` | 9 | `shell/temas/matugen/` | Shell |
| `default/sddm/` | 3 | `shell/temas/sddm/` | Shell |
| `default/logo/` | 3 | `shell/temas/logo/` | Shell |
| `default/fastfetch/` | 1 | `shell/temas/fastfetch/` | Shell |
| `default/tarefas/` | 4 | `shell/menus/tarefas/` | Shell (D3) |
| `default/conversa/` | 1 | `shell/menus/conversa/` | Shell (D3) |
| `default/snapper/` | 1 | `shell/integracoes/snapper/` | Shell |
| `default/r/` | 1 | `shell/integracoes/r/` | Shell, a confirmar na tarefa |
| `default/painel/` | 10 | `monitor/painel/` | Monitor |
| `default/visual/` | 3 | fica em `default/visual/` | Compartilhado (painel e Central usam) |

Soma: 78 Core, 36 Shell, 10 Monitor, 3 compartilhados.

`core/nucleo`, `core/orquestracao` e `core/delegacao` ficam como pastas
irmãs. As importações atuais dependem dessa vizinhança
(`default/delegacao/codex.py:19`, `default/nucleo/consultas.py:14`,
`default/orquestracao/cli.py:23`).

## 1.3 A pasta `shell/` que já existe

| Arquivo | Conteúdo | Destino |
|---|---|---|
| `shell/jangada.sh` | exporta `JANGADA_CORE_PATH` e `PATH`, ativa mise, zoxide e fzf; sem funções | fica onde está |
| `shell/jangada-shell.sh` | funções `agente`, `agentes`, `status`, `fim`, `revisar`, `resumir`, `mapa`, `mudancas`, `concluir`, `desistir`, `reverter`, `repassar`, `trocar`, `ajuda` | fica onde está |

Motivos para não mover: o bloco gravado em `~/.bashrc` e `~/.zshrc` aponta
para `shell/jangada.sh` (`install/30-shell.sh:9-12`), e os dois arquivos
descobrem a raiz pelo sufixo do próprio caminho (`shell/jangada.sh:14`,
`shell/jangada-shell.sh:11`). As funções de agente de `jangada-shell.sh`
são a mão do usuário sobre o Core por comandos públicos, então o arquivo é
Shell por inteiro.

## 1.4 O que permanece compartilhado na raiz

| Item | Motivo |
|---|---|
| `bin/` (fachada) | está no `PATH`, em arquivos do usuário e em 517 referências dos testes |
| `install/`, `install.sh` | uma instalação só; `install/lib.sh` é carregado pelas 24 migrações e por dois comandos |
| `migrations/` | `jangada-migrar:16` percorre `$JANGADA_CORE_PATH/migrations/*.sh` |
| `config/` | modelos do usuário; `config/hypr/hyprland.lua:8` carrega `default/hypr/bootstrap.lua` |
| `testes/` | ver 1.6 |
| `docs/`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `README.md`, `CHANGELOG.md`, `LICENSE` | |
| `default/visual/` | usado pelo Monitor e pelo Shell |

As etapas da instalação têm dono para efeito de revisão, sem sair de
`install/`: 20, 30 e 40 são do Shell; 50 é do Core (e chama
`jangada-painel --conferir`); 00, 10 e 90 são compartilhadas. `install/lib.sh`
tem funções de agente nas linhas 173 a 350.

## 1.5 Arquivos mistos e como tratar

| Arquivo | Mistura | Tratamento |
|---|---|---|
| `bin/jangada-config` | configuração e GPU (6 a 159), Core (175 a 303, 444 a 452), git seguro (372 a 393), estado e travas (341, 404, 429, 504, 529), eventos (353), interface (160, 545, 554) | fica inteiro em `bin/` nesta modularização; dividir é tarefa opcional do fim (M3-19) |
| `bin/jangada-agentes` | Core com `hyprctl`, saída para a Waybar e consumo | vai para o Core; contratos K3, K4 e K6 isolam os trechos |
| `bin/jangada-hook-*`, `jangada-isolar` | aviso à Waybar e notificação | contrato K3 |
| `bin/jangada-validar` | chama comando do Monitor | contrato K6 |
| `bin/jangada-subagentes`, `default/painel/subagentes.py` | indicador do Monitor e resumo de entrega do Core | contrato K6 |
| `default/painel/orquestracao.py` | herda `Estado`, classe de escrita do Core (linha 18) | contrato K5 |
| `default/painel/coletor.py` | importa do Core por `sys.path` (52, 56) | contrato K5 |
| `default/nucleo/monitoramento.py` | código de Monitor dentro do núcleo | sai em M3-17 |
| `default/orquestracao/metricas_projeto.py` | usado pelo Core e pelo painel | fica no Core e é lido pelo contrato K5 |
| `bin/jangada-verificar` | diagnóstico dos dois lados | vai para o Monitor e chama só consultas públicas |
| `bin/jangada-update` | repositório inteiro | compartilhado |

## 1.6 Testes

Os testes ficam em `testes/`. A tabela dá o módulo responsável pela revisão.
A tarefa M3-01 conferiu arquivo a arquivo pelo alvo de cada teste (comandos
chamados, pacotes importados e arquivos de `default/` lidos) e corrigiu
quatro classificações:

- `operacional.py` saiu do Shell para o Core: importa `estado`, `projetos`,
  `executor` e `nucleo.*` e chama `default/nucleo/cli.py`.
- `restaurar.sh` saiu de Compartilhado para o Core: testa
  `jangada-agentes --restaurar`.
- `subagentes.sh` saiu do Monitor para o Core: as linhas 1 a 168 testam os
  papéis de subagente, o `jangada-hook-leitor` e a instalação por
  `install/lib.sh`; só as linhas 170 a 270 testam `jangada-subagentes`, que é
  do Monitor.
- `fichas.py` saiu do Shell para Compartilhado: três dos seis casos testam
  `default/visual/fichas.py` e um testa uma migração; os outros dois testam
  `jangada-tema` e o modelo do matugen, do Shell.

Arquivos de apoio, sem teste próprio: `falso-codex-hooks.py` (Codex falso de
`codex.sh`, `isolar.sh` e `restaurar.sh`) e `amostras-subagentes.py`
(registros de exemplo para `painel.sh`, `subagentes.sh` e `validar.sh`).
`tarefas.sh` é misto: confere a Central de Tarefas e também
`jangada-agentes --lista` e `--integracao-json`.

| Módulo | Arquivos |
|---|---|
| Core (28) | `acompanhamento.py`, `agente-seletor.py`, `avaliar-ollama.py`, `baseline.py`, `codex-economico.py`, `codex.sh`, `confianca-p0.py`, `contexto-revisao.py`, `cota-codex.py`, `delegacao.py`, `delegar.sh`, `deterministico.py`, `eventos.sh`, `executor.py`, `extracao.py`, `falso-codex-hooks.py`, `fim.sh`, `hooks.sh`, `isolar.sh`, `metricas-projeto.py`, `operacional.py`, `orquestracao.py`, `provedores.sh`, `restaurar.sh`, `saude.py`, `subagentes.sh`, `supervisao.py`, `validar.sh` |
| Shell (14) | `aninhado.sh`, `barra.sh`, `bluetooth.sh`, `calendario.sh`, `conversa.py`, `importar.sh`, `interface.sh`, `mapear.sh`, `rede.sh`, `reverter.sh`, `simular-hypr.lua`, `snapshot.sh`, `tarefas.py`, `tarefas.sh` |
| Monitor (9) | `amostras-subagentes.py`, `diagnostico.sh`, `metricas.py`, `monitoramento.py`, `painel-local.py`, `painel-motores.R`, `painel-operacional.R`, `painel-orquestracao.py`, `painel.sh` |
| Compartilhado (9) | `capacidades.sh`, `contratos-caminhos.sh`, `contratos-fachada.sh`, `fichas.py`, `regra1.sh`, `update-codigo.py`, `update.sh`, `versao.sh`, `verificar.sh` |

Os 58 arquivos da base mais os dois testes de contrato da M3-01 somam 60.
As listas congeladas dos contratos ficam em `testes/contratos/`
(`comandos.txt` e `caminhos.txt`), e o `verificar.sh` roda todo
`testes/contratos-*` por padrão de nome.

## 1.7 Caminhos gravados fora do repositório

Estes arquivos guardam caminho absoluto e quebram se o destino some:

| Arquivo do usuário ou do sistema | Aponta para | Origem |
|---|---|---|
| `/usr/share/wayland-sessions/jangada.desktop` | `bin/jangada-sessao` | `install/40-interface.sh:35` |
| `~/.bashrc`, `~/.zshrc` | `shell/jangada.sh` | `install/30-shell.sh:9-12` |
| `~/.claude/settings.json`, `~/.gemini/config/hooks.json` | `bin/jangada-hook-*` | `install/lib.sh:281,315` |
| `~/.claude/skills`, `~/.claude/agents` (links) | `default/claude/...` | `install/50-agentes.sh` |
| `~/.config/jangada/hypr/hyprland.lua` | `default/hypr/bootstrap.lua` e `require("default.hypr.*")` | `config/hypr/hyprland.lua:8,11` |
| `~/.config/jangada/waybar/style.css` | `default/waybar/base.css` | modelo `style.css.modelo` |
| `default/fastfetch/config.jsonc:7` | `~/.local/share/jangada/default/logo/jangada.txt` | fixo no arquivo |

Por isso os caminhos antigos seguem existindo como links (contrato K2).

## 1.8 Custo de mover, medido

Ocorrências de `$JANGADA_CORE_PATH/<pasta>` por origem:

| De | `bin` | `default` | `shell` | `install` | `migrations` | `config` |
|---|---|---|---|---|---|---|
| `bin/` | 53 | 53 | 4 | 2 | 1 | 1 |
| `default/` | 23 | 1 | 0 | 0 | 0 | 0 |
| `install/` | 4 | 9 | 2 | 2 | 1 | 4 |
| `migrations/` | 12 | 2 | 0 | 0 | 0 | 0 |
| `shell/` | 14 | 0 | 0 | 0 | 0 | 0 |
| `testes/` | 10 | 0 | 0 | 0 | 0 | 0 |

Nos testes há ainda 517 referências a `bin/` e 196 a `default/` por caminho
relativo. Com os links, nenhuma dessas referências precisa mudar no dia da
mudança de pasta.
