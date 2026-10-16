# Regras de visualização de dados

Síntese de um levantamento de 03/10/2026 em repositórios, guias de estilo
institucionais, livros e artigos com evidência empírica. Estrelas, licenças,
versões de pacotes, oito DOIs e trechos dos guias do Urban Institute e do
Government Analysis Function foram conferidos na origem. A `checklist.md`
remete a estas regras pelo número entre colchetes; as decisões da casa que
se afastam delas estão no `SKILL.md`.

## Fontes prioritárias

Doze fontes cobrem quase tudo:

| Fonte | Papel no guia |
|---|---|
| Wilke, [Fundamentals of Data Visualization](https://clauswilke.com/dataviz/) e o repositório [clauswilke/dataviz](https://github.com/clauswilke/dataviz) | Referência conceitual, com código ggplot2 de cada figura |
| [Urban Institute, Data Visualization Style Guide](https://urbaninstitute.github.io/graphics-styleguide/) e [urbnthemes](https://github.com/UrbanInstitute/urbnthemes) | Modelo de guia com tabela de tamanhos para PDF e web, e de pacote de tema |
| [Government Analysis Function, charts](https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-charts/) e [colours](https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-colours-in-charts/) | Regras de formatação e de acessibilidade com valores numéricos |
| [BBC cookbook](https://bbc.github.io/rcookbook/) e [bbplot](https://github.com/bbc/bbplot) | Exemplo de função de tema e de exportação padronizada. Parado desde 2021 |
| [FT Visual Vocabulary](https://github.com/Financial-Times/chart-doctor) | Escolha do tipo de gráfico pela relação a mostrar |
| [From Data to Viz](https://www.data-to-viz.com/) e a página de [caveats](https://www.data-to-viz.com/caveats.html) | Árvore de decisão e catálogo de erros, com código R |
| Oficina de Cédric Scherer, [ggplot2-graphic-design](https://github.com/rstudio-conf-2022/ggplot2-graphic-design) | Acabamento em ggplot2: tipografia, cor, anotação |
| Cleveland e McGill (1984); Correll, Bertini e Franconeri (2020); Franconeri et al. (2021) | Base empírica |
| Crameri, Shephard e Heron (2020) e Wong (2011) | Base para as regras de cor |
| ColorBrewer, Okabe-Ito, `colorspace`, `scico`, `cols4all` | Paletas |
| [Evergreen e Emery, Data Visualization Checklist](https://stephanieevergreen.com/data-visualization-checklist/) | Modelo de lista de revisão |
| [PolicyViz, Style Guide Collection](https://policyviz.com/the-style-guide-collection/) | Catálogo para achar outros guias |

## Regras em que as fontes convergem

Escolha do gráfico

1. O tipo de gráfico sai da relação a mostrar: mudança no tempo, comparação,
   composição, distribuição, correlação, ordenação, fluxo, padrão espacial (FT
   Visual Vocabulary; From Data to Viz).
2. Variável quantitativa principal em posição ou comprimento; ângulo e área
   são lidos com menos precisão (Cleveland e McGill, 1984).
3. Um gráfico, uma mensagem (Government Analysis Function).
4. Tabela quando o leitor precisa do valor exato (Few, 2012; UNECE).

Eixos e escalas

5. Barras e colunas com eixo de valor a partir de zero (Urban Institute;
   Correll, Bertini e Franconeri, 2020).
6. Escala logarítmica para razões e variações relativas, indicada no eixo
   (From Data to Viz).
7. Eixos formatados em código, com `scales::label_*()` (ggplot2-book).
8. Categorias ordenadas pelo valor, salvo quando têm ordem própria (From Data
   to Viz).

Texto

9. Título que enuncia o achado, com subtítulo descritivo (Schwabish, 2021;
   Knaflic, 2015).
10. Rótulo direto no lugar de legenda; se houver legenda, na ordem das séries
    (Government Analysis Function; Urban Institute).
11. Fonte e notas abaixo do gráfico, no menor corpo (Urban Institute).
12. Uma família sem serifa, com hierarquia por tamanho e peso (Urban
    Institute; BBC).
13. Anotação no próprio gráfico para o que importa, em pouca quantidade
    (Schwabish, 2021).

Limpeza

14. Sem fundo sombreado, bordas, caixa em volta da legenda, textura, sombra ou
    3D (Government Analysis Function; Tufte, 1983).
15. No máximo dez linhas de grade, em cinza claro (Government Analysis
    Function).
16. Acima de cinco a sete séries, facetas ou destaque de uma série com as
    demais em cinza (From Data to Viz; Schwabish, 2021).

Cor e acessibilidade

17. Sequencial para dado ordenado, divergente para dado com ponto central,
    qualitativa para categorias (ColorBrewer; colorspace).
18. Sem arco-íris em variável contínua (Crameri, Shephard e Heron, 2020).
19. Quatro categorias de cor por gráfico como alvo (Government Analysis
    Function).
20. Cor nunca como único código (Government Analysis Function; Wilke, 2019).
21. Paleta qualitativa segura a daltônicos (Wong, 2011) e figura legível em
    tons de cinza (Munzner, 2014).
22. Contraste de 3 para 1 entre elementos gráficos vizinhos e de 4,5 para 1
    em texto (WCAG 2.2, critério 1.4.11).
23. Mesma cor para a mesma categoria em todo o documento (From Data to Viz;
    Urban Institute).

Distribuição e incerteza

24. Mostrar os pontos ou a forma da distribuição junto do resumo (Wilke, 2019;
    ggdist).

Mapas

25. Coroplético só com variável normalizada; contagem em símbolo proporcional
    (Geocomputation with R; From Data to Viz).
26. Método de classes declarado na legenda ou na nota (classInt).

Produção

27. Largura da figura fixada por meio de publicação antes de desenhar (Urban
    Institute: 6,25 polegadas no PDF, 760 px na web).
28. Tema do projeto definido uma vez; nada de edição manual depois da
    exportação (ggplot2-book; oficina de Cédric Scherer).
29. Vetor quando o destino aceita (Rougier, Droettboom e Bourne, 2014,
    sobre adaptar a figura ao meio).

## Onde as fontes divergem

| Tema | Posições | Implicação para o guia |
|---|---|---|
| Título dentro ou fora da imagem | Urban põe no documento quando o destino é PDF; BBC põe na imagem | Decidir por destino: no Word e no PDF, fora |
| Tamanho de fonte | BBC 28/22/18 px; Urban 12/10/8,5 pt no PDF; GAF não fixa mínimo | Os valores só valem junto da largura da figura |
| Posição da legenda | Topo (Urban, BBC) ou nenhuma (GAF) | Rótulo direto como padrão; topo quando não couber |
| Número de cores categóricas | Quatro (GAF), cinco a seis (Atlassian), oito (Urban, Okabe-Ito) | Quatro como alvo, oito como teto |
| Eixo truncado em linhas | Aceito quando o interesse é a variação; o efeito perceptual existe (Correll, Bertini e Franconeri, 2020) | Permitir em linhas, com o intervalo visível no eixo |
| Eixo duplo | Schwabish, Fung e From Data to Viz recomendam evitar | Evitar; dois painéis alinhados |
| Pizza | Rejeitada por Cleveland e McGill, Tufte e Few; reavaliada por Hill (2024), não lido | Barras como padrão |
| Barras ou pontos | Ambos aceitos; pontos dispensam o zero | Dot plot quando o zero achata a diferença |

## Lacunas

- **Nenhum guia de estilo de gráficos em português** foi localizado (IBGE,
  Ipea, Banco Central, FGV, Nexo, Folha, Volt Data Lab). É ausência de
  resultado na busca. Ficam sem cobertura a vírgula decimal, a forma da nota
  de fonte e a numeração de figuras nas normas brasileiras.
- **Projeção para mapas do Brasil**: a indicação levantada (policônica,
  EPSG:5880) não foi conferida em documento do IBGE e conflita com o critério
  de área igual.
- Não existe linter ou avaliador de gráficos aberto e maduro, em R ou Python.
- Tabelas, exportação (`ggsave`, `ragg`, fontes) e espaçamento interno quase
  não aparecem nas fontes.
- Franconeri et al. (2021) e Hill (2024) foram usados só pelo resumo.
- O número de 83,5% atribuído a Correll, Bertini e Franconeri (2020) não foi
  conferido e não deve ser citado.
- Skills e prompts de dataviz para agentes de código não foram levantados.
