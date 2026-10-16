# Diagnóstico opcional do Monitor

`jangada-monitor --json` acessa `default/painel/monitoramento.py`, cuja fonte única permanece em `monitor/painel/monitoramento.py`.
O comando e os testes de diagnóstico dispensam o caminho interno do Core.
O coletor permanece intacto: CPU e memória vêm de `/proc`, GPU de `nvidia-smi` e modelos carregados de `/api/ps` local.
Essa consulta não gera modelos nem constitui delegação; a política agy não muda.

## Compatibilidade e fronteira

A fachada `bin/jangada-monitor` e os campos `data`, `cpu_ticks`, `memoria_bytes`, `gpu`, `modelos_carregados` e `erros` permanecem iguais.
O modo JSON não abre terminal. Sem Monitor, sai com código 1, mensagem explícita no stderr e stdout vazio.
Medições indisponíveis continuam nulas com erros explícitos; não se transformam em zero ou sucesso vazio.
Os limites de tamanho e as recusas de endereço remoto, redirecionamento e JSON inválido permanecem no coletor.

O link `nucleo/monitoramento.py` foi preservado somente por compatibilidade, sem cópia de implementação.
Ele mantém `nucleo/monitoramento.py`, documentado na modularização e usado por `monitor/painel/operacional.R:247`.
Retirá-lo quebraria esse consumidor versionado. Os dois caminhos legados entram na prova K2 de links relativos internos.
A classificação K9 atribui o arquivo legado ao Monitor pela entrada específica, com precedência sobre a pasta do Core.
Uma regressão confere que esse acesso também recusa importação de classe de escrita; nenhuma exceção de fronteira foi acrescentada.

## Prova sintética e limites

`testes/monitoramento.py` importa a fonte do Monitor e executa o comando público numa cópia sem Core físico.
Usa API local sintética, GPU falsa e terminal sentinela; confere schema, consulta exclusiva de listagem e recusa quando o Monitor desaparece.
Os cenários negativos cobrem servidor/GPU indisponíveis, endereço remoto, redirecionamento, JSON inválido e listagem acima do limite.

`testes/core-independente.sh` copia Core e fachadas sem Shell/Monitor físicos, mantendo o link de compatibilidade pendurado.
Confere importações, consulta de sessão sintética sem escrita na origem e revisão falsa na ausência do resumo opcional.
Uma falha obrigatória de sintaxe shell impede revisão mesmo sem diagnóstico.
O percurso R de A2 permanece: R/lintr reais, isolamento, prioridade da regra da base e recusa sem padrão obrigatório.
Sem R/lintr, esse percurso sai com 77 e `UNAVAILABLE`; a prova R não é apresentada como executada.

O link preservado continua sendo acoplamento físico opcional, não uma dependência obrigatória demonstrada de execução do Core.
Este recorte A3 não elimina todos os acoplamentos, não conclui M1 e não cobre consultas A4/A5 ou compatibilidade de sessões M1.3.
A suíte externa e a revisão protegida do coordenador continuam necessárias antes da integração.
