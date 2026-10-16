---
name: relatorio-academico
description: >
  Use ao escrever ou revisar texto acadêmico: artigo, relatório de pesquisa,
  trabalho de disciplina, monografia, dissertação ou capítulo de tese (IMRaD,
  ABNT NBR 14724, template de periódico). Traz o que levantar antes de redigir,
  as regras de não inventar dado ou citação (marcar [FALTA: ...]), a estrutura
  por seção, figuras e tabelas e o checklist antes de entregar. Não use para
  postmortem, RFC ou ADR (veja a skill relatorio-tecnico).
---

# Protocolo: relatório acadêmico

Para artigo, relatório de pesquisa, trabalho de disciplina, monografia ou
capítulo de tese escrito por um agente ou com ajuda de um.
## 1. Antes de escrever

Levante e registre, sem começar o texto:

1. **Pergunta de pesquisa** em uma frase.
2. **Contribuição** em uma frase. Se não couber, o trabalho ainda não tem foco
   (hzwer: a contribuição de quase todo artigo cabe numa categoria só).
3. **Público e destino:** periódico, conferência, banca ou disciplina, e a
   norma que eles exigem (ABNT NBR 14724 para trabalho acadêmico no Brasil,
   template do periódico, diretriz de relato como CONSORT, PRISMA ou STROBE
   quando for estudo clínico ou revisão sistemática).
4. **Registro de evidências:** cada resultado, número, citação e figura que o
   texto vai usar, com a origem (arquivo de log, tabela, DOI, página).
   Nada entra no texto sem estar no registro (K-Dense: "Every factual or
   numeric manuscript claim must map to verified evidence").

Se faltar algum desses quatro itens, pergunte antes de redigir.

### Plano do argumento

Para documento extenso, acrescente um plano breve ao registro de evidências.
Registre por seção a pergunta, a afirmação central e a evidência que a
sustenta, com localização. Indique a lacuna que a próxima seção resolve.
Aproveite o plano existente; em revisão localizada, planeje só o trecho
alterado.

Use esse plano para conferir se cada seção contribui para a pergunta de
pesquisa e se uma conclusão ficou sem apoio. Fonte ausente permanece
`[FALTA: descrição]`. O plano cabe no registro ou na conversa; não exige
arquivo separado, aprovação por parágrafo ou quantidade fixa de frases.

## 2. Regras invioláveis

- **Não invente.** Citação, DOI, dado, tamanho de amostra, teste estatístico,
  versão de software, aprovação ética, financiamento: se não está no
  registro, escreva `[FALTA: descrição]` no lugar. Não preencha com texto
  plausível (K-Dense: "Do not substitute plausible boilerplate").
- **Expectativa não é observação.** Se a análise ainda não foi executada,
  descreva método e resultados esperados como plano ou hipótese. Não atribua
  sinal ou magnitude observados a uma estimativa que ainda não existe.
- **Resultado não é interpretação.** A seção de resultados diz o que foi
  observado; a discussão diz o que isso significa.
- **Associação não é causalidade**, e ausência de significância não é
  equivalência (K-Dense).
- **Preserve a incerteza:** intervalos, tamanho de amostra, resultados nulos
  e negativos entram no texto.
- **Não exagere.** "Supera o estado da arte" exige a comparação que mostra
  isso. Exagero é uma das críticas mais comuns de revisor (hzwer).
- **Verifique toda referência** antes de entregar: existe, os metadados
  batem, não foi retratada (citecheck faz isso por Crossref e OpenAlex).

## 3. Estrutura

Use IMRaD quando o trabalho for empírico; adapte quando não for (K-Dense:
"Use IMRAD only when appropriate"). Para trabalho acadêmico no Brasil, os
elementos pré e pós-textuais seguem a NBR 14724 (o modelo do abnTeX2 já
traz a estrutura).

| Seção | Responde | Regras |
|---|---|---|
| Título | Do que trata e qual o achado | Específico; sem "Um estudo sobre…" |
| Resumo | Objetivo, método, resultados, conclusão (NBR 6028) | Um parágrafo; números principais; se sustenta sem o texto; escreva por último |
| Introdução | Por que importa, o que falta, o que este trabalho faz | Três movimentos: território, lacuna, ocupação (hzwer). Contribuições em lista. Achado principal já na introdução |
| Trabalhos relacionados | Como os outros atacaram o mesmo problema | Compare e contraste com o seu trabalho; não resuma artigo por artigo (AI-Scientist). Reconheça o mérito antes da limitação |
| Métodos | O que foi feito, o suficiente para reproduzir | Como foi executado, não como foi planejado; desvios declarados; não invente detalhe de hardware ou parâmetro |
| Resultados | O que se observou | Na ordem declarada nos métodos; comparação com linha de base; intervalo de confiança; só o que está no registro |
| Discussão | O que significa e quais os limites | Interpretação ligada a cada resultado; explicações alternativas; limitações concretas; generalização delimitada |
| Conclusão | Resposta à pergunta de pesquisa | Curta; sem fato novo; sem otimismo genérico; trabalho futuro só se for específico |

## 4. Escrita

Valem as regras gerais de escrita (resultado primeiro, sem enchimento, frase
curta, adjetivo trocado por número). As específicas de texto acadêmico:

- **Frase-tópico no início do parágrafo.** Quem só lê a primeira frase de
  cada parágrafo entende o argumento (hzwer).
- **Uma frase, uma ideia** (MLNLP). Frase ambígua vira duas.
- **Defina o termo onde ele aparece:** "propomos X, um perceptron de duas
  camadas que…" (hzwer). Sigla definida no primeiro uso, grafia única do
  início ao fim (cooelf).
- **Conectivo só com relação lógica real.** "Para isso" precisa de um
  objetivo antes; "primeiro… por fim" só para itens com ordem (hzwer).
- **Afirmação com fonte ou evidência.** "É um problema central da área"
  pede referência ou dado (hzwer: "defensabilidade").
- **Grau de certeza calibrado, não empilhado.** "Os resultados sugerem" uma
  vez, onde a evidência é indireta. Não "parece possivelmente indicar".
- **Sem autorreferência nem narração:** nada de "neste trabalho iremos
  discorrer sobre" (open_deep_research). Diga o que foi feito.
- **Passiva só onde o agente não importa** (métodos). Conclusões e
  contribuições em voz ativa: "mostramos que", "o método reduz".
- **Densidade:** não explique o que o público já sabe; detalhe de
  hiperparâmetro vai para o apêndice (hzwer).

> Antes: Primeiramente, é importante destacar que a questão da evasão
> escolar constitui um tema de grande relevância no cenário atual, sendo
> amplamente discutida por diversos autores. Neste sentido, o presente
> trabalho busca analisar esse fenômeno.
>
> Depois: A evasão no primeiro ano dos cursos de engenharia da UFX foi de
> 31% entre 2019 e 2023 [FALTA: fonte institucional]. Este trabalho mede o
> efeito da monitoria sobre essa taxa.

> Antes: Os resultados demonstram claramente que o modelo proposto é
> significativamente superior, o que comprova a eficácia da abordagem.
>
> Depois: O modelo acertou 84,1% (IC 95%: 82,7 a 85,5) contra 80,3% da linha
> de base, no mesmo conjunto de teste. A diferença se mantém nas três
> sementes, mas não foi testada fora do domínio jurídico.

## 5. Figuras e tabelas

- Cada figura e tabela é citada no texto, na ordem em que aparece.
- A legenda diz o que mostrar e a conclusão, e explica as siglas; a figura
  deve ser entendível sem o texto (hzwer).
- A análise fica perto da figura ou tabela e liga a referência ao achado que
  ela sustenta. Diga o que a comparação mostra e seu limite; "a tabela
  apresenta os resultados" não substitui essa análise.
- Em Quarto, use identificadores `fig-` e `tbl-` e referências `@fig-...` e
  `@tbl-...`, conforme o [guia de referências](https://quarto.org/docs/authoring/cross-references).
  Assim a numeração acompanha a ordem do documento. Em outros formatos,
  preserve o mecanismo de referência adotado pelo projeto.
- Coloque lado a lado o que o leitor deve comparar, mesmo que repita uma
  linha de base (hzwer).
- Só figura que existe e resultado que foi rodado (AI-Scientist).

## 6. Revisão antes de entregar

Faça em passes separados, um objetivo por vez:

1. **Evidência:** cada número e cada citação batem com o registro. Toda
   marcação `[FALTA]` está listada para o usuário.
2. **Consistência:** o mesmo número é igual no resumo, no texto e na tabela;
   termos e siglas com grafia única; métodos e resultados na mesma ordem.
3. **Argumento:** cada seção sustenta sua afirmação central e contribui
   para responder à pergunta de pesquisa? Figuras e tabelas têm análise?
4. **Redundância:** o que se repete entre seções é cortado de onde menos
   serve (AI-Scientist: "Identify where we can save space… without weakening
   the message").
5. **Frase:** enchimento, ressalvas empilhadas, conectivos falsos, adjetivos
   sem número.
6. **Norma:** elementos obrigatórios da norma ou do template, formato das
   referências, limite de páginas.

## 7. Checklist final

- [ ] Pergunta e contribuição cabem numa frase cada, e aparecem na introdução.
- [ ] O resumo tem objetivo, método, resultado com número e conclusão.
- [ ] Nenhum dado, citação ou detalhe de método sem origem no registro.
- [ ] Referências verificadas (existem, metadados corretos, não retratadas).
- [ ] Resultados separados da interpretação.
- [ ] Limitações concretas declaradas.
- [ ] Trabalhos relacionados comparados com o próprio trabalho.
- [ ] Toda figura e tabela citada no texto, com legenda autoexplicativa.
- [ ] Números iguais em todo o documento.
- [ ] Nenhuma frase de autorreferência ou de conclusão genérica.
- [ ] Pendências (`[FALTA]`) listadas na resposta ao usuário.
