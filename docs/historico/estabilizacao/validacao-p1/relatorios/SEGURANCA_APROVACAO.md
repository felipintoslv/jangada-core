# Segurança da aprovação

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

PASSOU: 32 cenários em `testes/confianca-p0.py`, com isolamento Bubblewrap real nos ataques de montagem. Incluem escrita SQLite, links, FD herdado, interfaces com variável removida, COMPLETED forjado, revisão JSON inventada, artefato alterado, aprovação de outra tarefa, autoria ausente e rótulo sem revisão executada. Conferem estado persistente ou decisão protegida, não somente mensagem de erro. Logs completos e `ataques-bubblewrap.jsonl` preservados.

Três ensaios complementares passaram: novo commit não reutiliza aprovação anterior na prévia backend; autoria operacional adulterada não supera autoria protegida; aprovação sem parecer protegido bloqueia arquivamento e preserva originais. Provedores são simulados nesses ensaios, sem alegação de independência real de IA.

A marca de aprovação anterior pode permanecer após uma nova versão ser reprovada. O teste observou candidato diferente e `marca_atual=false` na prévia. Ela não constitui aprovação da versão nova. Evidência `aprovacao-commit-posterior.json`. Registro de exploratórios preservado: uma expectativa incorreta de exclusão física e depois fixture incompleta produziram falhas do experimento, corrigidas sem mudar produção. Não se ocultaram esses logs nem se classificou existência de arquivo como aprovação válida.

Autoridade: controlador host verifica decisão protegida vinculada à tarefa e digest; pareceres protegidos vinculam candidato Git, árvore, base e autoria. Campos fornecidos pelo executor não bastam. Modelo de ameaça não protege contra usuário com domínio irrestrito da conta/host.

Integração automática permanece bloqueada, comprovada pelo teste L. Nenhuma falsificação aceita nos cenários executados. Isso não certifica todos os ataques possíveis nem substitui o ciclo real de aprovação econômica.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.
