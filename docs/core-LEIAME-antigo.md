# core/

Módulo Core da modularização 3.0: sessões de agente, isolamento, validação,
delegação, fila, tarefas e provedores. O plano está em
[docs/modularizacao-3.0](../docs/modularizacao-3.0/README.md).

Esta pasta foi criada na tarefa M3-11 e ainda não tem código. Os arquivos
chegam na Onda C, um commit por mudança de pasta, com link relativo no
caminho antigo (`bin/`, `default/`). O destino de cada arquivo está em
[01-inventario.md](../docs/modularizacao-3.0/01-inventario.md).

| Subpasta prevista | Conteúdo | Tarefa |
|---|---|---|
| `core/bin` | 23 comandos | M3-18 |
| `core/nucleo`, `core/orquestracao`, `core/delegacao` | pacotes Python | M3-16 |
| `core/agentes`, `core/provedores` | perfis, subagentes, skills, hooks, tmux e registro de provedores | M3-16 |

O Git não guarda pasta vazia: cada subpasta passa a existir com o primeiro
arquivo movido.

Regras do módulo
([02-arquitetura.md](../docs/modularizacao-3.0/02-arquitetura.md) e
[03-contratos.md](../docs/modularizacao-3.0/03-contratos.md)):

1. O Core não chama nada do Shell nem do Monitor (K9).
2. Os comandos continuam públicos em `bin/` (K1). Comando chamado pelo
   caminho de `core/bin` não acha o `jangada-config`.
3. `testes/verificar.sh` e `testes/regra1.sh` examinam `core/bin`.
