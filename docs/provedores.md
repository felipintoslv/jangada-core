# Registro de provedores

O registro diz quais provedores existem e o que cada um pode fazer. Ele
substitui as listas que ficavam fixas no `jangada-agente` e no
`jangada-validar`.

## Onde ficam

Um arquivo `NOME.conf` por provedor, em `provedores/` (link de
compatibilidade; desde a modularização 3.0 a pasta mora em
`provedores/`). Uma cópia em
`~/.config/jangada/provedores/NOME.conf` tem precedência sobre a do
repositório, e um arquivo novo nessa pasta acrescenta um provedor.

O arquivo é lido, não executado. Nenhuma chave dele vai para o ambiente do
agente, e chave desconhecida é ignorada. Um arquivo inválido deixa o
provedor fora das listas.

## Chaves

| Chave | Valores | Uso |
|---|---|---|
| `NOME` | Texto | Nome mostrado nas mensagens. Sem ela, vale o nome do arquivo |
| `TIPO` | `cli` ou `ollama` | Obrigatória. Outros tipos são recusados. Em `cli`, o executável é o nome do arquivo |
| `FUNCOES` | `principal`, `revisor`, `delegacao`, separadas por espaço | Obrigatória |
| `PROTOCOLO_ARG` | Uma opção, como `--append-system-prompt` | Opção que recebe o protocolo da sessão. Sem ela, o agente abre sem protocolo |
| `MODELO_REVISOR` | Nome de modelo | Modelo da revisão quando `--modelo` não é dado |
| `RESERVA` | Número | Posição na fila de reserva da revisão. Sem ela, o provedor não entra como reserva |

## O que cada função libera

- `principal`: o provedor aparece em `jangada-agente --capacidades-json` e
  os perfis que usam o comando dele aparecem em `--perfis`. A Central lê as
  duas listas. Só vale com `TIPO=cli`; em outro tipo o arquivo é recusado.
- `revisor`: o nome é aceito em `--revisor` e em `JANGADA_VALIDAR_REVISOR`.
- `delegacao`: só descreve. Os destinos do `jangada-delegar` não mudaram.

## Provedores do repositório

| Provedor | Tipo | Funções | Observação |
|---|---|---|---|
| `claude` | `cli` | principal, revisor | Protocolo por `--append-system-prompt`; revisa com `sonnet`; primeira reserva |
| `agy` | `cli` | revisor, delegacao | Delegação padrão; segunda reserva da revisão |
| `codex` | `cli` | principal, revisor | Protocolo pelo `jangada-codex`; terceira reserva |
| `ollama` | `ollama` | delegacao | Delegação somente por escolha explícita |

Endereço e modelo do Ollama seguem em `JANGADA_OLLAMA_URL` e
`JANGADA_LOCAL_MODELO`. Não há seleção local automática na política padrão.

## Limites

- Um programa novo aparece como agente principal só com o arquivo do
  registro; um perfil em `~/.config/jangada/agentes/` é opcional.
- Um revisor novo ainda precisa de uma função `revisar_NOME` no
  `jangada-validar`: cada programa recebe o pedido de um jeito. Sem a
  função, o `jangada-validar` recusa com mensagem.
- A fila (`jangada-task`), a saúde dos provedores e os destinos da
  delegação continuam com as listas próprias.
- Provedores acessados por chave de API não são aceitos.
