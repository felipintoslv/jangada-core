# Backup e recuperação

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

## Inventário

| Conteúdo | Local usual | Necessário |
|---|---|---|
| Código instalado e commit | `~/.local/share/jangada-core`, ou `JANGADA_CORE_PATH` | Código e versão exata. |
| Configuração, políticas, ganchos, cores e regras de assinatura | `~/.config/jangada`, ou XDG_CONFIG_HOME | Sim. |
| Sessões, histórico, projetos, fila e artefatos | `~/.local/state/jangada`, ou XDG_STATE_HOME | Sim, incluindo `agentes/`, `revisoes/`, métricas e espelhos. |
| Bancos | `agentes/projetos/HASH/tarefas.sqlite` dentro do estado | Sim. Incluir transações confirmadas do WAL. |
| Dados auxiliares | `~/.local/share/jangada-core` e configurações dos provedores | Identificar na instalação; credenciais exigem guarda privada. |
| Worktrees | `~/.local/share/jangada-worktrees` | Sim, inclusive índice, pendências, arquivos novos e ignorados. |
| Projetos externos | Caminhos cadastrados em JANGADA_PROJETOS | Sim, com `.git`, ramos, objetos, dados e arquivos ignorados. |
| Cache | `~/.cache/jangada` | Dispensável para recuperação; guardar apenas se precisar investigar. |

Não basta um `git bundle`: ele não contém arquivos sem commit, índice ou arquivos ignorados. Links simbólicos não incluem os dados do destino. Inventarie os destinos e faça cópia separada quando necessários. Configurações dos provedores, chaves de assinatura e segredos não devem ser enviados a serviços externos.

## Cópia segura

1. Escolha um destino novo, privado, fora dos projetos e worktrees. Aplique `umask 077`. Não sobrescreva uma cópia anterior.
2. Pare as execuções, o painel e a Central. Interrompa agentes pelo terminal sem encerrar ou remover worktrees. Suspenda todas as escritas nos projetos e no estado.
3. Registre a versão, `git status`, `git worktree list` e os caminhos reais. Copie código, configuração, estado, worktrees e projetos inteiros com `cp -a`, para subpastas distintas do destino novo. Verifique códigos de saída; pare se qualquer cópia falhar. Sem escritas, copiar banco e WAL juntos preserva o conjunto.
4. Para cópia SQLite enquanto há transações confirmadas no WAL, use a API de cópia do SQLite, nunca copie apenas o arquivo principal. Exemplo para um banco sintético ou fonte cuja abertura foi autorizada:

```python
import sqlite3
from pathlib import Path
origem = Path('/caminho/da/fonte/tarefas.sqlite')
destino = Path('/caminho/novo/tarefas.sqlite')
if destino.exists():
    raise RuntimeError('destino já existe')
with sqlite3.connect(origem.as_uri() + '?mode=ro', uri=True) as entrada:
    with sqlite3.connect(destino) as saida:
        entrada.backup(saida)
        assert saida.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
```

5. Confira os arquivos copiados por conteúdo e verifique os bancos na cópia, com `PRAGMA integrity_check`. Guarde os SHA e um inventário. A cópia de um banco não torna coerentes arquivos de artefatos alterados ao mesmo tempo: para backup completo, suspenda as escritas.

## Restauração

Restaure primeiro em pasta nova e ambiente de teste, com HOME e variáveis XDG apontando para dados sintéticos. Preserve a origem e a instalação atual. Confira bancos, artefatos, configurações, ramos, índice e arquivos ignorados antes de iniciar serviços.

Worktrees possuem caminhos absolutos para o Git comum. Preserve os caminhos na restauração definitiva ou planeje `git worktree repair` supervisionado, conferindo cada registro e o repositório associado. Não execute reparo ou restauração em projetos reais durante o ensaio. Repor somente o banco sem seus artefatos e metadados deixa uma recuperação incompleta.

`testes/baseline.py` exercita cópia SQLite com WAL e restauração em destino novo. Também copia e restaura projeto, metadados e histórico com `cp -a`, incluindo índice, arquivos sem commit, novos e ignorados. Confere conteúdo, objetos Git e integridade e mantém a fonte. Não constitui teste de recuperação da sessão gráfica completa. Nenhum serviço automático de backup foi configurado.
