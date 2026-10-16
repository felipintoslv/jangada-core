# Consulta pública de sessões

`jangada-agentes --lista-json` fornece os dados de apresentação da Central
e do contador, sem leitura complementar dos registros pelo Shell.
A fachada K1 continua em `bin/`. O Core não depende de interface gráfica.

## Versão e campos

A resposta é um objeto JSON UTF-8: `{"versao":1,"sessoes":[]}`.
`versao` é inteiro, não booleano. `sessoes` é uma lista ordenada.
Cada sessão contém todos os campos abaixo, sempre como texto.
Campos adicionais são ignorados pelo consumidor da versão 1.

| Campo | Significado e padrão para registro antigo |
|---|---|
| `nome` | Nome tmux ou nome do arquivo sem `.json`; único na resposta |
| `estado` | Estado efetivo; ausente, nulo ou vazio vira `ativo` |
| `dir` | Diretório de trabalho; padrão vazio |
| `atualizado` | Data informada pelo registro; padrão vazio |
| `ramo` | Ramo informado; padrão vazio |
| `tarefa` | Tarefa completa, incluindo quebras de linha; padrão vazio |
| `agente` | Autor informado; padrão `Não informado` |
| `raiz` | Raiz informada ou `dir`, quando ausente, nula ou vazia |
| `projeto` | Último componente de `raiz`; padrão `Sem projeto` |
| `mensagem` | Atividade informada; padrão vazio |
| `desde` | Início temporal informado; padrão vazio |
| `coordenador` | Coordenador de exibição; padrão `dono` |
| `revisor` | Revisor informado; padrão `Não informado` |

`desde` alimenta `Sessao.inicio` na Central. O SHA `inicio` dos registros
não pertence à consulta. Datas ilegíveis continuam informativas, mas não
satisfazem a retenção temporal.
Estados desconhecidos permanecem textos informativos, sem novas permissões.
Coordenador, revisor, mensagem e estado são declarações graváveis.
Nenhum desses campos comprova identidade, autoridade, aprovação ou revisão.
A integração continua exigindo o contrato protegido existente.

## Seleção e compatibilidade

`nucleo/sessoes.py` concentra a seleção usada por JSON e TSV:

1. Sessões presentes no tmux, inclusive quando não há registro.
2. Registros com PID que responde à consulta de existência.
3. Registros `concluido` ou `aguardando` dentro de `JANGADA_AGENTES_GUARDAR`
   horas, padrão 24; registros `interrompido` dentro de 168 horas.
4. Registros sem PID, fora desses estados, com agente diferente de `par`
   e diretório existente. Aparecem como `interrompido`, sem gravar o estado.

A ordem é tmux primeiro, seguido pelos demais nomes ordenados.
As consultas não limpam, encerram, restauram nem autorizam sessões.
Estado inexistente não recebe diretórios. Com tmux vazio, retorna lista vazia.
Contextos `validacao-*-rN.contexto.json`, pareceres `revisao-*.json`
e relatórios `delegacao-*.json` não são carregados como sessões.

`--lista` e `--lista-atualizada` continuam com seis colunas TSV:
estado, nome, diretório, atualizado, ramo e resumo da tarefa.
Preservam o escape HTML do ramo/resumo, primeira linha e limite de 50
caracteres do resumo, e substituição de tabulações/quebras por espaços.
`--waybar` mantém seu formato e contagem. A limpeza explícita e as mutações
continuam com suas regras existentes.

O JSON preserva tabulações, quebras de linha, Unicode e entidades literais,
sem escape HTML adicional. A Central interpreta esses campos como texto.
O contador aplica escape HTML uma vez ao montar a dica da barra.

## Limites e erros

- Nome: `[A-Za-z0-9_.-]+`, até 255 caracteres, exceto `.` e `..`.
- Registro: arquivo regular, até 1 MiB; abertura relativa ao descritor da
  pasta, sem seguir links e sem bloquear em FIFO. A pasta final não pode ser link.
- Cada campo de apresentação: até 16.000 caracteres, sem truncamento.
- Consulta JSON: até 4.096 registros candidatos e sessões; resposta UTF-8 até 1 MiB.
- Central e contador: prazo de 10 segundos e limite agregado de 1 MiB
  para saída normal e diagnóstico, conferidos durante o transporte.

Na origem, campo ausente ou nulo usa o padrão documentado; outro tipo
recusa a consulta. PID, quando presente, exige inteiro positivo até 2.147.483.647.
Registro que não seja objeto JSON, arquivo inseguro, nome inválido ou limite
excedido recusa a resposta JSON inteira.
O comando sai com código 1, diagnóstico em stderr e nenhuma lista parcial.
O TSV continua tolerante: ignora campos de apresentação que não usa e preserva
seu resumo mesmo quando a tarefa ultrapassa 16.000 caracteres.
Registros inseguros ou ilegíveis usam os campos vazios anteriores, com aviso
em stderr; nomes inválidos são ignorados com aviso. Pasta inacessível ou
insegura e falha na varredura deixam só as sessões vivas, com aviso.
Texto que não pode ser codificado em UTF-8 usa os campos vazios no TSV.
Assim, um registro ruim
não interrompe a barra nem os consumidores internos do TSV.
Nomes inválidos vindos do tmux são ignorados com aviso em stderr nos dois
formatos, pois podem pertencer a sessões alheias ao jangada. Isso inclui
nomes com espaços ou acentos. Linhas vazias são ignoradas sem aviso.
Nomes inválidos de registros de sessão continuam recusando o JSON.
Sessões tmux com nomes reservados a pareceres, contextos ou relatórios
aparecem com os campos padrão; os arquivos correspondentes não são abertos.
A mesma seleção aplica os prazos recebidos de `jangada-agentes` aos dois formatos.
A retenção usa `date` por registro sem processo, com alternativa ISO pelo Python
quando não há comando disponível, ele rejeita a data, falha ou excede dois segundos. Esse custo não foi medido.

Na resposta pública, campos obrigatórios ausentes, nulos ou de tipo inesperado,
nomes repetidos, estado vazio, JSON inválido ou versão desconhecida são erros.
Não há retorno à leitura dos arquivos internos.
A Central preserva os últimos dados, mostra o erro e bloqueia ações até
uma consulta válida. O contador mostra `Tarefas · erro`.
Ao esgotar o prazo ou exceder o limite de saída, os consumidores encerram
somente o processo direto. Não encerram seu grupo de processos: o auxiliar
Python e seus filhos podem continuar até terminarem. O prazo de dois segundos
de cada chamada a `date` não limita o tempo total de todos os registros.
O prazo de transporte protege a interface, sem garantir cancelamento dos filhos.
A consulta não copia comandos, protocolos, credenciais ou históricos dos modelos.
Não há paginação; adequação a grande volume não foi medida.

## Provas

`testes/contratos-consulta.sh` compara hashes e caminhos antes/depois das
consultas K4 e verifica estado inexistente sem criação de pastas.
Usa sessões sintéticas vivas, com PID, retidas, restauráveis e expiradas;
confere TSV tolerante, barra e foco com registro inválido, dados completos
e Core funcionando sem Shell ou Monitor. Verifica retenção sem `date`, com
data recusada pelo comando e com prazo de interrupção recebido do chamador.
Também verifica JSON inválido, nomes inválidos, tipos, limites, links,
FIFO, diretórios e exclusão de contextos/pareceres.
Confere nomes tmux com espaços, acentos e travessia ignorados com aviso,
e nomes reservados sem abertura dos arquivos, mesmo com FIFO ou JSON inválido.
O TSV é conferido também com pasta linkada, sem leitura ou substituída por
arquivo, e com falha de varredura. A retenção é conferida com `date` lento
ou com falha de execução, sem perder a alternativa ISO.

`testes/tarefas.py` usa comando fictício com JSON e dados de apresentação
fora da pasta de sessões. Verifica consulta com registros internos ilegíveis,
seleção e posição preservadas, versão desconhecida, carga incompleta,
Unicode, multilinha, texto HTML literal, erros de comando, prazo e excesso.
As regressões de foco, retomada e integração permanecem na suíte.
A observação interna de arquivos A5 permanece fora deste contrato.
