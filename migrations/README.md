# Migrações

A pasta começa vazia no Core. As migrações anteriores à separação ficam no
histórico do monorepo e já têm marca em `$JANGADA_ESTADO/migracoes/`, então
não são reaplicadas.

Cada arquivo `AAAAMMDDHHMM-descricao.sh` é um script bash aplicado uma única vez
por `jangada-migrar` (chamado pelo `jangada-update`), em ordem de nome. Só
entram aqui ajustes de instalações existentes que dizem respeito ao Core.

Regras:

1. A migração deve poder rodar de novo sem estragar nada, porque uma falha no
   meio faz com que ela seja tentada outra vez.
2. Nunca apagar arquivos do usuário: mover para uma cópia `.bak` com data.
3. Explicar no topo do arquivo o que mudou e por quê.
4. Em simulação (`JANGADA_SIMULAR=1`), não alterar nada.
