# Independência do padrão R da validação

O percurso R de `jangada-validar` usa `validacao/lintr`, sem depender da integração R do Shell.
Este recorte resolve A2 do diagnóstico, primeiro acoplamento de M1.1. Base examinada: `ef707fa464123ffc603dd4c5bc436d324ce29ee9`.

## Contrato e compatibilidade

`validacao/lintr` é a única fonte das regras padrão, com conteúdo idêntico ao arquivo anterior.
`validacao/lintr` é um link versionado relativo para `../../../validacao/lintr`.
`default/r` continua no Shell; portanto, `validacao/lintr` preserva o acesso na instalação completa.
A integração R restante não mudou. Os links funcionam após cópia da árvore, sem caminhos absolutos da máquina.

A seleção em `bin/jangada-validar:800` mantém prioridade do `.lintr` da base.
Sem essa regra, os achados do padrão Jangada são avisos; com ela, violações novas reprovam antes do revisor.
O `.lintr` novo e o `.Rprofile` gravável do worktree continuam sem execução.
Ausência do padrão, R ou lintr e falha de execução continuam explícitas e impedem aprovação.
A fachada, os códigos de saída e os controles de revisão e isolamento permanecem os mesmos.

## Prova sintética

`testes/core-independente.sh` copia Core, fachadas e links necessários para uma árvore temporária sem Shell e Monitor físicos.
Executa R e lintr reais pelo isolamento de verificação, sem rede, com revisor Claude falso e estados fictícios.
Confere aviso na linha R nova e chamada do revisor sem `.lintr` da base.
Uma regra diferente na base proíbe `message()`; alterá-la no worktree não evita reprovação nem aciona o revisor.
Também confere proteção contra regra/perfil graváveis e reprovação explícita quando o padrão Core desaparece.
Sem R/lintr reais, o teste sai com código 77 e `UNAVAILABLE`, sem alegar prova atendida.
A suíte geral registra a prova não executada como etapa ignorada, sem reprovar por essa ausência.

O contrato de caminhos inclui os três acessos ao padrão e copia também os links intermediários.
Os casos negativos existentes de caminho ausente, link absoluto e saída do repositório permanecem ativos.
As regressões anteriores de `testes/validar.sh` foram preservadas; somente suas referências ao recurso foram atualizadas.

## Limites

A prova cobre somente a validação R e a compatibilidade desse recurso.
O link de monitoramento A3, as leituras A4/A5 e a compatibilidade de sessões M1.3 permanecem pendentes.
A ausência do resumo opcional do Monitor não elimina verificações obrigatórias.
Este resultado não demonstra independência completa do Core nem autoriza instalação, integração ou publicação.
