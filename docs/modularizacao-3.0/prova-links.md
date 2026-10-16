# M3-02. Prova dos links simbólicos (decisão D2)

Conclusão: **D2 se mantém com ressalvas.** O Git, o `git archive`, o clone,
a worktree, o avanço da cópia instalada, o `shellcheck`, o `regra1.sh` e o
`install.sh` simulado preservam e seguem os links sem mudança. O que
quebra é código que descobre a própria pasta resolvendo links
(`Path(__file__).resolve()`, `getwd()` do R, `realpath` do Bash) e dois testes
que copiam só parte do repositório. Esses defeitos não somem com arquivos de
repasse: pasta não tem repasse, e o repasse muda `BASH_SOURCE` do mesmo jeito.

## Montagem

Feita em 09/10/2026, dentro da sessão isolada (`JANGADA_ISOLADO=1`), a partir
desta worktree em `e654742`. `$S` é a pasta temporária da sessão; nada foi
gravado nesta worktree além deste arquivo.

| Cópia | Conteúdo |
|---|---|
| `$S/base` | clone sem mudança, para comparação |
| `$S/prova` | clone com o commit `558a50f` "prova: links simbólicos" |
| `$S/prova2` | `prova` mais os casos conhecidos de localização por caminho (ver item 2) |

Commit `558a50f` em `$S/prova`:

```
mkdir -p core/bin shell/bin monitor/bin
git mv bin/jangada-fila   core/bin/    && ln -s ../core/bin/jangada-fila     bin/jangada-fila
git mv bin/jangada-barra  shell/bin/   && ln -s ../shell/bin/jangada-barra   bin/jangada-barra
git mv bin/jangada-painel monitor/bin/ && ln -s ../monitor/bin/jangada-painel bin/jangada-painel
git mv default/waybar shell/waybar     && ln -s ../shell/waybar   default/waybar
git mv default/painel monitor/painel   && ln -s ../monitor/painel default/painel
git add -A && git commit
```

`git ls-files -s | grep ^120000` lista os cinco caminhos com modo `120000`.
`git diff -M` mostra o caminho antigo de `bin/` como `mode change 100755 =>
120000`, não como renomeação; com `git diff -M -B --stat` aparece
`{bin => core/bin}/jangada-fila | 0`. A aceitação comum da Onda C ("só
renomeações e links em `git diff --stat -M`") precisa citar o `-B`.

## 1. Comandos movidos e `jangada-config`

Rodados de `/`, sem `JANGADA_CORE_PATH`, com `HOME` e `XDG_*` temporários:

| Comando | Saída relevante | Resultado |
|---|---|---|
| `source $S/prova/bin/jangada-config; echo $JANGADA_CORE_PATH` | `$S/prova` | pasta acima de `bin/`, não de `core/bin` |
| `bin/jangada-barra --posicao` | `topo`, saída 0 | ok |
| `bin/jangada-barra --ajuda` | texto da ajuda, saída 0 | ok |
| `bin/jangada-painel --waybar` | `{"text":"󰄪",...,"class":"parado"}`, saída 0 | ok |
| `bin/jangada-painel --ajuda` | texto da ajuda, saída 0 | ok |
| `bin/jangada-fila --json` e `bin/jangada fila --json` | `AUTORIZACAO_RECUSADA: executor isolado não possui autoridade` | igual em `$S/base`: bloqueio do isolamento, não do link |
| `PATH=$S/prova/bin:$PATH type -p jangada-fila` | `$S/prova/bin/jangada-fila` | ok |
| `bash testes/contratos-caminhos.sh` (K2) | `tudo certo` | ok |

O `source "$(dirname "${BASH_SOURCE[0]}")/jangada-config"` funciona porque
`BASH_SOURCE` guarda o caminho do link, não o do destino. Por isso o comando
só funciona pela fachada: chamado pelo caminho real, ele procura o
`jangada-config` ao lado de si.

```
$ $S/prova/shell/bin/jangada-barra --posicao
$S/prova/shell/bin/jangada-barra: linha 14: $S/prova/shell/bin/jangada-config: Arquivo ou diretório inexistente
```

Isso torna quebrado todo código que chama um comando depois de `realpath`
(item 2, `jangada-codex`).

## 2. Python com `Path(__file__).resolve()` e a falta de `JANGADA_CORE_PY`

`JANGADA_CORE_PY` ainda não existe no repositório (`git grep` sem resultado
fora de `docs/`). Importação de cada módulo do painel, com
`sys.path.insert(0, 'default/painel')`:

| Módulo | `$S/base` | `$S/prova` |
|---|---|---|
| `coletor` | ok | `ModuleNotFoundError: No module named 'nucleo'` |
| `orquestracao` | ok | `ModuleNotFoundError: No module named 'nucleo'` |
| `subagentes`, `metricas`, `autonomia` | ok | ok |

`Path('default/painel/coletor.py').resolve().parent.parent` vira
`$S/prova/monitor` (`default/painel/coletor.py:56`,
`default/painel/orquestracao.py:9` e `:11`). Com
`PYTHONPATH=$S/prova/default`, que é o papel previsto para `JANGADA_CORE_PY`,
os dois voltam a importar. `coletor.py:854` usa `parents[2]` e continua
chegando à raiz do repositório.

`bin/jangada-painel --gerar` em `$S/prova`:

```
jangada-painel: a coleta falhou: ... ModuleNotFoundError: No module named 'nucleo'
```

O app R quebra pelo mesmo motivo: `default/painel/app.R:9` usa
`pasta_app <- getwd()`, que devolve a pasta física, e daí
`fichas.R:3` e `:4` (`../visual`), `app.R:119` (`../logo`) e
`operacional.R:247` (`../nucleo/monitoramento.py`):

```
cannot open file '$S/prova/monitor/painel/../visual/padrao.json': No such file or directory
```

Casos conhecidos simulados em `$S/prova2` (pacotes `nucleo`, `orquestracao` e
`delegacao` em `core/`; `default/tarefas` em `shell/menus/tarefas`;
`default/logo` em `shell/temas/logo`; `jangada-subagentes`,
`jangada-hook-leitor` e `jangada-hook-codex` nos `*/bin`, todos com link):

| Arquivo | Resultado |
|---|---|
| `default/nucleo/consultas.py:14`, `default/orquestracao/cli.py:23`, `default/delegacao/codex.py:19` | ok, porque os três pacotes continuam irmãos em `core/` |
| `default/tarefas/janela.py:25` | `ModuleNotFoundError: No module named 'visual'`; `parents[1]` vira `shell/menus` |
| `default/tarefas/janela.py:658` | procura `shell/menus/logo/jangada-symbolic.svg`, que não existe |
| `bin/jangada-subagentes:13` | `python3: can't open file '$S/prova2/monitor/bin/../default/painel/subagentes.py'` |
| `bin/jangada-hook-leitor:15` | `python3: can't open file '$S/prova2/core/bin/../default/claude/hook-leitor.py'` |
| `bin/jangada-codex:101` e `:102` | grava no Codex o caminho `core/bin/jangada-hook-codex`; chamado por ele, o hook não acha o `jangada-config` e sai 0 sem atualizar a sessão (`estado` fica `novo`; pelo link vira `trabalhando`) |

O último caso falha em silêncio, porque o hook manda tudo para `/dev/null`.

## 3. `testes/verificar.sh` completo

Comando, em cada cópia:

```
cd $S/<cópia> && env -u JANGADA_ISOLADO -u JANGADA_DELEGAR -u JANGADA_PAPEL \
  -u JANGADA_PAPEL_AJUSTE JANGADA_CORE_PATH=$S/<cópia> bash testes/verificar.sh </dev/null
```

| Cópia | Saída | Grupos falhos |
|---|---|---|
| `$S/base` | 1 | 21, todos por `AUTORIZACAO_RECUSADA` ou outro bloqueio do isolamento |
| `$S/prova` | 1 | 27 |

Diferença (`diff` das linhas `XX`), seis grupos a mais e um que muda de
causa:

| Grupo | Causa na prova |
|---|---|
| `testes/contratos-fachada.sh` | `testes/contratos-fachada.sh:68` copia só `bin/` com `cp -a`; os links ficam apontando para `core/` e `monitor/`, que não vêm na cópia ("cópia intacta de bin/ passa") |
| `testes/contratos-fronteiras.sh` | `testes/fronteiras.sh:191` copia só `bin`, `default` e `shell`; além disso `testes/contratos/modulos.txt` ainda lista `bin/jangada-fila`, `default/waybar/` etc. como arquivos ("linha de modulos.txt sem arquivo") |
| `testes/metricas.py` | `ModuleNotFoundError: No module named 'nucleo'` ao carregar `coletor.py` |
| `testes/painel.sh` | 26 casos; a coleta falha com o mesmo `ModuleNotFoundError` |
| `testes/painel-motores.R` | `../visual/padrao.json` a partir de `monitor/painel` |
| `testes/painel-operacional.R` | idem |
| `testes/painel-orquestracao.py` | já falha na base pelo isolamento; na prova falha antes, na importação (`No module named 'nucleo'`) |

Nenhuma diferença vem do Git ou do link em si. Os dois primeiros são testes
que precisam copiar `core/`, `shell/` e `monitor/` e uma lista que a tarefa
de migração atualiza; os outros são o defeito do item 2.

## 4. Link dentro do `jangada-isolar`

**Conferido em 09/10/2026 pelo coordenador, fora do isolamento**, sobre o
`main` em `e604eaa`, com os comandos abaixo. Dentro do `jangada-isolar`,
tanto com a casa padrão quanto com `JANGADA_ISOLAR_CASA=minima`, os dois
`readlink` devolveram `../core/bin/jangada-fila` e `../monitor/painel`.
`default/waybar` listou `base.css`, `config.jsonc` e `style.css.modelo`;
`jangada-barra --posicao` devolveu `topo` e `jangada-painel --waybar` devolveu
o JSON com `class` igual a `parado`.

Comandos usados fora do isolamento. A cópia fica na pasta pessoal porque o
`/tmp` do isolamento é próprio:

```
P="$(mktemp -d ~/prova-links.XXXXXX)/jangada"
git clone -q ~/Projetos/jangada "$P" && cd "$P" && mkdir -p core/bin shell/bin monitor/bin \
 && git mv bin/jangada-fila core/bin/ && ln -s ../core/bin/jangada-fila bin/jangada-fila \
 && git mv bin/jangada-barra shell/bin/ && ln -s ../shell/bin/jangada-barra bin/jangada-barra \
 && git mv bin/jangada-painel monitor/bin/ && ln -s ../monitor/bin/jangada-painel bin/jangada-painel \
 && git mv default/waybar shell/waybar && ln -s ../shell/waybar default/waybar \
 && git mv default/painel monitor/painel && ln -s ../monitor/painel default/painel \
 && git add -A && git commit -qm prova
for casa in "" minima; do
  (cd "$(mktemp -d)" && JANGADA_ISOLAR_CASA=$casa JANGADA_CORE_PATH="$P" "$P/bin/jangada-isolar" -- bash -c '
    readlink "$JANGADA_CORE_PATH/bin/jangada-fila" "$JANGADA_CORE_PATH/default/painel"
    ls "$JANGADA_CORE_PATH/default/waybar"
    "$JANGADA_CORE_PATH/bin/jangada-barra" --posicao
    "$JANGADA_CORE_PATH/bin/jangada-painel" --waybar')
done
```

Resultado: os dois `readlink`, os três arquivos da Waybar, `topo` e o JSON do
painel, nas duas casas. Depois, `rm -rf` da pasta criada pelo `mktemp`.

## 5. `jangada-update` numa cópia instalada falsa

**Conferido em 09/10/2026 pelo coordenador, fora do isolamento**, sobre o
`main` em `e604eaa`, com o `jangada-update --somente-codigo` e os comandos
abaixo. Na cópia instalada falsa, os três links apareceram em "mudam código
que roda fora do isolamento". A atualização terminou com "código instalado
em" o commit da prova; os links resolveram e `git status` ficou limpo.

Conferência anterior, dentro da sessão isolada: `$S/instalada` é um clone de
`$S/prova` posto em `e654742` (ramo `main` acompanhando a origem), com um
`default/painel/__pycache__/coletor.cpython-314.pyc` ignorado, como existe
hoje na cópia instalada real. Rodei os mesmos comandos do `jangada-update`,
com `jangada_git_seguro` carregado do `jangada-config` da prova:

```
status: []
fetch 0
avança em linha reta
  sensível: bin/jangada-barra
  sensível: bin/jangada-fila
  sensível: bin/jangada-painel
merge saida 0
depois: 558a50f
  bin/jangada-fila -> ../core/bin/jangada-fila [resolve]
  ...
  default/painel -> ../monitor/painel [resolve]
status depois: [] ignorados: []
  jangada-config: $S/instalada
```

O `merge --ff-only` troca a pasta pelo link e apaga o `__pycache__` ignorado
sem erro. A volta (`git switch --detach HEAD~1`) recria `default/painel` como
pasta. Os três links aparecem na lista "mudam código que roda fora do
isolamento", o que é correto.

Na conferência anterior, `jangada-update --somente-codigo` recusou:
`atualização exige terminal externo ao agente isolado`. O coordenador rodou
o comando abaixo fora do isolamento, depois de montar `$P` como no item 4.
O `XDG_CONFIG_HOME` temporário evita a conferência de assinatura do
`allowed_signers` real, e o `TMUX_TMPDIR` temporário evita a recusa pelas
sessões de agente abertas:

```
I="$(mktemp -d ~/instalada-falsa.XXXXXX)/jangada"
git clone -q "$P" "$I" && git -C "$I" switch -q -C main HEAD~1 && git -C "$I" branch -q -u origin/main
mkdir -p "$I/default/painel/__pycache__" && : >"$I/default/painel/__pycache__/x.pyc"
JANGADA_CORE_PATH="$I" XDG_CONFIG_HOME="$(mktemp -d)" TMUX_TMPDIR="$(mktemp -d)" \
  "$I/bin/jangada-update" --somente-codigo
readlink "$I/bin/jangada-fila" "$I/default/painel"
```

Resultado: lista com o commit `prova`, pergunta `[s/N]`, `código instalado em`
e os dois links resolvendo; `git status` limpo.

Ressalva: a conferência de processos do `jangada-update` (linhas 48 a 50)
procura `"$JANGADA_CORE_PATH/default/"` e `"$JANGADA_CORE_PATH/bin/jangada-"` na linha de
comando. Processo aberto por caminho resolvido (`core/...`, `monitor/...`),
como o `python3` do `jangada-subagentes`, escapa dela.

## 6. `shellcheck` e `testes/regra1.sh`

Em `$S/prova3`, clone de `$S/prova`:

| Comando | Resultado |
|---|---|
| `shellcheck -x -S warning install.sh install/*.sh bin/* migrations/*.sh testes/*.sh` (linha 23 do `verificar.sh`) | saída 0 |
| `shellcheck -x -S warning core/bin/* shell/bin/* monitor/bin/*` | saída 0 |
| `bash testes/regra1.sh` | `todos os testes da regra 1 passaram` |
| `nao_usada=1` acrescentado em `monitor/bin/jangada-painel` | `In bin/jangada-painel line 215: SC2034 (warning)`, saída 1 |
| `echo x >"$HOME/.novo/arquivo"` acrescentado em `core/bin/jangada-fila` | `FALHA caso 1: ... ~/.novo/arquivo (bin/jangada-fila:8)` |

Os dois seguem o link: o `shellcheck` recebe `bin/*` e lê o destino; o
`regra1.sh` usa `rglob("*")` com `is_file()`, que segue link
(`testes/regra1.sh:98`). O achado sai com o nome do link, não o do arquivo
real. Um arquivo em `core/bin` sem link em `bin/` não é examinado; isso é a
aceitação da M3-03.

## 7. `install.sh` com `JANGADA_SIMULAR=1`

```
cd $S/<cópia> && env -u JANGADA_CORE_PATH -u JANGADA_ISOLADO -u JANGADA_CONFIG -u JANGADA_ESTADO \
  -u JANGADA_REPO -u JANGADA_WORKTREES HOME=$H XDG_CONFIG_HOME=$H/.config \
  XDG_STATE_HOME=$H/.local/state XDG_CACHE_HOME=$H/.cache JANGADA_SIMULAR=1 bash install.sh </dev/null
```

As duas cópias saem com 0 e `ok instalação concluída`, em 137 linhas. O
`diff` das saídas, trocada a pasta da cópia, só mostra o horário no nome da
cópia de segurança de `jangada.desktop`. As pastas `$H` ficaram vazias. O
`style.css` gerado aponta `@JANGADA_CORE_PATH@/default/waybar/base.css`, que
resolve pelo link.

## 8. `git archive` e clone novo

```
$ git -C $S/prova archive --format=tar HEAD | tar -tvf - | grep ...
lrwxrwxrwx root/root 0 2026-10-09 21:28 bin/jangada-barra -> ../shell/bin/jangada-barra
lrwxrwxrwx root/root 0 2026-10-09 21:28 bin/jangada-fila -> ../core/bin/jangada-fila
lrwxrwxrwx root/root 0 2026-10-09 21:28 bin/jangada-painel -> ../monitor/bin/jangada-painel
lrwxrwxrwx root/root 0 2026-10-09 21:28 default/painel -> ../monitor/painel
lrwxrwxrwx root/root 0 2026-10-09 21:28 default/waybar -> ../shell/waybar
```

Extraídos do `tar`, do `zip` (`git archive --format=zip`) e de
`git clone file://$S/prova`, os cinco caminhos são links e resolvem.
`bin/jangada-barra --posicao` da cópia do `tar` imprime `topo`;
`bin/jangada-painel --waybar` do clone imprime o JSON. O clone sai com
`git status` limpo.

## 9. `git worktree add`

`git -C $S/prova worktree add $S/wt -b teste-wt`: os cinco links existem e
resolvem, `git status` limpo, e `jangada-config` carregado de `$S/wt/bin`
define `JANGADA_CORE_PATH=$S/wt`.

## Ressalvas para as tarefas seguintes

1. `JANGADA_CORE_PY` (K5) precisa existir antes da M3-17, e o painel R deve
   receber a pasta do jangada por variável em vez de `getwd()`
   (`default/painel/app.R:9`).
2. `default/tarefas/janela.py:25` e `:658` quebram na M3-15 pelo mesmo
   motivo; a linha `:658` não está na lista de arquivos permitidos da tarefa.
3. `bin/jangada-subagentes:13`, `bin/jangada-hook-leitor:15` e
   `bin/jangada-codex:102` usam `realpath` e quebram ao mover; precisam usar
   `JANGADA_CORE_PATH` ou deixar de resolver o link antes da M3-17 e da M3-18.
4. `testes/contratos-fachada.sh:68` e `testes/fronteiras.sh:191` precisam
   copiar também `core/`, `shell/` e `monitor/`; `testes/contratos/modulos.txt`
   muda junto com cada mudança de pasta.
5. A conferência de processos do `jangada-update` (linhas 48 a 50) passa a
   procurar também `core/`, `shell/` e `monitor/`.
6. A aceitação comum da Onda C usa `git diff -M -B --stat`.
