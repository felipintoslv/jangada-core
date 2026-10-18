# Preparação da atualização local em 09/10/2026

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

**Preparada, mas bloqueada. A instalação não foi atualizada e main não foi alterada.**
As correções foram combinadas apenas no ramo `agente/tarefa-772f05785b35`.
A avaliação P1 continua inconclusiva.

## Identidade e preservação

| Componente | Identidade conferida |
|---|---|
| Instalação ativa | `0.1.0-345-g9e72e9d`, commit `9e72e9dec4306ff92adbb2e08703099f87ef34e3` |
| main documental | `6f2f8ace74e1e5793767e0f35a3d2a6f81e53863` |
| P0 incorporada no candidato | `17178ded546642e3246bfe3bd5c33df8da821874` |
| Combinação de código | `40d7d5c0727a6c3b32fb32a937503613374eef95` |

A combinação preserva a ancestralidade da baseline e da P0.
Os relatórios P0, P1 e `ACHADOS_ATUAIS.md` mantêm os bytes do commit documental.
Os componentes críticos iniciais correspondiam aos bytes da P0.
A preparação seguinte corrigiu o limite de argumentos do validador e acrescentou atualização de somente código.
A integração automática permanece bloqueada em `bin/jangada-agente-fim`.
O módulo `default/orquestracao/confianca.py` existe no candidato e falta na instalação ativa.

A cópia principal, a worktree P0 e a instalação estavam sem alterações rastreadas ou novas visíveis.
Não houve push, lançamento, alteração de serviços ou instalação de pacotes pelo agente.

## Impedimentos à aplicação

Esta sessão tem `JANGADA_ISOLADO=1` e namespace próprio de processos.
Ela não pode substituir o controlador instalado nem modificar a pasta principal.
A única sessão identificável pelo estado visível é `jangada--tarefa-772f05785b35`, esta execução.
Isso não certifica ausência de outras sessões no host.

`jangada-update` busca `origin`, que aponta para `$HOME/Projetos/jangada`.
Portanto, publicação remota não é necessária.
Entretanto, o comando também executa `sudo pacman -Syu` e atualização AUR.
A versão instalada não oferece seleção de somente código nem simulação dessas operações.
A versão preparada acrescenta `--somente-codigo`, sem pacotes, migrações, recarga ou ganchos.
Ela recusa simulação, isolamento e processos ou sessões ativos.
O atualizador não foi executado sobre a instalação ativa.
Não houve substituição manual de executáveis.

Há `allowed_signers` na configuração visível.
A conferência e assinatura supervisionada dos commits deve ocorrer fora do isolamento, antes de qualquer avanço da instalação.
As falhas da suíte completa também impedem apresentar o candidato como entrega aprovada.

## Cópia de segurança e ensaio de restauração

As evidências privadas estão em `mapeamento/atualizacao-segura-20261009/` desta worktree.
A pasta tem modo `0700` e é ignorada pelo Git.
Não remover esta worktree antes de preservar essa pasta em destino privado durável no host.
O pacote Git do candidato fica nessa mesma pasta; não contém o backup privado.

Foram copiados código instalado com metadados Git, configuração Jangada e estado visível completo.
A conferência abrangeu 2.601 arquivos regulares, 88 links e 257 bancos SQLite, sem pendências de cópia.
Para os bancos, as cópias privadas de banco e WAL foram conferidas quanto à estabilidade.
A API SQLite produziu bancos independentes nessas cópias, sem abrir as origens para escrita.
Todos passaram em `PRAGMA integrity_check`.
Os auxiliares WAL e SHM não acompanham os bancos normalizados no backup final.

A restauração foi ensaiada em `restauracao-ensaio/`, sem tocar nas origens.
Todos os arquivos e links corresponderam ao manifesto; os 257 bancos passaram novamente.
O `git fsck --full` da instalação copiada passou.
`manifesto-backup.json`, `integridade-backup.json` e `restauracao-ensaio.json` registram a conferência.
`identidade.json` guarda os hashes dos componentes críticos instalados e candidatos.

**Esta cópia é complementar, não um backup integral do host.**
O isolamento oculta caminhos protegidos, inclusive `revisoes/` e a chave do painel.
Também não certifica coerência conjunta de metadados e bancos enquanto os processos continuam escrevendo.
Não inclui projetos externos, todas as worktrees nem configurações completas dos provedores.
Links foram preservados; seus destinos externos não foram copiados automaticamente.

## Verificações executadas

| Verificação | Resultado |
|---|---|
| `testes/verificar.sh` | Código 1; quatro grupos falharam, execução completa em 207 segundos |
| `testes/baseline.py`, pela suíte | 12 testes passaram |
| `testes/confianca-p0.py`, ambiente limpo | 32 testes passaram, sem ignorados, com Bubblewrap real |
| `testes/tarefas.py`, pela suíte | 67 testes passaram |
| `testes/update.sh`, pela suíte | Passou com origem, instalação e comandos de sistema sintéticos |
| Simulação de `jangada-migrar` | Código 0; nenhuma migração pendente, usando configuração e marcas copiadas |
| Restauração privada | Hashes, links, SQLite e Git íntegros |

O teste P0 cobre cadastro, fila, execução isolada, provedores simulados, decisão protegida,
encerramento e recuperação integral de evidências em projetos descartáveis.
Não comprova esses caminhos na instalação ativa nem uma avaliação com modelos reais.
As validações da primeira preparação e da correção ficam nas evidências privadas.
O erro inicial de `jq --arg pedido` foi corrigido usando entrada padrão; o ensaio preservou integralmente um pedido acima de 128 KiB.
Os dez ensaios de atualização de somente código passaram em clones descartáveis.
Uma revisão da própria sessão não equivale à aprovação protegida pelo controlador.

Os quatro grupos com falhas são `testes/validar.sh`, `testes/isolar.sh`,
`testes/delegar.sh` e `testes/codex-economico.py`.
Parte dos testes legados espera desligamento do isolamento, comportamento recusado deliberadamente pela P0.
Também há falhas na conferência de R, cobertura de pareceres e execução aninhada.
Essas ocorrências permanecem pendentes de diagnóstico completo; não foram classificadas todas como limitações ambientais.

No grupo econômico, uma repetição com ambiente limpo confirmou quatro falhas.
Duas cópias sintéticas omitem `confianca.py` e falham na importação.
Outro cenário omite `jangada-isolar` e não alcança a conclusão esperada.
Esses defeitos do ambiente sintético não demonstram falha da instalação, mas impedem aprovar a suíte.
O primeiro ensaio de ambiente limpo também omitiu HOME; foi corrigido no comando, sem alterar o teste.
Nenhuma expectativa dos testes preexistentes foi enfraquecida.
Foram acrescentados ensaios de contexto grande e atualização de somente código.

## Continuação e recuperação no terminal externo

1. Preserve a pasta privada de evidências em destino novo fora das worktrees, com acesso restrito.
2. Liste as sessões reais e os processos no host. Guarde a saída dos terminais em arquivos privados.
3. Interrompa os executores pelo terminal, inclusive `jangada--tarefa-772f05785b35`, sem encerrar ou remover suas worktrees.
   Feche a Central e o painel. Não use o encerrador antigo para tentar comprovar arquivamento P0 da sessão par-cobaia.
4. Suspenda escritas no estado e nos projetos. Complete o backup conforme `BACKUP_RECUPERACAO.md`, incluindo revisões protegidas,
   históricos, configurações de provedores, worktrees e Git comum. Confira destinos de links e os bancos com seus WAL.
5. Resolva as falhas dos testes e obtenha revisão externa independente. Confira novamente main e todas as alterações concorrentes.
   Integre manualmente o ramo da tarefa em main, preservando o commit documental; não use `--integrar`, que permanece bloqueado.
6. Confira assinaturas e use o programa novo com `--somente-codigo`, conforme `docs/atualizacao-e-migracoes.md`.
   Não passe a opção à versão antiga instalada: ela não a reconhece e pode atualizar os pacotes.
   Sessões de tmux preservadas também bloqueiam o novo modo; guarde sua saída antes de encerrá-las pelo terminal.
7. Após um fluxo autorizado de aplicação, confira versão, SHA e hashes contra o candidato exato, e repita o ciclo descartável usando a instalação.

Para recuperar, mantenha os executores parados e preserve a instalação e o estado posteriores em cópias separadas.
Restaure primeiro o backup integral do host em pasta nova; confira seu manifesto, SQLite, Git e destinos dos links.
Reponha código, configurações, marcas de migração, bancos, artefatos, decisões e históricos como conjunto.
Não misture bancos normalizados com WAL antigos. Não remova o histórico produzido depois do backup.
Na restauração definitiva, preserve os caminhos dos worktrees ou confira um reparo Git supervisionado.
Retome processos apenas depois da conferência. Não é necessário reiniciar o sistema para estas alterações de código.
O encerramento dos executores antigos e a reabertura com o runtime conferido são necessários antes de usá-lo.

## Segunda sessão, ramo `agente/tarefa-ae233e9b0edf`

O ramo parte do candidato `a598b43` por avanço direto e acrescenta correções de testes, do limite do arquivo histórico e da documentação.
A pasta privada `mapeamento/atualizacao-segura-20261009/` continua na worktree `tarefa-772f05785b35`, sem alteração.

Estado da suíte, com `env -u JANGADA_ISOLADO ... bash testes/verificar.sh </dev/null`: restam 17 falhas em `testes/validar.sh` e `testes/isolar.sh`.
Todas têm a mesma causa: `bin/jangada-isolar` chama `preparar-isolamento` também na verificação aninhada, e `exigir_controlador` recusa.
Com o candidato instalado, o `jangada-validar` chamado de dentro de uma sessão reprova todo projeto com arquivos R ou `.jangada/validar.sh`.
O revisor externo apontou o mesmo defeito. A correção altera o código do isolamento e ficou para decisão do usuário.

Achados para a aplicação:

- Nenhum dos commits entre `9e72e9d` e o candidato tem assinatura, e `~/.config/jangada/allowed_signers` existe.
  O atualizador novo recusa até que `jangada-assinar` os assine no terminal externo. A assinatura troca os SHA, não o conteúdo.
- A árvore de `git merge-tree --write-tree 6f2f8ac 17178de` é igual à da mescla `40d7d5c`; o `jangada-assinar` deve refazer a mescla sem divergência.
- O `jangada-isolar` novo recusa abrir quando a entrada, a saída ou o erro padrão é um socket.
  Terminal e tmux não são afetados. Um controlador que chame `jangada-validar` ou `jangada-delegar` com saída ligada a socket recebe
  `descritor padrão expõe estado protegido ou socket`. Nos testes, use `</dev/null` e saída em arquivo ou pipe.
