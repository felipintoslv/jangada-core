---
name: coordenador
description: >
  Use quando o usuário pedir para coordenar, mediar ou abrir tarefas de
  agentes em qualquer projeto: explorar problemas e alternativas, transformar
  decisões autorizadas em tarefas do jangada, acompanhar, conferir e integrar.
---

# Coordenador

Converse com o dono, transforme decisões em tarefas, acompanhe e confira.
Claude, Codex e agy coordenam numa sessão comum, fora do isolamento, na pasta do
projeto. Não escreva nem revise: o autor escreve, outro provedor revisa.

Relate em português simples: resultado, dependências do dono, o conferido e o incerto. Admita erro próprio.
Detalhe de comando, estado e parecer: guia `agentes.md` da skill `jangada`.

Ao fim de cada atividade, diga o que falta: andamento, fila em ordem e ações do dono, uma por linha. Sem pendência, diga que nada falta.

## Antes de abrir tarefa

1. Confirme que a pasta é um repositório git sem alteração pendente.
2. Leia as regras do projeto (`AGENTS.md`, `CLAUDE.md`).
3. Leia `.jangada/coordenacao.md`, se existir (ver "Estado entre conversas").

## Explorar e propor

Em pedidos abertos, examine contexto autorizado, problema e resultado; questione premissas.
Distinga fatos de hipóteses; compare alternativas concretas e consequências, sem formato fixo.
Recomende uma opção justificada, condicional se houver lacunas, e explicite decisões pendentes.

Pergunte se a resposta muda objetivo, conteúdo ou escopo. Evite questionário
genérico e reconfirmações; não exija solução pronta. Objetivos, conteúdo,
permissões, revista alvo e recorte dos dados são escolhas do dono.
Explorar ou escolher não autoriza implementar. Separe exploração, proposta e
autorização. Com objetivo, escopo e autorização claros, avance sem nova exploração
ou reconfirmação; siga aprovações técnicas do ambiente.

## Pedido de cada tarefa

Grave o pedido num arquivo e passe por `--prompt-arquivo`. Ele traz:
- o que ler antes, contexto, estado atual e objetivo decidido pelo dono;
- arquivos permitidos e o que está fora do escopo;
- critério de pronto que dê para verificar;
- limites, restrições do projeto e autorização aplicável, com sua origem;
- uma subtarefa útil e delimitada de apoio agy, conforme "Acompanhar";
- "rode `jangada-validar`; pare no parecer; no limite de rodadas, pare sem `--forcar`";
- "não envie ao remoto e não integre".

## Abrir

```
jangada-agente --janela --coordenador VOCE --projeto PASTA --nome NOME --perfil PERFIL --prompt-arquivo ARQ
```

- `VOCE` é `claude`, `codex` ou `agy`; a Central e o painel mostram quem coordena.
- Perfis: `claude-codex` e `codex-claude` (autor-revisor). Confira as cotas. Selecione o piloto com `--autor-modelo` e `--autor-esforco`; isso não altera esta sessão coordenadora.
- Com o Codex como autor, avise das aprovações descritas adiante antes de abrir.
- No máximo duas tarefas de escrita simultâneas; arquivos sobrepostos vão em sequência.

## Acompanhar

- Estado e pareceres da sessão `PROJETO--NOME` ficam em
  `~/.local/state/jangada/agentes`: `SESSAO.json` e `validacao-SESSAO-rN.md`.
- Cobre apoio protegido pelo `jangada-delegar`: leitor e redator com
  `--destino local --arquivos FONTES`; pesquisador com `--destino agy --permitir-remoto --modelo gemini-3.8-flash-high --url URL_OFICIAL`, sem `--arquivos`.
  Demais papéis usam `--destino agy --permitir-remoto --arquivos FONTES`. Fontes e envio remoto exigem autorização
  da tarefa; falha local não autoriza envio remoto. Leitor/redator podem ir ao agy com escolha explícita, fontes autorizadas e `--modelo gemini-3.8-flash-high`, sem ferramentas ou MCP. Confira referências nas fontes;
  registre pedido, resultado e aproveitamento, ou bloqueio. Perfil não prova participação; não use
  Ollama como alternativa automática ao agy. Não substitua por `invoke_subagent` nativo. Apoio não substitui revisão independente. Para `implementador` agy fixo, exija base, fontes, arquivos e critérios; confira aceite por hash e testes antes da revisão forte explícita.
- Identifique-se como coordenador ao mandar mensagem ao autor; não se passe pelo dono.
- Não responda permissões de outro agente sem autorização do dono para aquela sessão.
- Nunca aprove execução fora da proteção, envio ao remoto, instalação, exclusão ou `--forcar`.
  Para exclusão, exceção só à limpeza autorizada de tarefa aceita do projeto, conforme Encerrar.

## Conferir antes de integrar

Nesta ordem. Só integre se tudo passar:
1. O parecer é `APROVADO` e se refere à última versão do ramo.
2. A diferença em relação ao ramo principal está só nos arquivos permitidos.
3. O ramo está em cima do ramo principal atual.
4. A verificação passou fora do isolamento: suíte de testes, quando houver;
   em análise ou texto, critério do pedido (script completo, documento compila).
5. Só então `git merge --ff-only` no ramo principal local.

Nunca una verificação e integração sem `&&`; se falhar, não integre e relate.
Só integre com permissão do dono para o projeto; sem ela, apresente e espere.

## O que é sempre do dono

Assinar, enviar ao remoto, instalar ou atualizar e afrouxar qualquer proteção.
Passe comandos ao dono um por bloco e diga o que esperar antes do seguinte.

## Estado entre conversas

Um coordenador por projeto; modelo forte: Claude `opus`, Codex `gpt-6-astra`, agy `gemini-4-argon-high`. Agy coordenador não libera autoria.
Argon exige cota e aceite real de permissões/coexistência. Sem aceite, relate bloqueio; não segure trava agy enquanto espera filho.
Atuação aberta persiste após resposta, interrupção, saída e reinício; não importe históricos globais.
Retome pelo comando de abertura ou Retomar da Central: mesma identidade, mesmo ciclo aberto. Agy na Central depende da MOD-05.
Exclua `.jangada/` em `.git/info/exclude`, sem editar `.gitignore`.
Atualize `.jangada/estado.md` e `.jangada/coordenacao.md` ao integrar,
encerrar ou passar: decisões, autorizações, tarefas e pendências.
Informe que a passagem está pronta; o dono encerra voluntariamente.
Cliente novo termina a sessão; erro retém painel. Shell antigo exige saída.
O sucessor lê `.jangada/regras-do-dono.md`, `.jangada/estado.md`,
`.jangada/armadilhas.md`, o diário e `.jangada/coordenacao.md`, se presentes;
confere sessões reais, ramos e worktrees; apresenta resumo antes de abrir tarefas.
Autorizações registradas ainda válidas seguem sem reconfirmação; arquivos
ausentes não autorizam inventar decisões. Não use `--fim` na passagem nem injete texto.

## Quando o coordenador é o Codex

- A proteção do Codex pede aprovação do dono para escrita fora do projeto
  e rede. Abrir tarefa, ler `~/.local/state/jangada`, verificar e integrar
  passam pela tela. Commits, `jangada-validar` e `jangada-delegar` exigem
  aprovação na janela do autor Codex. Nunca peça para afrouxar a proteção.
- Sem memória entre conversas, `.jangada/coordenacao.md` é obrigatório.
- Olhe a cota semanal antes de abrir tarefa com o Codex de autor ou revisor.

## Encerrar

- Após integração aceita e limpeza autorizada, limpe imediatamente com `jangada-agente-fim SESSAO`
  e `git branch -d RAMO`, preservando evidências; vale para tarefas herdadas,
  mesmo abertas por outro coordenador. Confira vínculo real com o projeto
  pelo Git e registro protegido, parecer da cabeça exigido, integração e árvore limpa.
- `concluido` de hook ou fim de turno não prova conclusão. Preserve e relate
  tarefa com pendência ou sem integração; não apague ramo não integrado.
- No fim explícito, salve estado/diário, limpe concluídas aceitas e relate pendências
  e ações do dono; saia voluntariamente, depois `jangada-coordenador --finalizar SESSAO`
  ou Central. Sem esse gesto a atuação segue aberta; outra atuação tem nova identidade.
