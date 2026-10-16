---
name: relatorio-tecnico
description: >
  Use ao escrever ou revisar relatório técnico: investigação (spike), incidente
  (postmortem), proposta de mudança (RFC, design doc), registro de decisão (ADR)
  ou relatório técnico formal (ABNT NBR 10719). Traz a estrutura de cada tipo,
  as regras de fato com fonte, hipótese marcada e ação com dono e prazo, e o
  checklist antes de entregar. Não use para artigo, monografia ou tese (veja a
  skill relatorio-academico).
---

# Protocolo: relatório técnico

Para relatório de investigação, incidente, proposta de mudança, registro de
decisão ou relatório técnico formal escrito por um agente ou com ajuda de um.
## 1. Escolha o tipo

O tipo decide a estrutura. Não misture dois tipos num documento só.

| Tipo | Quando | Modelo de origem |
|---|---|---|
| Investigação | Responder a uma pergunta técnica ("X aguenta 10 mil conexões?") | Spike (Microsoft playbook) |
| Incidente | Algo falhou e afetou alguém | Postmortem (SRE, PagerDuty) |
| Proposta | Pedir aprovação para uma mudança | RFC (Rust), KEP (Kubernetes), design doc (Go) |
| Decisão | Registrar uma escolha já feita e o porquê | ADR (Nygard, MADR) |
| Relatório formal | Entrega contratual ou institucional | ABNT NBR 10719 (modelo do abnTeX2) |

### Plano para relatórios extensos

Antes de redigir um relatório extenso, planeje a função de cada seção.
Registre a pergunta que responde, a conclusão ou decisão pretendida e a
evidência necessária, com localização. A conclusão pretendida é hipótese
de trabalho; ajuste-a se a evidência a contrariar.

Aproveite o roteiro existente ou faça esse plano na conversa. Em texto
curto ou revisão localizada, basta conferir a ligação entre afirmação e
fonte no trecho; não crie arquivo nem rodada de aprovação adicional.

## 2. Regras que valem para todos

- **Comece pelo resumo.** Duas a quatro frases: o que aconteceu ou o que se
  propõe, o impacto e o que se pede do leitor (decisão, aprovação, nada).
  Quem ler só o resumo deve saber o que fazer.
- **Fato com fonte.** Cada número, horário e comportamento aponta para a
  origem: gráfico, log, commit, ticket (PagerDuty: "For each item in the
  timeline, identify a metric or some third-party page").
- **Fato separado de análise.** A linha do tempo e as evidências não trazem
  juízo; a análise vem depois (PagerDuty: "Separate what happened from how
  to fix it").
- **Hipótese marcada como hipótese.** Pode especular, desde que diga que é
  especulação e o que confirmaria (dzhng: "just flag it for me").
  `[NÃO VERIFICADO]` quando não houve como checar.
- **Palavra exata para o impacto.** "Indisponibilidade" só se o serviço caiu;
  "lentidão em 12% das requisições por 40 minutos" se foi isso (PagerDuty:
  não usar "outage" se não foi).
- **Alternativas e desvantagens explícitas** em toda proposta e decisão
  (Rust: "Drawbacks", "Rationale and alternatives"; MADR: prós e contras por
  opção).
- **O que não se sabe tem seção.** Questões abertas, riscos, onde tivemos
  sorte (Rust, Go, KEP, SRE).
- **Ação com dono, escopo e prazo.** "Melhorar o monitoramento" não é ação;
  "alertar quando a fila passar de 5 mil mensagens (dono: time de dados,
  até 15/10)" é (PagerDuty: "actionable, specific, and bounded in scope").
- **Sem culpa.** Descreva a ação e o que no sistema a permitiu. "Erro
  humano" não é causa (PagerDuty).
- **Termo e sigla definidos** para quem não estava no incidente ou na
  discussão.

## 3. Estruturas

### Investigação (spike)

| Seção | Conteúdo |
|---|---|
| Resumo | A pergunta e a resposta, em duas frases |
| Pergunta | O que se queria saber e por quê |
| Método | Como se testou: protótipo, carga, leitura de código, conversa com especialista |
| Evidências | Medições, logs, trechos de doc, com fonte |
| Conclusão | A resposta, com o grau de confiança e o que ficou de fora |
| Próximos passos | Trabalho que a resposta destrava ou bloqueia |

### Incidente (postmortem)

| Seção | Conteúdo |
|---|---|
| Resumo | Duração, impacto observável, estado atual |
| Impacto | Quem foi afetado, quanto, por quanto tempo (o impacto pode começar antes da detecção) |
| Linha do tempo | Só fatos, com horário e fonte; inclui o que só se soube depois |
| Fatores contribuintes | Técnicos e de processo; por que o sistema permitiu a falha |
| Detecção e resposta | Como foi percebido, quanto demorou, o que ajudou e o que atrapalhou |
| Onde tivemos sorte | O que poderia ter piorado e não piorou |
| Ações | Específicas, com dono e prazo, ligadas a um fator contribuinte |

### Proposta (RFC, design doc)

| Seção | Conteúdo |
|---|---|
| Resumo | A mudança em um parágrafo |
| Motivação | O problema, com evidência de que ele existe |
| Objetivos e não objetivos | O que a proposta resolve e o que deixa de fora de propósito |
| Proposta | A mudança, precisa o bastante para ser implementada |
| Alternativas | Outras opções e por que não foram escolhidas |
| Desvantagens e riscos | Custos da proposta e mitigação |
| Compatibilidade | O que quebra, como migrar |
| Questões abertas | O que ainda não se sabe |

### Decisão (ADR)

| Seção | Conteúdo |
|---|---|
| Título | A decisão, curta ("Usar PostgreSQL para filas") |
| Status | Proposta, aceita, substituída (por qual) |
| Contexto | A situação e as forças em jogo |
| Opções consideradas | Cada uma com prós e contras |
| Decisão | A escolha e o motivo principal |
| Consequências | O que fica mais fácil e o que fica mais difícil |

### Relatório formal (NBR 10719)

Siga os elementos pré-textuais, textuais e pós-textuais da norma (o modelo
`abntex2-modelo-relatorio-tecnico.tex` do abnTeX2 já traz a estrutura). No
texto, use as regras da seção 2: resumo com objetivo, método, resultados e
conclusões (NBR 6028), fatos com fonte e recomendações acionáveis.

## 4. Escrita

Valem as regras gerais de escrita (resultado primeiro, sem enchimento, frase
curta, adjetivo trocado por número). As específicas de relatório técnico:

- **Números com unidade e base:** "p99 de 480 ms para 120 ms, medido em
  produção de 2 a 9/9", não "muito mais rápido".
- **Horário com fuso** na linha do tempo.
- **Nome de sistema, comando e arquivo em código:** `api-pagamentos`,
  `kubectl rollout undo`.
- **Tabela para comparação** de opções e medições; parágrafo para a análise.
  Ligue cada figura ou tabela à conclusão que ela sustenta e explicite os
  limites da comparação. Apontar que uma tabela "apresenta os dados" não
  explica o que eles mostram.
- **Resultado medido e resultado esperado separados.** Projeção, simulação
  ou benefício de uma mudança ainda não executada não é efeito observado
  em produção. Declare as premissas que sustentam a expectativa.
- **Sem narrar o processo de escrita** ("neste relatório vamos abordar").

> Antes: Durante o período analisado, observou-se uma degradação
> significativa no desempenho do sistema, possivelmente relacionada a
> problemas no banco de dados, o que impactou negativamente a experiência
> dos usuários. A equipe atuou prontamente para mitigar a situação.
>
> Depois: Das 14:02 às 14:41 (UTC−3), 12% das requisições ao checkout
> passaram de 2 s ([painel](link)). O pool de conexões do `pedidos-db`
> estava esgotado desde a migração das 13:55 ([log](link)). O rollback às
> 14:38 normalizou a latência em três minutos.

> Antes: Ações: melhorar o monitoramento; revisar o processo de deploy.
>
> Depois:
> - Alertar quando o pool do `pedidos-db` passar de 80% (dono: plataforma, 10/10).
> - Rodar migração de schema fora do horário de pico, com a checagem no CI (dono: pagamentos, 17/10).

## 5. Revisão antes de entregar

1. **Resumo:** quem ler só o resumo sabe o que aconteceu e o que fazer?
2. **Fontes:** todo número e horário tem link ou origem?
3. **Fato e análise:** a linha do tempo ou a seção de evidências tem juízo?
4. **Hipóteses:** toda especulação está marcada?
5. **Ações:** todas têm dono, escopo e prazo?
6. **Argumento:** cada conclusão ou recomendação é sustentada pelas
   evidências? Seções e tabelas têm função na resposta à pergunta técnica?
7. **Redundância:** o mesmo achado aparece em mais de uma seção?
8. **Frase:** enchimento, adjetivo sem número, "erro humano", "indisponibilidade"
   que não foi.

## 6. Checklist final

- [ ] Tipo escolhido e estrutura dele seguida.
- [ ] Resumo com impacto ou proposta e o pedido ao leitor.
- [ ] Todo fato com fonte; nada marcado como fato sem ter sido verificado.
- [ ] Hipóteses e `[NÃO VERIFICADO]` explícitos.
- [ ] Alternativas e desvantagens (proposta e decisão).
- [ ] Questões abertas ou riscos declarados.
- [ ] Ações específicas, com dono e prazo (incidente e investigação).
- [ ] Nenhuma atribuição de culpa a pessoa.
- [ ] Siglas e nomes internos explicados.
