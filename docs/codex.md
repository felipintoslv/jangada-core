# Codex na Jangada

O Codex implementa no mesmo ciclo de worktree, tmux, validação e integração
usado pelos outros agentes. Desde a modularização 3.0, os perfis moram em
`agentes/perfis/` e os comandos em `bin/`; os caminhos
`agentes/perfis/` e `bin/jangada-*` citados aqui são links de
compatibilidade e continuam sendo a forma de uso. Há dois perfis padrão, e
o Codex participa dos dois:

| Perfil | Implementa | Revisa | Delegação |
|---|---|---|---|
| `codex-claude` | Codex | Claude | leitor e redator no Ollama, demais papéis no agy |
| `claude-codex` | Claude | Codex | leitor e redator no Ollama, demais papéis no agy |

```sh
jangada-agente --perfil codex-claude --nome tarefa --prompt "Implemente a tarefa"
```

Outra combinação, como o Codex revisando o próprio trabalho ou o agy como
revisor, sai por `--revisor`, `--delegacao` ou perfil pessoal em
`~/.config/jangada/agentes/`.

## Preparação

Instale o Codex CLI e faça `codex login` num terminal comum. A Jangada não
instala o CLI nem altera a configuração global dele. O adaptador exige uma
versão que ofereça `--no-daemon`, para não conectar a sessão a um processo
compartilhado fora do isolamento. A implementação foi conferida com a ajuda
do Codex CLI 0.159.2 e com executáveis simulados nos testes.

Os perfis são lidos diretamente de `agentes/perfis/`, com precedência da
cópia em `~/.config/jangada/agentes/`. Não exigem migração de configuração
ou instalação de hooks globais. A cópia instalada precisa receber a
atualização pelo fluxo habitual de atualização (`git merge --ff-only` na cópia instalada).

## Execução e isolamento

`bin/jangada-agente` chama `bin/jangada-codex` dentro do
`bin/jangada-isolar`. O adaptador acrescenta o protocolo por
`developer_instructions`, mantém `workspace-write`, pede permissões ao
usuário e usa `--no-daemon`.

Do estado da Jangada, a proteção interna do Codex recebe como raiz gravável
só `$JANGADA_ESTADO/agentes` (`--add-dir`), onde ficam o estado da sessão, o
protocolo e os pareceres. A raiz de `$JANGADA_ESTADO` não entra: ela é
somente leitura no bubblewrap, e o Codex precisa criar pontos de montagem
(`.git`, `.codex`, `.agents`, `.aws`) dentro de cada raiz gravável antes de rodar
qualquer comando. Esses pontos aparecem em `agentes/` durante o comando e
somem no fim; nada na Jangada lista entradas ocultas dessa pasta.
`validar.jsonl`, `eventos-agentes.jsonl`, `delegacoes.jsonl` e `local.lock`
seguem graváveis no bubblewrap, mas não são raízes do Codex, que só aceita
pastas.

Continuam passando pelo pedido de permissão do Codex, porque a proteção
interna dele não libera a rede nem escrita fora da pasta de trabalho, do
`/tmp` e de `agentes/`:

- `git commit`, que grava na pasta do worktree dentro do `.git` comum;
- `jangada-validar`, que chama o revisor pela rede e grava no login dele
  (`~/.claude` ou `~/.codex`) e em `validar.jsonl`;
- `jangada-delegar`, que usa a rede (agy ou Ollama) e grava em
  `~/.gemini/antigravity-cli`, `delegacoes.jsonl` e `local.lock`.

Aprovado o pedido, o comando roda só com as montagens do bubblewrap, que já
liberam esses caminhos.

Por isso o Codex deve rodar `jangada-validar` e `jangada-delegar` com
`sandbox_permissions: "require_escalated"` e uma justificativa curta; o dono
aprova na janela. Dentro da proteção do Codex, `~/.claude`, `~/.gemini` e o
`CODEX_HOME` são somente leitura e o revisor falharia sem parecer. O
`jangada-validar` confere isso antes de contar a rodada e, se a pasta do
revisor não for gravável, para com código 5 e uma mensagem que pede o escalonamento.

O Codex exige isolamento, inclusive com `--sem-isolar` ou
`JANGADA_AGENTE_ISOLAR=0`. A chamada direta ao adaptador sem isolamento é
recusada antes de executar o CLI.

Dentro do bubblewrap, a pasta do Codex (`CODEX_HOME`, ou `~/.codex`) é
montada a partir de `~/.local/state/jangada/codex/SESSAO`. Conversas, bancos e
confiança dos hooks persistem ali. O `CODEX_HOME` não é trocado.
Configuração, autenticação, instruções globais, perfis, regras, skills,
plugins e hooks existentes são montados somente para leitura.
Arquivos de configuração ausentes ficam vazios; pastas de instruções
ausentes ficam vazias e somente leitura. A sessão não altera a configuração
do Codex aberto fora da Jangada.

No início da sessão, o adaptador pergunta se o usuário confia na pasta,
antes de executar o CLI. A confirmação fica em `jangada-confianca.json`
nos dados próprios da sessão, e a tabela `projects` com a entrada da pasta
é passada pela configuração da chamada. Assim o CLI não precisa gravar
no `config.toml` somente leitura. A pergunta não se repete na retomada da
mesma pasta; outra pasta exige nova confirmação. Uma entrada exata já
confiável na configuração global também dispensa a pergunta. Sem terminal
nem confiança registrada, o adaptador recusa abrir a sessão. O revisor
não passa por essa etapa, pois ignora a configuração do usuário e da pasta.

O parser de `-c` divide o nome da chave nos pontos, sem interpretar aspas
TOML nessa chave. Por isso a confiança vai como uma tabela TOML no valor
de `projects`, com o caminho entre aspas dentro da tabela. Usar
`projects."CAMINHO".trust_level` cria uma chave incorreta e deixa o CLI
pedir confiança novamente. O teste consulta `config/read` no Codex real,
quando instalado, para conferir o resultado sem fazer pedidos ao modelo.

Um endereço próprio em `CODEX_HOME` precisa ser absoluto e já existir.
`CODEX_SQLITE_HOME` é fixado na pasta montada para os bancos não escaparem
para um endereço global. O login não pode ser regravado dentro da sessão:
se exigir renovação, faça o login novamente no terminal comum.

O encerramento mantém os dados do Codex para preservar a conversa. Eles
ficam fora dos arquivos `agentes/SESSAO.json` removidos pela limpeza. Não há
limpeza automática desses dados nesta primeira integração.

## Hooks e estados

Os hooks são passados na configuração da chamada, sem editar
`~/.codex/config.toml`. O adaptador consulta `hooks/list` no Codex para
obter as chaves e hashes das oito definições da Jangada. Na primeira
abertura, mostra os comandos e pede autorização antes de abrir a conversa.
Uma recusa encerra a abertura; uma alteração na definição exige nova
autorização. A escolha fica em `jangada-hooks-confianca.json` nos dados da
sessão e entra pela tabela `hooks.state` na chamada. Outros hooks continuam
sujeitos à aprovação do próprio Codex. O revisor não passa por essa etapa.

Isso evita o `/hooks` tentando gravar a aprovação no `config.toml` montado
somente leitura. A consulta e a aprovação usam o CLI real, sem pedidos ao
modelo, e não desligam a verificação de confiança dos hooks.

O processo externo de `jangada-isolar` observa as gravações do arquivo de
estado da sessão com `inotifywait` e envia o sinal 10 à Waybar. O hook
isolado não enxerga o processo da barra no namespace de PID do host.
Sem o observador, a barra só perceberia o novo estado na consulta periódica
de 30 segundos. O observador é encerrado junto com o isolamento.

| Evento | Estado |
|---|---|
| `SessionStart` | `iniciado`, com UUID da conversa |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse` | `trabalhando` |
| `PermissionRequest` | `aguardando` |
| `Stop`, `Interrupt` | `concluido` |
| `SessionEnd` | `concluido`, com mensagem de encerramento |

`bin/jangada-hook-codex` não decide permissões: sua saída é vazia. Ele
atualiza apenas uma sessão existente, sob a trava comum, e grava mudanças
em `eventos-agentes.jsonl`. Eventos identificados como de subagente não
alteram o estado principal. A barra e o painel leem esses registros pelo
mecanismo existente. Perguntas ao usuário fora de `PermissionRequest` ainda
não têm estado de espera próprio.

## Restauração e delegação

`jangada-agentes --restaurar SESSAO` recompõe o comando da configuração
atual. Valida o UUID, a pasta, o agente e o revisor, ignora `.comando` e
`.isolar`, e refaz o protocolo antes de abrir a sessão.

Com UUID, usa `codex resume UUID`. Sem UUID, num worktree próprio, usa
`codex resume --last`, com o filtro de pasta do CLI. Sem UUID no modo direto,
abre uma conversa nova para não retomar a conversa de outro agente.

Os perfis `codex-claude` e `claude-codex` usam `JANGADA_DELEGAR=agy` e
recebem a mesma regra de delegação, na abertura e na retomada. Leitor e
redator usam `jangada-delegar PAPEL ... --destino local --arquivos FONTES`
(Ollama, sem terminal, Git nem escrita). Os demais papéis usam
`--destino agy --permitir-remoto`, com fontes e envio remoto autorizados. Uma
falha local registra o motivo e fica local: não vai ao agy, ao Claude nem ao
Codex sem decisão explícita. A recusa do agy registra bloqueio, sem
alternativa local automática. `JANGADA_DELEGAR=local` continua uma escolha
explícita: os demais papéis ficam na sessão. O Codex não chama subagentes do
Claude.

## Cota disponível

`jangada-router status --atualizar-codex --permitir-remoto` consulta somente
metadados pelo método `account/rateLimits/read` do Codex. Não inicia conversa,
gera texto, envia fontes ou ativa execução de ferramentas.

A consulta copia o token de acesso existente para uma pasta própria em
`$XDG_RUNTIME_DIR/jangada-credenciais` (modo 0700; o arquivo, 0600), sem
configuração do usuário. Essa pasta fica fora do estado do jangada e não
aparece dentro do isolamento, que tem `XDG_RUNTIME_DIR` próprio. Sem
`XDG_RUNTIME_DIR`, ou com ele aberto a outros usuários, a consulta recusa
sem gravar cópia. O token de
renovação não é transmitido nem copiado. Tokens vencidos ou com menos de
60 segundos de validade impedem a consulta e deixam o estado em `UNKNOWN`.
Encerra o grupo do processo e remove a pasta ao concluir, falhar ou receber
Ctrl-C, SIGTERM ou SIGHUP. Morto por SIGKILL, o processo não remove nada: a
cópia fica até a próxima consulta, que apaga as pastas `.cota-codex-PID-*`
do mesmo usuário com mais de 60 segundos e sem trava. Cada execução segura
uma trava (`flock`) na própria pasta enquanto vive, e o executor econômico a
passa ao processo do Codex; uma execução ativa nunca é recolhida. Ligações
simbólicas e nomes fora do padrão são ignorados. Não faz login, não renova a credencial original e não usa
chaves de API do ambiente. Autenticação ausente ou incompatível deixa
o estado em `UNKNOWN`. O ambiente do filho contém somente caminhos
temporários, idioma, busca de executáveis, certificados e configuração de proxy.

O saldo registrado é o menor das janelas presentes no grupo de consumo
`codex`. Grupos diferentes não substituem esse saldo. Uma janela vencida
exige nova consulta; não se presume que a cota foi renovada. A observação
vale no máximo 60 segundos e expira antes da renovação mais próxima.
A reserva padrão é 25%, ajustável por `JANGADA_CODEX_COTA_MIN` entre 0 e 100.
Saldo zero produz `QUOTA_EXHAUSTED`; abaixo da reserva, `QUOTA_LOW`.
Pausa e espera vigente impedem a consulta.

Essa observação pode apoiar o executor econômico configurado. Não comprova
acesso a um modelo específico nem cota
independente para variantes econômicas. Os estados continuam sendo dados
operacionais editáveis, não autorização para enviar fontes ou alterar recursos.

Referência: [cotas no Codex App Server](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt).

## Executor econômico

O destino `codex-economico` aceita as três capacidades documentais do leitor.
Configure `JANGADA_CODEX_ECONOMICO_MODELO` com o identificador exato escolhido
pelo usuário. Vazio desabilita o executor. Não há modelo padrão nem troca
automática para outro modelo. Essa configuração declara a escolha econômica;
o Jangada não infere preço, acesso ou qualidade pelo nome.

Inclua `codex-economico` na lista da capacidade em `delegacao.json`, por exemplo
`"analise_documental": ["agy", "codex-economico", "local"]`. A chamada exige
`--permitir-remoto --permitir-codex` e perfil de sessão que permita delegação
remota. O perfil `local` continua impedindo envio ao Codex.

Na fila, são necessários também `permitir_remoto: true` e
`permitir_codex: true` na tarefa. `jangada-executar` e `jangada-retomar`
aceitam as duas opções. O perfil `offline` impede envio; `quality` continua
escolhendo agy explicitamente. Risco alto continua aguardando executor principal.
Os campos do plano são dados e não comprovam aprovação externa.

O executor consulta a cota antes de gerar, respeita a reserva compartilhada e
usa uma trava para impedir duas delegações Codex simultâneas no mesmo estado.
Sem cota conhecida, recusa. Após geração, não presume que o saldo anterior
continua disponível. Para pausar essa alternativa, use `jangada-provedor pausar codex`.

São enviados somente pedido e fontes de texto UTF-8 numeradas, até 80 mil
caracteres no conjunto preparado. PDF e binários exigem outro executor.
O Codex usa o adaptador isolado da revisão, com terminal, ferramentas, busca,
plugins e configuração do usuário desativados. Não retoma conversa e não
recebe token de renovação. Cada execução registra modelo, cota anterior,
consumo informado e decisão. O coletor lê o consumo em `delegacoes.jsonl`.
Se o orquestrador morrer, o executor interrompe a geração e remove sua
autenticação temporária. O observador usa identificador de processo do Linux.

Sucesso exige processo encerrado sem erro, um turno concluído, texto não vazio
e referências válidas. A fila mantém `REVIEW_REQUIRED`, pois esses controles
não comprovam a interpretação. Os testes usam executores simulados; acesso
e qualidade de cada modelo configurado precisam ser conferidos em uso.

## Revisão com Codex

`jangada-validar --revisor codex` também aceita `--modelo`. Sem modelo
explícito, usa o padrão do CLI com a configuração do usuário ignorada.
A revisão roda numa pasta temporária vazia, em `read-only`, sem retomada,
com `--ephemeral` e sem os hooks da sessão. Terminal, execução por código,
subagentes, plugins, aplicativos, navegador e busca externa são desativados.

Fora de uma sessão isolada, o revisor também passa pelo `jangada-isolar`,
mesmo com `JANGADA_AGENTE_ISOLAR=0`. Seus dados ficam em
`$JANGADA_ESTADO/codex/revisao-codex-ROTULO`, com login e configuração
somente leitura. A resposta sai por um arquivo da pasta temporária e o
processo pai grava o parecer em `revisoes/`. Dentro de uma sessão isolada,
usa a montagem do Codex já preparada nela. Por isso sessões de outros
agentes também recebem essa montagem quando há uma pasta do Codex existente.

O revisor recebe as regras da base, commits, diff e parecer anterior pela
entrada padrão. Nesta etapa ele avalia somente esse pedido, sem ler outros
arquivos do projeto. Isso preserva a proibição de comandos do protocolo.
Ausência de contexto pode resultar em `STATUS: REVISAR`.
Quando o diff é cortado ou traz arquivo novo acima de 50 KB, o
`jangada-validar` recusa o Codex como revisor: ele aprovaria sem ter lido a
entrega inteira.

A última mensagem é normalizada pelo mesmo mecanismo de Claude e agy.
Erro do processo não aprova a entrega, mesmo que tenha produzido um arquivo
com `STATUS: APROVADO`. A aprovação para integração continua sendo a revisão
externa para o commit exato e limpo, em `revisoes/`.

## Verificação

`testes/codex.sh` confere lançamento, protocolo, TOML, hooks e recusas.
`testes/restaurar.sh` cobre UUID, retomada por pasta e isolamento obrigatório.
`testes/isolar.sh` confere a separação dos dados e as montagens protegidas;
quando o ambiente permite bubblewrap, executa também esses controles.
`testes/validar.sh` verifica os pareceres e as falhas com Codex simulado.
`testes/cota-codex.py` confere protocolo, janelas, reserva, prazo, interrupção
e remoção de credenciais temporárias, sem serviços externos.

Referências: [CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
[configuração](https://learn.chatgpt.com/docs/config-file/config-reference) e
[hooks](https://learn.chatgpt.com/docs/hooks) da documentação oficial.

## Seleção por tarefa no piloto

`--autor-modelo` e `--autor-esforco` selecionam Luna medium ou Sol high.
O revisor independente é Opus high. A restauração usa `modelos_tarefa`
protegido, não o comando ou a seleção gravável da sessão.
Veja o [contrato do piloto](coordenacao-central/10-executor-agy.md).
