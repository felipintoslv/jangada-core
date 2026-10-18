# Correções

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

| Correção | Evidência e teste |
|---|---|
| Bloqueio de `--integrar`, inclusive confirmação gráfica e `--sem-revisao`, sob trava do repositório. Nenhum merge, rollback ou limpeza é iniciado. | `testes/fim.sh`: HEAD, índice, alterações, arquivos novos, sessão e worktree preservados; chamadas simultâneas recusadas. `testes/baseline.py`: conflito e publicação manual anterior preservados. |
| Retirada do rollback destrutivo e dos caminhos de integração que ficaram sem uso. | Reprodução do mecanismo antigo em repositório descartável e conferência do backend sem merge/reset. |
| Bloqueio de reversão ao atingir limite de validação. | Caso 11c de `testes/validar.sh` preserva o arquivo pendente. |
| Validação aplicável sem ferramenta reprova; lintr ausente ou falhando não aprova. | Ensaios de ferramentas ausentes em `testes/baseline.py`; casos 12e e 12i da suíte de validação. |
| Verificações registradas em `validacao-*-rN.verificacoes.tsv` com PASSED, FAILED, UNAVAILABLE, SKIPPED ou NOT_APPLICABLE. | Ensaio de entrega identificada e de validação pulada. Uma indisponibilidade pode também causar FAILED no conjunto. |
| Validação pulada, autorrevisão e autoria externa sem metadados protegidos não geram aprovação. | Casos de autorrevisão, caso 11b e ensaios da baseline, incluindo autoria sem cópia protegida. |
| Marcas usadas para encurtar diff exigem verificação local, independência, candidato, árvore e base; marcas graváveis pelo agente não encurtam revisão. | Ensaio de árvore inválida e caso 15 fora do isolamento. |
| Prazo nos scripts de validação do projeto e no lintr. | Limites explícitos de 300 segundos no projeto e 120 no lintr, seguidos de 5 segundos para encerramento. Execução real sem rede permanece bloqueada pelo ambiente. |
| Prévia confere verificação local, árvore e base antes de declarar aprovação válida. | Ensaio de prévia incompleta em `testes/baseline.py` e caso 21b. |
| CI instala `qt6-svg`. | Dependência já presente na instalação; importação de QtSvg confirmada localmente. CI remoto não executado. |

Os testes que esperavam merge automático passaram a exigir seu bloqueio e a preservação do estado. Os ensaios de atualização continuam com merge manual em repositório sintético, preservando cobertura de atualização e assinatura. Nenhuma suíte de isolamento foi desabilitada.
