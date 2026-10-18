# Comandos do jangada-core

Os comandos da área de trabalho (jangada-shell) e do painel e dos indicadores
(comandos opcionais, fora do Core por ora) estão na documentação desses repositórios.

## Comandos

| Comando | Função |
|---|---|
| `jangada doctor` ou `jangada-doctor` | diagnóstico somente de leitura do Core, com resumo por resultado; `--json` imprime o contrato versão 1 e `--ajuda` descreve o uso; não atualiza cotas, credenciais, hooks nem migrações |
| `jangada-versao` | mostra a versão da cópia (`0.1.0`, ou `0.1.0-3-gabc1234` com commits depois da tag); `--novidades [DE [ATE]]` lista as mudanças, `--registro` imprime o registro completo e `--lancar X.Y.Z` grava o `CHANGELOG.md`, faz o commit e cria a tag `vX.Y.Z` (sem push); `-C DIR` opera em outro repositório |
| `jangada-assinar` | assina com a chave SSH (`JANGADA_ASSINATURA_CHAVE`) os commits da cópia de trabalho ainda não enviados e sem assinatura válida, depois da confirmação; roda num terminal comum, porque o isolamento oculta o `~/.ssh` |
| `jangada-agente` | escolhe o agente (Claude ou Codex; o agy fica só de suporte), o projeto e cria um worktree, e abre o agente numa sessão tmux, isolado pelo `jangada-isolar` (`--prompt`, `--prompt-arquivo`, `--perfil`) |
| `jangada-isolar` | roda um comando no bubblewrap, com o sistema somente leitura e a pasta atual gravável; `--mostrar` imprime a chamada ao `bwrap` |
| `jangada-delegar PAPEL "pedido"` | executa o apoio com destino e fontes explícitos; veja [subagentes e delegação](subagentes-e-delegacao.md) |
| `jangada-avaliar-ollama` | repete três casos de leitura com fontes sintéticas, compara fatos e referências com um gabarito e registra recusas, tempo e variação; não promove o modelo nem chama provedores remotos |
| `jangada-fila` | mostra a fila persistente do projeto; `--importar PLANO.json` acrescenta tarefas, `--json` detalha o estado, `--revisao` lista o que aguarda revisão e `--metricas` resume consumo, revisões e custo estimado pelos preços de `precos.json` (ver [fila](subagentes-e-delegacao.md#fila-persistente-de-projetos)) |
| `jangada-projeto` | cadastra projeto e política, cria atividade, reassocia caminho e consulta sessões, fila, execuções e revisões; `consultar --todos` reúne todos os projetos sem alterar o estado |
| `jangada-executar` | executa tarefas elegíveis da fila pelo `jangada-delegar`, sem aprovar o conteúdo (`--limite`, `--perfil balanced\|quality\|offline`, `--permitir-remoto`, `--permitir-codex`, `--supervisionar`, `--amostrar`, `--paralelo`); `--acompanhar` mantém a fila em primeiro plano até o prazo |
| `jangada-retomar` | recoloca na fila tarefas que esperavam cota ou provedor, quando há executor, orçamento e tentativas (`--atualizar`, `--executar`) |
| `jangada-task ID AÇÃO` | controla uma tarefa: `pausar`, `retomar`, `cancelar`, `repetir`, `revisar --aprovar\|--reprovar --parecer` (aceita `ID1,ID2` no mesmo parecer), e `assumir`, `entregar` e `executar-principal` para os agentes principais |
| `jangada-router status` | estado, cota e espera dos provedores (`--atualizar`, `--atualizar-codex`) |
| `jangada-provedor pausar\|ativar ID` | tira um provedor da execução da fila ou o devolve |
| `jangada-filtrar` | roda um comando e condensa a saída para o agente (`-m`, `-e`, `-p`); prefira `jangada-filtrar -- COMANDO` ao modo cano, que não vê o código de saída |
| `jangada-mapa [PASTA]` | mapa compacto do repositório (arquivos e assinaturas de funções) para dar contexto a um agente |
| `jangada-worktree-preparar` | leva para um worktree novo os arquivos ignorados que o projeto precisa (chamado pelo `jangada-agente`) |
| `jangada-validar` | confere a entrega localmente e manda o diff ao revisor configurado (Claude, agy ou Codex) e devolve `STATUS: APROVADO` ou `REVISAR`; ferramenta aplicável ausente, validação pulada e autorrevisão não aprovam; o agente chama antes de entregar |
| `jangada-agentes` | lista as sessões de agentes, com estado, e permite abrir, integrar ou encerrar (`--proximo`, `--anterior`, `--restaurar`) |
| `jangada-coordenador` | abre o coordenador de um projeto (`--projeto PASTA [--provedor claude\|codex]`), um por projeto, sem worktree nem isolamento, com modelo forte explícito (`opus` ou `gpt-6-astra`); falhas do cliente mantêm o painel para conferência; outro provedor exige saída voluntária da sessão anterior, conforme a [passagem manual](ciclo-da-tarefa.md#coordenador); `--fim SESSAO` encerra a sessão e mantém as tarefas. Consulta: `jangada-agentes --coordenadores-json` |
| `jangada-agente-fim` | encerra uma sessão e remove o worktree após conferência; `--integrar` exige aprovação independente protegida, confirmação humana e testes; mantém sessão, ramo e worktree. Veja [ciclo da tarefa](ciclo-da-tarefa.md#fim-da-sessão) |
| `jangada-gancho` | roda os ganchos do usuário de um evento (chamado pelos outros comandos) |

## Diagnóstico do ambiente

`jangada doctor` lista programas obrigatórios e opcionais, teste mínimo real
de namespaces, registros dos provedores, credenciais locais, cotas observadas,
requisitos de isolamento, hooks, modelo local, versão, migrações e pastas de estado.
Cada item informa `ok`, `aviso`, `falha` ou `nao_verificavel`. Uma consulta
indisponível não interrompe as seguintes. Saída 1 indica alguma falha; 0 permite
avisos e itens não verificáveis. Argumento inválido devolve 2.

O JSON tem `versao: 1`, `gerado_em`, `verificacoes` (objetos com `id`,
`categoria`, `estado` e `detalhe`), `resumo` (contagem dos quatro estados) e
`codigo_saida`. O texto segue a apresentação por item e resumo do `cata doctor`.

As consultas não iniciam clientes de agentes, login, geração, migrações ou
regravação de hooks. O teste de bubblewrap executa apenas `/usr/bin/true`, com
raiz somente leitura e prazo de 3 segundos. Ele não comprova as montagens de
cada provedor. O comando não chama `jangada-isolar --mostrar`.

O saldo do agy vem apenas de `agy-usage.json`, dentro do prazo do cache;
o do Codex vem da observação ainda válida em `agentes/runtime/tarefas.sqlite`.
O banco é lido para memória, sem abrir a origem com SQLite; com WAL presente,
o saldo fica não verificável. Claude não tem contrato de saldo local vigente.
Cota ausente, vencida ou inválida fica não verificável, sem atualização pela rede.
Credencial presente comprova só o formato local; login no servidor e keyring
do agy não são consultados. Nenhum segredo ou configuração completa é impresso.

O Ollama recebe apenas `GET /api/tags`, em HTTP de `localhost`, `127.0.0.1`
ou `::1`, sem proxy nem redirecionamento. O relatório informa se o modelo
configurado está presente, sem carregá-lo ou testar geração e memória.
Outros endereços ficam não verificáveis. Provedores adicionais do registro
recebem resultados próprios, sem presumir contratos de autenticação ou isolamento.

A versão compara a cabeça da cópia indicada por `JANGADA_CORE_PATH` com
`refs/remotes/origin/main` ou `estavel`, já disponível localmente. Confere a
assinatura SSH da referência e dos commits pendentes por `allowed_signers`,
até 512 commits. Não busca referências na rede nem garante atualidade remota.
Sem assinantes ou referências locais, a comparação fica não verificável.

Os hooks de Claude e agy são comparados com os padrões registrados em arquivo;
isso não comprova execução. Os do Codex são fornecidos pelo adaptador em cada
sessão e ficam não verificáveis sem iniciar o cliente. As pastas ausentes não
são criadas. Dono e modos são observados, sem teste de escrita ou análise de ACL.
Dentro de isolamento, os resultados descrevem apenas o ambiente visível ali.
