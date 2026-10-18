# Validação final da modularização 3.0 (M3-20)

Conferência feita em 10/10/2026 sobre o `main` em `390a63b`, na worktree
`agente/m3-20-final`. A etiqueta de partida é `jangada-pre-modularizacao-3.0`
(`ad30fdd`); entre ela e `390a63b` há 69 commits.

A conferência original rodou dentro da sessão isolada do agente
(`JANGADA_ISOLADO=1`). Nesse ambiente uma parte da suíte falha por bloqueio
do próprio isolamento, com a mensagem `AUTORIZACAO_RECUSADA`. Nesta
complementação (M3-20b), foram registrados os resultados fornecidos pelo
coordenador em 10/10/2026, fora do isolamento, no commit `dbc168a` da M3-20.
O autor desta complementação não reproduziu essas execuções. Os resultados
estão nas seções 4 e 5.

Esta tarefa só alterou documentação. Nenhum código, teste ou arquivo de
contrato foi alterado, e nenhum link de compatibilidade foi removido.

## 1. Resultado

Critérios da especificação, na ordem da tabela de
[05-migracao-testes-reversao.md](05-migracao-testes-reversao.md#critérios-de-aceitação-da-especificação):

| # | Critério | Resultado | Prova |
|---|---|---|---|
| 1 | Três pastas reais no monorepositório | atendido | seção 2.1 |
| 2 | Core independente do Shell e do Monitor | não atendido: o teste de fronteira passa, mas o teste de remoção mostrou que o `jangada-validar` depende de um arquivo do Shell | seções 2.2, 3 e 4 |
| 3 | Monitor por contratos definidos | atendido com ressalva | seção 2.3 |
| 4 | Comandos `jangada-*` preservados | atendido | seção 2.4 |
| 5 | `shell/` existente não sobrescrito | atendido | seção 2.5 |
| 6 | Sistema atual operacional durante o processo | atendido | seção 2.6 |
| 7 | Nenhum agente aprova a própria alteração | atendido com ressalva | seção 2.7 |
| 8 | Integração supervisionada | atendido | seção 2.8 |

Aceitação da própria M3-20, conforme o [backlog](04-backlog.md#m3-20-validação-final-e-documentação):

| # | Item | Resultado | Prova |
|---|---|---|---|
| 9 | Lista de exceções de K9 vazia ou com justificativa | atendido com ressalva: 8 linhas, todas justificadas; a aprovação das justificativas é do usuário | seção 3 |
| 10 | Teste de remoção | feito, com resultado negativo: sem `shell/` e `monitor/`, 4 testes do Core falham a mais, e um deles mostra dependência do Core no Shell | seção 4 |
| 11 | Nenhum documento alterado cita caminho que não existe | atendido com ressalva | seção 6 |
| 12 | `testes/verificar.sh` com saída 0 fora do isolamento | atendido, conforme resultado fornecido pelo coordenador no commit `dbc168a` | seção 5.2 |
| 13 | Trabalho `sandbox-e2e` com saída 0 | atendido pelo equivalente local, conforme resultado fornecido pelo coordenador no commit `dbc168a` | seção 5.2 |

Um critério não foi atendido: a independência do Core (critério 2). As
ressalvas estão descritas em cada seção, e os defeitos achados no caminho
estão na seção 7. Os critérios 12 e 13 foram confirmados pelos resultados
externos fornecidos pelo coordenador; o teste de remoção externo confirmou
as falhas da seção 4.

## 2. Provas por critério

### 2.1 Três pastas reais

```
$ for d in core shell monitor; do echo "$d: $(git ls-files $d | wc -l) arquivos, $(stat -c %F $d)"; done
core: 103 arquivos, diretório
shell: 64 arquivos, diretório
monitor: 16 arquivos, diretório
$ git ls-files -s | grep -c ^120000
73
```

Os 73 links versionados são: 52 em `bin/` (23 para `core/bin`, 25 para
`shell/bin`, 4 para `monitor/bin`), 20 em `default/` e
`core/nucleo/monitoramento.py`, que aponta para
`monitor/painel/monitoramento.py`. Todos são relativos e todos resolvem
(conferido com `readlink` e `test -e` em cada um). Em `bin/` ficaram como
arquivos reais os 7 compartilhados (`jangada`, `jangada-assinar`,
`jangada-config`, `jangada-gancho`, `jangada-migrar`, `jangada-update`,
`jangada-versao`); em `default/`, só a pasta `default/visual`.

As contagens batem com o [inventário](01-inventario.md): 23, 25 e 4 comandos
por módulo e 7 compartilhados.

### 2.2 Core independente do Shell e do Monitor

O critério pede o teste de fronteira (K9) sem exceção `sem-contrato`, só com
as exceções permanentes da D8, e o teste de remoção.

```
$ bash testes/fronteiras.sh | tail -1
tudo certo
$ grep -c sem-contrato testes/contratos/fronteiras-excecoes.txt
0
$ grep -vc -e '^#' -e '^$' testes/contratos/fronteiras-excecoes.txt
8
```

O teste de fronteira passa. O critério não é atendido por causa do teste de
remoção (item 3 abaixo).

1. A lista não tem só as exceções permanentes. Além das 6 permanentes, há 2
   linhas do contrato K6: chamadas opcionais do Core a comandos do Monitor.
   A justificativa de cada uma está na seção 3.
2. `core/nucleo/monitoramento.py` é um link do Core para um arquivo do
   Monitor. Ele existe por decisão da M3-17 (repasse no nome antigo), e o
   teste de fronteira o conta como Core. Sem `monitor/`, o link fica
   quebrado. O efeito disso no teste de remoção está na seção 4.
3. O teste de remoção (seção 4) achou uma dependência que o teste de
   fronteira não vê: o `jangada-validar`, do Core, lê a configuração do
   lintr em `default/r/lintr`, que mora em `shell/`.

### 2.3 Monitor por contratos definidos

Contratos K5 (leitura da fila e dos projetos) e K7 (formato dos registros).

```
$ grep -rn 'import Estado\|from estado' monitor/
(sem resultado)
$ grep -n JANGADA_CORE_PY bin/jangada-config | head -1
14:JANGADA_CORE_PY="$JANGADA_CORE_PATH/core"
```

O Monitor não importa a classe de escrita do Core, e o caminho do núcleo
chega pela variável `JANGADA_CORE_PY`. O teste de fronteira recusa a
importação (caso "Monitor que chama comando que altera estado é apontado" e
a regra 2 de K9).

O `testes/contratos-registros.py` (K7) passou dentro do isolamento, na base
e nesta entrega. Ressalva: o `testes/painel-orquestracao.py` (K5) falha
dentro do isolamento, na base e nesta entrega, por `AUTORIZACAO_RECUSADA`, e
a execução do coordenador confirmou a suíte fora do isolamento (seção 5). O
`testes/contratos-registros.py` é também intermitente quando roda junto de
outras suítes (seção 8, item 5).

### 2.4 Comandos `jangada-*` preservados

```
$ grep -vc -e '^#' -e '^$' testes/contratos/comandos.txt
59
$ bash testes/contratos-fachada.sh | tail -1
tudo certo
$ bash testes/contratos-caminhos.sh | tail -1
tudo certo
```

Os 59 nomes da lista congelada existem em `bin/`, com permissão de execução
(58; `jangada-interface-processos` é biblioteca carregada), e o despachante
`bin/jangada` alcança cada um. Os caminhos legados de K2 existem e nenhum
link aponta para fora do repositório.

Um comando só funciona pela fachada:

```
$ env -u JANGADA_CORE_PATH bin/jangada-barra --posicao
topo
$ env -u JANGADA_CORE_PATH shell/bin/jangada-barra --posicao
shell/bin/jangada-barra: linha 14: shell/bin/jangada-config: Arquivo ou diretório inexistente
```

Isso é o comportamento previsto na [prova dos links](prova-links.md), item
1, e está escrito no `core/LEIAME.md` e na skill.

### 2.5 `shell/` existente não sobrescrito

```
$ for f in shell/jangada.sh shell/jangada-shell.sh; do
    echo "$f agora $(sha256sum <$f | cut -c1-16) etiqueta $(git show jangada-pre-modularizacao-3.0:$f | sha256sum | cut -c1-16)"
  done
shell/jangada.sh agora 8c322217ba20aef5 etiqueta 8c322217ba20aef5
shell/jangada-shell.sh agora 2f57b59c143dbc3a etiqueta 2f57b59c143dbc3a
$ git log --oneline jangada-pre-modularizacao-3.0..HEAD -- shell/jangada.sh shell/jangada-shell.sh
(sem resultado)
```

Os dois arquivos são iguais, byte a byte, aos da etiqueta de partida, e
nenhum commit da modularização os tocou.

### 2.6 Sistema atual operacional durante o processo

```
$ git -C ~/.local/share/jangada log -1 --format='%h %ad' --date=short
db0ee93 2026-10-09
$ git merge-base --is-ancestor db0ee93 jangada-pre-modularizacao-3.0 && echo anterior
anterior
```

A cópia instalada, lida de dentro da sessão isolada, está em `db0ee93`, o
mesmo commit registrado na linha de base do [README](README.md) e anterior à
etiqueta de partida. Ela não recebeu nenhum commit da modularização: o
jangada em uso continuou na versão anterior durante todo o processo. A
atualização segue sendo decisão do usuário, por `jangada-update`.

Esta tarefa não escreveu na cópia instalada, em `~/.config/hypr` nem no
banco de estado real.

### 2.7 Nenhum agente aprova a própria alteração

As entregas passaram pelo `jangada-validar`, que manda o diff a um revisor
de outro modelo e grava em cada rodada se o revisor é independente do autor
(campo `independente` de `validar.jsonl`). Esta conferência não releu o
registro de cada rodada, que fica no banco de estado real, fora do alcance
desta tarefa.

Ressalva: duas tarefas foram integradas por decisão do usuário sem parecer
`STATUS: APROVADO`.

- M3-03: o `jangada-validar` chegou ao limite de três rodadas com `REVISAR`.
  O registro está no [backlog](04-backlog.md#m3-03-teste-de-fronteira).
- M3-14: integrada com o parecer da rodada 3 em `REVISAR`. Os dois itens
  abertos eram a autorização do ajuste em `testes/contratos-caminhos.sh` em
  commit separado e a forma das linhas de `testes/contratos/modulos.txt`.

Nos dois casos quem decidiu foi o usuário, não o autor. A prova deste
critério é o histórico das sessões e o registro do backlog; não há comando
que a reproduza a partir do repositório.

### 2.8 Integração supervisionada

Cada tarefa entrou no `main` por decisão do usuário, uma por vez. O
histórico entre a etiqueta e `390a63b` é linear:

```
$ git rev-list --count jangada-pre-modularizacao-3.0..390a63b
69
$ git rev-list --count --merges jangada-pre-modularizacao-3.0..390a63b
0
```

Esta tarefa não integra nem envia ao remoto.

## 3. Exceções de K9, linha a linha

`testes/contratos/fronteiras-excecoes.txt` tem 8 linhas de exceção. Esta
tarefa não editou o arquivo. O teste fixa um teto por contrato
(`testes/fronteiras.sh:50`: K6 com 2, `permanente` com 6, `sem-contrato` com
0), e linha nova acima do teto reprova.

| # | Marca | Onde está hoje | O que cruza a fronteira | Justificativa |
|---|---|---|---|---|
| 1 | K6 | `core/bin/jangada-agentes:620` | o Core chama `jangada-consumo --curto`, do Monitor | chamada opcional: termina em `\|\| true`, e a lista de sessões sai sem o consumo quando o comando falta (contrato K6) |
| 2 | K6 | `core/bin/jangada-validar:159` | o Core chama `jangada-subagentes --entrega`, do Monitor | resumo de entrega opcional: o `jangada-validar` tolera a falta, o tempo esgotado e o erro; o caso 17d de `testes/validar.sh` roda sem os comandos do Monitor e confere o mesmo parecer |
| 3 | permanente | `core/bin/jangada-agente:365` | o Core chama `jangada-snapshot --agente`, do Shell, com `--snapshot` | chamada opcional, pedida por opção, que termina em `\|\| true`; o caso 7 de `testes/snapshot.sh` mostra que a sessão abre sem o comando (D8) |
| 4 | permanente | `monitor/bin/jangada-verificar:76` | o Monitor chama `jangada-agente`, que altera estado | só com a opção `--agente`, pedida pelo usuário; passa pela fachada K1 (D8) |
| 5 | permanente | `shell/jangada-shell.sh:132`, `_jangada_sessao_atual` | o Shell lê arquivo de estado | compara o campo `worktree` de cada sessão com a raiz do repositório; a consulta K4 devolve outro campo e só sessões vivas ou guardadas, e com ela uma sessão `--direto` passaria a ser achada na raiz do projeto e uma encerrada fora do prazo deixaria de ser. Decisão do usuário na M3-10c |
| 6 | permanente | `shell/jangada-shell.sh:271`, `repassar` | o Shell lê arquivo de estado | lê o último parecer e a tarefa; não há consulta do Core que devolva o parecer, e criá-la seria funcionalidade nova (D8). Dívida para depois da 3.0 |
| 7 | permanente | `shell/menus/tarefas/janela.py:694`, `observar_estado` | o Shell monta caminho do estado | só vigia mudança de arquivo, sem ler o conteúdo (D8) |
| 8 | permanente | `shell/menus/tarefas/janela.py:700`, `observar_estado` | o Shell monta caminho do estado | só vigia mudança de arquivo, sem ler o conteúdo (D8) |

Observações sobre a lista:

- As linhas 5 a 8 ocupam 4 das 6 vagas de `permanente` previstas na D8 junto
  com as linhas 3 e 4. A sexta exceção prevista em
  [03-contratos.md](03-contratos.md#exceções-permanentes-de-k9) era a de
  `central.py` no modo `--simular`; ela não foi necessária. No lugar dela
  entrou a de `_jangada_sessao_atual` (linha 5), que a D8 previa retirar pela
  consulta K4 e que ficou por decisão do usuário na M3-10c.
- O arquivo escreve os caminhos antigos (`bin/jangada-agentes`,
  `default/tarefas/janela.py`), que hoje são links. A tabela mostra onde o
  arquivo mora. O teste segue o link e por isso passa.
- O comentário da linha 1 no arquivo ainda cita `bin/jangada-agentes:635`.
  O trecho está hoje na linha 620 de `core/bin/jangada-agentes`. O teste
  compara o trecho, não o número.
- O arquivo registra, fora da contagem, a leitura do `.json` da sessão por
  `default/tarefas/dados.py` em `registro(pasta, nome)`. O teste não a
  aponta porque o caminho chega por parâmetro. É exceção por decisão do
  usuário na M3-10c.
- O teste de fronteira não confere chamada do Shell ao Monitor.
  `shell/bin/jangada-monitor:9`, com `--json`, roda
  `default/nucleo/monitoramento.py`, que é código do Monitor alcançado por um
  caminho do Core. O inventário (1.1) previa registrar isso como exceção; não
  há linha para o caso.

As linhas 1 e 2 não são "exceções permanentes da D8": são o próprio contrato
K6, que permite a chamada opcional. Fica para o usuário decidir se elas
seguem na lista com a marca K6 ou se passam a `permanente`.

## 4. Teste de remoção

Feito em duas cópias do repositório em `390a63b`, numa pasta temporária: uma
intacta e outra sem `shell/`, sem `monitor/` e sem os 42 links que apontam
para eles (29 em `bin/`, 12 em `default/` e `core/nucleo/monitoramento.py`).
Nas duas rodaram os 27 testes do Core do inventário (seção 1.5;
`falso-codex-hooks.py` é apoio, não teste).

```
git clone -q "$W" intacta; git clone -q "$W" semmod
cd semmod
find . -path ./.git -prune -o -type l -print | while read -r l; do
  case "$(readlink "$l")" in ../shell/*|../monitor/*|../../monitor/*) rm "$l";; esac
done
rm -rf shell monitor
# em cada cópia, para cada teste t do Core:
env -u JANGADA_ISOLADO -u JANGADA_DELEGAR -u JANGADA_PAPEL -u JANGADA_PAPEL_AJUSTE -u JANGADA_VALIDAR_REVISOR \
  JANGADA_CORE_PATH="$PWD" timeout 900 python3 testes/$t </dev/null   # ou bash, para .sh
```

**Resultado: o Core não roda inteiro sem os outros módulos. Uma dependência
do Core no Shell não é vista pelo teste de fronteira.**

Dentro do isolamento, 20 dos 27 testes já falham na cópia intacta por
`AUTORIZACAO_RECUSADA`. A comparação foi feita caso a caso: a mesma lista de
casos falhos nas duas cópias quer dizer que a remoção não mudou nada que o
isolamento deixa ver.

| Teste | Intacta | Sem `shell/` e `monitor/` | Causa da diferença |
|---|---|---|---|
| 23 testes | mesmos casos falhos | mesmos casos falhos | nenhuma diferença |
| `hooks.sh` | passa | 6 falhas | os 6 casos conferem a saída do `jangada-verificar`, que é do Monitor |
| `subagentes.sh` | passa | 23 falhas | todos os casos de `jangada-subagentes` (registros, entrega, indicadores, memo), que é do Monitor; o inventário já dizia que essa parte do teste é do Monitor |
| `delegar.sh` | 42 falhas | 43 falhas | o caso "painel: falha total..." carrega `default/painel/metricas.py`, do Monitor |
| `validar.sh` | 36 falhas | 60 falhas | ver abaixo |

As 24 falhas a mais do `validar.sh`:

- 20 casos: 13 do grupo 12 (lintr) e, em cadeia, 6 do caso 17 e 1 do caso
  22. A causa é `core/bin/jangada-validar:803`: sem `.lintr` no projeto, a
  verificação local usa `$JANGADA_CORE_PATH/default/r/lintr`. `default/r` é link
  para `shell/integracoes/r`, do Shell. Sem ele, a cópia do arquivo falha
  (`cp: não foi possível obter estado de '.../default/r/lintr'`), as rodadas
  do caso 12 terminam diferente e o contador de rodadas chega deslocado ao
  caso 17 (a sequência começa na rodada 2 e termina em "limite").
- Prova da causa: com só `shell/integracoes/r` e o link `default/r`
  devolvidos à cópia sem módulos, o `validar.sh` cai de 60 para 40 falhas,
  e a única diferença para a cópia intacta são os 4 casos abaixo.
- 4 casos (17b e 17d) conferem o resumo de subagentes gravado com o
  `jangada-subagentes` presente. Sem o Monitor, o `jangada-validar` grava a
  linha com `"subagentes_erro": "jangada-subagentes saiu com código 127"` e
  segue, que é o comportamento do contrato K6. Os 9 casos do 17d que
  conferem a falta do `jangada-subagentes` e do `jangada-consumo` passam.

Leitura do resultado:

1. As falhas de `hooks.sh`, `subagentes.sh` e `delegar.sh` são de casos que
   testam código do Monitor de dentro de um teste classificado como Core. O
   Core em si segue funcionando; o que falta é o código testado.
2. A dependência de `default/r/lintr` é real: o `jangada-validar`, do Core,
   lê um arquivo de configuração que mora no Shell. O teste de fronteira só
   procura chamada de comando, import e caminho do estado, e não vê leitura
   de arquivo de configuração de outro módulo. Fica registrado como defeito
   na seção 7, item 2.
3. O isolamento esconde o efeito da remoção nos 20 testes que falham nas
   duas cópias. A confirmação externa abaixo permite comparar os 27 testes
   sem essas falhas do ambiente.

### Confirmação externa pelo coordenador

Em 10/10/2026, o coordenador refez a comparação fora do isolamento, com dois
clones do ramo no commit `dbc168a`: um intacto e outro sem `shell/`,
`monitor/` e os links que apontam para esses módulos. Rodou os mesmos 27
testes do Core do inventário citados nesta seção. O autor desta
complementação não reproduziu essa execução; registrou o resultado
fornecido pelo coordenador.

| Cópia | Testes com código 0 | Testes com código 1 |
|---|---|---|
| Intacta | 27 | nenhum |
| Sem `shell/` e `monitor/` | 23 | `delegar.sh`, `hooks.sh`, `subagentes.sh`, `validar.sh` |

Fora do isolamento, a cópia intacta não tem falhas, ao contrário das
contagens da execução isolada acima. Os quatro testes que falham após a
remoção são os mesmos já apontados nesta seção. O critério 2 continua não
atendido.

## 5. `testes/verificar.sh` e `sandbox-e2e`

### 5.1 Dentro do isolamento

Na M3-20 original, a suíte rodou duas vezes, num clone de `390a63b` (base) e
num clone do ramo `agente/m3-20-final` (entrega), uma depois da outra e sem
outras suítes em paralelo:

```
env -u JANGADA_ISOLADO -u JANGADA_DELEGAR -u JANGADA_PAPEL -u JANGADA_PAPEL_AJUSTE -u JANGADA_VALIDAR_REVISOR \
  JANGADA_CORE_PATH="$PWD" bash testes/verificar.sh </dev/null >verificar-<base|entrega>.log 2>&1
$ diff <(grep '^XX' verificar-base.log | sort) <(grep '^XX' verificar-entrega.log | sort) && echo diferença-vazia
diferença-vazia
```

As duas saíram com código 1 e "21 falha(s)". Os 21 grupos falhos são os
mesmos: `testes/acompanhamento.py`, `agente-seletor.py`, `baseline.py`,
`codex-economico.py`, `codex.sh`, `contexto-revisao.py`, `cota-codex.py`,
`delegar.sh`, `deterministico.py`, `executor.py`, `fim.sh`, `isolar.sh`,
`metricas-projeto.py`, `operacional.py`, `orquestracao.py`,
`painel-orquestracao.py`, `restaurar.sh`, `saude.py`, `supervisao.py`,
`update-codigo.py` e `validar.sh`. As falhas são do isolamento: o log da base
tem 315 linhas com `AUTORIZACAO_RECUSADA`. Como esta entrega só muda
documentação, a lista igual é o resultado esperado.

### 5.2 Fora do isolamento, pelo coordenador

O coordenador forneceu os resultados das execuções feitas em 10/10/2026,
fora do isolamento, no commit `dbc168a`. O autor desta complementação não
reproduziu essas execuções. Elas confirmam os critérios 12 e 13; não
eliminam o defeito de independência do Core registrado na seção 4.

Comando da suíte completa, executado no worktree da M3-20:

```sh
env -u JANGADA_ISOLADO -u JANGADA_DELEGAR -u JANGADA_PAPEL -u JANGADA_PAPEL_AJUSTE JANGADA_CORE_PATH=$PWD bash testes/verificar.sh </dev/null
```

Resultado informado pelo coordenador: código de término 0, nenhuma linha
começando com `XX`, 2127 linhas "ok" e última linha "tudo certo".

Comando do equivalente local do trabalho de CI `sandbox-e2e`:

```sh
JANGADA_TESTES_EXIGIR_ISOLAMENTO=1 JANGADA_TESTES_EXIGIR="bwrap sem-rede jq gitleaks zsh R lintr" sh -ec 'testes/capacidades.sh; testes/isolar.sh; testes/validar.sh; testes/fim.sh'
```

Resultado informado pelo coordenador: código de término 0 e última linha
"tudo certo". Esse resultado é do equivalente local, não de uma execução
do trabalho no serviço de CI.

O coordenador também refez o teste de remoção fora do isolamento no mesmo
commit. Na cópia intacta os 27 testes do Core saíram com 0; sem os módulos,
23 saíram com 0 e os mesmos 4 testes da seção 4 saíram com 1.

## 6. Documentos alterados e conferência de caminhos

Arquivos alterados na M3-20 original, e o que mudou em cada um. A
complementação M3-20b alterou somente este documento.

| Arquivo | Mudança |
|---|---|
| `README.md` | árvore da seção Estrutura com `core/`, `shell/` e `monitor/`; parágrafo sobre os links de compatibilidade; linha para esta pasta na tabela de documentos; nota sobre o aviso do `jangada-update` |
| `AGENTS.md` | só a tabela de exceções: a coluna "Quem grava" cita onde cada arquivo mora |
| `docs/atualizacao-e-migracoes.md`, `docs/boas-praticas.md`, `docs/ciclo-da-tarefa.md`, `docs/codex.md`, `docs/isolamento.md`, `docs/painel.md`, `docs/provedores.md`, `docs/registros.md`, `docs/subagentes-e-delegacao.md` | um parágrafo em cada, com a pasta real do que o documento cita e a informação de que o caminho antigo é link |
| `docs/modularizacao-3.0/README.md` | situação em 10/10/2026 e duas linhas na tabela de documentos |
| `core/agentes/claude/skills/jangada/SKILL.md` | tabela "onde mora" por módulo, cuidados com os links e regra 1 ajustada |
| `core/agentes/claude/skills/jangada/agentes.md`, `hyprland.md`, `interface.md` | nota no topo; em `agentes.md`, o link corrigido (seção 7, item 4) |
| `docs/modularizacao-3.0/06-validacao-final.md` | este documento |

Os caminhos antigos que esses documentos citam (`bin/jangada-*`,
`default/...`) foram mantidos: continuam válidos e são a forma de uso. Os
demais documentos de `docs/` não citam local de arquivo que tenha mudado de
sentido, ou são registros datados (seção 8, item 17).

A conferência de caminhos usou este programa, rodado na raiz do repositório.
Ele lê o texto entre crases e o destino dos links Markdown, separa o que
começa por uma pasta da raiz e testa se existe. Tira o `:linha` do fim e não
confere nome com curinga ou de modelo (`NOME`, `PAPEL`, `SESSAO`).

```python
import re, sys, pathlib
RAIZ = r'(?:bin|core|shell|monitor|default|install|migrations|config|testes|docs|revisao|estudos|benchmarking)'
faltas = 0
for arq in sys.argv[1:]:
    doc = pathlib.Path(arq); texto = doc.read_text()
    achados = set()
    for m in re.finditer(r'`([^`\n]+)`', texto):
        for tok in m.group(1).split():
            tok = re.sub(r'^(\$JANGADA_CORE_PATH/|\$PWD/|\./)', '', tok.strip('"\'(),;'))
            if re.match(RAIZ + r'/', tok):
                achados.add((tok, pathlib.Path('.')))
    for m in re.finditer(r'\]\(([^)#\s]+)(?:#[^)]*)?\)', texto):
        alvo = m.group(1)
        if not re.match(r'[a-z]+://', alvo):
            achados.add((alvo, doc.parent))
    for tok, base in sorted(achados, key=lambda x: x[0]):
        limpo = re.sub(r'(:[0-9][0-9,\- a-z]*)$', '', tok).rstrip('.,:;')
        if re.search(r'[*<>$@{}\[\]]|\.\.\.|NOME|PAPEL|SESSAO|AAAA|NN', limpo):
            continue
        if not (base / limpo).exists():
            faltas += 1
            print(f'{arq}: {tok}')
print(f'caminhos inexistentes: {faltas}')
```

```
$ python3 caminhos.py $(git diff --name-only 390a63b..)
core/agentes/claude/skills/jangada/agentes.md: config/read
docs/codex.md: config/read
docs/modularizacao-3.0/06-validacao-final.md: bin/jangada-par
docs/modularizacao-3.0/06-validacao-final.md: bin/jangada-x
docs/modularizacao-3.0/06-validacao-final.md: config/read
docs/modularizacao-3.0/06-validacao-final.md: core/projetos
docs/modularizacao-3.0/06-validacao-final.md: core/tarefas
docs/modularizacao-3.0/06-validacao-final.md: docs/arquitetura/modulos.md
docs/modularizacao-3.0/06-validacao-final.md: monitor/historico
docs/modularizacao-3.0/06-validacao-final.md: shell/default
docs/modularizacao-3.0/README.md: bin/jangada-x
docs/modularizacao-3.0/README.md: core/projetos
docs/modularizacao-3.0/README.md: core/tarefas
docs/modularizacao-3.0/README.md: docs/arquitetura/modulos.md
docs/modularizacao-3.0/README.md: monitor/historico
docs/registros.md: bin/jangada-par
caminhos inexistentes: 16
```

Ressalva: o programa aponta os nomes acima, e nenhum é caminho que o texto
dê como existente. Os do próprio 06 são as citações da tabela abaixo.

| Citação | Onde | Por que não é caminho quebrado |
|---|---|---|
| `config/read` | `docs/codex.md`, `agentes.md` da skill | nome de um método do Codex, não arquivo; já estava no texto |
| `bin/jangada-par` | `docs/registros.md` | comando antigo, citado como removido; já estava no texto |
| `bin/jangada-x` | `docs/modularizacao-3.0/README.md` | exemplo genérico de nome de comando no texto da decisão D2 |
| `core/projetos`, `core/tarefas`, `monitor/historico` | `docs/modularizacao-3.0/README.md` | pastas do esboço da especificação, citadas na decisão D4 como não criadas |
| `docs/arquitetura/modulos.md` | `docs/modularizacao-3.0/README.md` | arquivo de outro projeto, citado como origem da especificação |
| `shell/default` | este documento | citado na seção 8, item 6, como pasta que não existe |

O programa só enxerga caminho escrito por inteiro a partir da raiz. Nome de
arquivo solto no texto não é conferido.

## 7. Defeitos encontrados e não corrigidos

Esta tarefa não pode alterar código. Os itens abaixo ficam registrados.

1. **O aviso do `jangada-update` deixou de cobrir os comandos movidos.**
   `bin/jangada-update:99` monta a lista "mudam código que roda fora do
   isolamento" com `git diff --name-only ... -- migrations install bin`.
   Desde a M3-14, a M3-17 e a M3-18, 52 dos 59 comandos são links em `bin/`.
   Uma mudança no arquivo real não altera o link e não entra na lista.
   Prova, num clone temporário com uma linha acrescentada a
   `core/bin/jangada-isolar` e a `core/nucleo/consultas.py`:

   ```
   $ git diff --name-only HEAD~1 HEAD
   core/bin/jangada-isolar
   core/nucleo/consultas.py
   $ git diff --no-ext-diff --no-textconv --name-only HEAD~1..HEAD -- migrations install bin
   (sem resultado)
   ```

   Antes da modularização, a mesma mudança no `jangada-isolar` aparecia com
   o aviso `!!`. Os commits e o resumo por arquivo continuam aparecendo
   antes da pergunta, então a mudança não fica escondida; some o destaque. A
   conferência de processos do mesmo comando (linhas 49 a 51) já procura
   `core/`, `shell/` e `monitor/`. O README e
   `docs/atualizacao-e-migracoes.md` passaram a dizer que o aviso não cobre
   as três pastas.
2. **O `jangada-validar` do Core lê um arquivo do Shell.**
   `core/bin/jangada-validar:803` usa `$JANGADA_CORE_PATH/default/r/lintr` como
   configuração do lintr quando o projeto não tem `.lintr`. `default/r` é
   link para `shell/integracoes/r`. Sem `shell/`, a verificação de arquivos R
   falha (seção 4). O teste de fronteira não confere leitura de arquivo de
   configuração entre módulos, então a lista de exceções não tem linha para
   isso. O inventário classificou `default/r/` como Shell "a confirmar na
   tarefa" (`01-inventario.md:107`).
3. **Os três `LEIAME.md` dos módulos estão desatualizados.**
   `core/LEIAME.md:7` e `monitor/LEIAME.md:7` dizem que a pasta "ainda não
   tem código", e os três falam de subpastas "previstas". Eles ficam fora
   dos arquivos permitidos desta tarefa.
4. **Um link relativo da skill quebrou com a mudança de pasta.** Em
   `core/agentes/claude/skills/jangada/agentes.md:421`, o link para
   `docs/ciclo-da-tarefa.md` subia quatro níveis, o certo quando a skill
   morava em `default/claude/skills/jangada`. Este foi corrigido na M3-20
   original, por ser guia da skill: agora sobe cinco níveis.
5. **`shell/menus/tarefas/janela.py:27` sem `JANGADA_CORE_PATH`.** Ver seção 8,
   item 6.
6. **Aviso do `jangada-validar` para link de pasta.** Ver seção 8, item 3.

## 8. Pendências para depois da 3.0

Registradas sem resolver.

1. **Remoção dos links de compatibilidade.** Os 73 links seguem versionados.
   A decisão D7 é retirá-los só em versão posterior, com migração própria
   dos arquivos do usuário que guardam caminho absoluto (inventário 1.7) e
   com autorização.
2. **Limpeza de fotos e cópias órfãs** (pendência da M3-17a). Uma foto em
   `fotos/` ou uma cópia em `integracoes/`, no estado, sobra quando o
   processo cai antes da limpeza. No caso normal, a armadilha de saída do
   `jangada-validar` e o `verificar_fora` do `jangada-agente-fim` removem a
   árvore. Não há rotina que recolha as sobras.
3. **Aviso `head: erro ao ler ... É um diretório` no `jangada-validar`.**
   Quando a entrega traz um link de pasta, a verificação local lê os dois
   primeiros bytes de cada caminho alterado para saber se é script
   (`core/bin/jangada-validar:727`), e o `head` reclama do link que aponta
   para pasta. O aviso não muda o parecer.
4. **`testes/baseline.py`, `test_trava_liberada_apos_interrupcao`,
   intermitente.**
5. **`testes/contratos-registros.py` intermitente.** Falha quando o modelo
   local não responde a tempo, o que acontece com outras suítes rodando
   junto.
6. **Reserva de `janela.py:27`.** `shell/menus/tarefas/janela.py:27` usa
   `JANGADA_CORE_PATH` e, na falta dele, `Path(__file__).absolute().parents[2]`.
   Com o arquivo em `shell/menus/tarefas`, essa reserva dá `shell/`, não a
   raiz do repositório, e `shell/default` não existe. Pelo comando
   `jangada-tarefas` a variável sempre chega; a reserva só falha para quem
   rodar o arquivo direto, sem a variável.
7. **Nomes antigos em `testes/baseline.py` e `testes/confianca-p0.py`.** Os
   dois chegam ao código por `bin/` e `default/` (por exemplo
   `default/orquestracao`, em `testes/confianca-p0.py:22`, `:231` e `:233`).
   Funcionam pelos links e precisam mudar antes de os links saírem.
8. **`01-inventario.md:26`.** A linha diz que o `--integrar` do
   `jangada-agente-fim` "segue bloqueado". A M3-11a restaurou a integração.
9. **M3-19, dividir o `jangada-config`.** Ficou de fora por decisão do
   usuário. O arquivo continua inteiro em `bin/`, com funções dos três
   módulos.
10. **M3-14 integrada com parecer `REVISAR`.** Por decisão do usuário, com
    os dois itens da rodada 3 em aberto (seção 2.7).
11. **Aviso do `jangada-update`**, defeito 1 da seção 7.
12. **`LEIAME.md` dos módulos**, defeito 3 da seção 7.
13. **Configuração do lintr no Shell**, defeito 2 da seção 7: o
    `jangada-validar` lê `default/r/lintr`, que mora em `shell/`.
14. **Comentário com linha antiga em `fronteiras-excecoes.txt`** e a decisão
    sobre a marca das duas linhas K6 (seção 3).
15. **`jangada-monitor --json`**: chamada do Shell a código do Monitor por um
    caminho do Core, sem linha na lista de exceções (seção 3).
16. **Divergências registradas no plano e não ajustadas**: a ordem "Shell
    primeiro, Core por último" e o momento 2 da atualização da cópia
    instalada, em
    [05-migracao-testes-reversao.md](05-migracao-testes-reversao.md), e a
    dúvida sobre a M3-15 poder subir antes da M3-14, no
    [backlog](04-backlog.md#onda-c-migração-fase-4).
17. **Documentos de registro não atualizados.** `docs/estabilizacao/` e
    `docs/evolucao-2.0/` são relatórios datados e citam os caminhos da época.
    Os documentos 01 a 05 e a prova dos links desta pasta também descrevem o
    plano e o estado de quando foram escritos. Todos os caminhos antigos
    citados neles continuam resolvendo pelos links.
    Isso vale para a data desta validação: em 18/10/2026, `docs/estabilizacao/`
    passou para `docs/historico/estabilizacao/` e a citação do caminho antigo
    não resolve mais. O [índice histórico](../historico/README.md) mostra o novo lugar.
