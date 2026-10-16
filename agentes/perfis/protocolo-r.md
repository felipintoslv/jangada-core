9. Código R (o projeto tem arquivos R):
   - Escreva o mínimo que resolve o pedido: sem parâmetros, opções ou funções
     auxiliares que ninguém pediu.
   - Sem código comentado nem variável sem uso. Apague o que a sua mudança
     deixou órfão; código morto que já existia, aponte em vez de apagar.
   - Mensagem não vai por `cat()` nem `print()`. Aviso ao usuário:
     `message()` ou `cli::cli_inform()`, seguindo o que o projeto já usa;
     progresso: `cli::cli_progress_bar()`; falha: `stop()` ou
     `cli::cli_abort()`, nunca `cat()` seguido de `return(NULL)`.
     `cat()` e `print()` ficam em métodos `print.*`, `format.*` e `summary.*`
     e no relatório que um script imprime no fim, dentro de
     `# nolint start: undesirable_function_linter.` e `# nolint end`.
   - `tryCatch()` só com recuperação real. Valide entradas uma vez, na entrada.
   - Prefira vetorização e `vapply()` ou `purrr::map_*()`; use `seq_along()`
     em vez de `1:length()`; `return()` só para saída antecipada.
   - O `jangada-validar` roda o `lintr` nas linhas R que você alterou. Com
     `.lintr` já integrado ao projeto, um achado reprova a entrega; um
     `.lintr` que só a sua entrega traz não é lido.
