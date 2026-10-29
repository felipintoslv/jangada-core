# Subagentes e delegação

O agente da sessão pode passar trabalho de leitura a um subagente: explorar
código, ler documento longo, pesquisar na web, verificar antes do
`jangada-validar`, auditar segurança, analisar arquitetura, avaliar interface e uso, procurar gargalo
ou revisar redação. O subagente só lê e devolve um relatório curto com
`caminho:linha`; quem edita é sempre o agente da sessão, porque o worktree é
um só. Paralelismo de implementação é outra sessão do jangada.

## Papéis

São dez papéis de apoio. Nove existem no Claude e no agy com o mesmo nome.
O `designer` existe somente no agy, em `agentes/agy/agents/designer/agent.md`.
Os demais ficam em `agentes/claude/agents/PAPEL.md` e
`agentes/agy/agents/PAPEL/agent.md`.

Desde a modularização 3.0, os caminhos de `default/` e `bin/` citados neste
documento são links de compatibilidade e continuam sendo a forma de uso. Os
arquivos moram em `agentes/claude/`, `agentes/agy/`,
`agentes/perfis/`, `delegacao/`,
`nucleo/` e `bin/`. O `jangada-subagentes` e o painel de subagentes ficam
em comando opcional, fora do Core por ora.
O mapa das pastas está na seção Estrutura do [README](../README.md).

| Papel | Uso | Claude |
|---|---|---|
| explorador | localizar código e ligações entre partes | haiku |
| leitor | trechos de PDF, planilha, relatório | haiku |
| pesquisador | documentação e dados públicos na web | haiku |
| verificador | testes, lint e regras antes do `jangada-validar` | sonnet |
| auditor | segurança: injeção, credenciais, permissões | sonnet |
| arquiteto | módulos, contratos e impacto de mudança | sonnet |
| designer | hierarquia visual, consistência, acessibilidade e passos de uso | somente agy (flash) |
| otimizador | gargalos, leituras redundantes, memória | sonnet |
| redator | clareza e regras de texto do `AGENTS.md` | haiku |
| supervisor | fidelidade de relatório intermediário às fontes | haiku |

No agy, `--modelo gemini-3.8-flash-high` fixa o executor econômico por tarefa,
sem alternativa automática. Sem essa opção, permanece a lista de compatibilidade
`JANGADA_DELEGAR_MODELOS`. Catálogo e cota não comprovam execução.

O agy tem mais um agente, fora da delegação: o `revisor`, usado só pelo
`jangada-validar`, com ferramentas de leitura.

Só o leitor e o verificador têm terminal (Bash no Claude, `run_command` no
agy). O leitor lê documentos de fora, que podem trazer injeção de prompt: no
Claude, o hook `PreToolUse` do frontmatter chama o `jangada-hook-leitor`, que
só deixa passar comandos de leitura (`pdftotext` com saída `-`, `pdfinfo`,
`grep`, `head`, `tail`, `wc`, `cut`, `tr`, `cat`, `ls`) ligados por `|`, sem
redirecionamento, `;`, `&` nem expansão. Sem o script no PATH, o comando é
recusado. No agy, o mesmo script responde ao `PreToolUse` do `run_command`
(`jangada-hook-leitor --agy`, em `~/.gemini/config/hooks.json`). Esse hook
dispara para todo agente do agy: reconhece o leitor pela variável
`JANGADA_AGY_PAPEL=leitor`, que o `jangada-delegar` põe no agy que roda o
papel, ou, quando o leitor é subagente de uma sessão, pelo
`brain/*/.system_generated/subagents/CONVERSA.json` com o `typeName`
`leitor`. Para o leitor, o comando fora da lista recebe `deny`; o resto
recebe `ask`, que segue as permissões do agy. Sem terminal, o agy só roda o
que está em `permissions.allow`, e essa lista vale para todos os agentes
(pode ter `cp` ou `curl`). O hook continua obrigatório no uso nativo desse papel.
Na leitura remota pelo delegador, o papel privado recebe texto extraído sem
ferramentas ou MCP. O verificador roda os testes do projeto com terminal.

## Instalação

```mermaid
flowchart TD
    A[install/50-agentes.sh<br>ou migração] --> B{claude ou ~/.claude?}
    B -- sim --> C[ligar_agentes_claude:<br>links em ~/.claude/agents]
    A --> D{agy ou ~/.gemini?}
    D -- sim --> E[mesclar_agentes_agy:<br>caminho em ~/.gemini/config]
    A --> F[mesclar_hooks_claude:<br>SubagentStart e SubagentStop]
```

As funções ficam em `install/lib.sh`. A migração que leva papel novo a uma
instalação existente fica no repositório jangada-shell.

## Para onde vai a delegação

```mermaid
flowchart TD
    A[Claude ou Codex<br>perfis claude-codex e codex-claude] --> C{Papel de apoio}
    C -- leitor ou redator --> OL[jangada-delegar --destino local<br>Ollama, arquivos explícitos]
    OL --> F{Falha local?}
    F -- sim --> FL[Motivo registrado,<br>continua na sessão, sem agy]
    C -- demais papéis --> AG[jangada-delegar --destino agy<br>--permitir-remoto]
    AG --> P{Autorização, acesso,<br>confiança e cota?}
    P -- sim --> R[Relatório a conferir]
    P -- não --> B[Bloqueio registrado]
```

`JANGADA_DELEGAR=agy` é o padrão dos dois perfis. O protocolo, na abertura e
na retomada, manda `--destino` explícito: leitor e redator vão ao Ollama; os
demais papéis vão ao agy com fontes autorizadas. Por escolha explícita da tarefa,
leitor e redator também podem ir ao agy, com `--permitir-remoto`, modelo fixo
e `--arquivos`. Isso preserva a opção local e não autoriza envio após falha.
O comando não escolhe o
destino por papel: `jangada_delegacao` em `bin/jangada-config` e o padrão do
comando continuam agy. O perfil prevalece sobre a configuração global. Falha
local nunca vira envio remoto, e recusa do agy nunca vira chamada local ou ao
Claude. Sem agy instalado, os demais papéis registram recusa.

| Agente e destino | Protocolo em `agentes/perfis/` | Regra |
|---|---|---|
| Claude, `agy` | `protocolo-delegar-agy.md` | leitor e redator no Ollama, demais no agy; recusa registrada |
| Claude, `claude` explícito | `protocolo-delegar-claude.md` | subagentes do Claude |
| agy restaurado, `nativo` | `protocolo-delegar-nativo.md` | subagentes do próprio agy |
| Claude, `local` | `protocolo-delegar-local.md` | escolha local explícita; demais papéis na sessão |
| Codex, `agy` ou `local` | `protocolo-delegar-codex.md` | mesma regra do Claude com agy; local explícito |

O Codex não chama subagentes do Claude. O agy só recebe delegações e revisa;
o destino `nativo` resta para sessões antigas do agy restauradas.

Todos recebem também `agentes/perfis/protocolo-delegar.md`: citar fontes,
conferir contribuição e aproveitamento, não editar nem substituir revisão
independente pelo `jangada-validar`. Perfil com destino agy não comprova
participação; o coordenador cobra apoio executado ou bloqueio rastreável.

### Instalações existentes e restauração

Sem preferência explícita, os comandos passam a herdar agy do repositório.
A restauração recompõe destino e protocolo pelo perfil e configuração atual,
sem usar o destino gravado no estado. Não é necessária migração nem regravação
de configuração pessoal para isso. Sessões já abertas mantêm seu ambiente
e devem ser retomadas para receber o protocolo atualizado.

Preferências explícitas em `jangada.conf`, perfis pessoais e
`delegacao.json` são preservadas. Configurações antigas que escolhem local
continuam locais, inclusive políticas com alternativas locais. Para adotar
a política nova, o dono deve escolher `JANGADA_DELEGAR=agy` e ajustar ou
retirar sua política pessoal. Para compatibilidade local, use
`--delegacao local`, `JANGADA_DELEGAR=local` ou `--destino local` explicitamente.
Nenhuma dessas escolhas autoriza envio remoto de dados confidenciais.

## jangada-delegar

O destino pode ser explícito: `--destino local` ou `--destino agy`.
Sem essa opção, o comando usa o destino definido pela configuração, agy por padrão.
Os protocolos dos dois perfis padrão sempre passam `--destino`: com
`JANGADA_DELEGAR=agy`, `--destino local` atende leitor e redator.
`JANGADA_DELEGAR=claude` recusa ambos; `JANGADA_DELEGAR=local` recusa o agy.

### Seleção por capacidade

`--capacidade` ativa seleção para o papel `leitor`, com fontes em
`--arquivos`. As capacidades disponíveis são `leitura_documental`,
`resumo_curto` e `analise_documental`. Sem essa opção, o destino padrão também é agy.

```sh
jangada-delegar leitor "Compare os documentos" \
  --capacidade analise_documental --permitir-remoto \
  --arquivos fontes/a.txt fontes/b.txt
```

A política padrão em `delegacao/roteamento.json` contém somente agy
para as três capacidades, sem alternativa local automática. Um arquivo opcional
`~/.config/jangada/delegacao.json` substitui essa política: contém um objeto
com capacidades e listas de destinos, sem comandos. Aceita apenas `local`,
`agy` e `codex-economico`, sem repetições. Capacidade ausente ou configuração inválida recusa
a execução. Claude e Codex não são alternativas automáticas.

Com ou sem `--capacidade`, o agy exige `--permitir-remoto` nesta tarefa e um
perfil que permita o destino. A autorização não vence `JANGADA_DELEGAR=local`. Sem autorização,
a seleção padrão registra bloqueio; uma falha local nunca autoriza envio remoto.
`--destino` explícito restringe a seleção a esse destino.

Cada candidato é tentado uma vez. Permitem tentar o próximo destino
autorizado: `indisponivel`, `modelo_ausente`, `ocupado`, `cota_desconhecida`,
`cota_insuficiente`, `contexto_insuficiente`, `saida_invalida` e
`erro_execucao`. Isso inclui jogo aberto, vaga ocupada, modelo concorrente,
falha de chamada e tempo esgotado de uma chamada. Negação de ferramentas,
ausência de confiança ou de proteção do leitor interrompem a seleção.

`JANGADA_DELEGAR_TEMPO_TOTAL` limita a seleção e seus executores a 600
segundos. `JANGADA_DELEGAR_CHAMADAS_MAX` limita as chamadas aos modelos a
8, incluindo partes e consolidação local. Ambos aceitam inteiros positivos
de até seis dígitos. Consultas de disponibilidade e cota entram no tempo
total, mas não na contagem de chamadas ao modelo.
Antes de processar um documento dividido, o executor local verifica se há
chamadas suficientes para todas as partes e uma consolidação. Se faltar
orçamento, recusa antes de consumir tokens.
Na extração estruturada, a consolidação é determinística e não consome uma chamada.
Cada chamada documental com capacidade solicita raciocínio desligado e limita a geração
a 1.024 tokens. Alguns modelos continuam raciocinando; saída interrompida
pelo limite de geração é recusada, sem aprovação parcial. Chamadas sem
capacidade preservam as opções anteriores de geração.
Ao atingir o limite global, o GNU `timeout` envia SIGKILL ao grupo de
processos do executor e encerra os filhos que permanecem nesse grupo. Processos que
criem outra sessão ou pedidos já aceitos pelo provedor exigem cancelamento
próprio; o limite da execução local não garante esse cancelamento.

Antes de gravar ou entregar o relatório completo, a verificação exige uma referência
a cada fonte fornecida, em linha ou página existente. Nomes de arquivo
ambíguos exigem o caminho. Essa conferência não comprova fidelidade nem
aprova conclusões. Sem saída válida, recusa com código 4.
Para exigir completude estrutural, repita `--requisito "Nome do item"`.
Cada requisito exige uma seção `## Nome do item`, uma referência e pelo
menos cinco palavras de explicação além do título e do localizador.
Isso rejeita listas de referências sem explicações, mas não comprova que
a explicação responde corretamente ao pedido. Confira o conteúdo na fonte.
Essa opção exige `--capacidade`; pedidos sem requisitos mantêm a conferência
de referências. Quando os requisitos passam, `verificacao` contém
`referencias_e_requisitos_validos`.

Para extrair campos tipados no Ollama, use `--destino local`,
`--capacidade leitura_documental` e repita `--extrair campo:tipo`.
Os tipos são `texto`, `inteiro` e `booleano`; nomes usam letras minúsculas,
números e sublinhado, começando com letra. Campos repetidos são recusados.
Essa opção exige leitor e não aceita `--requisito`, que usa seções de texto.

```sh
jangada-delegar leitor "Extraia o prazo em dias e a responsável" \
  --destino local --capacidade leitura_documental \
  --extrair prazo_dias:inteiro --extrair responsavel:texto --arquivos politica.txt
```

O Ollama recebe uma estrutura JSON obrigatória. Cada campo contém `valor`
e `referencia`; ausência no trecho exige ambos `null`.
Valores presentes exigem o tipo declarado e uma referência ao próprio trecho.
O delegador normaliza as referências para caminhos completos.
Partes são unidas sem nova geração: ausência não apaga fatos, valores iguais
preservam a primeira citação e valores diferentes recusam a extração.
O registro contém `campos_extracao` e, quando houve divisão,
`consolidacao: "deterministica"`. A conferência devolve
`estrutura_e_referencias_validas`; ela não verifica se a linha sustenta o fato,
nem se o modelo omitiu informação presente. A revisão do conteúdo continua necessária.
Relatórios reprovados pela conferência ficam em
`$JANGADA_ESTADO/agentes/delegacao-reprovada-ID.md`, com o caminho registrado
no executor e `verificacao=reprovada`. Não substituem o arquivo da entrega.
O corte por palavras pode omitir referências na prévia. Nesse caso, leia
o arquivo completo indicado; a verificação vale para esse arquivo.

`--json` devolve o relatório, capacidade, decisão, motivos e tentativas em
JSON. `verificacao_escopo` identifica o relatório completo;
`relatorio_cortado` e `artefato` identificam a prévia e seu arquivo completo.
O `roteamento_id` reúne os registros dos executores da mesma seleção.
As tentativas anteriores aparecem no resultado do executor seguinte. Se o
tempo interromper um executor, seu número de chamadas fica desconhecido.
O painel mantém a contagem por registro: cada executor e a recusa final
da seleção são entradas distintas. Ele não agrupa pedidos por
`roteamento_id`. As chamadas locais são medidas individualmente, sem
somar de novo o histórico repetido em `tentativas`.

```mermaid
flowchart LR
    A[jangada-delegar] --> D{Destino permitido?}
    D -- não --> R[Recusa, código 4]
    D -- local --> L[Leitor ou redator<br>--arquivos obrigatório]
    L --> O[Ollama, sem ferramentas]
    D -- agy --> G[Papéis instalados no agy<br>confiança, fontes e cota]
    G --> F[agy, com ferramentas do papel]
    O --> J[Relatório e delegacoes.jsonl]
    F --> J
```

### Fontes e pesquisa delimitadas

```sh
jangada-delegar leitor "Extraia o prazo" --destino agy --permitir-remoto \
  --modelo gemini-3.8-flash-high --arquivos contrato.txt:10-25
jangada-delegar pesquisador "Busque e abra a documentação oficial" \
  --destino agy --permitir-remoto --modelo gemini-3.8-flash-high \
  --url https://ai.google.dev/gemini-api/docs/google-search
```

Leitor e redator remotos exigem fontes explícitas. O controlador extrai somente
o texto autorizado, numerado por linha ou página, e entrega ao papel privado
sem ferramentas ou MCP. O arquiteto com fontes explícitas usa a mesma cópia de
texto, evitando buscas fora dos arquivos autorizados. Aceita somente arquivos
regulares e faixas de linhas; pastas são recusadas antes de chamar o modelo.
A faixa de linhas vale para texto; PDF exige o arquivo
inteiro e `pdftotext`. Fontes com links, conteúdo inválido ou acima de 2 MiB são
recusadas. Pedido e texto extraído juntos têm limite de 96 KiB; delimite uma
faixa menor quando necessário. A pasta do projeto e a configuração pessoal ficam ocultas no executor.
Isso não altera os subagentes nativos nem a opção local.

A pesquisa com `--url` aceita somente domínios HTTPS autorizados por tarefa,
sem fontes locais. Cria configuração privada por chamada, preserva as recusas
pessoais e permite abertura apenas dos domínios indicados. Não acrescenta regras
à configuração pessoal. O pesquisador busca, abre e lê o corpo baixado. Um hook privado recusa
`view_file` fora de `brain/CONVERSA/.system_generated/steps/N/content.md`
da própria conversa. Esse artefato vem da página pública autorizada.
Sem login, confiança, cota ou abertura, registre o bloqueio; não troque modelo.

`fontes_autorizadas`, `urls_autorizadas` e `cotas_modelos` registram escopo,
modelo, grupo e percentual consultado. `registro_ferramentas` aponta o estado
privado do cliente, incluindo conversas e registros para conferir ferramentas.
Nenhum texto do modelo comprova busca ou abertura: confira esses registros,
a URL, a data e o trecho lido. Ação negada sempre resulta em recusa.
Resultado do Flash e aceite por hash não significam testes ou revisão aprovados.

### Destino agy

O destino `agy` segue o fluxo abaixo. O destino local não consulta cota
nem depende do agy instalado; seu funcionamento está na próxima seção.

```mermaid
flowchart TD
    A[jangada-delegar PAPEL pedido] --> B{papel conhecido<br>e pedido presente?}
    B -- não --> X2[uso errado, código 2]
    B -- sim --> C{perfil permite agy?}
    C -- não --> R[recusa, código 4]
    C -- sim --> D{agy instalado e<br>pasta em trustedWorkspaces?}
    D -- não --> R
    D -- sim --> E{papel instalado no agy?}
    E -- não --> R
    E -- sim --> F{algum modelo da lista com cota<br>acima de JANGADA_DELEGAR_COTA_MIN?}
    F -- não --> R
    F -- sim --> G[timeout agy -p --agent PAPEL<br>--sandbox --output-format json]
    G -- cota esgotada --> F
    G -- 124 ou outro erro --> R
    G -- ok --> H{status SUCCESS e<br>resposta não vazia?}
    H -- não --> R
    H -- sim --> I{mais de<br>JANGADA_DELEGAR_PALAVRAS?}
    I -- sim --> J[imprime cortado e grava<br>o completo no estado]
    I -- não --> K[imprime o relatório, código 0]
    J --> K
    R --> L[registra em delegacoes.jsonl]
    K --> L
```

- A pasta é a raiz do repositório atual, que o agy precisa confiar; um
  worktree do jangada entra em `trustedWorkspaces` pelo
  `jangada-worktree-preparar`, só se a raiz já estiver lá, e sai no
  `jangada-agente-fim`. A abertura e a retomada da tarefa repetem essa
  conferência; veja Confiança do agy no
  [ciclo da tarefa](ciclo-da-tarefa.md).
- A recusa por confiança sai com código 4 e diz o caso. "A raiz está
  autorizada, mas este worktree ainda não recebeu a confiança derivada": rode
  `jangada-agentes --confianca SESSAO` fora da sessão isolada. "O agy não
  confia na raiz": abra o agy na raiz, responda à pergunta de confiança e
  rode o mesmo comando. O `jangada-delegar` só diagnostica; ele não grava a
  confiança.
- A cota vem de `agy -p "/usage"`, guardada por `JANGADA_DELEGAR_CACHE`
  minutos (5), com no máximo uma consulta por execução. O agy separa os
  grupos Flash/Pro (`gemini-weekly` e `gemini-5h`), Argon
  (`gemini-argon-wtu-weekly`) e Claude/GPT (`3p-weekly` e `3p-5h`).
  A seleção usa o grupo real do modelo e vale a menor
  fração entre os que não vêm com `disabled`. Se a atualização falhar, não
  usa o valor expirado.
  Uma resposta atual com cota válida de algum grupo configurado pode ser usada.
  Grupo ausente ou ilegível é pulado, sem bloquear modelos de outro grupo válido.
- A consulta `agy agents` deve terminar com sucesso antes de conferir o papel.
  Falha de inicialização, inclusive soquete local proibido pelo ambiente,
  registra `indisponivel` com diagnóstico; não significa papel ausente.
  O comando consome o catálogo completo para evitar que saída antecipada
  do `grep` provoque SIGPIPE no produtor sob `pipefail`.
  Ao testar o comando do worktree, use os recursos da instalação protegida
  quando os hooks reais apontarem a ela. Não regrave hooks nem amplie permissões.
- Os modelos vêm de `JANGADA_DELEGAR_MODELOS`, em ordem de preferência
  (padrão `gemini-3.8-flash-high claude-sonnet-5-5-high gpt-oss-120b-medium`).
  O modelo com cota desconhecida ou abaixo de `JANGADA_DELEGAR_COTA_MIN`
  (20%) é pulado. Se o agy responder que a cota acabou, o comando tenta o
  seguinte. Sem nenhum modelo atendido, recusa com o motivo do primeiro.
- O tempo limite é `JANGADA_DELEGAR_TEMPO` segundos (300).
- Ação negada recusa o resultado, inclusive quando há resposta textual.
  Não se altera configuração pessoal para contornar o bloqueio.
- O relatório conta as frases sem fonte (`caminho:linha`, URL, página ou
  célula), que entram no registro.
- Na recusa, o comando pede registro e aviso do bloqueio. No Codex, a
  investigação pode continuar na sessão, sem declarar o apoio concluído.
  O `jangada-delegar` nunca chama o Claude.

### Várias contas do agy

O catálogo opcional `$JANGADA_ESTADO/contas/agy.json` contém uma lista:

```json
[{"nome":"argon","pasta":"/home/USUARIO/.local/state/jangada/contas/argon","argon":true},
 {"nome":"flash","pasta":"/home/USUARIO/.local/state/jangada/contas/flash","argon":false}]
```

Sem esse arquivo, permanece a conta implícita `principal`, em
`~/.gemini/antigravity-cli`, com os mesmos argumentos de isolamento.
Nomes são únicos; pastas precisam ser absolutas, sem links ou sobreposição.
Cada pasta é `~/.gemini/antigravity-cli` (a principal) ou fica dentro de
`$JANGADA_ESTADO/contas/`, onde a importação cria as contas. Outro lugar
recusa o catálogo: o jangada grava na pasta da conta (confiança, `bin`), e só
essas duas áreas já estão na regra 1. A pasta `contas` não pode ser link, e
com catálogo a escrita de confiança só vai ao `settings.json` da conta escolhida.
O arquivo é lido como dados. O dono o configura fora da sessão isolada.

`jangada-delegar PAPEL "pedido" --conta NOME` fixa uma conta. Sem a opção,
o comando preserva a prioridade dos modelos e escolhe, para cada família,
a conta habilitada que confia na pasta e tem maior saldo real. A confiança
é conferida antes de consultar cota. Argon exige `argon: true`.
Medida ausente fica atrás de qualquer saldo conhecido, inclusive zero;
continua desconhecida e não autoriza chamar o modelo. Empates preservam a
ordem do catálogo. Cada conta tem cache de cota próprio. O registro inclui
`conta`; as medidas por modelo também identificam a conta consultada.

`jangada-agente` escolhe a conta ao criar uma sessão nova com catálogo. Vale,
nesta ordem: `--conta-agy NOME`, `JANGADA_AGY_CONTA` do ambiente, ou a conta
que confia na pasta da tarefa e tem o maior saldo conhecido do grupo `gemini`.
O saldo conhecido é a medida mais recente da conta entre o `cotas.json` e o
`cota_depois` das linhas de `delegacoes.jsonl` com modelo `gemini` (sem Argon),
mesmo vencida: ela só ordena as contas, e quem autoriza chamar o modelo
continua sendo o `jangada-delegar`. Conta sem medida fica atrás de qualquer
saldo conhecido; empate, ou nenhuma medida, mantém a ordem do catálogo. Se
nenhuma conta confia na pasta, vale a primeira do catálogo. A escolha só lê
arquivos do estado: não chama o agy nem a rede, e não roda
`jangada-router cotas --atualizar`. Nome inexistente, em opção ou ambiente,
recusa antes de criar o worktree. A abertura imprime
`conta do agy: NOME (gemini NN%, medido às HH:MM)` ou
`conta do agy: NOME (sem medida)`.

A conta escolhida vai ao `jangada-isolar --conta` e ao campo `conta_agy` do
registro protegido da sessão (`revisoes/SESSAO.json`). Reabrir uma sessão
que existe só anexa o tmux, com a conta registrada e sem nova escolha; a
opção `--conta-agy` e `JANGADA_AGY_CONTA` só valem para sessão nova: na
retomada, mesmo com nome inexistente, o pedido é ignorado com aviso e a sessão
anexa com a conta registrada. O `jangada-agentes --restaurar` passa ao
`jangada-isolar --conta` o `conta_agy` do registro protegido, sem nova escolha
e sem olhar o ambiente nem o saldo de hoje; se a conta saiu do catálogo, recusa
sem executar nada. Registro sem `conta_agy` (sessão antiga) e instalação sem
catálogo seguem como antes. A sessão monta uma conta só, até o fim; trocar de
conta no meio dela não é suportado.

`jangada-isolar --conta NOME -- COMANDO` monta a conta em
`~/.gemini/antigravity-cli` e oculta as pastas originais das contas.
O `bin` da conta é criado vazio quando falta, como na principal, e montado em
camada temporária (somente leitura, sem suporte do kernel): o que o agente
gravar ali não persiste. Um `bin` que seja link recusa a abertura.
Sem opção, usa `JANGADA_AGY_CONTA` ou a primeira conta do catálogo.
Dentro de uma sessão isolada, somente a conta montada participa da seleção;
pedir outra conta com `--conta` recusa antes de ler seu cache ou chamar o agy.
A seleção também chega à leitura e à implementação privadas da MOD-03:
com catálogo, o arquivo `antigravity-oauth-token` da conta é montado somente para leitura.
Esses executores escondem a casa; a pasta de cada conta que fica fora dela recebe um `tmpfs`,
e só o login e a pasta `builtin` da conta escolhida voltam, por montagens explícitas.
Sem catálogo, os argumentos e a autenticação desses executores ficam iguais aos da base.
Renovar o login exige agir fora desses executores.
A confiança é conferida por conta; o delegador não cria autorização.
Na abertura ou retomada, todas as contas são conferidas; o aviso de confiança
pendente nomeia a conta, e a frase de que delegação e revisão pelo agy ficam
indisponíveis só sai quando nenhuma conta confia. Quando o dono aceita
abrir o agy para responder à pergunta de confiança, ele abre pela conta
correspondente, com `jangada-isolar --conta NOME -- agy`.
Ao preparar ou encerrar um worktree sem conta explícita, os ajustes de
confiança existentes são aplicados a todas as contas cadastradas. A adição
exige que a raiz já seja confiável naquela conta.

`jangada-migrar` oferece copiar `conta1` e `conta2` do estado do Catamarã.
Copia a subpasta `antigravity-cli` de cada conta. Exige confirmação em terminal
e pergunta quais contas têm Argon. Sem terminal ou com recusa, apenas informa
e permite as migrações seguintes; em simulação, apenas informa.
Para importar depois, o dono executa em terminal:

```sh
bash "$JANGADA_CORE_PATH/migrations/202610241200-importar-contas-agy.sh"
```

Links dentro de `antigravity-cli` (como o `cli.log` que o agy recria a cada
execução) não são seguidos nem copiados, e a migração lista os pulados pelo
caminho relativo. Arquivo especial (fifo, soquete, dispositivo) ou link na
própria pasta da conta recusa a importação.

Catálogo ou destino existente são preservados. Nada é movido ou apagado
na origem.

## Avaliação controlada do Ollama

`jangada-avaliar-ollama` executa três repetições de cada caso pelo
`jangada-delegar leitor --destino local --capacidade leitura_documental`.
Aceita `--repeticoes N`, de 1 a 10, e `--saida PASTA`, dentro da pasta atual.
Usa apenas fontes sintéticas geradas
para a execução, sem autorização de envio remoto.

Os casos são extração de fatos, informação ausente e documento dividido.
O último usa contexto de 3.000 tokens e exige registros de pelo menos duas
fatias e consolidação determinística. Os casos usam `--extrair`.
O gabarito fica no avaliador, fora do pedido
enviado ao modelo. Cada campo exige valor do tipo esperado e referência à
linha correspondente; informação ausente exige valor e referência nulos.

As fontes, respostas, erros e medições ficam numa pasta própria em
`$JANGADA_ESTADO/avaliacoes-ollama/`. O `resultado.json` é atualizado após
cada repetição; `concluida: false` identifica uma execução incompleta.
Ele registra modelo, contexto, tempo, chamadas locais, omissões e
divergências do gabarito. O resumo conta respostas conformes, recusas e
variantes interpretáveis, ignorando formatação e caminhos equivalentes.
Resposta estável e errada continua divergente.
As marcas de jogos e memória de vídeo continuam sendo lidas do estado
original. Recusas por essas proteções não medem a qualidade do modelo.
Cada repetição respeita a trava compartilhada do Ollama; vaga ocupada
recusa sem chamar o modelo. O consumo conhecido de tentativas recusadas
também aparece no resultado.

O comando sai com código 0 quando a avaliação termina, inclusive com
recusas ou divergências. Isso não aprova o modelo, não altera o roteamento
nem substitui a conferência do principal. Os casos medem leitura em formato
JSON e não avaliam redação livre ou documentos reais. Não há comparação de
tempo com Claude ou Codex nesta avaliação.

## Destino local

O destino `local` do `jangada-delegar` despacha tarefas de leitura a um modelo
executado no Ollama na máquina local. Esse destino não gasta cotas externas
e mantém os dados locais.

Para evitar alucinações e desperdício de contexto, o destino local atende
exclusivamente os papéis `leitor` e `redator`; os demais papéis recusam o
destino local com `capacidade_incompativel`, sem chamar o Ollama. A falha local
(Ollama fora, modelo ausente, jogo, memória, contexto, fatias, vaga ou tempo)
recusa com código 4 e fica registrada no destino local, sem passar ao agy. O
script lê e extrai os
arquivos indicados (`--arquivos`), numerando linhas ou páginas, e envia texto
puro ao modelo. O modelo não possui ferramentas de terminal. O `leitor` roda com
temperatura zero, para que a mesma entrada dê a mesma resposta; o `redator`
mantém a temperatura padrão do modelo. Quando o conteúdo cabe em uma fatia, o
pedido do `leitor` termina com uma regra que exige a citação de cada
afirmação, com um prefixo real do documento como exemplo.

Um argumento `ARQUIVO:INI-FIM` envia só essas linhas, com a numeração do
arquivo, e pode se repetir para o mesmo arquivo:

```bash
jangada-delegar leitor "onde num_ctx é enviado?" --destino local \
  --arquivos bin/jangada-delegar:600-640 testes/delegar.sh:296-360
```

O argumento que existe como arquivo vale inteiro, o que cobre nomes com
dois-pontos. Faixa invertida ou além do fim do arquivo é recusada. A faixa
não vale para PDF nem com `--capacidade`.

### Medições e escolha do modelo

Observação pontual realizada em 29/09/2026 numa NVIDIA GeForce RTX 4060 (8 GB de memória de vídeo, driver proprietário 580.126.09, área de trabalho Hyprland ocupando ~2,4 GB e ~5,6 GB disponíveis para o Ollama):

- Método: chamadas diretas ao endpoint `/api/chat` do Ollama 0.34.4.
- Medição de tempo: campos `eval_count`, `eval_duration`, `prompt_eval_count` e `prompt_eval_duration` do JSON retornado.
- Memória: inspeção por `/api/ps` e `nvidia-smi`.

| Modelo | Contexto (`num_ctx`) | Memória total | Memória de vídeo | Transbordo CPU | Geração (t/s) | Avaliação de prompt (t/s) |
|---|---|---|---|---|---|---|
| `qwen3:8b` | 8192 | 6,12 GiB | 5,03 GiB | 1,09 GiB | 33,2 | ~212 |
| `qwen3:8b` | 4096 | 5,56 GiB | 5,08 GiB | 0,48 GiB | 44,9 | ~238 |
| `qwen3:4b` | 16384 | 4,75 GiB | 4,75 GiB (100%) | 0 | 86,2 | ~3.600 |
| `qwen3:4b` | 8192 | 3,61 GiB | 3,61 GiB (100%) | 0 | 85,6 | ~3.691 |

Num teste com documento real de 10 páginas (4.098 tokens de prompt), o
`qwen3:4b` avaliou o prompt em 1,11s (3.691 t/s) e gerou 2.992 tokens em
44,27s (67,6 t/s).

A `qwen3:8b` não coube inteiramente na memória de vídeo com a área de trabalho ativa,
com queda substancial de desempenho. A `qwen3:4b` com contexto 8192 coube 100% na GPU
e preservou cerca de 2,0 GB de folga, atendendo a margem mínima de 1,5 GB.

### Configuração e proteção

- `JANGADA_LOCAL_MODELO`: `qwen3:4b`.
- `JANGADA_LOCAL_CTX`: `8192`.
- `JANGADA_LOCAL_VRAM_MIN`: `4000` (MiB livres exigidos no `nvidia-smi` quando
  presente; a memória do modelo já residente no Ollama é somada à livre).
- `JANGADA_LOCAL_KEEP_ALIVE`: `2m` (descarrega o modelo rapidamente para
  liberar memória de vídeo aos jogos).
- `JANGADA_LOCAL_ESPERA`: `30` (segundos de espera pela trava de concorrência).
- `JANGADA_LOCAL_FATIAS_MAX`: `5` (limite de fatias para documentos que excedem o contexto).
- `JANGADA_CONVERSA_CTX`: o valor de `JANGADA_LOCAL_CTX` (contexto da Conversa de
  Pescador, `jangada-conversa`; a delegação local não o lê).
- `JANGADA_OLLAMA_URL`: `http://localhost:11434` (endereço da API do Ollama).
- Concorrência e modelo de ameaça: uma vaga exclusiva por chamada controlada por trava
  exclusiva (`flock`) em `$JANGADA_ESTADO/local.lock`, obtida antes das checagens de
  memória e de processos. Como o arquivo de trava é gravável pelo agente dentro do isolamento,
  um agente hostil pode segurar o `flock` indefinidamente; o pior efeito é negação de serviço
  local para as próximas delegações, sem vazamento ou execução de código fora do isolamento.
- Proteção de jogos e isolamento: fora do isolamento, verifica `pgrep -f 'reaper SteamLaunch'`
  e `nvidia-smi`. Na sessão isolada (`jangada-isolar`), como `pgrep` e `nvidia-smi` não conseguem
  inspecionar o host diretamente pelo namespace de PID e pela falta de nós de GPU, o host grava
  marcas com carimbo de data/hora em `$JANGADA_ESTADO/marcas/vram-livre` e `$JANGADA_ESTADO/marcas/jogo-ativo`
  na inicialização e as renova conforme `JANGADA_MONITOR_INTERVALO` (padrão de 30 segundos). Um
  intervalo configurado perto ou acima de 120 segundos faz o `jangada-delegar` recusar por marca
  expirada. O script lê essas marcas apenas sob `JANGADA_ISOLADO=1` e descarta marcas com mais de
  120 segundos. A ausência de `jogo-ativo` depende do host estar vivo para criá-la quando um jogo
  abre; caso o host morra, a expiração da marca de VRAM livre garante a recusa se o modelo não
  estiver residente. Se a memória não puder ser verificada e o modelo não estiver residente, a
  chamada é recusada por segurança.
  Se o `nvidia-smi` devolver texto de erro na saída padrão, esse texto é
  descartado antes de ler a marca do host. A marca recente continua sujeita
  ao limite de memória; uma marca expirada não libera a delegação.
- Falhas e privacidade: em qualquer falha (Ollama inacessível, modelo ausente,
  jogo aberto, memória insuficiente ou contexto estourado), o comando recusa com código 4
  informando o bloqueio, sem redirecionar dados para a nuvem. O protocolo
  da sessão orienta o agente a consultar o usuário antes de recorrer ao Claude em
  documentos confidenciais.

## Modelo operacional de projetos

`jangada-projeto --projeto PASTA cadastrar` cria o registro do projeto.
Com `--politica ARQUIVO.json`, aplica restrições de dados, provedores,
orçamento e contexto mínimo da revisão. Sem política, permanecem as
autorizações atuais; nenhum destino novo é liberado.

```sh
jangada-projeto --projeto "$PWD" atividade --titulo "Auditoria" \
  --objetivo "Conferir a configuração" --criterio "Fontes conferidas"
jangada-projeto --projeto "$PWD" consultar
jangada-projeto consultar --todos
```

A atividade devolve `atv-…`. O plano pode usar esse valor em `atividade` e
acrescentar `criterios_aceite`, `entradas`, `saidas` e `contexto`, como listas
de textos. `contexto` contém caminhos de arquivos do projeto; eles passam
pela mesma conferência e são enviados com as fontes. Tarefas importadas
continuam imutáveis. `jangada-agente --atividade ID --tarefa-id ID` registra
vínculos opcionais; não reserva nem conclui a tarefa da fila.

Cada reserva cria `exe-…`, inclusive quando termina sem chamada ao modelo.
Expiração encerra a execução com consumo desconhecido. Eventos, delegações
e validações podem apontar para a execução; esse vínculo não é aprovação.

Uma política pode conter:

```json
{"dados":"remoto_permitido","provedores":["ollama","agy"],
 "orcamento":{"chamadas":8,"periodo_segundos":86400},
 "revisao_minima":{"1":{"independente":true,"contexto":"diff"}}}
```

As reservas comprometem o saldo de chamadas na mesma transação SQLite.
Consumo desconhecido bloqueia nova execução automática. Sessões interativas
não garantem teto de consumo e são recusadas quando há orçamento de projeto.
Cadastrar teto de chamadas também recusa consumo desconhecido no período;
a política anterior permanece. Consumo desconhecido nunca é convertido em zero.
Se a sessão do tmux desaparecer sem passar pelo encerramento, sua execução
pode continuar `RUNNING` no registro. Para encerrar esse registro por nome,
rode fora do isolamento:

```sh
jangada-projeto --projeto /caminho/do/projeto sessao-encerrar NOME
```

O comando marca as execuções `RUNNING` desse nome como `CANCELLED`, sem
concluir tarefas da fila. O consumo permanece desconhecido. O cadastro de
orçamento e novas reservas continuam bloqueados até o fim da janela contada
do encerramento: `periodo_segundos`, ou 86.400 segundos quando omitido.
As mensagens de recusa indicam o comando e a espera necessária.

Revisão independente na fila está implementada somente para intermediários
de risco 1, com contexto `diff`, no fluxo de supervisão automática. O parecer
precisa de execução comprovada, com provedor e modelo diferentes do autor.
O cadastro recusa exigências para outros riscos, contexto `repositorio` ou
políticas sem dois provedores autorizados, incluindo um revisor remoto.
A tarefa precisa de `intermediaria`, `supervisao_automatica` e `permitir_remoto`
verdadeiros e ao menos duas chamadas. Esse fluxo não aceita `criterios_aceite`
manuais nem `amostragem`. Se a dupla depender de Codex, a tarefa também precisa
de `permitir_codex`. As permissões de execução e a opção de supervisão ainda
precisam ser fornecidas ao executor; cota, modelo configurado e disponibilidade
podem deixar a tarefa aguardando supervisão para retomada posterior. Opções
de execução que desabilitam essa revisão são recusadas antes de reservar
a tarefa ou chamar o autor.

Cadastro ou mudança de política confere tarefas pendentes, e a importação
recusa planos incompatíveis sem inserção parcial. Registros antigos continuam
legíveis, mas combinações incompatíveis são recusadas antes de reservar outra
execução. Parecer humano sem identidade registra independência desconhecida
e não atende essa exigência. Informar o nome de um modelo no comando de revisão
também não comprova execução. A revisão independente geral de tarefas de maior
risco ou com contexto do repositório ainda precisa ser implementada.
Um teto `custo_estimado` também recusa execuções de modelos: os executores
atuais não fornecem limite de consumo comprovável antes da chamada.
Conferências determinísticas locais continuam possíveis, sem consumir chamadas.

`rotear ID --modo manual|assistido|automatico_supervisionado` consulta
candidatos e motivos sem chamar provedores. Manual recebe `--executor`;
assistido exige também `--confirmar`. Automático exige disponibilidade
verificada e mantém os limites atuais de risco e qualidade.
Os modos são independentes dos perfis `balanced`, `quality` e `offline`.
Para executar uma escolha na fila:

```sh
jangada-executar --tarefa T1 --modo assistido --executor local --confirmar
```

Revisões da fila exigem execução fora do isolamento. Chamadas antigas
continuam como revisão humana explícita. `--revisor`, `--modelo-revisor` e
`--contexto-revisao` identificam um parecer externo; o backend recusa autor
e revisor iguais, inclusive os nomes alternativos do Codex, e identidades
de modelo desconhecidas. Isso não executa um modelo nem substitui
`jangada-validar` para entrega de código.

Tarefas com critérios exigem `--parecer` em JSON, vinculando tarefa e artefato:

```json
{"tarefa":"T1","artefato_sha256":"SHA_COMPLETO",
 "criterios":[{"criterio":"Fontes conferidas","resultado":"APROVADO",
               "justificativa":"O conteúdo foi comparado às fontes."}]}
```

Cada critério precisa aparecer na ordem declarada, com resultado `APROVADO`
ou `REVISAR` e justificativa. Aprovação exige todos aprovados; a revisão
registra identidades, critérios e o hash do artefato conferido.

Depois de renomear a pasta, use
`jangada-projeto --projeto CAMINHO_ANTIGO reassociar CAMINHO_NOVO`.
O comando exige sessões encerradas, nenhuma reserva ativa e destino sem
estado. Preserva identidade, especificações e hashes; fontes são resolvidas
para a raiz atual em memória e reconferidas antes da execução.

O núcleo em `nucleo/` consulta cópias estáveis do banco e WAL,
sem criar arquivos na origem. Estados da 2.0 e da atividade são calculados.
As ações chamam `bin/`; integração conserva a confirmação dos SHA e a
revisão protegida do backend. O painel lê a coleta do núcleo em `nucleo.json`;
a Central consulta projetos e fila diretamente, sem carregar os catálogos.

## Fila persistente de projetos

`jangada-fila --importar plano.json` importa tarefas sem executar os dados
do plano. `jangada-fila --json` permite consultar o estado. Cada projeto,
identificado pela raiz do Git ou por `--projeto PASTA`, tem um banco separado em
`$JANGADA_ESTADO/agentes/projetos/HASH/tarefas.sqlite`.
Fora do Git, a pasta atual identifica o projeto. Subpastas do mesmo
repositório consultam a mesma fila.

```json
[
  {
    "id": "T1", "papel": "leitor", "capacidade": "leitura_documental",
    "pedido": "Extraia as regras de roteamento", "risco": 1,
    "qualidade": "medium", "fontes": ["fontes/documento.md"],
    "requisitos": ["Autorizações", "Limites"], "max_tentativas": 2
  },
  {
    "id": "T2", "papel": "leitor", "capacidade": "resumo_curto",
    "pedido": "Prepare o resumo final", "risco": 2,
    "qualidade": "high", "fontes": ["fontes/documento.md"],
    "dependencias": ["T1"]
  }
]
```

Uma importação repetida com fontes inalteradas preserva resultados. Alterar
a tarefa ou o conteúdo de uma fonte exige outro identificador. Ciclos e dependências inexistentes são recusados antes
de gravar o plano. As fontes precisam estar dentro do projeto; caminhos
resolvidos e resumos SHA-256 são preservados na especificação.

O campo opcional `prioridade` aceita, nesta ordem, `critical`, `high`,
`normal`, `low` e `background`. Sem esse campo, conserva `normal` e a
ordem anterior: data de criação, depois identificador. A fila mostra a
prioridade declarada na última coluna.

Na reserva, tarefas prontas são ordenadas pela prioridade efetiva. Uma
tarefa em fila transmite sua prioridade aos antecessores também em fila,
para antecipar os pré-requisitos de um trabalho importante. A transmissão
é transitiva e para em tarefas pausadas, em revisão ou fora da fila.
Um antecessor pronto pode ser antecipado mesmo quando outra dependência
do trabalho importante aguarda revisão ou provedor. Assim, seus demais
pré-requisitos avançam durante a espera; o descendente continua impedido
até a conclusão de todas as dependências.
Dependências continuam exigindo conclusão; a prioridade não interrompe
uma reserva existente nem altera risco, qualidade, permissões ou orçamento.
O evento `reservada` registra as prioridades declarada e efetiva.

`jangada-task T1 pausar`, `retomar`, `cancelar` e `repetir` controlam tarefas
fora de execução. A repetição mantém o limite total de tentativas. Uma
reserva expirada exige conferência antes de repetir; outro executor não
pode concluir a reserva anterior. Os artefatos usam resumo SHA-256 do conteúdo
e são gravados em UTF-8, com substituição atômica. Dependências que falharam
ou foram canceladas deixam suas tarefas dependentes em `BLOCKED`, com motivo.

Uma saída de modelo fica em `REVIEW_REQUIRED`, sem liberar dependências.
Após conferir o artefato e as fontes, o responsável registra
`jangada-task T1 revisar --aprovar --parecer "Conferido nas fontes"` ou
`--reprovar`. A revisão aceita somente o mesmo artefato preservado. Esse
registro é uma anotação editável do projeto. O comando não autentica o
revisor nem impede que o autor registre sua própria aprovação. Portanto,
`COMPLETED` não comprova revisão independente e não autoriza integração,
envio externo ou operação irreversível. A revisão da fila não substitui
`jangada-validar`.

`jangada-fila --revisao` lista as tarefas em `REVIEW_REQUIRED`, com
capacidade, executor, modelo e caminho do artefato preservado. Depois de
conferir cada artefato, um parecer comum vale para várias tarefas:
`jangada-task T1,T2,T3 revisar --aprovar --parecer "Conferidos nas fontes"`.
O lote grava todas as revisões ou nenhuma: uma tarefa ausente, repetida ou
fora de `REVIEW_REQUIRED` recusa o comando inteiro.
Tarefas em revisão não podem ser pausadas para contornar a conferência.

### Execução da fila

`jangada-executar --limite 10` executa até dez tarefas elegíveis em sequência.
Para modelos, usa `jangada-delegar`, sem interpretar comandos no plano. Atende `leitor`
com `leitura_documental`, `resumo_curto` ou `analise_documental`, risco até 2
e qualidade `low` ou `medium`. Tarefas que exigem um principal aguardam em
`WAITING_REVIEWER`; capacidades sem adaptador aguardam em `WAITING_PROVIDER`.

As fontes são conferidas antes e depois da chamada. Artefatos das dependências
concluídas entram como fontes adicionais, com conferência de integridade.
O relatório completo passa pela verificação de referências e requisitos;
depois fica em `REVIEW_REQUIRED`, sem aprovação automática do conteúdo.

`max_chamadas` e `tempo_total` valem para todas as tentativas da tarefa.
Interrupção ou resposta sem contagem confiável impede repetição automática.
Recusa antes de qualquer chamada não consome tentativa. Cota insuficiente
ou desconhecida mantém `WAITING_QUOTA` até uma retomada explícita.

`jangada-executar --paralelo 3 --limite 12 --permitir-remoto` divide o limite
entre três processos, de 2 a 4. Cada processo reserva uma tarefa diferente
da mesma fila, e as dependências continuam valendo: só entra tarefa cujas
dependências já concluíram. A opção exige `--permitir-remoto` e perfil com
nuvem, porque o modelo local tem uma vaga só; não combina com `--acompanhar`.
Ela não autoriza envio: cada tarefa ainda precisa de `permitir_remoto: true`.

- Tarefa que cai no modelo local ocupado espera a vaga por
  `JANGADA_LOCAL_ESPERA` segundos. Esgotada a espera, fica em
  `WAITING_PROVIDER` sem gastar tentativa e volta com `jangada-retomar`.
- O Codex econômico também tem uma vaga: a segunda chamada é recusada.
- A cota do agy é lida antes de cada chamada, sem reserva. Chamadas
  simultâneas podem ser liberadas pela mesma leitura; por isso o teto de
  quatro processos.
- Ctrl+C, término (`SIGTERM`) e fechamento do terminal (`SIGHUP`) são
  repassados uma vez a cada processo, que encerra a tarefa em curso como na
  execução em sequência. Se o comando recebe `SIGKILL`, vigias locais detectam
  o fechamento do canal privado do controlador e encerram os descendentes,
  inclusive clientes que abriram outra sessão ou grupo de processos.
- Se um processo falha, o comando imprime os resultados dos demais e sai
  com código 2. Consulte `jangada-fila` antes de repetir.

### Tarefas dos agentes principais na sessão aberta

Claude e Codex podem assumir uma tarefa de alta qualidade ou risco 3
na própria sessão, sem abrir outra chamada de modelo:

```sh
jangada-task T5 assumir --executor codex
# Use o identificador dono devolvido na reserva.
jangada-task T5 entregar --dono IDENTIFICADOR --arquivo work/sintese.md
jangada-task T5 revisar --aprovar --parecer 'Conferido por revisão separada'
```

`assumir` devolve a especificação, os caminhos e resumos dos artefatos das
dependências, o identificador da reserva e seu prazo. Exige dependências
concluídas, fontes inalteradas e orçamento disponível. Aceita tarefas em
fila, em `WAITING_PROVIDER` ou em `WAITING_REVIEWER`. Não assume tarefas
pausadas, em espera de cota, reservadas, com consumo desconhecido ou risco 4.

O agente executa o pedido e grava um relatório UTF-8 dentro do projeto.
As fontes importadas continuam imutáveis; alterações de código exigem
outro fluxo. `entregar` confere reserva, integridade das fontes e dependências,
referências e requisitos. Preserva o relatório completo, limitado a 1 MiB,
em `REVIEW_REQUIRED`; falha de formato ou integridade gera `REVISION_REQUIRED`.
Recusas antes da validação do conteúdo, como arquivo fora do projeto,
especial, simbólico, acima do limite ou sem UTF-8 válido, mantêm a reserva
para corrigir o arquivo e entregar novamente dentro do prazo. A recusa
por codificação fica registrada, sem copiar bytes inválidos para o estado.
O prazo é conferido novamente ao persistir: se expirar durante a validação,
a entrega inteira é recusada, sem gravar artefato ou conclusão no estado.
O arquivo de relatório original permanece no projeto.
Somente a revisão separada libera os dependentes. Esses comandos não
publicam, enviam, fazem integração de código ou substituem `jangada-validar`.

`--executor` e o `--modelo` opcional são declarações para rastreabilidade,
sem autenticar a identidade ou conferir autoridade. Os dados da tarefa
nunca autorizam comandos externos. A reserva respeita o tempo restante
da tarefa; após expirar, uma entrega é recusada. Não há medição confiável
das chamadas e tokens da sessão aberta: o consumo permanece desconhecido,
impedindo uma repetição automática. Este fluxo não inicia agentes em segundo
plano nem aplica uma variante econômica ou premium por conta própria.

### Execução documental principal pelo Codex

Uma tarefa de risco 3 ou qualidade `high` ou `critical` pode executar uma
análise principal por chamada delimitada, sem ferramentas. Configure
`JANGADA_CODEX_PRINCIPAL_MODELO` com o identificador do modelo disponível
na sua conta. O padrão vazio desativa essa execução; não há modelo implícito.
O nome configurado não comprova qualidade: o relatório exige revisão separada.

```sh
jangada-task T5 executar-principal --executor codex --permitir-remoto --permitir-codex
```

A tarefa também exige `permitir_remoto: true` e `permitir_codex: true`,
perfil de delegação `agy`, dependências concluídas e fontes inalteradas.
Aceita capacidades `analise_documental`, `sintese` e `revisao_critica`.
Recusa microtarefas, risco 4, programação e ações externas. Este comando
não faz parte das alternativas econômicas nem da execução automática da fila.
Claude permanece disponível pelo fluxo da sessão aberta.

Antes de gerar texto, consulta a cota real do Codex e respeita
`JANGADA_CODEX_COTA_MIN`, com reserva de 25% por padrão. Usa a mesma cota
e trava da variante econômica; modelos distintos não têm cotas independentes.
Cota desconhecida ou insuficiente produz `WAITING_QUOTA`, sem consumir
tentativa de geração. Após atualizar a saúde do provedor, retome a tarefa
com `jangada-task T5 retomar` e solicite novamente a execução principal.
Pausa, indisponibilidade ou trava ocupada recusam o comando antes da reserva.

O orçamento da tarefa inclui chamadas e tempo anteriores. Fontes e artefatos
das dependências são enviados como texto UTF-8 numerado, sujeito ao limite
de contexto do adaptador. PDF precisa de extração prévia. A execução usa
credenciais copiadas para uma pasta privada temporária, sem renovação,
ferramentas ou gravação nas fontes. Interrupção com consumo desconhecido
impede repetição automática. Chamadas e tokens confirmados ficam nas métricas.

O relatório completo passa pelos critérios de referências, requisitos e
integridade e fica em `REVIEW_REQUIRED`. Saída reprovada fica preservada em
`REVISION_REQUIRED`. Somente a revisão separada libera dependentes. A execução
principal não aprova a entrega final nem substitui `jangada-validar`.

### Supervisão automática de relatórios intermediários

Uma tarefa documental de risco 1 pode declarar `intermediaria: true` e
`supervisao_automatica: true`. Exige papel `leitor`, qualidade `low` ou
`medium` e uma das capacidades documentais já integradas. Tarefas finais,
de risco maior ou alta qualidade não aceitam essa política.

```sh
jangada-executar --supervisionar --permitir-remoto
jangada-executar --acompanhar --supervisionar --permitir-remoto
```

A opção do comando não autoriza envio por si só: a tarefa também precisa
de `permitir_remoto: true`, e o perfil da sessão precisa permitir nuvem.
O supervisor é agy ou Codex econômico, sempre diferente do autor. Codex
exige modelo explícito e autorização do comando e da tarefa, como na execução.
Ollama pode produzir o relatório, mas nunca fornece a aprovação semântica.

Esse papel existe nos padrões de Claude e agy, com ferramentas somente
de leitura; o adaptador Codex recebe o mesmo pedido sem ferramentas.
O agy precisa encontrar `supervisor` no catálogo, como os demais papéis.
Uma instalação anterior sem esse papel recusa a revisão até ser atualizada.
O supervisor recebe objetivo, fontes e relatório como dados. Confere
fidelidade, completude e extrapolações em JSON estrito, com justificativas
e referências. O parecer identifica a tarefa e o SHA-256 do relatório.
Somente todos os critérios `PASS`, sem observações e com referências
conferidas, permitem `COMPLETED` e liberam dependências intermediárias.
Erros exigem correção; ambiguidades, parecer inválido ou consumo desconhecido
mantêm revisão pendente. Não se repetem pareceres inconclusivos até obter aprovação.

Autor e supervisor compartilham o limite de chamadas e o tempo da tarefa.
As retomadas de supervisão também compartilham `max_tentativas`, cujo padrão
é 2. Uma retomada que inicia chamadas usa a segunda tentativa; recusas com
zero chamadas não gastam tentativa. Esgotar esse limite deixa o relatório
para revisão manual, sem repetir o autor.
Sem quota ou supervisor autorizado, o relatório completo permanece salvo.
`--supervisionar` retoma somente a revisão quando o provedor estiver disponível;
`--acompanhar` consulta a saúde e aguarda a recuperação dentro do prazo configurado.
As fontes e dependências são conferidas novamente antes da conclusão.

O parecer completo fica no resultado da tarefa. Referências ao relatório
temporário são vinculadas pelo SHA-256 ao artefato preservado. As métricas
distinguem pareceres automáticos, revisões manuais e esperas de quota. `esperas_supervisao`
conta tentativas que aguardaram um supervisor, separadas dos pareceres.
Uma aprovação automática
não alimenta o histórico usado para sugerir redução da amostragem.
Essa supervisão não aprova entregas finais, publicação, alterações de produção
ou a entrega de código do próprio Jangada. `jangada-validar` continua obrigatório.

### Conferência determinística de JSON

A capacidade `validacao_json` executa um critério local de formato, sem
modelos, comandos das fontes ou acesso à rede. Exige papel `verificador`,
risco zero e nenhum `requisito` adicional. O `pedido` descreve a tarefa;
não acrescenta critérios executáveis. Para importar uma conferência:

```json
[
  {
    "id": "J1", "papel": "verificador", "capacidade": "validacao_json",
    "pedido": "Confira a sintaxe dos dados JSON", "risco": 0,
    "qualidade": "medium", "fontes": ["dados.json"]
  }
]
```

O critério aceita raízes JSON de qualquer tipo, em UTF-8. Rejeita chaves
repetidas, valores não finitos, substitutos Unicode isolados e texto após
o valor. Limita a profundidade a 64 níveis, as fontes a 32 arquivos,
o tamanho a 1 MiB por arquivo e a 4 MiB no total. Recusa arquivos
especiais e links simbólicos no último componente do caminho. Diretórios
intermediários podem ser links; o executor verifica antes da leitura que
o destino resolvido permanece dentro do projeto.

O relatório preserva caminho, SHA-256, tamanho e o critério executado.
Antes de gravar `COMPLETED`, o estado repete a conferência das fontes
importadas e compara o relatório. Uma aprovação declarada na saída não
substitui esse critério. A conclusão libera dependências automaticamente.

O campo opcional `esquema` indica um arquivo do projeto com um esquema
JSON, aplicado a todas as fontes da tarefa:

```json
{
  "id": "J2", "papel": "verificador", "capacidade": "validacao_json",
  "pedido": "Confira os dados pelo esquema", "risco": 0,
  "qualidade": "medium", "fontes": ["dados.json"], "esquema": "esquema.json"
}
```

A importação guarda o caminho e o SHA-256 do esquema; alterá-lo depois
impede a conclusão. O esquema segue os mesmos limites de leitura das fontes.
São aceitas as palavras-chave `type`, `enum`, `const`, `required`,
`properties`, `additionalProperties`, `items`, `minItems`, `maxItems`,
`minLength`, `maxLength`, `minimum` e `maximum`, além das anotações
`$schema`, `title` e `description`. Qualquer outra, como `pattern`, `$ref`
ou `allOf`, recusa o esquema inteiro: uma regra ignorada aprovaria dados
que o esquema proíbe. Comprimentos contam caracteres Unicode, `integer`
aceita `1.0` e `true` não é igual a `1`. A falha informa o caminho do
primeiro valor fora do esquema, como `$["itens"][2]`, sem copiar o valor.
O relatório registra o critério `sintaxe_json_estrita_e_esquema` e o resumo
do esquema.

JSON inválido, fora do esquema ou fonte alterada deixa `REVISION_REQUIRED`. Risco maior,
papel incompatível ou requisitos adicionais deixam `WAITING_REVIEWER`.
Consumo anterior desconhecido impede repetição automática; os limites de
tempo e tentativas continuam persistidos. O contador de chamadas a modelos
permanece zero. Funciona também no perfil `offline`.

Esse critério comprova somente o formato e, com `esquema`, a estrutura
declarada. Não valida fidelidade documental, conteúdo ou autorização para
operações externas.
Os relatórios de modelos continuam sujeitos à revisão de conteúdo, manual
ou automática quando a política intermediária permitir.

Perfis disponíveis:

| Perfil | Seleção |
|---|---|
| `balanced` | política existente por capacidade |
| `quality` | agy explícito, com revisão do conteúdo pendente |
| `offline` | somente local, sem permissão remota |

Com a política padrão contendo somente agy, `offline` não tem executor
elegível. Uso local exige política ou destino explicitamente escolhidos.

Envio remoto exige `--permitir-remoto`, `permitir_remoto: true` no plano e
perfil de sessão compatível. Os perfis não ampliam as permissões da sessão.
O destino opcional `codex-economico` exige também `--permitir-codex`,
`permitir_codex: true` no plano e modelo econômico explicitamente configurado.
Consulte [as restrições do executor Codex](codex.md#executor-econômico).
Nenhum perfil chama Claude como trabalhador externo. Os registros
de cada tentativa ficam no resultado da tarefa e no histórico persistente.

### Disponibilidade dos provedores e retomada

`jangada-router status` consulta as observações compartilhadas entre projetos,
em `$JANGADA_ESTADO/agentes/runtime/`. Estados expirados aparecem como
`UNKNOWN`; o término de uma espera não declara o provedor disponível.
Pausas e observações ficam persistidas, com data, motivo e histórico.
São dados operacionais graváveis pela sessão. A pausa não resiste a um
agente hostil: ele pode alterar o banco ou chamar os controles diretamente.
Esses registros não comprovam autorização externa nem substituem as
restrições de isolamento e de envio remoto. Os controles da fila não
impedem uma chamada direta ao `jangada-delegar` fora dela.

`jangada-provedor pausar agy` impede novas delegações pelo executor da fila.
`jangada-provedor ativar agy` remove a pausa e exige nova verificação.
Uma espera `COOLDOWN` ainda vigente é preservada ao pausar ou ativar.
Três falhas de serviço registradas desde a última observação `AVAILABLE`
geram `COOLDOWN` por 900 segundos. Saídas com erro de conteúdo não são
tratadas como falhas de rede.

`jangada-router status --atualizar` consulta os modelos instalados no Ollama
e lê a cota recente do agy. Com `--permitir-remoto` e sessão que permita
agy, pode consultar `/usage` quando o registro estiver ausente ou expirado.
Essa consulta envia somente o comando de metadados, sem as fontes da tarefa.
Roda com isolamento do agy, entrada fechada e fora da pasta do projeto.
Cota ausente, inválida ou expirada permanece desconhecida. A reserva segue
`JANGADA_DELEGAR_COTA_MIN`, como na delegação existente.

O estado `UNKNOWN` permite as verificações do adaptador, sem comprovar
disponibilidade. Antes de gerar um relatório remoto, o `jangada-delegar`
precisa confirmar a cota. Provedores pausados ou em espera são descartados
com motivo estruturado e zero chamadas. A disponibilidade não comprova
qualidade nem amplia permissões.

`jangada-retomar` recoloca na fila tarefas em `WAITING_QUOTA` ou
`WAITING_PROVIDER` que tenham executor disponível, orçamento e tentativas
restantes. Confere permissão remota, perfil e capacidade. As fontes são
conferidas pelo executor antes e depois da execução.
Não retoma tarefas pausadas, em revisão ou com consumo desconhecido.
Para atualizar os provedores e executar a fila após a retomada:

```sh
jangada-retomar --atualizar --executar --limite 10 --permitir-remoto
```

O comando faz uma passagem; não instala um serviço permanente.

### Acompanhamento da fila

Para manter a fila em execução enquanto houver trabalho ou espera recuperável:

```sh
jangada-executar --acompanhar --duracao 28800 --intervalo 60 --limite 100 --permitir-remoto
```

O acompanhamento roda em primeiro plano. Por padrão, dura até oito horas,
com intervalo de 60 segundos e limite de 100 execuções. `--duracao` aceita
1 a 86400 segundos, `--intervalo` aceita 1 a 3600 e `--limite` aceita 1 a 1000.
Sem `--acompanhar`, o comando mantém a passagem única e o limite padrão de uma tarefa.

O prazo impede iniciar novas tarefas e limita a espera pelo delegado,
pelo supervisor e pelas consultas de disponibilidade ao tempo global restante.
Vale sempre o menor entre esse tempo e o orçamento próprio da tarefa.
O encerramento dos processos e a gravação do estado podem levar tempo adicional.
A consulta de cota do agy encerra também seu grupo de processos ao ser interrompida.
Uma conferência determinística em andamento termina sua leitura local antes
de registrar o prazo atingido e exigir revisão. Cada execução com chamadas consome uma posição
do limite, inclusive uma falha. Conferências determinísticas iniciadas
também consomem posição, mesmo sem chamadas a modelos. Uma recusa antes
da execução não consome posição. Consumo desconhecido exige revisão antes de repetir.

As esperas por cota ou provedor são retomadas somente com capacidade,
permissões e orçamento restantes. As sondas ocorrem no máximo uma vez
a cada 60 segundos por acompanhamento. Codex exige as mesmas permissões
explícitas da passagem única, inclusive `--permitir-codex` e modelo configurado.
O perfil da sessão continua limitando o envio à nuvem.

O comando registra cada ciclo e o encerramento em linhas JSON na saída.
Uma trava impede dois acompanhamentos simultâneos do mesmo projeto.
Ao pressionar Ctrl+C, ou receber SIGTERM ou SIGHUP, nenhuma outra tarefa é iniciada.
O executor sequencial, assim como o paralelo, encerra seus descendentes
antes de sair. Um vigia local também trata a morte forçada do controlador:
tenta SIGTERM para permitir a limpeza de temporários e, após até dois segundos,
força o encerramento dos filhos restantes. A coleta usa vínculos de parentesco
mantidos pelo kernel Linux, sem usar PIDs vindos de registros graváveis.
O vigia exige Linux com `/proc` e suporte a subreaper; falha ao iniciar o cliente
se não consegue habilitar essa proteção. Não instala serviço de monitoramento.

Reservas automáticas têm uma trava mantida pelo controlador. Ao abrir a fila
com `jangada-fila`, ou iniciar outro executor, o Core confere essas travas
e trata reservas abandonadas, inclusive depois de um reinício da máquina.
Também trata reservas legadas cujo prazo já venceu. Essa recuperação é uma
transação própria e não depende de conseguir reservar outra tarefa.
A tarefa e a execução interrompidas passam para `REVISION_REQUIRED`, com
consumo desconhecido. O prazo, o dono e o comprometimento da reserva são
encerrados, sem aprovar relatórios, converter consumo em zero ou repetir
a tarefa. A recuperação é idempotente e preserva artefatos já registrados.
Consultas somente leitura pelo núcleo não fazem essa recuperação.

Reservas interativas de `jangada-task assumir` continuam válidas após o comando
terminar e são regidas pelo prazo; sua vida não corresponde à do comando curto.
Reservas automáticas anteriores a essa proteção também dependem do prazo.
O desligamento da máquina encerra os processos pelo sistema operacional;
a recuperação do estado ocorre na próxima abertura da fila. Os testes simulam
falhas de processo e transações SQLite interrompidas, não perda física de energia.
Se o próprio vigia for encerrado à força, a coleta de descendentes não é garantida.
Arquivos temporários deixados pelo controlador morto são preservados para
conferência; não há remoção automática de diretórios a partir do estado.
Tarefas aprovadas, pausadas ou em revisão não são retomadas automaticamente.
Quando só restam dependências de revisão ou tarefas sem adaptador, o
acompanhamento encerra. Não aprova relatórios nem instala serviços.

### Revisão por amostragem de relatórios intermediários

Uma tarefa que aceita supervisão automática também pode declarar
`amostragem: true`, com as mesmas exigências: `intermediaria: true`, papel
`leitor`, risco 1, qualidade `low` ou `medium` e capacidade documental.

```sh
jangada-executar --amostrar --permitir-remoto
jangada-executar --amostrar --supervisionar --permitir-remoto
```

Sem a opção do comando ou sem o campo da tarefa, todo relatório continua em
revisão. Com os dois, depois de conferir referências, requisitos e
integridade, o executor aplica a taxa de amostragem do grupo (capacidade,
executor, modelo e risco) descrita em [registro e medição](#registro-e-medição).
O sorteio vem do identificador da tarefa e do SHA-256 do relatório: repetir
a conta dá o mesmo resultado, e o estado refaz o cálculo antes de aceitar
a conclusão.

- Relatório sorteado: segue para o supervisor, com `--supervisionar`, ou
  fica em `REVIEW_REQUIRED`.
- Relatório fora da amostra: fica `COMPLETED` e libera dependentes
  intermediários **sem revisão do conteúdo**. O resultado guarda taxa,
  sorteio e revisões na janela, e o motivo registra que o conteúdo não
  foi conferido.

A taxa só cai abaixo de 100% com 20 revisões manuais do grupo na fila do
projeto; pareceres do supervisor e conclusões fora da amostra não contam.
Relatório produzido pelo Ollama é sempre revisado. O histórico é uma
anotação editável: quem aprova sem conferir reduz a própria amostra. Por
isso a amostragem vale só para relatórios intermediários, não aprova
entrega final e não substitui `jangada-validar`.

## Registro e medição

`jangada-fila --metricas` mostra os indicadores do projeto em JSON. Consulta
o histórico em uma transação de leitura, sem chamar provedores ou importar
tarefas. Não aceita `--importar` na mesma chamada.

O resumo inclui estados, execuções registradas, processamentos confirmados,
recusas sem chamadas, reservas expiradas, repetições solicitadas, retomadas,
chamadas, segundos, tokens disponíveis e revisões aprovadas ou reprovadas.
Um total desconhecido aparece como `null`; os campos `*_confirmados` ou
`*_confirmadas` preservam a parcela conhecida. Reserva expirada torna
consumo e duração desconhecidos.

O custo só é estimado com preços declarados em
`~/.config/jangada/precos.json`, por executor e modelo, na moeda e nos
valores que você informar. O Jangada não traz tabela de preços nem os
deduz do nome do modelo:

```json
{
  "moeda": "USD",
  "precos": {
    "codex-economico": {
      "MODELO": {"entrada_por_milhao": 0.0, "saida_por_milhao": 0.0}
    }
  }
}
```

Substitua `MODELO` pelo identificador registrado em `por_executor` e os
zeros pelo preço por milhão de tokens. Arquivo com outro formato recusa a
consulta. Ausência de preço não é custo zero: sem o arquivo,
`custo_estimado` permanece `null`. Com ele, cada execução entra assim:

- sem chamadas a modelos: custo zero;
- uma chamada do Codex com tokens de entrada e saída e preço declarado:
  tokens vezes o preço;
- qualquer outra: custo desconhecido. Isso inclui agy e Ollama, que não
  informam tokens à fila, cadeias com mais de uma chamada, modelo sem preço
  e reservas expiradas ou em aberto.

Uma execução de custo desconhecido torna `custo_estimado` `null`.
`custo_estimado_confirmado` soma a parcela conhecida e `execucoes_sem_custo`
conta as demais, no total e em `por_executor`. É uma estimativa pelos
tokens registrados: não considera cache, descontos nem assinatura, e não
substitui a fatura do provedor.
Registros sem duração são aceitos por compatibilidade, mas não comprovam
duração zero. O resumo preserva as chamadas informadas; o controle de
orçamento recusa repetição quando a duração é desconhecida.

`por_executor` agrupa pelo executor e modelo registrados no encerramento.
Os campos `*_do_fluxo_*` abrangem toda a cadeia daquela execução, incluindo
alternativas; não atribuem chamadas ou duração individualmente a cada provedor.
Os contadores `chamadas_do_fluxo_desconhecidas` e `duracoes_do_fluxo_desconhecidas`
indicam parcelas não medidas. Reservas expiradas entram em `nao_informado`,
pois não comprovam qual executor chegou a trabalhar.
Reservas ainda em `RUNNING` aparecem em `reservas_em_aberto`, com consumo
e duração desconhecidos. O estado não comprova que o processo continua vivo.
`mudancas_entre_candidatos` conta mudanças de destino na sequência registrada,
inclusive candidatos recusados. Tokens Codex conhecidos entram no total
somente quando representam a única chamada; em cadeias com outras chamadas,
entram na parcela conhecida e o total permanece desconhecido.

`desempenho` separa capacidade, executor, modelo e risco. Considera as últimas
50 revisões de cada grupo, ligadas a uma saída preservada. Conferências
determinísticas concluídas automaticamente não entram na taxa de revisão.
Com menos de 20 revisões, risco acima de 1 ou identidade incompleta, a
amostragem sugerida é 100%. Para os demais grupos, sugere 10% normalmente,
50% com reprovação acima de 5% e 100% acima de 15%.

A taxa é aplicada somente em tarefas com `amostragem: true` executadas com
`--amostrar`; nos demais casos é uma sugestão. `selecionadas_na_amostra` e
`conclusoes_fora_da_amostra` contam os sorteios. Não altera permissões nem
preferências do roteador.
O histórico registra pareceres editáveis; não autentica revisores nem
comprova independência ou qualidade real das respostas.

- Cada chamada do `jangada-delegar`, atendida ou recusada, vira uma linha em
  `delegacoes.jsonl`, com papel, modelo, segundos, código, palavras, cota
  antes e depois e motivo da recusa.
- Os hooks `SubagentStart` e `SubagentStop` do Claude
  (`agentes/claude/hooks.json`, `bin/jangada-hook-claude`) gravam
  `subagente-inicio` e `subagente-fim` em `eventos-agentes.jsonl`, com o id e
  o tipo do subagente.
- Um comando opcional, fora do Core por ora, lê esses registros e as conversas dos
  subagentes. Seu `jangada-subagentes` mostra os indicadores, o resumo de
  uma entrega (`--entrega`, que o `jangada-validar` grava no campo
  `subagentes` do `validar.jsonl`, quando o comando existe) e os registros
  crus (`--registros`). A árvore do painel também é dele.

Os campos de cada arquivo estão em [registros](registros.md).

## Testes

| Arquivo | O que cobre |
|---|---|
| `testes/subagentes.sh` | papéis do Claude e do agy e a instalação deles; hook do leitor no Claude e no agy (papel pela variável, subagente pelo json da conversa, conversa fora do formato, falha do Python) |
| `testes/delegar.sh` | `jangada-delegar` com agy falso: recusas (entre elas o leitor sem o hook no agy), cota, corte do relatório e registro |
| `testes/validar.sh` | o campo `subagentes` e o `subagentes_erro` do `validar.jsonl` |

## Implementador opcional

A exceção à leitura é o papel `implementador`, exclusivo do caminho protegido
de implementação. Ele edita uma cópia sem Git e sem terminal; os outros papéis
continuam sem escrita. Relatório leitor nunca substitui revisão independente.
Veja o [contrato](coordenacao-central/10-executor-agy.md).

O autor só chama o implementador quando o coordenador liga a opção no pedido,
em tarefa pequena e bem especificada (arquivos exatos, critério testável, sem
casos extremos de formato). O teto é de 3 chamadas por tarefa, e a chamada com
`saida_invalida` conta no teto. Acabado o teto, o autor termina à mão e
registra no corpo do commit quais linhas são dele. No piloto MOD-06 (relatório
de 25/10/2026), delegar não reduziu o gasto do autor: 28.306 tokens de saída
contra 18.372 escrevendo. Voltar atrás é parar de ligar a opção nos pedidos;
nenhum padrão foi trocado e o MOD-04 fica parado.

Sem login do agy, o implementador grava `motivo_codigo` `sem_login_agy` só
quando o isolador detecta a falta: sessão sem o soquete do implementador, item
ausente no keyring ou código 69. Com o item presente e a credencial vencida ou
inválida, o agy sai com código 1 e o registro diz `erro_execucao`, com o código
de saída no `motivo`; a renovação do login é feita fora do isolamento. Não há
sinal confiável da falha de autenticação sem o agy real. O dono decidiu esse
escopo em 25/10/2026. Os detalhes estão em [isolamento](isolamento.md).

## Critérios de acompanhamento do apoio

A aba Autonomia de agentes e o `jangada-subagentes`, ambos comandos opcionais fora do Core por ora, mostram os indicadores
por entrega: tokens do Claude com e sem agy, fração delegada, recusas,
compressão, cota gasta, aprovação na primeira rodada, afirmações sem fonte,
desvios do protocolo e árvore de subagentes. Um `*` marca grupos com menos
de 15 entregas.

- Após 30 entregas com agy, se os tokens do Claude por entrega aprovada não
  caírem, retirar a preferência pelo agy do protocolo.
- Se a aprovação na primeira rodada cair com delegação, rever os papéis.
- Se o verificador não aumentar a aprovação na primeira rodada em 30
  entregas, retirar esse papel do fluxo.

Sem agy instalado, o destino padrão continua `agy` e registra bloqueio.
Uma preferência local explícita continua válida. Apoio não aprova entrega;
`jangada-validar` mantém a revisão independente.
