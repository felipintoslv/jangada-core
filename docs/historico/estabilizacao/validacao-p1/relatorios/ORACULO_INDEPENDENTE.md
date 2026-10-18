# Oráculo independente

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

PASSOU: `scripts/oraculo.py` e `scripts/oraculo.R` implementam separadamente importação, classificação por versão, deduplicação idêntica, interpolação interna e indicadores. Duas sementes protegidas em `privado/rodada-N/geracao.json`; referências Python e R em pastas distintas. Comparações completas em `evidencias/oraculos-comparacao-N.json`.

Cada rodada contém 150 municípios fictícios, 80 códigos de atividade simulados e sete anos, totalizando 84.000 células válidas. Os códigos não são CNAE oficial nem municípios reais. Rodada 1: 100 ausências, oito duplicatas, seis inválidos; rodada 2: 240 ausências, 15 duplicatas, seis inválidos. Não representam evidência empírica sobre o Brasil.

Critérios: referência nacional anual para QL; HHI, 1-HHI, Shannon e diversidade efetiva; crescimento municipal desde 2019; shift-share clássico NS=e0*G, IM=e0*(gj-G), RS=e1-e0*(1+gj). Soma dos três efeitos deve igualar a variação. Imputação é retrospectiva, usa âncoras observadas e não serve para previsão. Conflitos de chave devem bloquear, duplicatas idênticas são colapsadas e ausências não viram zero.

Python/R concordam em 181.050 linhas de quatro tabelas por rodada, tolerância absoluta 1e-8 mais relativa 1e-9. Agregações, participações, residual shift-share e irregularidades foram conferidos antes de qualquer modelo. Não houve modelo posterior.

Comandos efetivos: `python3 scripts/oraculo.py`; `Rscript --vanilla scripts/oraculo.R DIRETORIO_DADOS DIRETORIO_PRIVADO_R`; `python3 -B scripts/executar.py`. Consultar logs de comandos para argumentos completos. Não reexecutar no estado existente sem preparar outro ensaio.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.
