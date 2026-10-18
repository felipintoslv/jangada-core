# Diagnóstico da baseline 2026-10

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Inspeção em 08/10/2026. Origem: `bf7a5f1e7b11c7156d94de42c7869ed98940c20d`, ramo `main`, sem alterações locais. Havia uma worktree, a de origem. Intervenção na worktree `jangada-baseline-2026-10`, ramo `estabilizacao/baseline-2026-10`. Os arquivos da origem, o ramo `main` e a instalação ativa foram preservados. O Git comum recebeu apenas o registro da worktree, o ramo de estabilização e seus commits locais.

| Prioridade | Evidência confirmada | Tratamento |
|---|---|---|
| P0 | `mesclar_sob_trava()` publicava no worktree principal e usava `reset --hard` quando a conferência posterior falhava. A trava não cobre o editor ou Git externo. | Integração automática bloqueada no backend. Reprodução sintética em `testes/baseline.py`. |
| P0 | `jangada-validar --reverter-se-limite` usava `reset --hard` e `clean -fd` em worktrees, sem preservar arquivos pendentes. | Reversão automática bloqueada. |
| P1 | Integração pelo terminal podia prosseguir sem revisão. A aprovação consumida não exigia `local_verified`. | Nenhuma aprovação, confirmação ou opção libera a integração automática. |
| P1 | ShellCheck, luac e Rscript ausentes podiam ser ignorados. Código 2 do lintr era ignorado; falha sem `.lintr` podia apenas avisar. | Verificação aplicável indisponível ou falha impede aprovação. |
| P1 | `--pular-local` e exceção do gitleaks permitiam parecer aprovado sem todas as verificações. Autorrevisão podia produzir `STATUS: APROVADO`. | Aprovação incompleta e autorrevisão viram `REVISAR`; não criam marca. |
| P1 | Sem cópia protegida da autoria, o estado gravável pela sessão podia simular independência. | Parecer continua disponível, mas a aprovação é recusada sem autoria protegida fora do isolamento. |
| P1 | Marca anterior podia encurtar revisão sem conferir independência, execução local, árvore e base. | Somente marca protegida e vinculada aos objetos pode encurtar o diff. |
| P1 | CI principal instalava PyQt6, mas não `qt6-svg`, importado pela Central. | Acrescentada dependência; instalação já a declarava. |
| P1 | Script de validação do projeto não tinha prazo próprio. | Prazo de 300 segundos e encerramento forçado após mais 5. |
| P2 | `nucleo/consultas.py` carrega tarefas, execuções e eventos completos. | Sem falha bloqueante reproduzida. Backlog com medição antes de alterar consultas. |

## Inspeções sem defeito confirmado

A sessão cria worktree e protocolo; o Codex passa por isolamento obrigatório. Git fora do isolamento usa `jangada_git_blindar`, desliga ganchos e monitor de arquivos. A revisão congela uma entrega e, fora do isolamento, busca objetos em espelho protegido. Scripts do projeto e `.lintr` continuam no perfil de verificação, que exige Bubblewrap. A marca de isolamento é conferida em montagens, não apenas por variável de ambiente.

As travas usam `flock` com espera limitada, ou trava por diretório com PID. SQLite usa WAL, chaves estrangeiras e transações. Consultas copiam banco e WAL com conferência de alterações. Processos da Central têm temporizadores. `idade()` aceita fuso e trata horário inválido; não se confirmou defeito de timestamp. A instalação recusa worktree para execução real e oferece simulação. O CI já declara `pkgconf` e exige `library(lintr)` após instalar o pacote.

## Limites do ambiente

O sandbox permite Bubblewrap básico, mas recusa namespace de rede e abertura de servidores e soquetes locais. Testes com servidor HTTP local, soquete da Central, perfil sem rede e D-Bus real falham com restrições do ambiente. Não houve tentativa de alterar serviços, pacotes, permissões globais ou contornar o sandbox. Essas falhas não demonstram aprovação nem, isoladamente, defeito no Jangada.

A revisão por provedores reais, a sessão Hyprland e a instalação completa não foram executadas. Os provedores dos ensaios são sintéticos e não transmitem dados.
