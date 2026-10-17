# Consultas do terminal e do Monitor, recorte M1.2

O terminal e o retrato de orquestração do Monitor consultam o Core sem
conhecer nomes de arquivos ou descobrir bancos. Este recorte retira duas
exceções de K9. Não conclui M1: compatibilidade, volume e prova integral
continuam nos recortes seguintes. Não altera políticas de delegação.

## Sessão por árvore de trabalho

`bin/jangada-agentes --sessao-worktree-json CAMINHO` retorna
`{"versao":1,"sessao":"nome"}` ou `{"versao":1,"sessao":null}`.
O caminho exige forma absoluta, até 4.096 caracteres. A comparação com
`worktree` é literal, sem normalizar barras, consultar processos ou aplicar
retenção. `dir` e `raiz` não participam. Assim, uma sessão `--direto` sem
`worktree` não corresponde; uma sessão legada ou encerrada ainda corresponde.
O nome continua vindo do arquivo, mesmo sem campo `sessao` no registro.
Arquivos reservados a revisões, delegações e contextos de validação não são
registros de sessão e não são abertos; diretórios `*.json` são ignorados.

`JANGADA_SESSAO` mantém precedência no terminal e dispensa a consulta.
Sem essa variável, `_jangada_sessao_atual` entrega ao Core o topo do Git.
Ausência de correspondência retorna 1 na função do terminal. Falhas retornam
2 com diagnóstico. `repassar` não abre o seletor após erro da consulta.

Havia ambiguidade quando vários registros tinham o mesmo `worktree`: o
Shell escolhia o primeiro resultado de `find`, cuja ordem não era contrato.
A consulta agora recusa e informa os nomes, sem escolher arbitrariamente.

## Contexto explícito por sessão

`bin/jangada-agentes --contexto-json SESSAO` retorna um objeto com:

| Campo | Tipo e significado |
|---|---|
| `versao` | Inteiro 1 |
| `sessao` | Nome solicitado |
| `tarefa` | Texto original; ausente ou nulo vira texto vazio |
| `parecer` | Nulo ou objeto com `rodada` inteira, `origem` relativa e `texto` |

A seleção preserva a origem anterior: Markdown `validacao-SESSAO-rN.md`
na árvore de `agentes/`, inclusive subpastas de pareceres. Não desce em
`agentes/projetos/` ou `agentes/runtime/`, áreas operacionais protegidas.
Não consulta `revisoes/`,
conversas, históricos dos modelos, protocolos nem credenciais. A maior
rodada numérica vence, portanto r10 vem depois de r2 independentemente da
subpasta. Empate na maior rodada recusa o repasse. A ordenação anterior
por caminho completo podia privilegiar a subpasta; esse caso não tinha
critério explícito por rodada. Sufixos diferentes de dígitos não são pareceres.
Rodadas acima de nove dígitos recusam a consulta.

`repassar` continua sendo ação explícita do dono. O texto é marcado como
dado não confiável, sem autoridade de aprovação ou execução. O consumidor
substitui caracteres de controle, preservando tabulações e quebras de linha.
O comando não dá acesso a pareceres protegidos por ligações simbólicas ou
adicionais. Ausência de registro e parecer produz contexto vazio identificado,
como antes. Um erro impede criar ou abrir a nova tarefa.

## Rodadas por sessão

`bin/jangada-agentes --rodadas-json SESSAO` lista as rodadas de revisão da
sessão, sem o texto dos pareceres. O texto do último continua no
`--contexto-json`. A resposta é
`{"versao":1,"sessao":"...","execucao":...,"rodadas":[...]}`.

| Campo | Tipo e significado |
|---|---|
| `versao` | Inteiro 1 |
| `sessao` | Nome solicitado |
| `execucao` | Execução escolhida, texto ou nulo |
| `rodadas` | Lista em ordem de `data`, da mais antiga à mais recente |

Cada rodada tem:

| Campo | Tipo e significado |
|---|---|
| `rodada` | Inteiro do registro, a partir de 1; recomeça depois de um APROVADO; nulo se inválido |
| `origem` | `sessao` (`validar.jsonl`) ou `protegida` (`revisoes/validar.jsonl`) |
| `resultado` | `aprovado` ou `revisar` |
| `etapa` | `revisor` |
| `revisor`, `modelo` | Texto do registro; vazio quando não gravado; nulo fora de `[A-Za-z0-9_.:/@+[]-]`, até 128 caracteres |
| `data` | Hora do registro, ISO com fuso; nulo se ilegível. O registro não tem início separado |
| `segundos` | Número do registro, duração do `jangada-validar` até o registro; nulo se inválido |
| `apontamentos` | Inteiro do campo `itens`; nulo se inválido |
| `parecer_origem` | Sempre nulo nesta versão; ver abaixo |

A fonte é o `validar.jsonl` da [seção 1 dos registros](../registros.md),
pelas regras do `jangada-indicadores`: mesmo `rotulo` e rodada válida
(`etapa` `revisor` e resultado `aprovado` ou `revisar`, função
`rodada_valida`). Erro, limite e barragem local não entram. Com
`agentes/SESSAO.json` presente, vale o campo `execucao` dele, inclusive
nulo. Sem esse registro, a sessão está encerrada e vale a execução da
rodada válida mais recente.

Esta é a única leitura em `revisoes/`: a consulta abre só
`revisoes/validar.jsonl`, sem listar a pasta nem abrir pareceres ou cópias
de sessão. Sem esse arquivo, as rodadas protegidas não aparecem.

`parecer_origem` é sempre nulo nesta versão. O registro não grava o N do
arquivo `validacao-SESSAO-rN.md`, o N não é a rodada, e o horário de
modificação não prova a associação: um parecer antigo com horário alterado
passaria por outro. A consulta não lista nem confere pareceres. Preencher o
campo exige que o `jangada-validar` grave o N na linha, mudança de outra
tarefa.

Cada `validar.jsonl` é lido nos últimos 8 MiB e nas últimas 5.000 linhas.
Linha acima de 64 KiB, JSON inválido ou valor que não é objeto são
ignorados. Arquivo ausente dá lista vazia; link ou arquivo não regular
recusa a consulta. São devolvidas as 50 rodadas mais recentes. Rodada sem
`data` legível fica antes das datadas. A saída não tem `NaN` nem texto
`None`; valor inválido vira nulo.

Nome de sessão inválido ou número errado de argumentos sai com 2 e mensagem
curta. Outra falha sai com 1, diagnóstico e stdout vazio. A consulta não
cria, move nem apaga nada. `testes/rodadas.py` confere esses casos.

## Limites do terminal

Nomes seguem `[A-Za-z0-9_.-]+`, até 255 caracteres, exceto `.` e `..`.
A pasta final não pode ser simbólica. A raiz configurada do estado é resolvida
antes da leitura; os componentes abaixo dela são abertos sem seguir links.
JSON e parecer selecionado exigem arquivo regular sem ligações adicionais,
até 1 MiB. `worktree` exige texto ou nulo, até 16.000 caracteres. `tarefa`
exige texto ou nulo, até 1 MiB, sempre condicionada aos tetos do arquivo e
da resposta inteira. O repasse aceita pedidos acima de 16.000 caracteres
sem truncamento; não herda o limite dos campos da lista de apresentação.
JSON malformado ou de outro tipo em registro de sessão recusa a consulta,
inclusive se o registro não corresponder à árvore solicitada.

A varredura usa `scandir` sem ordenar ou armazenar todas as entradas.
São aceitos até 4.096 registros de sessão na busca por árvore. Relatórios,
contextos e arquivos auxiliares excluídos pelo filtro não consomem esse teto.
Na busca de parecer, o teto de 16.384 conta somente candidatos e pastas
percorridas, com profundidade máxima de 32. Auxiliares como `delegacao-*.md`
e `fim-*.log` não consomem esse teto. Diretórios simbólicos não são
percorridos; um parecer candidato simbólico ou FIFO recusa a consulta.
A resposta UTF-8 inteira tem teto de 1 MiB, sem truncamento. O Core sai
com 1, diagnóstico e stdout vazio em caso de erro.

Entrada removida entre enumeração, conferência e leitura é ignorada, sem
cancelar as outras sessões ou pareceres. Se o parecer selecionado desaparecer
na abertura final, `parecer` é nulo, sem escolher uma rodada anterior.
Outras falhas continuam recusando a consulta, inclusive tipos inválidos,
JSON malformado e substituição por link ou FIFO.

O terminal valida versão inteira 1, campos e tipos antes de usar a resposta.
O transporte usa Python em modo isolado (`-I`), sem importar módulos da
pasta atual ou de `PYTHONPATH`. Limita stdout e stderr agregados a 1 MiB e
dez segundos.
Falha, JSON malformado ou versão desconhecida não vira ausência de sessão.
O prazo encerra o processo direto; não promete encerrar seus descendentes.
Diagnósticos preservam acentos em UTF-8 e escapam somente controles C0/C1;
quebras de linha vindas da fonte aparecem como texto escapado.
Não há retorno à leitura dos arquivos privados.

## Fila e provedores do Monitor

`nucleo.consultas.consultar_filas(raiz, projetos=(), precos=None)` recebe a
raiz configurada do estado, caminhos dos projetos conhecidos e a tabela de
preços já lida pelo consumidor. A resposta tem versão inteira 1 e listas
`projetos`, `provedores`, `erros`.

Cada projeto entrega `id` opaco, `caminho` conhecido ou nulo, `tarefas`,
`consumos` por ID e `metricas`. O Core decide descoberta, seleção dos bancos
e correspondência dos caminhos. A chave usa o destino resolvido, mas
`caminho` conserva o texto recebido, inclusive aliases por links simbólicos.
O Monitor decide apenas o nome de exibição;
para projeto desconhecido, conserva `projeto-` seguido dos primeiros doze
caracteres do ID. Não recebe conexão SQL nem caminho de banco.

Cada tarefa entrega apenas `id`, `status`, `tentativas`, `motivo`, `atualizado`
e a parte de `especificacao` usada na apresentação: `papel`, `capacidade`,
`prioridade`, `dependencias`, `max_chamadas` e `tempo_total`. Campos opcionais
ausentes continuam ausentes. Pedidos, objetivos, resultados e demais colunas
não atravessam esse contrato. O cálculo interno conserva os dados completos.
Consumo continua
com `chamadas` e `segundos`. As métricas reutilizam o cálculo existente no
Core, sobre o mesmo retrato de leitura. Preços inválidos continuam gerando
erro; consumo ou custo desconhecido continua nulo. Provedores mantêm a
expiração, a pausa e a cota não confirmada. Não há consulta remota.

Cada erro contém `projeto` e `caminho` opcionais, além de `mensagem`.
Projeto ilegível não entrega tarefas ou métricas parciais. Erro de provedores
é explícito. Ausência de estado ou de banco é resultado vazio válido e não
cria pastas. Fila existente sem tarefas ainda entrega métricas vazias.
O Monitor recusa versão desconhecida e conserva o erro na saída do coletor.

Bancos e WAL são copiados para pasta temporária privada, nunca abertos para
escrita na origem. `query_only` e transação de leitura permanecem ativos.
Banco, WAL e SHM simbólicos ou não regulares são recusados. Cada arquivo
copiado admite 64 MiB; há até 4.096 projetos e 16.384 tarefas ou provedores
por banco. Eventos não têm teto de contagem separado do limite dos arquivos.
A resposta codificada admite 1 MiB. Provedores são consultados primeiro.
Projeto cuja apresentação excede o saldo da resposta gera erro identificado,
sem descartar provedores ou outras filas válidas. Uma reserva de 1 KiB
permite relatar erros de limite. Se os próprios diagnósticos excederem a
resposta, são resumidos por uma mensagem explícita com a quantidade de erros. O esquema legado tem `user_version=0`;
outro valor é erro nesta API. Esses tetos são proteções, não prova de
adequação a volume. Mudança concorrente durante a cópia continua exigindo
nova tentativa limitada ou erro, conforme `banco_leitura`.

## Provas e pendências

`testes/consulta-terminal.sh` exerce as fachadas reais com estado reposicionado,
retenção zero, sessões antigas, `--direto`, duplicidade e r2/r10. No bash e
zsh, também usa comando sintético e estado privado inacessível para provar
precedência, transporte, versão e recusa sem executar o destino.

`testes/consultas-modulos.py` compara o cálculo existente e o conteúdo do
Monitor com SQLite sintético, WAL confirmado e transação não confirmada.
Confere preços, provedores expirados, fila vazia, erros, limites, links e
FIFO. O consumidor recebe uma resposta pública sintética sem poder enumerar
ou testar arquivos privados. Ambos os testes comparam caminhos e hashes da
origem antes/depois, inclusive WAL e ausência de estado.

Os contratos existentes de consulta, fachada, caminhos e fronteiras continuam
ativos. Não foram ampliados tetos ou exceções de K9. Não há alteração de TSV,
de `--lista-json` versão 1, de links relativos ou de registros documentados.

Antes de integrar, executar `testes/painel-orquestracao.py` e a suíte integral
em ambiente com autoridade para preparar as fontes sintéticas. As provas
específicas incluem 400 pedidos longos sem aumentar a resposta, estouro por
projeto com provedores preservados e aliases simbólicos no nome de exibição.
A busca do terminal é conferida com contextos grandes, relatórios inválidos
e mais de 16.384 artefatos protegidos, sem abrir essas fontes como sessões
ou pareceres. Esses casos não substituem a avaliação de volume de M1.3.

## Ampliação pontual autorizada

`testes/metricas.py` foi incluído no escopo autorizado após a falha da suíte
externa do candidato `91b8905`. A fixture carregava o coletor candidato com
`JANGADA_CORE_PY` herdado da instalação. O commit `da46193` fixa o Core
candidato e confere a origem das funções importadas, preservando as asserções
de métricas. Essa ampliação pontual integra a lista de 15 arquivos permitidos.
