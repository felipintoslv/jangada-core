# Camada de agentes

Os comandos de agentes moram em `bin/`, os perfis e o protocolo em
`agentes/perfis/`, e os hooks e subagentes em `agentes/claude/` e
`agentes/agy/`. O mapa está em [SKILL.md](SKILL.md).

## Consulta da fila

SQLite em `mode=ro` ainda pode criar arquivos WAL/SHM na origem.
O núcleo consulta uma cópia temporária estável do banco e do WAL.
Não omita o WAL: ele pode conter transações confirmadas que ainda não
chegaram ao banco principal. Mudanças durante a cópia exigem nova tentativa
ou erro explícito, sem apresentar uma consulta incompleta como sucesso.

## Consulta de sessões

O `tmux list-sessions` traz também sessões alheias ao jangada. Nomes com
espaços ou acentos não devem derrubar a consulta: são ignorados com aviso.
Filtre nomes reservados a pareceres e contextos antes de abrir o registro,
inclusive quando o nome vem do tmux, para não carregar relatórios como sessões.

Um `mkdir -p` no início do comando cria estado mesmo numa opção de leitura.
A consulta precisa dispensá-lo também quando a pasta de estado não existe.
Na retenção, `date` pode rejeitar a data ou exceder o prazo; a alternativa
ISO deve tratar a exceção do prazo, além do código de saída não zero.

No terminal, `dir` não substitui `worktree`: inclui sessões `--direto`, e a
lista geral aplica retenção. Use `--sessao-worktree-json` para correspondência
literal, com erro em duplicidade. Para repassar contexto explícito, use
`--contexto-json SESSAO`; r10 sucede r2 por número, sem ler `revisoes/`.
Um auxiliar Python recebido por stdin inclui a pasta atual nas importações.
Use `python3 -I -` no transporte do terminal para não executar módulos do
worktree nem de `PYTHONPATH` com a identidade do dono.
Texto repassado permanece dado não confiável. O contrato e os limites estão
em `docs/coordenacao-central/11-consultas-modulos.md`.

## Codex

O `account/rateLimits/read` separa limites por grupo de consumo. Para a cota
Codex, use `rateLimitsByLimitId.codex` quando o mapa estiver presente;
`rateLimits` é a forma antiga. Considere a janela com menor saldo, não
presuma renovação quando `resetsAt` passar nem cota separada por modelo.
`jangada-router status --atualizar-codex --permitir-remoto` consulta esses
metadados sem iniciar conversa; exige autenticação existente e não habilita
delegação ao Codex.

O Codex CLI 0.159.3 dispara `SessionStart` no primeiro turno, não apenas em
`thread/start`. Os testes com o CLI real usam um provedor restrito a
localhost para iniciar o turno sem consumir tokens externos. A confiança
dos hooks preserva `enabled=false`: aprovar um hook não deve reativá-lo.

A aprovação dos hooks no `/hooks` tenta gravar `config.toml`, que está
somente leitura. O adaptador consulta os hashes das definições em
`hooks/list`, pede autorização dos oito hooks da Jangada no início e
guarda a escolha em `jangada-hooks-confianca.json`. A tabela `hooks.state`
vai na chamada; outros hooks mantêm a própria verificação de confiança.
O sinal à Waybar precisa vir de fora do namespace de PID: o
`jangada-isolar` observa o arquivo da sessão com `inotifywait` e sinaliza
a barra no host. O `pkill` executado dentro do isolamento não a enxerga.

A confiança da pasta precisa ser resolvida antes de abrir o CLI: ele tenta
salvá-la em `config.toml`, que o isolamento monta somente leitura.
O adaptador pergunta no início e salva a escolha em
`jangada-confianca.json` nos dados da sessão. A entrada de confiança vai
como argumento TOML, sem alterar a configuração global. Retomar a mesma
pasta reaproveita a escolha; trocar de pasta exige nova confirmação.
O parser de `-c` do Codex separa a chave por pontos sem interpretar aspas:
`projects."CAMINHO".trust_level` não funciona. Passe a tabela inteira no
valor de `projects`, com o caminho como chave TOML entre aspas. Confira
o resultado por `config/read` no CLI real; tomllib sozinho não detecta isso.

O perfil `codex-claude` usa o mesmo ciclo de sessões. O adaptador
`jangada-codex` exige `--no-daemon`, injeta o protocolo por
`developer_instructions` e passa hooks sem alterar a configuração global.
Os hooks precisam de conferência pelo `/hooks` do CLI; não dispense a
confiança dos hooks para fazer a barra funcionar.

O Codex sempre exige isolamento, inclusive com `--sem-isolar` e
`JANGADA_AGENTE_ISOLAR=0`. A chamada direta ao adaptador é recusada.

Dentro do bubblewrap, dados próprios em `$JANGADA_ESTADO/codex/SESSAO`
ocupam a pasta do Codex. O login e as configurações do host ficam somente
leitura. A pasta original não pode ficar gravável: seus hooks, regras e
plugins seriam executados fora do isolamento. `CODEX_SQLITE_HOME` aponta
para a pasta montada, sem mudar `CODEX_HOME`.

A proteção interna do Codex (bwrap aninhado) cria `.git`, `.codex`,
`.agents` e `.aws` como pontos de montagem dentro de cada raiz gravável e
os remove ao sair. Raiz somente leitura no `jangada-isolar` faz todo
comando falhar com `bwrap: Can't create file ...: Read-only file system`;
arquivo como raiz derruba o CLI. Por isso `--add-dir` recebe só
`$JANGADA_ESTADO/agentes`. `codex sandbox -c 'sandbox_mode="workspace-write"'
-c 'sandbox_workspace_write.writable_roots=[...]' -- COMANDO` reproduz a
montagem sem pedido ao modelo.

Na restauração, UUID vai por `resume UUID`. Sem UUID, `resume --last` só
vale no worktree próprio; direto no projeto abre conversa nova.
O revisor Codex recebe só o pedido completo numa pasta vazia, sem terminal,
hooks ou ferramentas externas. Mais detalhes em `docs/codex.md`.

## Peças

Os perfis `claude-codex` e `codex-claude` seguem a mesma regra: `leitor` e
`redator` com `--destino local --arquivos FONTES`; os demais papéis com
`--destino agy --permitir-remoto`. O protocolo da abertura e o da retomada
trazem essa regra. O `jangada-delegar --capacidade` seleciona destinos para
leitura documental. O envio ao agy exige autorização da tarefa
(`--permitir-remoto`) e do perfil. Uma falha do Ollama não autoriza esse
envio. Veja os limites e capacidades em `docs/subagentes-e-delegacao.md`.

No teste real, o qwen3:4b consumiu milhares de tokens de raciocínio para
devolver apenas localizadores. Com capacidade, o delegador usa `think: false` e
`num_predict: 1024`; recusa saída cortada pelo limite. O template local
antigo abre `<think>` mesmo com a opção desligada. Para Qwen3, a mensagem
termina também em `/no_think`, conforme o [controle do Qwen3](https://qwen.readthedocs.io/en/stable/getting_started/quickstart.html).
O modelo de 4 bilhões disponível continuou raciocinando mesmo com ambos
os controles. Não presuma suporte: saída limitada deve ser recusada.
Nos testes sintéticos, uma estrutura JSON obrigatória eliminou o estouro;
`format: "json"` sozinho deixou campos e citações incorretos.
Para extração, use `--destino local --capacidade leitura_documental` e
`--extrair campo:tipo`, com `texto`, `inteiro` ou `booleano`.
Campos ausentes no trecho usam valor e referência nulos. A conferência
valida os tipos e a presença da posição citada naquele trecho, sem avaliar o sentido.
Quando uma referência é recusada, o diagnóstico limitado aparece no `stderr`;
a referência bruta não fica guardada no registro da delegação.
Na prova instalada de 15/10/2026, o leitor tipado removeu a barra inicial
de um caminho absoluto e a referência foi recusada. O pedido fornece
um exemplo real por fonte da fatia, sem valores: nome curto quando único
entre as fontes autorizadas, caminho exato para homônimos e página para PDF.
Os rótulos originais e a conferência permanecem iguais; caminho malformado
continua recusado, sem correção automática da resposta.
A consolidação por modelo chegou a apagar a responsável encontrada na última
parte. A extração une partes de forma determinística: valores presentes
substituem ausências, `false` e zero são preservados, conflitos recusam.
Essa união não consome chamada; textos livres ainda usam consolidação pelo modelo.
Use requisitos explícitos (`--requisito`) para exigir explicações em cada seção, além
das referências. Essa conferência estrutural não aprova o sentido.
Documentos divididos exigem orçamento para todas as partes e consolidação
antes da primeira chamada.

Limites internos do agy usam `--foreground` nas seleções por capacidade
para manter os filhos no grupo do limite global.

Uma consulta de cota que falha não pode reutilizar o valor expirado.
Uma resposta parcial de `/usage` não torna todos os grupos inválidos.
Validar o cache somente pelo primeiro modelo bloqueava outro grupo com cota válida.
O delegador aceita cache atual com algum grupo configurado válido; cada modelo
continua exigindo a cota do próprio grupo. O indicador de disponibilidade segue essa regra.
Cota desconhecida impede a chamada ao modelo daquele grupo.
Consumo de tokens do Claude não comprova cota restante.

Se testes de sinais passam isolados, mas falham na suíte, compare com
`env --default-signal=INT,QUIT testes/verificar.sh`. Essa chamada reinicializa
os sinais herdados e mantém todas as verificações. Investigue qualquer
falha que persistir.

Ao conferir `/proc/PID/stat` depois de cancelar um processo, a leitura pode
levantar `FileNotFoundError` ou `ProcessLookupError`. Ambos indicam que o
processo desapareceu. O teste deve aceitar esses dois erros, mantendo a
conferência de processo zumbi e o prazo; outros erros continuam sendo falhas.

| Peça | Papel |
|---|---|
| `jangada-agente` | escolhe projeto, cria worktree `agente/<nome>` e abre o agente numa sessão `tmux -L jangada`; `--prompt`/`--prompt-arquivo` já entregam a tarefa, `--perfil` escolhe o agente, `--sem-isolar` abre fora do bubblewrap |
| `jangada-isolar` | roda o agente no bubblewrap: sistema somente leitura, pasta da tarefa gravável; `--mostrar` imprime a chamada ao `bwrap` |
| `jangada-worktree-preparar` | copia para o worktree novo os ignorados do `.worktreeinclude`, liga o que está em `.jangada/links` e roda `.jangada/preparar.sh`; com `--so-confianca`, só sincroniza a confiança do agy |
| `jangada-hook-claude` | chamado pelos hooks do Claude Code; grava o estado e notifica |
| `jangada-hook-agy` | o mesmo para o agy, pelo `~/.gemini/config/hooks.json` (PreInvocation e Stop) |
| `jangada-hook-leitor` | PreToolUse do leitor: só comandos de leitura no terminal; no Claude pelo frontmatter do agente, no agy (`--agy`) pelo `PreToolUse` do `run_command` no `~/.gemini/config/hooks.json` |
| `jangada-filtrar` | condensa saídas longas de comandos no terminal para poupar tokens; atalho `resumir` no jangada shell |
| `jangada-mapa` | extrai a estrutura de arquivos e assinaturas em Markdown; atalho `mapa` no jangada shell |
| `jangada-validar` | revisão do diff por outro modelo ou pelo mesmo modelo isolado (claude ou agy), só leitura, chamada pelo agente antes de entregar; executa portão determinístico local antes (conflitos, script com byte nulo, sintaxe, lintr, gitleaks nas linhas acrescentadas; sem gitleaks reprova, inclusive com `JANGADA_VALIDAR_SEM_GITLEAKS=1`; `.gitleaks.toml`, `.gitleaksignore`, `AGENTS.md` e `CLAUDE.md` valem da base, e `.lintr` também quando a base tem um); só a primeira linha não vazia do parecer decide o status; pareceres em `validacao-<sessao>-rN.md`; a primeira linha tem de ser exatamente `STATUS: APROVADO` ou `STATUS: REVISAR`, e aprovação pelo autor, com autoria não comprovada fora do isolamento ou com validação local incompleta vira `REVISAR`; a revisão lê uma foto congelada da entrega, não o worktree vivo; depois de um APROVADO, `validacao-<sessao>.aprovado` (JSON) guarda commit, árvore, base e revisor, e a próxima entrega parte dele com as rodadas zeradas; cada rodada vira uma linha em `~/.local/state/jangada/validar.jsonl`, resumida por `--metricas` |
| `jangada-agentes` | seletor, painel, módulo da barra, `--focar`, `--proximo`, `--anterior`, `--restaurar` |
| `jangada-agente-fim` | encerra e remove a worktree após conferência, mantendo o ramo; `--integrar` avança a base por `merge --ff-only` até o commit com parecer APROVADO independente em `revisoes/`, depois de confirmação humana (resposta `s` ou `--confirmacao` da Central) e de `testes/verificar.sh` sair com 0 fora do isolamento; se a base andou, refaz o ramo na worktree da tarefa e exige parecer do commit novo; recusa com cópia principal alterada e com `--sem-revisao`; não envia ao remoto, não assina, não atualiza a cópia instalada e mantém sessão, ramo e worktree |
| `jangada-consumo` | consumo do Claude Code no bloco de 5 horas em andamento (`--curto`, `--json`); a barra de `jangada-agentes --waybar` o mostra |
| `jangada-painel` | comando opcional, fora do Core por ora |
| `jangada-gancho` | roda os ganchos do usuário em `~/.config/jangada/ganchos/` |

## Revisão incremental e integração

Uma aprovação anterior protegida, com autoria, árvore, base e execução local
conferidas, pode mover o início do diff para o commit aprovado,
mesmo com `--base main`. Confira a quantidade de arquivos anunciada:
aprovar as correções não comprova que o revisor leu toda a entrega acumulada.

Na revisão manual fora do isolamento, use `JANGADA_SESSAO` com o nome
completo registrado da sessão. Sem ele, o rótulo vem do nome da pasta;
a marca recebe outro nome, e a conferência manual deve identificar a entrega
correta. O `--integrar` não chama o revisor: lê a marca dessa sessão e
confere commit, árvore, base, verificação local e independência.

## Isolamento (`jangada-isolar`)

O agente aberto pelo `jangada-agente` roda no bubblewrap, com
`JANGADA_ISOLADO=1` no ambiente. De dentro:

- Grava só na pasta da tarefa (worktree, ou o repositório com `--direto`), em
  `~/.claude`, `~/.gemini/antigravity-cli`, `~/.local/state/jangada/agentes`,
  no `validar.jsonl`, no `eventos-agentes.jsonl`, no `delegacoes.jsonl` e no
  que estiver em `JANGADA_ISOLAR_ESCRITA`. O resto é somente leitura,
  inclusive `~/.claude.json`, `~/.local/share/claude`, `~/.gemini/config` e o
  resto de `~/.local/state/jangada`: escrever em `~/.config`, instalar pacote
  do R na biblioteca do usuário ou rodar `pip install --user` falha com
  "Read-only file system".
- O `~/.cache`, `~/.claude/shell-snapshots`, `~/.claude/session-env` e
  `~/.claude/ide` aceitam escrita, mas ela fica numa camada em memória que
  some no fim (sobreposição do bwrap). Cache grande de compilação ocupa RAM
  enquanto a sessão dura. `~/.cache/yay` e `~/.cache/paru` são somente
  leitura, e `~/.cache/cliphist` (histórico da área de transferência) fica
  oculto.
- Em `~/.claude` são somente leitura `settings.json`, `settings.local.json`,
  `CLAUDE.md`, `commands`, `agents`, `skills`, `hooks`, `plugins`,
  `output-styles`, `backups` e os scripts soltos. `/model` ou `/config` de
  dentro não persistem.
- Git num worktree: o `.git` comum é somente leitura, menos `objects`,
  `refs`, `logs`, `rr-cache`, `reftable` e a pasta do próprio worktree (sem
  o `commondir`, o `gitdir` e o `config.worktree`). Commit, ramo, `checkout -b`, `reset` e `stash` funcionam; apagar
  ramo ou tag e `git gc` falham (regravam o `packed-refs` da raiz). Com
  `--direto`, a raiz do `.git` segue gravável, menos `config`, `hooks`,
  `worktrees`, `modules` e `commondir`; o `jangada-isolar` cria um
  `commondir` com `.` quando falta, porque um bind sobre arquivo ausente
  deixaria no disco um arquivo vazio, e commondir vazio quebra o git.
  `git config` e mudança em `.git/hooks` falham nos dois modos.
- O `/tmp` é próprio da sessão e some quando ela acaba. Não deixe nele nada
  que o usuário ou outra sessão precise ler; use a pasta da tarefa.
- Sem tmux: o socket fica no `/tmp` de fora, e `TMUX` e `TMUX_PANE` saem do
  ambiente. Não há como comandar outra sessão, e a notificação sai sem o botão
  Abrir.
- O `XDG_RUNTIME_DIR` é próprio: sem Hyprland (`hyprctl` falha), Wayland, X,
  gpg-agent e systemd do usuário. O D-Bus da sessão vem pelo
  `xdg-dbus-proxy`, que só fala com `org.freedesktop.Notifications` e, com
  o agy instalado, `org.freedesktop.secrets` (inteiro, ou só os itens de
  `JANGADA_ISOLAR_KEYRING_ITEM`); o proxy vive enquanto o bwrap guarda o
  cano de sincronização (`--sync-fd`). Esse cano é aberto com
  `exec {fd}< <(...)`, e não com `coproc`: o bash fecha os descritores do
  coproc no `exec bwrap`, e o proxy morreria antes de o agente abrir. O D-Bus do sistema e o Docker ficam
  ocultos, e o namespace de PID é próprio: `kill` e `ps` só alcançam os
  processos da sessão, e um pid gravado de dentro não vale fora.
- `~/.ssh`, `~/.gnupg`, `~/.git-credentials`, `~/.config/gh`, os chaveiros e
  os perfis de navegador aparecem vazios, e `SSH_AUTH_SOCK` sai do ambiente.
  `git push` por ssh ou com credencial guardada não funciona: o push é do
  usuário, fora da sessão.
- `jangada-isolar` chamado de dentro no perfil `agente` roda direto, desde
  que `JANGADA_ISOLADO` venha com a marca `/tmp/.jangada-isolado` montada
  pelo bwrap, conferida em `/proc/self/mountinfo`. Só a variável não basta.
  Os perfis `verificacao` e `verificacao-rede` sempre criam outro isolamento,
  mesmo com `JANGADA_AGENTE_ISOLAR=0`: a sessão do agente ainda tem logins
  e rede que o `lintr` e o `.jangada/validar.sh` não devem herdar.
  `revisar` no jangada shell e o `.jangada/preparar.sh` também passam pelo
  `jangada-isolar`. Para rodar os testes dentro da sessão, use
  `env -u JANGADA_ISOLADO testes/verificar.sh`. Se uma rodada anterior deixou
  `/tmp/isolar-teste`, remova esse arquivo antes: ele falseia o teste do
  `/tmp` próprio.
- Se a tarefa precisa gravar fora dessas pastas, pare e peça ao usuário:
  acrescentar a pasta em `JANGADA_ISOLAR_ESCRITA` no `jangada.conf`. Não há
  abertura sem isolamento. Não contorne o isolamento.

O isolamento fecha os caminhos conhecidos para rodar código fora do bwrap
(estado executado na restauração, configuração do git, hooks do Claude,
sockets do Hyprland e do sistema), mas não é uma barreira completa: o
chaveiro inteiro é legível pelo D-Bus filtrado, `~/.claude/projects` e o
`settings.json` do agy seguem graváveis, e repositórios aninhados no índice
só ficam protegidos quando o git de fora passa por `jangada_git_seguro`.
`JANGADA_AGENTE_ISOLAR=0` e `--sem-isolar` não desligam mais: geram aviso e
a sessão abre isolada. `JANGADA_ISOLAR_OCULTAR` substitui a lista de ocultos, e
`JANGADA_ISOLAR_OCULTAR_EXTRA` acrescenta a ela. `JANGADA_ISOLAR_PERFIL=verificacao`
(usado pelo `jangada-validar` no `lintr` e no `.jangada/validar.sh`) corta a
rede e oculta os logins e as chaves dos provedores. Repositório em reftable
é recusado. O `/sys` é o do host mesmo sem rede: para conferir a rede de
dentro, leia `/proc/net/dev`. O estado guarda
`comando` e `isolar` só para consulta: o `--restaurar` recompõe o comando e
volta isolado. Sem o `bwrap`, o `jangada-isolar` sai com erro e o agente não
abre: instale o pacote `bubblewrap`.

## Contrato de estado

Um JSON por sessão em `~/.local/state/jangada/agentes/<sessao>.json`, com
`sessao`, `dir`, `raiz`, `worktree`, `ramo`, `base`, `agente`, `revisor`, `estado`,
`mensagem`, `desde`, `atualizado`, `comando`, `isolar`, `perfil`, `tarefa`, `conversa`
(id da conversa, gravado pelo hook), `inicio` (HEAD na criação),
`delegar` (destino dos subagentes) e `validacao` (última rodada do
`jangada-validar`, com o revisor). `comando` e `isolar` são só para consulta:
o estado é gravável de dentro do isolamento, e nada dele é executado como
texto.
Estados: `iniciado`, `trabalhando`, `aguardando`, `concluido`, `interrompido`.

`interrompido` é a sessão cujo tmux sumiu (reinício, queda do servidor) com
worktree ainda presente. Ela fica guardada por 168 horas; `--restaurar` (ou o
`--focar` nela) recria a sessão tmux e retoma a conversa com
`claude --resume <conversa>`; sem o id, `--continue` num worktree e conversa
nova direto no repositório. O comando sai de campos conferidos (agente
`claude` ou `agy`, conversa em formato uuid, pasta dentro de
`JANGADA_WORKTREES` ou `JANGADA_PROJETOS`, revisor) e da configuração; estado
que não passa na conferência é recusado. O ambiente de um perfil é relido de
`~/.config/jangada/agentes/NOME.conf` na restauração, nunca guardado no
estado.

Cada mudança de estado vira também uma linha em
`~/.local/state/jangada/eventos-agentes.jsonl`, com `data`, `sessao`,
`projeto` (nome da pasta da raiz), `agente` e `estado`. Além dos estados
acima, o arquivo tem `inicio` e `fim` (SessionStart e SessionEnd do Claude),
`foco` (cada `--focar` numa sessão viva) e `subagente-inicio` e
`subagente-fim` (com `subagente_id`, `subagente_tipo` e `conversa`). Só
gravam o histórico os hooks e o `jangada-agentes`, por
`jangada_registrar_evento` (`bin/jangada-config`), que nunca falha: um erro ao gravar não pode derrubar o hook. A linha entra por
`jangada_anexar_linha`, sob `flock` no próprio arquivo: o `printf` do bash
divide uma linha grande em várias escritas, e duas sessões anexando ao mesmo
tempo misturavam os pedaços. O `delegacoes.jsonl` usa a mesma função. Em
teste, linha grande se gera com `printf`, não com `jq --arg` (300 KB estouram
o limite de argumentos). O histórico só
cresce; o mapa de todos os registros está
em `docs/registros.md`.

## Hooks do Claude Code

`agentes/claude/hooks.json` é mesclado em `~/.claude/settings.json` pela
instalação e pela migração, por evento, sem duplicar (a chave é o comando sem
o caminho até `/bin/`). Eventos: `UserPromptSubmit` e `PostToolUse` (trabalhando),
`Notification` (aguardando; `auth_success` é ignorado e `idle_prompt` vira
concluído sem aviso), `Stop` (concluído), `SessionStart` (iniciado) e
`SessionEnd` (concluído; `reason=clear` não muda o estado). Todo evento grava
`conversa` com o `session_id`. `SubagentStart` e `SubagentStop` (Claude Code
2.1.283 confirmado) trazem `agent_id` e `agent_type`, e o Stop traz também
`agent_transcript_path` e `last_assistant_message`. Eles só gravam uma linha
no histórico: não mexem no estado nem na barra, porque o agente principal
segue trabalhando. O `Stop` comum não dispara no fim de um subagente. Quem
lê o histórico e mede tempo por estado deve pular os estados `subagente-*`,
como já pula o `foco`.
A `mensagem` vem de `.message` (Notification), `.last_assistant_message`
(Stop) ou `.prompt` (UserPromptSubmit), primeira linha; o `PostToolUse`
mantém a anterior. Toda alteração do arquivo passa por
`jangada_alterar_estado` (`bin/jangada-config`), que usa `flock` na própria
pasta `agentes/`, aberta só para leitura: os hooks rodam em paralelo. Não
volte a um arquivo de trava aberto com `>`: o agente troca o arquivo por um
link, e o `jangada-agentes` ou o `jangada-validar` de fora truncariam o alvo.

`aguardando` e `concluido` são resultado, não processo: continuam no painel
depois de o processo sair, até o `Ctrl+X` do seletor ou até vencer
`JANGADA_AGENTES_GUARDAR` horas. O `jangada-agente-fim` não mata o pid
guardado de um estado final, porque o número pode ter sido reaproveitado.

A variável `JANGADA_SESSAO` da sessão tmux é o que liga o hook ao arquivo;
agente aberto fora do `jangada-agente` só gera notificação. O título da janela
do terminal é o nome da sessão (`set-titles-string "#S"`), e é por ele que o
`--focar` encontra a janela.

Os hooks rodam dentro do isolamento do agente. Arquivo novo que um hook
precise gravar fora de `agentes/` tem de entrar como gravável no
`jangada-isolar` (e existir antes do bind); sem isso a escrita falha calada,
porque o hook engole o erro.

## Scripts bash deste repositório

- Trap só em `EXIT`. Um trap em `INT`/`TERM` não encerra o script: o bash roda
  o handler e segue na linha seguinte.
- O fzf roda a prévia com o `$SHELL` do usuário; no zsh uma palavra começando
  com `=` (como `-t =sessao:` do tmux) é expandida. Chame o próprio script
  (`--previa`) em vez de montar o comando na string.
- Em sessões diretas no repositório (sem ramo nem worktree), `jangada-agente-fim`
  com `--integrar` avisa que não há ramo a integrar, sai com erro e mantém a
  sessão.
- `read -p` só mostra o texto quando a entrada é um terminal. Aviso que um
  teste precisa ver (ou quem responde por cano) sai num `echo` antes da
  pergunta.
- Testes de abertura que herdam `TMUX` e `HYPRLAND_INSTANCE_SIGNATURE`
  fazem o `jangada-agente` buscar outro terminal, mesmo com tmux falso.
  Controle `TMUX` no ambiente do teste, como `TMUX=''` em
  `testes/agente-seletor.py`, para usar o `attach` falso.

## Avaliação local (`jangada-avaliar-ollama`)

Na avaliação pelo `jangada-avaliar-ollama`, o estado das delegações fica
separado, mas as marcas de jogos e memória de vídeo apontam para o estado
original, e cada repetição adquire a trava compartilhada do Ollama. Uma
pasta de estado vazia perde essas marcas e causa recusa por
memória não verificável no isolamento; essa recusa não avalia o modelo.

## Revisão cruzada (`jangada-validar`)

Na CI do Arch, o `sandbox-e2e` instala R e `lintr`. O pacote R `xml2`,
dependência do `lintr`, precisa de `libxml2` e de `pkgconf`, que fornece
`pkg-config` para localizar os cabeçalhos em `include/libxml2`. Instalar
apenas `libxml2` pode produzir a mensagem de biblioteca ausente mesmo com
os cabeçalhos presentes. Confira com `pkg-config --cflags --libs libxml-2.0`.
O `install.packages()` pode terminar com código 0 após falhas de compilação;
carregue `library(lintr)` na mesma etapa para a falha aparecer na instalação,
antes dos testes de capacidades.

O `jangada-par` (Claude implementando em lote, agy revisando) saiu em
22/09/2026: o agente interativo com o protocolo faz o mesmo sem uma segunda
porta de entrada. O que se aprendeu com ele vale para o revisor agy:

- Por padrão, Codex revisa Claude e Claude revisa Codex. Fora de sessão e
  nas sessões antigas do agy, Claude revisa.
  Com `--revisor mesmo` ou num perfil pessoal com o revisor igual ao
  executor, o mesmo modelo revisa em processo isolado.
- Revisor que falha (agy sem cota, por exemplo) passa a vez: outros modelos
  na ordem `claude`, `agy`, `codex`, e por último o do autor. Não passa com
  `--revisor` nem com o prazo vencido. O estado e o `validar.jsonl` dizem
  quem deu o parecer.
- Sem terminal, o agy não tem como pedir permissão: comando ou escrita é
  recusado e ele devolve `status: SUCCESS` com `response` vazio. O pedido
  manda **não executar comandos** e ler com a ferramenta de leitura.
  `--dangerously-skip-permissions` foi recusado de propósito.
- A ferramenta de leitura carrega o arquivo inteiro: um PDF ou planilha grande
  estoura o limite de 1.048.576 tokens. O pedido proíbe binários, e o diff tem
  teto (`JANGADA_VALIDAR_DIFF_MAX`).
- Às vezes sai com código 0 sem escrever nada. Repetir resolve; o
  `jangada-validar` tenta duas vezes.
- A saída do agy é lida por cano, não por arquivo: ele reabre o próprio
  descritor, e com redirecionamento o JSON já foi parar num arquivo sem nome.
- O pedido vai como argumento, e o Linux limita um argumento a 128 KiB
  (`MAX_ARG_STRLEN`). Acima de 126000 bytes o diff sai do pedido e vai para
  `validacao-<sessao>-rN.md.diff`, que o agy lê pela pasta liberada em
  `--add-dir`.
- A revisão pelo agy leva minutos; o protocolo manda dar 10 minutos de tempo
  limite à ferramenta de comando.
- O revisor erra sobre `set -e`: falha dentro de uma lista `a && b && c`, fora
  do último comando, não encerra o script. Teste com `bash -c` antes de aceitar.
- Ao preservar o contexto da revisão, o pedido pode ultrapassar os 128 KiB
  de um argumento do Linux. Passe o texto ao `jq` pela entrada padrão,
  com `-Rs`; `--arg pedido` falha antes de chamar o revisor.
- Dentro do isolamento, parecer, `.aprovado` e `validar.jsonl` ficam onde o
  agente grava e não provam revisão. Fora dele (`JANGADA_ISOLADO` vazio), o
  `jangada-validar` grava em `revisoes/`, oculta pelo `jangada-isolar`, e lê
  base, tarefa e revisor da cópia `revisoes/SESSAO.json`. Os testes que
  chamam o `jangada-validar` sem querer esse modo passam `JANGADA_ISOLADO=1`.
- Prefira fazer o commit antes de `jangada-validar`, para revisar uma entrega
  limpa. O comando também aceita alterações sem commit; nesse caso, registra
  a aprovação com `limpo` falso. Veja o [ciclo da tarefa](../../../../docs/ciclo-da-tarefa.md).
- `.aprovado` com `limpo` falso (worktree com alteração sem commit) não move o ponto
  de comparação: com o commit igual ao `HEAD`, a próxima rodada daria "nada a
  revisar" sem ninguém ter visto o commit sozinho.
- O Git não reconfere o hash de um objeto solto ao ler. A revisão fora do
  isolamento busca objetos em espelho protegido. A trava por repositório
  coordena o Jangada, mas não impede o editor ou Git externo de escrever.
  Uma falha posterior ao avanço não autoriza `reset --hard`: ele pode apagar
  uma edição concorrente. O `--integrar` só avança com `merge --ff-only`,
  com a cópia principal sem alterações, e uma divergência depois do avanço
  só gera aviso; `update-ref` sozinho não garante consistência do worktree.
- Uma marca só encurta a próxima revisão quando está protegida em `revisoes/`,
  registra execução local completa e revisão independente e bate com
  candidato, árvore e base. Marca gravável pelo agente não vale para isso.
- `read -p` só mostra a pergunta com a entrada num terminal. Teste que
  responde pela entrada padrão confere a mensagem anterior à pergunta, não a
  pergunta.
- O `jangada-validar` executa uma checagem determinística local antes do revisor por IA (marcadores de conflito do Git, sintaxe de scripts alterados e `.jangada/validar.sh`). Se falhar, grava `STATUS: REVISAR (local)` sem acionar a API externa, economizando tokens. A opção `--pular-local` permite obter um parecer diagnóstico, mas não aprovação. O arquivo `.verificacoes.tsv` distingue PASSED, FAILED, UNAVAILABLE, SKIPPED e NOT_APPLICABLE.
- Um comentário de shell que começa pela palavra `shellcheck` vira diretiva e
  quebra a análise do arquivo inteiro (SC1073). Reescreva a frase.
- O `gitleaks dir` lê sozinho o `.gitleaks.toml` e o `.gitleaksignore` da
  pasta examinada. O espelho das linhas novas não copia esses dois arquivos;
  as regras vão por `--config` e `--gitleaks-ignore-path`, tiradas da base.
- Ao atingir o limite de rodadas, `--reverter-se-limite` preserva arquivos e
  commits. A reversão automática está bloqueada. O `reverter` manual do
  shell ainda confirma descarte, mas o ramo de cópia guarda somente commits:
  não preserva arquivos novos ou alterações sem commit. Não o use sem backup.
- No perfil de verificação, Bubblewrap precisa criar namespace de rede e
  soquetes internos de loopback. Um sandbox externo pode permitir a chamada
  básica e impedir esse perfil. Nesse caso a validação falha, e os testes
  reais continuam pendentes; não substitua por execução fora do isolamento.


Depois de integrar uma mudança no próprio jangada, confira os
commits e atualize a cópia instalada com `git merge --ff-only`.

## agy como suporte

- O agy não abre sessão principal desde 03/10/2026: o `jangada-agente`
  recusa `--agente agy` e perfil com `COMANDO=agy`. Ele atende o
  `jangada-delegar` e a revisão do `jangada-validar`. Sessão antiga do agy
  aberta sem perfil ainda é restaurada pelo `jangada-agentes`.
- O seletor do `jangada-agente` oferece o padrão e os perfis, cada um com a
  descrição calculada entre parênteses. Os perfis de `agentes/perfis/`
  são dois: `claude-codex.conf` e `codex-claude.conf`, com
  revisor de outro provedor e `JANGADA_DELEGAR=agy`. Perdem para perfis de
  mesmo nome em `~/.config/jangada/agentes`, onde também ficam autorrevisão,
  revisor agy e os destinos `claude` e `local`. O agy só atende em pasta
  marcada como confiável nele; se recusar, a sessão principal faz o trabalho.
- O estado da sessão guarda o nome do perfil, e o `--restaurar` recusa perfil
  que não existe mais. Retirar ou renomear um perfil padrão pede migração do
  campo `perfil` em `~/.local/state/jangada/agentes/*.json`.
- O protocolo é `agentes/perfis/protocolo.md`. No Claude vai por
  `--append-system-prompt` e no Codex pelo `jangada-codex`; na restauração o
  `jangada-agentes` monta o protocolo de novo (`refazer_protocolo`), sem ler o
  `comando` guardado.
- Hooks do agy: só o global `~/.gemini/config/hooks.json` foi carregado pelo
  CLI nos testes de 22/09/2026. O `.agents/hooks.json` do projeto deu "loaded 0
  named hooks" no log (`~/.gemini/antigravity-cli/log/`). O hook roda com a
  pasta do `hooks.json` como diretório atual e herda o ambiente, inclusive
  `JANGADA_SESSAO`.
- Skills do agy: a raiz global é `~/.gemini/config/skills/<nome>/SKILL.md`
  (teste de 26/09/2026). Não é `~/.gemini/antigravity/skills` nem
  `~/.gemini/antigravity-cli`, como sugerem textos da web. O agy segue link
  simbólico e aceita o frontmatter do Claude Code (`name`, `description` com
  `>`). A referência oficial vem no próprio CLI, em
  `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/`.
- Antes de cada comando, o agy regrava `~/.gemini/antigravity-cli/bin/agentapi`
  (teste de 28/09/2026). Com a pasta somente leitura, todo comando falha com
  "failed to write agentapi script: read-only file system"; por isso o
  `jangada-isolar` a monta em camada temporária.
- **Não registre `PreToolUse` respondendo `{}`**: o agy trata como recusa e a
  ferramenta é negada ("tool call denied by pre-tool hook").
- O Stop traz `fullyIdle`, `terminationReason` e `error`; não traz a última
  resposta. No jq, `.fullyIdle // true` dá `true` mesmo com `false`.
- **Arquivo de configuração vazio passa calado pelo jq**: `jq FILTRO arq` com
  `arq` de 0 bytes não devolve nada e sai com 0. Uma conferência que espera
  saída vazia para "nada falta" dava os hooks por instalados, e a mescla os
  dava por já instalados sem gravar. Leia com `jq -n '(first(inputs) // {})'`
  ou confira antes com `jq -e 'type == "object"'`. Em 28/09/2026 o
  `~/.claude/settings.json` real apareceu com 0 bytes, sem causa achada, e o
  `jangada-verificar` dizia que estava tudo certo.
- Chamadas auxiliares desligam os hooks da sessão: o `jangada-validar` chama
  o revisor com `env -u JANGADA_SESSAO JANGADA_HOOK_DESLIGADO=1`, que os dois
  hooks respeitam.
- A confiança do agy na pasta é por caminho exato (`trustedWorkspaces` em
  `~/.gemini/antigravity-cli/settings.json`; confiar em `~` não cobre as
  subpastas). Só o `jangada-worktree-preparar` e o fim da sessão mexem
  nela; o `jangada-delegar` recusa pasta sem confiança em vez de confiar,
  porque a confiança libera agentes, regras e MCP da própria pasta. O
  worktree só herda a confiança da raiz: se o usuário não confiou no
  repositório principal, o `jangada-worktree-preparar` não confia no
  worktree, e o agy abre com a pergunta "Do you trust the contents of this
  project?", que o usuário responde na janela.
- A preparação do worktree roda uma vez, na criação. Raiz autorizada no agy
  depois disso deixava a tarefa sem confiança para sempre, e o
  `jangada-delegar` recusava com código 4. Agora a conferência é separada da
  preparação (`jangada-worktree-preparar --so-confianca`, sem cópia e sem
  `.jangada/preparar.sh`) e roda na abertura, no reaproveitamento e na
  restauração de tarefa que delega ou revisa pelo agy. Para tarefa já aberta:
  `jangada-agentes --confianca SESSAO`, fora do isolamento.
  A sincronização exige que o Git aponte o worktree como registrado na raiz
  autorizada, lê a raiz da cópia em `revisoes/` (o estado em `agentes/` é
  gravável pelo agente) e relê o `settings.json` depois de gravar. A raiz
  nunca é gravada pelo jangada: fechar o agy sem responder não vale como
  autorização.
  A pasta `~/.gemini/antigravity-cli` é gravável pelo agente isolado, e o
  fim da sessão regrava o `settings.json` de fora do isolamento: se o arquivo
  virou link simbólico, o jangada não mexe nele, e a troca é por rename
  (`jangada_gravar_atomico`), que não segue link.
- Para testar hooks sem tocar no estado real, mude `XDG_STATE_HOME`; o
  `jangada-config` recalcula `JANGADA_ESTADO` a partir dele.
- Clones de referência em subpastas (como `referencia/`): se contiverem
  `CLAUDE.md` ou `AGENTS.md`, o harness do Claude ou do agy pode carregar os
  arquivos de terceiros como se fossem regras do projeto. Apague esses arquivos
  de dentro de `referencia/` logo após clonar.

## Subagentes do agy

Hooks do agy, testados em 28/09/2026:

- `~/.gemini/config/hooks.json` agrupa por nome (`{"jangada": {EVENTO:
  [...]}}`). `PreInvocation` e `Stop` levam os comandos direto na lista;
  `PreToolUse` leva `{"matcher": "run_command", "hooks": [{"command": ...}]}`.
- O `PreToolUse` recebe JSON em camelCase (`conversationId`,
  `toolCall.name`, `toolCall.args.CommandLine`) e precisa responder JSON:
  `{"decision": "allow|deny|ask|force_ask", "reason": ...}`. `{}` conta como
  recusa, e saída inválida dá erro na ferramenta. Por isso o
  `jangada-hook-leitor --agy` responde `deny` também quando o Python falha.
- O hook global dispara para todos os agentes, também para subagentes. O
  `conversationId` é o do subagente, e o tipo dele está em
  `brain/MAE/.system_generated/subagents/CONVERSA.json`
  (`subagentDescriptor.typeName`). No `agy -p --agent PAPEL` não há esse
  arquivo: o papel vem da variável `JANGADA_AGY_PAPEL`.
- Sem terminal, `allow` e `ask` só deixam passar o que está em
  `permissions.allow`; `ask` é a resposta neutra.
- Para testar um hook que recusa, peça um comando que o modelo ache de
  leitura e que esteja no `permissions.allow` (como `sort`). Com `cp`, o
  próprio leitor recusa pelo texto do papel, e o hook nem é chamado.

Agentes personalizados:

Testes de 27/09/2026, agy 1.2.12:

- Agente personalizado em `agent.md` (frontmatter YAML, prompt depois de um
  título H1), numa pasta listada em `~/.gemini/config/agents.json`
  (`{"entries": [{"path": PASTA}]}`, lida um nível abaixo). A pasta
  `~/.gemini/config/agents/` sozinha não é lida.
- `model:` aceita só `flash`, `pro` ou `inherit`. Com o nome completo
  (`gemini-3.8-flash-low`) o agente some sem aviso. O esforço vai na
  chamada: `agy -p ... --agent PAPEL --model gemini-3.8-flash-low`.
- **`--agent` com nome desconhecido não falha**: cai no agente padrão, com
  todas as ferramentas. Só o log diz (`Agent "x" not found, falling back to
  default`). Confira com `agy agents` antes da chamada, como fazem o
  `jangada-delegar` e o `jangada-validar`: falha fechada, não aberta.
- `tools:` restringe de fato; `manage_task` e `send_message` vêm sempre.
- No `-p`, `run_command` é negado sem regra em `permissions.allow`
  (`denied_actions` no JSON e `response` vazio).
- O JSON do `-p` traz `usage` (`input_tokens`, `output_tokens`,
  `total_tokens`) e `duration_seconds`.
- `agy -p "/usage" --output-format json` responde em uns 3 segundos, sem
  gastar cota: a fração restante fica em
  `.command.data.groups[].buckets[]` com `id` `gemini-5h`, `gemini-weekly`,
  `3p-5h` e `3p-weekly` (`remaining_fraction`, de 0 a 1).
- **O limite de 5 horas sozinho engana**: com a semanal zerada, o `/usage`
  devolve `gemini-weekly` em 0 e `gemini-5h` em 0,99 com `"disabled": true`,
  e toda chamada falha com 429 (`RESOURCE_EXHAUSTED`). Em 03/10/2026 o
  `jangada-delegar` lia só o `gemini-5h` e mandava ao agy sem cota. A cota de
  um grupo é a menor fração entre os buckets sem `disabled`.
- Flash e Pro dividem o grupo `gemini-*`; trocar entre eles não rende cota.
  Os modelos Claude e GPT do agy usam o grupo `3p-*`. Por isso
  `JANGADA_DELEGAR_MODELOS` põe depois do Flash modelos do outro grupo.
- Falha ao iniciar `agy agents` não comprova ausência de um papel.
  No sandbox do Codex, soquete local proibido e logs somente leitura fizeram
  a consulta sair com código 1, sem catálogo. Capture código e erro antes
  de conferir nomes; registre `indisponivel`, sem ampliar permissões.
- Sob `pipefail`, `agy agents | grep -qx PAPEL` pode recusar um papel presente.
  O `grep -q` termina na primeira correspondência; saída posterior provoca
  SIGPIPE no produtor. Capture o catálogo completo de uma consulta bem-sucedida
  e depois confira o nome, como faz `jangada-delegar`.
- `agy agents` lista um nome por linha só dos agentes que carregaram (um
  `model:` inválido some da lista). Em 27/09/2026, com a saída num cano ou
  num arquivo e sem terminal (`setsid`, `</dev/null`), a lista saiu inteira.
- Agente com `subagent: false` e `model: inherit` carrega e atende ao
  `--agent` com `--model` na chamada (testado em 27/09/2026 com o `revisor`
  do `jangada-validar`, que negou criar arquivo e rodar comando).
- `--sandbox` restringe só o terminal. Leitura sem escrita vem do `tools:`
  do agente.
- `--dangerously-skip-permissions` não serve para delegar: libera escrita.
  O `jangada-delegar` usa `--sandbox` e depende do `permissions.allow`.

Pegadinhas da delegação local:

Testes de 29/09/2026, Ollama 0.34.4:

- **Isolamento e checagens do sistema**: dentro do `jangada-isolar` (`bwrap` com
  `--unshare-pid` e sem nós `/dev/nvidia*`), `pgrep` não enxerga processos do
  host (como Steam) e `nvidia-smi` não consegue comunicar com o driver. O host
  grava marcas em `$JANGADA_ESTADO/marcas/vram-livre` e `$JANGADA_ESTADO/marcas/jogo-ativo`
  antes de isolar e as renova conforme `JANGADA_MONITOR_INTERVALO` (padrão de
  30 segundos; valores perto ou acima de 120 s causam recusa por expiração no
  delegar), e o script consulta `/api/ps` no Ollama.
  O `nvidia-smi` pode escrever uma falha na saída padrão dentro do isolamento.
  Descarte qualquer saída que não seja numérica antes de consultar a marca
  de memória livre gravada pelo host; texto de erro não é medição.
- **Memória de vídeo com modelo residente**: com `keep_alive` ativo, o modelo
  permanece na memória de vídeo após a primeira chamada. A memória livre cai
  e pode barrar chamadas seguintes; é preciso consultar `/api/ps` e somar a
  memória do modelo já residente à memória livre.
- **Opção num_ctx obrigatória**: sem definir explicitamente `options.num_ctx`
  no `/api/chat`, o Ollama assume o padrão de 2048 tokens mesmo para modelos que
  suportam janelas muito maiores.
- **Truncamento de contexto**: se a entrada ultrapassar `num_ctx`, o Ollama
  trunca o texto sem emitir erro na resposta. Como `prompt_eval_count` pode
  reportar apenas o valor truncado (`tent >= ctx` não é garantia se o servidor
  já truncou a entrada), a proteção efetiva depende da checagem prévia do
  tamanho estimado do texto antes do envio.

Testes de 07/10/2026, `qwen2.5-coder:7b`, 10 tarefas de localização:

- **Regra de citação depois do documento**: o modelo respondia certo sem
  citar a linha, mesmo com o pedido de citação antes do texto. A regra ao fim
  do pedido, depois do documento, levou os acertos exatos de 17 para 21 em 30.
- **Exemplo com prefixo real**: com um modelo de formato genérico
  (`caminho:linha: trecho`), o modelo escreveu a palavra `caminho` no lugar
  do arquivo. O exemplo precisa ser um prefixo real do documento enviado.
- **Alternativa de "não encontrado"**: oferecer uma resposta pronta como
  `NAO_ENCONTRADO` fez o modelo desistir de respostas presentes no trecho
  (4 de 10 tarefas). A regra pede a busca no documento inteiro e não dá
  marcador de desistência.
- **Temperatura zero**: torna a resposta repetível (9 de 10 textos idênticos
  entre chamadas), mas não mudou a precisão medida.
- **Fatiamento e consolidação**: perguntas de localização sobre arquivo
  fatiado acertaram 2 a 3 em 10. Envie uma faixa que caiba em uma fatia
  (`--arquivos ARQUIVO:INI-FIM`).

Conversa aberta (`jangada-conversa`), Ollama 0.35.1, medida em 07/10/2026:

- **`think: false` no `qwen3:4b`**: o modelo raciocina do mesmo jeito e
  escreve o raciocínio em inglês dentro de `message.content`, fechado por
  `</think>`. O `/no_think` na mensagem não muda isso. Com `think: true` o
  raciocínio vai para `message.thinking` e a resposta sai limpa, em 18 s para
  duas frases. A janela já pede `think: true` a esse modelo; em outro que
  vaze, corta o que vem antes de `</think>` e muda o pedido seguinte.
- **Modelos que respondem rápido**: `qwen3:8b` obedece a `think: false`
  (5 s na mesma pergunta) e `qwen2.5-coder:7b` não raciocina (4 s).

## Perfis e ganchos

- Perfil: `~/.config/jangada/agentes/NOME.conf` com `COMANDO=`, `ARGS=`,
  `DESCRICAO=` e
  outras chaves em maiúsculas, que viram ambiente só daquela sessão (exemplo
  em `agentes/perfis/exemplo.conf`). O arquivo é lido, não executado.
  Na correção P0, `JANGADA_AGENTE_ISOLAR=0` não desliga o isolamento.
- Ganchos: executável `~/.config/jangada/ganchos/EVENTO` ou arquivos em
  `EVENTO.d/`. Eventos: `pos-tema`, `pos-agente-fim` (sessão, raiz, integrado),
  `pos-validar`, `pos-update`. Falha de gancho gera só aviso.

## Agente sem ferramentas e resposta progressiva

O agy aceita nomes desconhecidos em `--agent` e pode usar o agente padrão, com ferramentas. Confira `agy agents` antes de chamar um agente que deve rodar sem ferramentas. Claude fornece eventos parciais com `--output-format stream-json --verbose --include-partial-messages`; eventos `assistant` e `result` repetem o texto e não devem ser concatenados aos trechos recebidos.

- Função Bash definida dentro de outra não captura suas variáveis locais.
  A conferência da marca declara o caminho na própria função, pois também
  roda sob a trava depois de terminar a chamada de revisão.

## Fronteira de confiança da fila e encerramento

Bubblewrap preserva descritores adicionais herdados. Uma montagem somente
leitura não impede escrita por um descritor aberto antes do isolamento.
O lançador fecha esses descritores, exceto o cano do proxy criado por ele,
e recusa descritores padrão apontando para estado protegido ou sockets.
Arquivos protegidos com ligações físicas adicionais também são recusados.
O isolamento é obrigatório também na abertura e retomada de sessões.

A fila em `agentes/projetos` é somente leitura no isolamento, mesmo com
extras de escrita. O controlador fora do isolamento é quem reserva,
registra e autoriza conclusões. Um rótulo de revisor recebido por comando
não comprova que um modelo revisou: use supervisão efetivamente executada
ou decisão manual identificada, respeitando a política da atividade.

O encerramento arquiva pareceres, contextos das rodadas, prompts e marcas
em `revisoes/arquivo` antes de limpar documentos operacionais. Falha de
arquivamento mantém os originais. A aprovação antiga sem contexto deve ser
reconferida; a documentação da correção P0 descreve recuperação e limites.

Revisores chamados fora de uma sessão também precisam do Bubblewrap. A saída
protegida deve ser coletada por cano e escrita pelo controlador: herdar um
descritor do próprio parecer exporia o arquivo antes da montagem. A foto
congelada fica em `fotos/` do estado, e a cópia da suíte do `--integrar`, em
`integracoes/`: as duas levam os links versionados da entrega, e link dentro
de `revisoes/` faz o `jangada-isolar` recusar qualquer lançamento. As duas
pastas ficam ocultas; só a foto escolhida volta, somente leitura.
Prompts e protocolos são registrados antes de iniciar ou retomar a sessão.

## Piloto do implementador agy

- Selecione modelo e esforço do autor na abertura; `modelos_tarefa` protegido
  conserva a escolha na restauração, sem executar `.comando`.
- `jangada-delegar implementador` exige base SHA exata, fontes, arquivos
  permitidos e critérios. Modelo fixo: `gemini-3.8-flash-high`, sem alternativa.
- A cópia é somente leitura, com montagens graváveis de arquivos individuais.
  Um bind de arquivo impede rename; se a ferramenta depender disso, registre
  falha sem liberar o diretório. Novos arquivos vêm criados vazios na cópia.
- O modo cria Bubblewrap mesmo dentro da sessão. O CLI só grava em memória,
  sem Git, hooks pessoais, estado protegido ou terminal do implementador.
- A prova de kernel mostrou que `/tmp` vazio ainda permite criar arquivos
  irmãos transitórios. O modo monta a pasta acima da tarefa vazia e somente
  leitura; um diretório temporário separado atende o CLI, sem virar entrega.
- Em Bash, `$!` pode ficar ausente após substituição de processo num comando
  externo. Abra o cano com `exec {fd}> >(...)`, capture o PID, feche o descritor
  após a chamada e aguarde a captura antes de conferir o erro.
- O papel global `implementador` só lê. O controlador deriva um papel privado
  com edição, visível exclusivamente dentro da montagem restrita.
- D-Bus exige item de keyring já selecionado; o modo não permite CreateItem,
  SetSecret ou Delete. Renovação de login pode falhar; não amplie acesso.
  Sem `JANGADA_ISOLAR_KEYRING_ITEM` no `jangada.conf` o modo não abre. Grave
  `JANGADA_ISOLAR_KEYRING_ITEM=service=gemini username=antigravity` sem
  aspas: o arquivo é lido literalmente, e com aspas o agy espera 60 s e sai
  com "authentication failed or timed out".
- O agy 1.3.5 cria `~/.gemini/config/projects` ao abrir conversa; com
  `config` inteira somente leitura ele sai com código 1. O modo monta `config`
  em memória, devolve `agents.json` e `hooks.json` somente leitura e deixa
  gravável só `projects`.
- Sem terminal, o agy nega escrita que não tenha a regra
  `write_file(<caminho absoluto>)` em `permissions.allow`. O modo gera uma
  regra por arquivo permitido; não use curinga.
- Inspecione fontes, contrato, arquivos e relatório; aceite com ID, base e
  hash recebido. Teste depois de aceitar. Falha parcial pede inspeção manual.
- `aceita_pelo_autor` não significa testes passados nem revisão aprovada.
  Chame revisão forte com provedor explícito, sem alternativas automáticas.

Contrato: [piloto](../../../../docs/coordenacao-central/10-executor-agy.md).

- Em Arch com systemd-resolved, `/etc/resolv.conf` pode apontar para `/run`.
  Ocultar `/run` também oculta o DNS. A implementação devolve somente leitura
  o arquivo resolvido, preservando o ocultamento dos soquetes.
