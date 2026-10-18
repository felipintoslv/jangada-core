# Revisão adversarial

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Foram executadas 16 entregas R deliberadamente defeituosas, oito classes em cada rodada. Autoria: auditor, sem IA. Evidência individual com valor correto, observado, consequência e correção proposta: `evidencias/defeitos-metodologicos.json`; código: `scripts/entrega_sintetica.R` e `metodologia_adversarial.py`.

| Classe | Mecanismo observado |
| --- | --- |
| A1 | Junção sem versão duplica valores, detectada contra painel privado. |
| A2 | Correspondência setorial adulterada altera agregações. |
| A3 | Contraexemplo de composição refuta inferência sobre grupos a partir do agregado. |
| A4 | Denominador regional diverge do QL nacional exigido. |
| A5 | Ausência tratada como zero diverge da política predefinida. |
| A6 | Sinal de IM no residual viola identidade shift-share. |
| A7 | Uso de dados futuros altera QL histórico. |
| A8 | Conclusão causal sem identificação viola critério metodológico. |

Os 96 testes públicos estruturais passaram nas entregas defeituosas. Seis classes numéricas por rodada foram detectadas pelo gabarito, A3 pelo contraexemplo e A8 por critério de admissibilidade metodológica. A8 não constitui prova matemática de causalidade nem detector automático de linguagem. A1 pode conter efeitos adicionais da junção defeituosa; não atribuir isolamento perfeito de um único erro.

Revisor real, justificativa de IA, falsos positivos de IA e resultado após correção por modelo: NÃO EXECUTADOS. O controle correto do auditor concordou com referências nas duas rodadas; isso não equivale a rodada de correção do executor.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.
