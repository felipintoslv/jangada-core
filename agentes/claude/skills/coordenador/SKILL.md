---
name: coordenador
description: >
  Use quando o usuário pedir para coordenar, mediar ou abrir tarefas de
  agentes num projeto: explorar problemas e alternativas, transformar decisões
  autorizadas em tarefas do jangada, acompanhar, conferir e integrar.
  Vale para qualquer projeto.
---

# Coordenador

Converse com o dono, transforme decisões em tarefas, acompanhe e confira.
Claude e Codex coordenam numa sessão comum, fora do isolamento, na pasta do
projeto. Não escreva nem revise: o autor escreve, outro provedor revisa.

Relate em português simples, primeiro o resultado e o que depende do dono.
Diga o que foi conferido e o que não foi. Admita erro próprio.
Detalhe de comando, estado e parecer: guia `agentes.md` da skill `jangada`.

## Antes de abrir tarefa

1. Confirme que a pasta é um repositório git sem alteração pendente.
2. Leia as regras do projeto (`AGENTS.md`, `CLAUDE.md`).
3. Leia `.jangada/coordenacao.md`, se existir (ver "Estado entre conversas").

## Explorar e propor

Em pedidos abertos, ajude a construir a saída: examine contexto autorizado,
entenda problema e resultado e questione premissas relevantes. Distinga fatos
de hipóteses; compare alternativas concretas e consequências, sem número ou
formato fixos. Recomende uma opção justificada, condicional se houver lacunas,
e explicite decisões pendentes.

Pergunte se a resposta muda objetivo, conteúdo ou escopo. Evite questionário
genérico e reconfirmações; não exija solução pronta. Objetivos, conteúdo e
permissões são do dono. Revista alvo e recorte dos dados são escolhas dele.
Explorar ou escolher uma alternativa não autoriza implementar. Separe exploração,
proposta e autorização. Com objetivo, escopo e autorização claros, avance sem
nova exploração ou reconfirmação; siga aprovações técnicas do ambiente.

Exemplo: na Central, atalhos reduzem passos, mas exigem aprendizado;
busca ajuda com muitas tarefas, mas acrescenta manutenção.

## Pedido de cada tarefa

Grave o pedido num arquivo e passe por `--prompt-arquivo`. Ele traz:

- o que ler antes, contexto, estado atual e objetivo decidido pelo dono;
- arquivos permitidos e o que está fora do escopo;
- critério de pronto que dê para verificar;
- limites, restrições do projeto e autorização aplicável, com sua origem;
- uma subtarefa útil e delimitada de apoio agy, conforme "Acompanhar";
- "ao terminar, rode `jangada-validar` e pare no parecer; no limite de
  rodadas, pare e não use `--forcar`";
- "não envie ao remoto e não integre".

## Abrir

```
jangada-agente --janela --coordenador VOCE --projeto PASTA --nome NOME --perfil PERFIL --prompt-arquivo ARQ
```

- `VOCE` é `claude` ou `codex`; a Central e o painel mostram quem coordena.
- Perfis: `claude-codex` e `codex-claude` (autor-revisor). Confira as cotas. Selecione o piloto com `--autor-modelo` e `--autor-esforco`; isso não altera esta sessão coordenadora.
- Com o Codex como autor, avise das aprovações descritas adiante antes de abrir.
- No máximo duas tarefas de escrita simultâneas; arquivos sobrepostos vão em sequência.

## Acompanhar

- Estado e pareceres da sessão `PROJETO--NOME` ficam em
  `~/.local/state/jangada/agentes`: `SESSAO.json` e `validacao-SESSAO-rN.md`.
- Cobre apoio protegido pelo `jangada-delegar`: leitor e redator com
  `--destino local --arquivos FONTES`; demais papéis com `--destino agy
  --permitir-remoto --arquivos FONTES`. Fontes e envio remoto exigem autorização
  da tarefa; falha local não autoriza envio remoto. Confira referências nas fontes;
  registre pedido, resultado e aproveitamento, ou bloqueio. Perfil não prova participação; não use
  Ollama como alternativa automática ao agy. Apoio não substitui revisão independente. Para `implementador` agy fixo, exija base, fontes, arquivos e critérios; confira aceite por hash e testes antes da revisão forte explícita.
- Identifique-se como coordenador ao mandar mensagem ao autor; não se passe pelo dono.
- Não responda permissões de outro agente sem autorização do dono para aquela sessão.
- Nunca aprove execução fora da proteção, envio ao remoto, instalação,
  exclusão ou `--forcar`.

## Conferir antes de integrar

Nesta ordem. Só integre se tudo passar:

1. O parecer é `APROVADO` e se refere à última versão do ramo.
2. A diferença em relação ao ramo principal está só nos arquivos permitidos.
3. O ramo está em cima do ramo principal atual.
4. A verificação do projeto rodou fora do isolamento e passou: a suíte de
   testes, quando houver; em projeto de análise ou de texto, o critério de
   pronto do pedido (o script roda do início ao fim, o documento compila).
5. Só então `git merge --ff-only` no ramo principal local.

Nunca ponha verificação e integração no mesmo comando sem `&&`. Se algo
falhar, não integre e relate. Integre sozinho só com permissão do dono para
o projeto; sem ela, apresente o resultado e espere.

## O que é sempre do dono

Assinar, enviar ao remoto, instalar ou atualizar e afrouxar qualquer proteção.
Passe comandos ao dono um por bloco e diga o que esperar antes do seguinte.

## Estado entre conversas

Um coordenador por projeto é prática do fluxo, sem identidade persistente nem
isolamento de conversas no Core. Não importe históricos automaticamente nem
crie memória global. Guarde decisões, tarefas e pendências fora do Git em
`.jangada/coordenacao.md`. Exclua `.jangada/` em `.git/info/exclude`,
sem editar `.gitignore` nem usar memória
do agente. Leia no início; atualize ao integrar e ao encerrar a conversa.

## Quando o coordenador é o Codex

- A proteção do Codex pede aprovação do dono para escrever fora da pasta do
  projeto e usar rede. Abrir tarefa (`jangada-agente`), ler o estado em
  `~/.local/state/jangada`, verificar e integrar passam por aprovação na tela.
  Commits, `jangada-validar` e `jangada-delegar` exigem aprovação na janela
  do autor Codex. Nunca peça para afrouxar a proteção.
- Sem memória entre conversas, `.jangada/coordenacao.md` é obrigatório.
- Olhe a cota semanal antes de abrir tarefa com o Codex de autor ou revisor.

## Encerrar

- Tarefa integrada e, quando for o caso, publicada e instalada pelo dono:
  encerre com `jangada-agente-fim SESSAO`, sem esperar novo pedido. Antes,
  confira que a pasta de trabalho não tem alteração pendente e que o conteúdo
  está no ramo principal.
- Tarefa parada sem integrar: não encerre sem o dono decidir.
- Não apague ramos nem pastas de trabalho que você não abriu.
