# Testes da baseline 2026-10

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Todos os ensaios usaram repositórios, dados e provedores sintéticos. Nenhum projeto real, credencial ou instalação ativa foi usado para execução de agente ou restauração.

| Verificação | Resultado confirmado |
|---|---|
| `python3 testes/baseline.py` | 12 testes aprovados: rollback antigo reproduzido; entrega identificada; ferramentas ausentes; validação pulada; autorrevisão; autoria sem cópia protegida; árvore inválida; prévia incompleta; conflito e publicação anterior; interrupção da trava; SQLite com WAL; arquivos e metadados restaurados. |
| `testes/fim.sh` | Aprovado. Estado adulterado recusado; bloqueio em terminal, confirmação gráfica e sem revisão; preservação de HEAD, índice, pendências, arquivos novos, sessão e worktree; concorrência; encerramento normal. |
| `testes/update.sh` | Aprovado. Cópia instalada preservada pelo bloqueio; atualização, assinaturas, ganchos hostis e instalação simulada continuam conferidos em dados sintéticos. |
| ShellCheck dos arquivos alterados e `git diff --check` | Aprovados. A suíte completa também confere sintaxe Bash e Lua, JSON e regras de escrita. |
| `Rscript testes/painel-motores.R` | Aprovado. Indicadores e filtros, sem provedor real. |
| `Rscript testes/painel-operacional.R` | Aprovado. Identidade, ausência de dados, autenticação, leitura e monitoramento. Avisos de sessão Shiny simulada e de arquivo sintético ausente fazem parte dos casos. |
| Importação de QtSvg, D-Bus e GObject | Aprovada neste host; QtSvg acrescentado ao CI. |
| Capacidades exigindo `sem-rede` | Reprovado, código 1: Bubblewrap falha com `Failed to create NETLINK_ROUTE socket: Operation not permitted`. Demais ferramentas exigidas presentes. |
| `testes/verificar.sh` | Executado integralmente no código `5816c76e8182`; saída 1 e 7 grupos reprovados. Não é considerado aprovado. |

Grupos reprovados na execução final:

- `monitoramento sob demanda`.
- `testes/validar.sh`.
- `testes/isolar.sh`.
- `testes/tarefas.py`.
- `testes/conversa.py`.
- `testes/painel.sh`.
- `testes/delegar.sh`.

## Limites

Validações R isoladas e `.jangada/validar.sh` sem rede falham na preparação do isolamento neste sandbox. Isso preserva a recusa da aprovação, mas impede demonstrar os casos positivos. Os ensaios de D-Bus real e de servidor/soquete local também ficam impedidos. Testes de monitoramento, conversa, painel e delegação que dependem de serviço local sintético não comprovam seu fluxo completo aqui.

A suíte real de isolamento continua habilitada e reporta as falhas. Não foram usados `|| true`, execução direta ou mudança de serviços para transformar verificações obrigatórias em aprovação.

## Ponta a ponta

A suíte exercita cadastro e política de projeto, atividade e tarefa, fila, reserva, produção e conferência de artefato, supervisão, revisão e persistência com executores sintéticos. A baseline exercita revisão de commit congelado, aprovação independente sintética, bloqueio de integração e preservação. Os testes de tarefas verificam componentes Qt, prazos e estado.

Faltam sessão gráfica real, comunicação completa da Central, agente e revisor reais e isolamento sem rede funcional. Nenhuma aprovação sintética vale para uma entrega real. Não se declara ponta a ponta real aprovado.

## Reprodução em ambiente compatível

```sh
JANGADA_TESTES_EXIGIR='bwrap sem-rede shellcheck jq gitleaks zsh pdftotext pyarrow R lintr' \
JANGADA_TESTES_EXIGIR_ISOLAMENTO=1 testes/verificar.sh
Rscript testes/painel-motores.R
Rscript testes/painel-operacional.R
```

Use usuário comum, dados sintéticos e as dependências declaradas no CI. O CI remoto não foi disparado; sua alteração foi apenas local. Os registros em `/tmp/jangada-baseline-*` pertencem aos ensaios desta missão e podem desaparecer com a limpeza de temporários. `EVIDENCIAS.json` guarda códigos, nomes e hashes dos registros principais.
