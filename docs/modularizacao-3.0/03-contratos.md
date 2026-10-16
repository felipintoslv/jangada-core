# 5. Contratos entre módulos

Cada contrato tem dono, forma e teste. Os testes entram em `testes/` e na
lista de passos de `testes/verificar.sh`. Nenhum contrato cria serviço
permanente nem funcionalidade nova: todos fixam o que já existe ou trocam
uma chamada direta por uma indireta.

| # | Contrato | Dono | Consumidor | Situação hoje |
|---|---|---|---|---|
| K1 | Fachada de comandos | compartilhado | todos, usuário | existe, sem teste |
| K2 | Caminhos legados | compartilhado | arquivos do usuário | existe, sem teste |
| K3 | Aviso de mudança de estado | compartilhado | Core emite, Shell recebe | Core chama a Waybar direto |
| K4 | Consulta de sessões sem efeito | Core | Shell, Monitor | consultas públicas sem escrita; terminal preserva worktree e repasse explícito |
| K5 | Leitura da fila e dos projetos | Core | Monitor, Shell | Monitor recebe filas, métricas e provedores sem descobrir bancos |
| K6 | Resumo de entrega opcional | Core | `jangada-validar` | chama comando do Monitor |
| K7 | Formato dos registros | Core | Monitor | documentado, sem teste de formato |
| K8 | Módulos da Waybar | Shell | Core, Monitor | existe, sem teste único |
| K9 | Fronteira entre módulos | Revisor | todos | teste ativo; contrato público da Central delimita A5 |
| K10 | Abertura de interface e foco de janela | compartilhado | Core chama, Shell executa | Core chama `jangada-terminal`, `jangada-tarefas` e `hyprctl` direto |

## K1. Fachada de comandos

- Todo nome `jangada-*` hoje presente em `bin/` continua resolvendo em
  `$JANGADA_CORE_PATH/bin/<nome>` e continua executável. São 59 nomes.
- Opções, códigos de saída e saídas `--json` não mudam nesta modularização.
  Em especial: `jangada-validar` sai com 0 (aprovado), 3 (revisar), 4
  (limite) ou 1 (erro), e a primeira linha do parecer é `STATUS: APROVADO`
  ou `STATUS: REVISAR`.
- `jangada-config` continua carregável por
  `source "$(dirname "${BASH_SOURCE[0]}")/jangada-config"` a partir de
  `bin/`, forma usada por 43 comandos, e continua definindo `JANGADA_CORE_PATH`
  como a pasta acima de `bin/` (`bin/jangada-config:6`).
- Teste `testes/contratos-fachada.sh`: lê `testes/contratos/comandos.txt`
  (lista congelada dos 59 nomes), confere existência e permissão de execução
  em `bin/`, e confere que `bin/jangada <nome>` despacha. Nome novo entra na
  lista; nome retirado exige migração.

## K2. Caminhos legados

- Continuam existindo, como arquivo ou link: `shell/jangada.sh`,
  `shell/jangada-shell.sh`, `bin/jangada-sessao`, `bin/jangada-hook-claude`,
  `bin/jangada-hook-agy`, `bin/jangada-hook-codex`, `bin/jangada-hook-leitor`,
  `default/hypr/bootstrap.lua`, os módulos `default/hypr/*.lua` usados em
  `require("default.hypr.*")`, `default/waybar/base.css`,
  `default/waybar/config.jsonc`, `default/logo/jangada.txt`,
  `default/claude/skills`, `default/claude/agents`, `default/agy/agents`,
  `default/agy/hooks.json`, `default/claude/hooks.json`.
- Links são relativos e versionados, para valer na cópia instalada, nas
  worktrees e dentro do isolamento.
- Teste `testes/contratos-caminhos.sh`: lê `testes/contratos/caminhos.txt`,
  confere que cada caminho existe e que nenhum link aponta para fora do
  repositório.

## K3. Aviso de mudança de estado

- Hoje: cinco pontos do Core mandam `pkill -RTMIN+10 -x waybar` e os hooks
  chamam `notify-send`.
- Contrato: o Core chama só `jangada_avisar_interface EVENTO` e
  `jangada_notificar`, funções de `bin/jangada-config`. O corpo delas é o
  único lugar que conhece Waybar e `notify-send`, e falha em silêncio quando
  não há sessão gráfica. Eventos: `estado-sessao`, `fila`, `validacao`.
- Sinais reservados, sem mudança: 8 (atualizações), 9 (indicadores), 10
  (agentes).
- Teste: o teste de fronteira (K9) recusa `pkill`, `waybar`, `notify-send`
  e `hyprctl` em arquivos do Core fora da lista de exceções. Um segundo
  teste roda `jangada_alterar_estado` sem `WAYLAND_DISPLAY` e confere saída 0
  e estado gravado.

## K4. Consulta de sessões sem efeito

- Hoje: `jangada-agentes --lista-atualizada` e `--waybar` chamam
  `limpar_orfaos`, e a Waybar dispara isso a cada 10 s por
  `jangada-tarefas --waybar`.
- Contrato: as consultas `jangada-agentes --lista`, `--lista-atualizada` e `--waybar` não
  gravam nada. A limpeza vira `jangada-agentes --limpar-orfaos`. Para não
  mudar o comportamento percebido, `jangada-tarefas --waybar` (Shell) passa
  a chamar a limpeza antes da consulta. O Monitor usa só a consulta.
- Situação M1.2: `_jangada_sessao_atual` usa
  `jangada-agentes --sessao-worktree-json`, sem trocar worktree por dir nem
  aplicar retenção. `repassar` usa `--contexto-json SESSAO`, que seleciona
  tarefa e parecer na origem pública anterior. As duas exceções do terminal
  foram retiradas de K9. Campos, ambiguidades, limites e provas estão no
  [contrato do recorte](../coordenacao-central/11-consultas-modulos.md).
- Teste: tira um retrato (`sha256sum`) de `~/.local/state/jangada` em pasta
  temporária com uma sessão órfã falsa, roda as três consultas e confere que
  nada mudou; roda `--limpar-orfaos` e confere que a órfã saiu.
- Esta é a única mudança de comportamento do plano. Ver decisão D6.

## K5. Leitura da fila e dos projetos

Situação M1.2: `nucleo.consultas.consultar_filas` concentra a descoberta e
seleção das filas e provedores. O Monitor recebe dados, consumos e métricas,
sem conexão SQL nem conhecimento dos caminhos dos bancos. O contrato e as
provas estão em [11-consultas-modulos.md](../coordenacao-central/11-consultas-modulos.md).
Os itens abaixo registram o plano anterior da modularização.

- Hoje: `default/painel/orquestracao.py:18` declara `class Consulta(Estado)`
  e `coletor.py:52,56` importa pacotes do Core por `sys.path`.
- Contrato: o Monitor lê por `nucleo.consultas` (que já abre o SQLite por
  cópia privada, só leitura) e pelos comandos `jangada-fila --json`,
  `jangada-fila --metricas --json`, `jangada-projeto consultar` e
  `jangada-router status`. O Monitor não importa `estado.Estado` nem outra
  classe que grave.
- O caminho de importação do Core é entregue por uma variável só,
  `JANGADA_CORE_PY`, definida em `jangada-config`, no lugar de
  `Path(__file__).resolve().parent.parent`. Sem isso o painel deixa de achar
  o núcleo no dia em que `default/painel` virar link para `monitor/painel`,
  porque `resolve()` segue o link.
- O caminho do jangada chega por `JANGADA_CORE_PATH` ao app R
  (`default/painel/app.R:9`, hoje `getwd()`) e à Central de Tarefas
  (`default/tarefas/janela.py:25` e `:658`, hoje `resolve()` para importar
  `visual` e localizar o logo). Recursos usam os caminhos legados sob essa
  raiz; importações do Core usam `JANGADA_CORE_PY`.
- Os comandos `bin/jangada-subagentes:13` e `bin/jangada-hook-leitor:15`
  deixam de inferir a raiz por `realpath`; recebem `JANGADA_CORE_PATH`.
  `bin/jangada-codex:101` e `:102` devem registrar o caminho da fachada
  `$JANGADA_CORE_PATH/bin/jangada-hook-codex`, sem resolver o link. O destino
  físico procura `jangada-config` na pasta errada. Esse caso falha em
  silêncio: o hook sai com 0 e descarta a saída, mas não atualiza a sessão.
- A [prova dos links](prova-links.md)
  exige corrigir esses caminhos na Onda A, antes de mover cada arquivo.
  A aceitação cobre importações, recursos do R e da Central e atualização
  real do estado pelo hook do Codex, também com links em cópia temporária.
- Teste: `testes/painel-orquestracao.py` passa a rodar com o banco em modo
  somente leitura (arquivo `0400`, pasta `0500`); o teste de fronteira
  recusa `from estado import Estado` em `monitor/`.

### Caminho único do estado das sessões (acréscimo da D8, M3-10c)

- Hoje: o Shell monta o caminho da pasta de sessões em quatro pontos:
  `bin/jangada-tarefas:12` (`$JANGADA_ESTADO/agentes`) e o padrão
  `XDG_STATE_HOME` ou `~/.local/state`, mais `jangada/agentes`, em
  `default/tarefas/central.py:121`, `dados.py:129` e `janela.py:259`.
- Contrato: `bin/jangada-config` exporta a pasta de sessões numa variável,
  na forma de `JANGADA_CORE_PY`; o nome é fixado na M3-10c. Hoje ele já
  exporta `JANGADA_ESTADO` (`bin/jangada-config:8` e `:96`), a pasta acima
  de `agentes/`. `jangada-tarefas` repassa a variável e os arquivos Python
  deixam de montar o caminho.
- Ponto a conferir: `jangada-tarefas --simular` chama `central.py` sem
  `--estado`, e `central.py:121` calcula o caminho também nesse modo, para
  o nome do soquete. Se o modo simulado precisar do padrão, fica no máximo
  uma exceção, registrada com o motivo.
- Ponto a conferir: `dados.py:132` e `janela.py:683` derivam
  `XDG_STATE_HOME` da pasta de sessões (`estado.parent.parent`) para chamar
  `jangada-agentes`. A tarefa mantém essa passagem ou a troca pela variável
  nova, sem mudar o comportamento.
- Limite conhecido, a decidir na M3-10c: `default/tarefas/dados.py`, na
  função `registro(pasta, nome)` (linha 79), lê o `.json` da sessão para
  `raiz`, `desde`, `tarefa`, `agente` e `mensagem`. O teste de fronteira
  não aponta porque o caminho chega por parâmetro. A M3-10c decide entre
  exceção permanente e campos a mais na consulta K4; este plano não decide.
- Teste: o teste de fronteira (K9) deixa de ter as quatro exceções; um caso
  em `testes/tarefas.py` ou `testes/tarefas.sh` confere que a Central usa a
  pasta da variável.

## K6. Resumo de entrega opcional

- Hoje: `jangada-validar:159` chama `jangada-subagentes --entrega`, que mora
  em `default/painel/subagentes.py`.
- Contrato: a função que monta o resumo de entrega é do Core e passa para
  `core/delegacao/`. `jangada-subagentes --entrega` continua existindo e
  chama essa função. O indicador de subagentes (texto e `--json`) fica no
  Monitor. `jangada-validar` segue tolerando a falta do resumo, como já faz
  com tempo esgotado e erro.
- O mesmo vale para `jangada-agentes:635`: o consumo é opcional e a lista
  sai sem ele quando `jangada-consumo` não existe.
- Teste: `testes/validar.sh` ganha um caso com `jangada-subagentes` e
  `jangada-consumo` ausentes do `PATH` e confere o mesmo parecer.

## K7. Formato dos registros

- Os formatos já estão em `docs/registros.md`: `validar.jsonl` (seção 1),
  pareceres em `agentes/` (2), `SESSAO.json` (4), `eventos-agentes.jsonl`
  (8), `delegacoes.jsonl` (9).
- Contrato: essas cinco seções são a interface de dados entre Core e
  Monitor. Campo novo pode entrar; campo existente não muda de nome nem de
  tipo sem migração e sem atualizar o documento no mesmo commit.
- Teste `testes/contratos-registros.py`: gera um registro de cada tipo com
  os comandos reais em pasta temporária e confere campos obrigatórios e
  tipos contra uma tabela em `testes/contratos/registros.json`.

## K8. Módulos da Waybar

- `jangada-tarefas --waybar`, `jangada-painel --waybar` e
  `jangada-atualizacoes --waybar` emitem uma linha JSON com `text`,
  `tooltip` e `class`. Texto vazio esconde o módulo.
- Teste: já coberto em parte por `testes/barra.sh`; passa a conferir os três
  comandos pela mesma função.

## K9. Fronteira entre módulos

- Teste `testes/fronteiras.sh`, com lista de exceções em
  `testes/contratos/fronteiras-excecoes.txt` (um caminho e linha por
  exceção, com o contrato que a retira).
- Regras conferidas:
  1. Arquivo do Core não cita `shell/`, `monitor/`, `default/painel`,
     `default/tarefas`, `default/hypr`, `default/waybar`, nem os comandos
     do Shell e do Monitor, nem `hyprctl`, `waybar`, `notify-send`.
  2. Arquivo do Monitor não chama comando que altera estado
     (`jangada-task`, `jangada-executar`, `jangada-agente`,
     `jangada-agente-fim`, `jangada-provedor`, `jangada-fila --importar`) e
     não importa classe de escrita.
  3. Arquivo do Shell não lê arquivo de estado direto; usa comando ou
     `nucleo.consultas`.
- A observação da Central (A5) usa `jangada-agentes --observacao-json`:
  o Core seleciona os caminhos e o Shell os trata como referências para o
  `QFileSystemWatcher`. A resposta não é fluxo de eventos; a Central conserva
  a consulta periódica como reserva. O contrato, limites e falhas estão em
  [09-observacao-publica.md](../coordenacao-central/09-observacao-publica.md).
- A lista de exceções começa com os acoplamentos do inventário e só pode
  diminuir. Linha nova na lista falha o teste.
- Antes da mudança de pasta o teste usa a lista de arquivos por módulo do
  inventário; depois, usa as pastas.

## K10. Abertura de interface e foco de janela

Decidido pelo usuário em 10/10/2026 (D8, grupos A e B).

- Hoje: o Core abre terminal ou a Central e fala com o Hyprland direto, em
  dez pontos:
  - `bin/jangada-agente:118`: `exec jangada-tarefas --nova`;
  - `bin/jangada-agente:134` e `:534`: `exec jangada-terminal`;
  - `bin/jangada-agentes:423` e `:426` (função `focar`): `jangada-terminal`
    em segundo plano, por `setsid -f` ou por `&`;
  - `bin/jangada-agentes:716`: `exec jangada-tarefas`;
  - `bin/jangada-agentes:390` e `:461`: título da janela ativa por
    `hyprctl activewindow`;
  - `bin/jangada-agentes:417`: endereço da janela cujo título é a sessão,
    ou começa por ela, por `hyprctl clients`;
  - `bin/jangada-agentes:420`: foco por `hyprctl dispatch`.
- Contrato: o Core chama só funções de `bin/jangada-config`, na forma do
  K3. O corpo delas é o único lugar que conhece `jangada-terminal`,
  `jangada-tarefas` e `hyprctl`. Funções, com nomes propostos que a M3-10b
  pode ajustar e o teste fixa:
  - `jangada_abrir_terminal`: abre o terminal do jangada com classe e
    comando; com variante que substitui o processo (`exec`) e variante que
    solta o terminal, para manter cada chamada como é hoje;
  - `jangada_abrir_central`: abre a Central, com ou sem `--nova`;
  - `jangada_janela_ativa`: imprime o título da janela ativa, ou nada;
  - `jangada_focar_janela`: procura a janela pelo título da sessão e a foca;
    devolve 1 se não achar, para o chamador abrir o terminal.
- Sem sessão gráfica, as funções avisam em vez de falhar. Com sessão
  gráfica, o comportamento é o de hoje.
- `jangada_focar_classe` (`bin/jangada-config:575`) já segue essa forma:
  é função do arquivo compartilhado que chama `hyprctl`.
- Teste: o teste de fronteira (K9) deixa de ter as dez exceções; um teste
  das funções roda sem `WAYLAND_DISPLAY` e sem
  `HYPRLAND_INSTANCE_SIGNATURE` e confere aviso e saída 0, e com um
  `hyprctl` e um `jangada-terminal` falsos no `PATH` confere os argumentos
  recebidos.

## Exceções permanentes de K9

Decididas pelo usuário em 10/10/2026 (D8). Ficam na lista de exceções com
uma marca própria e o motivo no lugar de `sem-contrato`; a troca é da
M3-10c. São no máximo seis. As duas exceções do terminal foram superadas pelas
consultas públicas do recorte M1.2, sem ampliar o teto de K9.

| Arquivo e trecho | Fronteira | Motivo |
|---|---|---|
| `bin/jangada-agente:365`, `jangada-snapshot --agente` com `--snapshot` | Core chama comando do Shell | chamada opcional e tolerante à ausência, na forma do K6; caso de teste mostra que a sessão abre sem o comando |
| `bin/jangada-verificar:76`, `exec jangada-agente` com `--agente` | Monitor chama comando que altera estado | ação pedida pelo usuário por opção explícita; passa pela fachada K1 |
| `default/tarefas/central.py:121`, caminho padrão do modo `--simular`, se a M3-10c mostrar que é preciso | Shell monta caminho do estado | modo simulado sem `--estado`; ver o caminho único em K5 |

`default/tarefas/dados.py`, em `registro(pasta, nome)`, não está na lista
porque o teste não o aponta; o destino fica para a M3-10c (ver K5).

## Compatibilidade com os comandos `jangada-*`

Nenhum comando muda de nome, de opção ou de código de saída. A única opção
nova é `jangada-agentes --limpar-orfaos` (K4). As funções de K10 e a
variável da pasta de sessões (K5) são internas de `jangada-config`. As variáveis `JANGADA_CORE_PATH`,
`JANGADA_REPO`, `JANGADA_CONFIG` e `JANGADA_PROJETOS` mantêm o sentido.
