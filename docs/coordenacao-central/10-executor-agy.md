# Piloto de autor, implementador e revisor

O autor delimita a atividade, seleciona especialistas e confere os arquivos.
O implementador agy escreve numa cópia isolada. O autor inspeciona, aceita e
testa antes da revisão independente. Nenhum resultado do executor autoriza
commit, integração ou exclusão. O coordenador continua sendo a sessão externa;
um nome declarado não comprova identidade, autoridade ou modelo real.

## Modelos por tarefa

| Autor | Esforço | Revisor independente | Esforço |
|---|---|---|---|
| Codex `gpt-6-luna` | `medium` | Claude `opus` | `high` |
| Codex `gpt-6.1-sol` | `high` | Claude `opus` | `high` |
| Claude `sonnet` ou `opus` | `high` | Codex `gpt-6.1-sol` | `high` |

Exemplo de abertura pelo coordenador, numa tarefa futura:

```sh
jangada-agente --perfil codex-claude --projeto PASTA --nome TAREFA \
  --autor-modelo gpt-6-luna --autor-esforco medium \
  --revisor-modelo opus --revisor-esforco high --prompt-arquivo PEDIDO
```

O piloto é explícito: `--autor-modelo` ou `JANGADA_AUTOR_MODELO` ativa o contrato.
Os perfis padrão conservam o comportamento antigo quando não há seleção.
Precedência: opções da abertura, campos do perfil pessoal ou padrão, campos
da configuração global/ambiente. Quando o modelo vem de uma opção, o esforço
ausente é deduzido desse modelo; não herda o esforço de outro modelo no perfil. Perfil pessoal de mesmo nome prevalece
inteiramente sobre o padrão. Os campos são `JANGADA_AUTOR_MODELO`,
`JANGADA_AUTOR_ESFORCO`, `JANGADA_VALIDAR_MODELO` e `JANGADA_VALIDAR_ESFORCO`.
Sem modelo do autor, perfis antigos conservam seus argumentos e comportamento.
No contrato de `--perfis --json`, `modelo` e `modelos_tarefa` mostram a seleção
configurada. Um perfil inválido é omitido com diagnóstico, sem ocultar os demais.

A seleção nova usa valores fechados, exige outro provedor forte e recusa
argumentos adicionais do autor, inclusive `ARGS` antigos. Não mistura duas
formas de selecionar modelo. Só confere os argumentos efetivamente usados:
`PERFIL_ARGS` com perfil, ou `JANGADA_AGENTE_ARGS` sem perfil. Valores incompatíveis falham antes de criar
worktree. A seleção não troca o modelo de uma sessão já aberta.

A abertura preserva `modelos_tarefa` no registro da sessão e em sua cópia
protegida em `revisoes/`. Na restauração, essa cópia prevalece sobre mudanças
posteriores no perfil. Seleção gravável sem cópia protegida é recusada. Uma abertura com seleção
nova já é recusada dentro do isolamento, antes de criar worktree ou sessão.
Aberturas antigas sem seleção continuam seguindo seu fluxo anterior.
Registros antigos continuam sendo recompostos pela configuração confiável;
o campo `comando` nunca é executado.

O CLI recebe explicitamente modelo e esforço. Isso registra o pedido ao
provedor; não é atestado da identidade interna do serviço. Indisponibilidade
do modelo falha sem trocar a seleção do autor. No piloto, a revisão deve ser
chamada com `--revisor` explícito, para impedir as alternativas antigas do
validador: `jangada-validar --revisor claude --modelo opus --esforco high`.
Para autor Claude, use `--revisor codex --modelo gpt-6.1-sol --esforco high`.

## Implementação delimitada

```sh
jangada-delegar implementador "Mudar valor para 2 nos dados sintéticos" \
  --destino agy --permitir-remoto --base SHA_COMPLETO \
  --arquivos criterios.txt --permitidos dados.txt \
  --criterio "O teste do autor deve confirmar valor=2"
```

`--base` deve ser o HEAD exato. Fontes e arquivos existentes permitidos precisam
coincidir com os objetos da base. `--novos ARQUIVOS` autoriza somente nomes
exatos também listados em `--permitidos`; o controlador os cria vazios na cópia.
Não há autorização de diretório, glob, exclusão ou mudança de permissões.
`--prazo` vai de 1 a 600 segundos; o padrão é 360.

O modelo é sempre `gemini-3.8-flash-high`. A lista de alternativas da delegação
de leitura não se aplica. `--modelo` só aceita esse valor. Confiança, catálogo,
cota, prazo e registrador são reaproveitados. Uma trava global disputa a conta
existente entre leitura e implementação; concorrência é recusada, sem fila ou
repetição automática. Uma segunda trava protege decisões na mesma tarefa.

O papel global novo é somente leitura. O controlador cria um papel privado
com ferramentas de edição de arquivo somente no runtime isolado, sem terminal
ou MCP. A chamada direta ao papel global não habilita escrita. Os especialistas existentes continuam sem escrita. O agy continua
recusado como agente principal genérico.

## Fronteira de escrita

O modo `implementacao` do `jangada-isolar` sempre cria Bubblewrap, inclusive
dentro de uma sessão isolada. A casa e a pasta acima da tarefa começam vazias.
Só voltam as fontes copiadas, no caminho exato já confiável, sem `.git`.
A cópia é somente leitura; arquivos permitidos recebem montagens graváveis
individuais. Arquivos de controle, outras tarefas e estado persistente ficam
inacessíveis. Caminhos absolutos, travessia, links simbólicos, ligações físicas
e submódulos são recusados na entrada e na entrega.

O CLI tem estado temporário, configuração filtrada e somente o papel privado
derivado do contrato instalado para esta execução. Não carrega hooks ou MCP pessoais. Descritores
extras são fechados; descritores padrão de arquivos regulares e soquetes são
recusados. O ambiente é reconstruído sem credenciais exportadas.
O catálogo privado é conferido dentro do isolamento antes da chamada ao modelo.
Papel ausente recusa a execução, sem usar o agente padrão do agy.

O D-Bus, quando disponível, exige atributos de keyring já configurados em
`JANGADA_ISOLAR_KEYRING_ITEM`. Somente leitura dos itens selecionados volta ao
executor; ele não pode criar, substituir ou excluir credenciais. Não se libera
o serviço inteiro. Falha de autenticação ou necessidade de renovar login
impede a prova. O piloto não altera a configuração pessoal para contorná-la.

Chamado de dentro da sessão isolada do autor, o implementador lê o keyring por
`$XDG_RUNTIME_DIR/bus-implementacao`, soquete que o isolamento de fora liga
com o filtro do implementador (ver [isolamento](../isolamento.md), "Implementador
chamado de dentro do isolamento"). Sem esse soquete a execução falha com
`motivo_codigo` `sem_login_agy`, distinto de `erro_execucao`.

`sem_login_agy` vale só quando o isolador detecta a falta: sessão sem o
soquete do implementador, item ausente no keyring ou código 69. Com o item
presente e a credencial do agy vencida ou inválida, o agy sai com código 1 e
o registro diz `erro_execucao`, com o código de saída no `motivo`. A
renovação do login é feita fora do isolamento. Não há sinal confiável da
falha de autenticação sem o agy real, pois a mensagem de login também aparece
nas chamadas boas. O dono decidiu esse escopo em 25/10/2026.

Montagens de arquivo não aceitam substituição por rename. Se uma ferramenta
de edição do agy exigir esse mecanismo, a chamada falha e mantém diagnóstico;
não se libera o diretório. Arquivos temporários do CLI ficam em memória e não
entram na entrega. Comandos ou patches retornados pelo modelo nunca são
executados pelo controlador.

## Inspeção, aceite e recuperação

A chamada devolve ID, estado e pasta em `$JANGADA_ESTADO/agentes/implementacoes/CHAVE/ID`.
`contrato.json` identifica tarefa, execução, atividade, base, modelo, papel,
fontes com hashes, arquivos e critérios. `registro.json` vincula a delegação
real e os metadados medidos. `entrega.json` contém hashes da cópia e contrato.
`estado.json` conserva código e diagnóstico, sem gravar erros brutos do cliente.
`CHAVE` é o hash do caminho absoluto do worktree, que distingue tarefas homônimas.
Os artefatos ficam fora do Git, inclusive quando `.jangada/validar.sh` é versionado.
O estado de execução usa `agentes/`, já gravável na sessão normal; o executor
vê somente a cópia selecionada por montagens, sem acesso a esses registros.

O autor lê os arquivos e o relatório como dados, compara o resultado e guarda
o hash `entrega` devolvido. Só então aplica:

```sh
jangada-delegar --aceitar ID --base SHA_COMPLETO --entrega HASH_INSPECIONADO
```

O controlador reconfere base, contrato, resultado e fontes atuais antes de
copiar apenas arquivos permitidos ao worktree. Resultado alterado, edição
concorrente ou base divergente são recusados. O autor roda os testes aplicáveis
e a suíte do projeto; `aceita_pelo_autor` não significa teste ou revisão aprovada.
Um erro durante a cópia deixa `aceite_parcial`, para inspeção manual; não tenta
desfazer edições nem reaplicar automaticamente.

```sh
jangada-delegar --devolver ID --base SHA_COMPLETO --motivo "Critério incompleto"
```

Devolução conserva os artefatos. Falha, prazo vencido, interrupção, cota desconhecida,
ação negada ou saída parcial não chegam a `aguarda_autor`. Não há retomada
automática: examine o estado e delimite outra chamada, se autorizada.

## Demonstração supervisionada pendente

Os testes `testes/implementacao-agy.py` fazem o percurso inteiro com cliente
falso e uma prova de escrita com Bubblewrap real, sem modelo remoto.
`testes/modelos-tarefa.py` confere seleção e restauração protegida.
Isso não comprova ferramentas de escrita do agy real.

Após integração e instalação pelo dono, o fluxo normal registra o papel pela
etapa 50 ou pela migração `202610141900-executor-agy.sh`. Não execute essa
instalação a partir do worktree do autor. Confira `agy agents` e a confiança
da tarefa pelo fluxo normal. Prepare um projeto com somente `dados.txt`
(`valor=1`) e `criterios.txt`, versionados. Execute o exemplo de delegação,
inspecione a cópia, aceite pelo hash e teste `valor=2` antes da revisão.
Se faltar papel, confiança, cota, acesso ao item de login ou escrita em arquivo
montado, registre o bloqueio e pare, sem configurar permissões pessoais.

## Verificação da MOD-03

A opção `--modelo gemini-3.8-flash-high` fixa o executor sem alternativa.
Flash/Pro usam seu próprio grupo de cota; Argon esgotado ou ausente não bloqueia
Flash. Grupo desconhecido não recebe cota emprestada. A implementação delimitada
continua exigindo base exata, inspeção e aceite pelo hash, antes dos testes e da
revisão Claude Opus ou Codex Sol de outro provedor. Argon no agy não revisa Flash
com independência de provedor.

`testes/implementacao-agy.py` entrega uma mudança sintética, inspeciona a cópia,
aceita pelo hash e testa o valor aplicado. Recusa escrita fora do contrato,
links, base divergente e entrega alterada. Usa clientes falsos e inclui a
fronteira do Bubblewrap real; isso não comprova implementação pelo Flash real.
Leitor/redator remotos recebem somente fontes ou faixas autorizadas, sem
ferramentas ou MCP. A opção local continua disponível; falha local não autoriza
nuvem. Arquiteto com fontes explícitas recebe a mesma cópia de texto.

Para comprovar pesquisa real, renove a consulta `/usage` antes da chamada.
Fixe o modelo e autorize somente a página pública necessária, por exemplo:

```sh
jangada-delegar pesquisador "Busque e abra a documentação oficial" \
  --destino agy --permitir-remoto --modelo gemini-3.8-flash-high \
  --url https://ai.google.dev/gemini-api/docs/google-search --json
```

Confira no registro privado indicado por `registro_ferramentas` a conversa,
a busca, a abertura da URL e a leitura do corpo baixado. Registre URL, data da
consulta, trecho sustentado, ferramentas executadas, versões e hashes das
fontes do executor no relatório da tarefa. Confira esse material separadamente
da resposta textual. Uma ação negada recusa o resultado, mesmo com texto parcial.

O apoio arquiteto exige fontes explícitas autorizadas em `--arquivos` e modelo
fixo. Confira as fontes do pedido, o resultado recebido e os casos aproveitados
no relatório da tarefa. Esse apoio não revisa nem aprova a entrega.
