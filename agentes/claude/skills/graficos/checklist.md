# Checklist de revisão de gráficos

Derivada das 29 regras de `regras.md`; o número entre colchetes remete à
regra. As colunas "R" e "Python" dizem o que `tema_dv.R` e `tema_dv.py` já
resolvem: **sim** quer dizer que basta usar o tema e as funções dele;
**parte**, que há função de apoio mas a decisão é de quem faz o gráfico;
**não**, que só a revisão pega.

Título, subtítulo, nota e fonte **não entram na imagem**. Ficam em comentário
acima do gráfico no script e são escritos no documento de destino.

## Antes de desenhar

| # | Item | R | Python |
|---|---|---|---|
| 1 | A mensagem do gráfico cabe em uma frase, e é uma só [3] | não | não |
| 2 | O tipo de gráfico sai da relação a mostrar: tempo, comparação, composição, distribuição, correlação, espaço [1] | não | não |
| 3 | A variável principal está em posição ou comprimento, não em ângulo ou área [2] | não | não |
| 4 | Se o leitor precisa do valor exato, é tabela [4] | não | não |
| 5 | A largura da figura foi fixada pelo destino: 16 cm em página A4 [27] | sim, `salvar_figura()` | sim, `salvar_figura()` |

## Eixos e escalas

| # | Item | R | Python |
|---|---|---|---|
| 6 | Barras e colunas começam em zero [5] | parte, `escala_barras()` | parte, `escala_barras(ax)` depois de desenhar |
| 7 | Em linha com eixo truncado, o intervalo está visível no eixo [5] | não | não |
| 8 | Escala logarítmica está indicada no título do eixo [6] | não | não |
| 9 | Números com ponto de milhar e vírgula decimal, formatados em código [7] | parte, `rotulo_num()`, `rotulo_pct()`, `rotulo_moeda()` | parte, as mesmas funções em `set_major_formatter()`; sem elas o eixo sai com ponto decimal |
| 10 | Categorias ordenadas pelo valor, salvo ordem própria (tempo, faixas) [8] | não, `forcats::fct_reorder()` | não, ordene os dados antes de desenhar |
| 11 | Um só eixo de valor; duas medidas vão em dois painéis | não | não |

## Texto

| # | Item | R | Python |
|---|---|---|---|
| 12 | Título e subtítulo estão em comentário acima do gráfico (`# Título:`, `# Subtítulo:`), fora da imagem; o título enuncia o achado [9] | sim, `salvar_figura()` retira da imagem | parte, `salvar_figura()` retira o título da figura e o do painel único; texto de `fig.text()` fica |
| 13 | Séries com rótulo direto; legenda só quando não couber, no topo e na ordem das séries [10] | parte, legenda no topo | parte, `legenda_dv(ax)` |
| 14 | Nota e fonte estão em comentário (`# Nota:`, `# Fonte:`), fora da imagem; todo gráfico tem fonte [11] | sim, `salvar_figura()` retira da imagem | não |
| 15 | Uma família sem serifa; hierarquia por tamanho e peso [12] | sim | sim |
| 16 | Anotação só no que importa; nunca um número em cada ponto de uma linha [13] | não | não |
| 17 | Texto em preto ou cinza, não na cor da série | sim nos padrões | sim nos padrões |
| 18 | Sem título na imagem, a unidade está no título do eixo ou da legenda | não | não |

## Limpeza

| # | Item | R | Python |
|---|---|---|---|
| 19 | Sem fundo, borda, caixa de legenda, sombra, textura ou 3D [14] | sim | sim |
| 20 | No máximo dez linhas de grade, cinza claro, só no eixo de valor [15] | parte, `tema_dv(grade = )`; conferir a contagem | parte, `usar_tema_dv(grade=)` e `grade_dv(ax, )`; conferir a contagem |
| 21 | Mais de seis séries: painéis, ou uma em destaque e as demais em cinza [16] | parte, `dv_destaque`; a paleta para com erro na sétima cor | parte, `DV_DESTAQUE`; `pal_dv()` para com erro na sétima cor |

## Cor e acessibilidade

| # | Item | R | Python |
|---|---|---|---|
| 22 | Paleta pelo tipo de dado: qualitativa, sequencial ou divergente [17] | parte, `scale_*_dv()`, `dv_seq()`, `dv_div()` | parte, `pal_dv()`, `dv_seq()`, `dv_div()`, `mapa_seq()`, `mapa_div()` |
| 23 | Sem arco-íris em variável contínua [18] | sim | sim |
| 24 | Até quatro cores de categoria; seis é o teto [19] | sim, aviso na quinta e erro na sétima | parte, só quando a cor vem de `pal_dv()` ou `dv_cores_por()` |
| 25 | Em escala divergente, o centro neutro cai no valor de referência [17] | parte, `scale_fill_dv_div(midpoint = )` | parte, `mapa_div()` com `TwoSlopeNorm(vcenter=)` |
| 26 | A cor nunca é o único código: há rótulo, posição ou forma junto [20] | não | não |
| 27 | Paleta segura a daltônicos [21] | sim, validada | sim, as mesmas cores |
| 28 | A figura se lê em tons de cinza [21] | **não**: as cores da paleta têm luminosidade parecida. Conferir com `magick figura.png -colorspace Gray` e depender do item 26 | **não**, idem |
| 29 | Contraste de 3:1 entre marcas e fundo, 4,5:1 em texto [22] | sim na paleta qualitativa; a classe clara do mapa não atinge | idem |
| 30 | Mesma cor para a mesma categoria em todo o documento [23] | parte, `dv_cores_por()` uma vez por projeto | parte, `dv_cores_por()` uma vez por projeto |
| 31 | Comércio e serviços aparecem agregados | não | não |

## Distribuição e incerteza

| # | Item | R | Python |
|---|---|---|---|
| 32 | O resumo (média, mediana, caixa) vem com os pontos ou a forma da distribuição [24] | não | não |
| 33 | A nota explica o que a caixa, a haste ou a faixa representam | não | não |

## Mapas

| # | Item | R | Python |
|---|---|---|---|
| 34 | Coroplético só com taxa, proporção ou valor por habitante; contagem vai em símbolo proporcional [25] | não | não |
| 35 | Método e número de classes declarados na nota [26] | não, `classInt::classIntervals()` | não |
| 36 | Projeção de área igual em mapa nacional | não; os parâmetros de Albers em `exemplos.R` não foram conferidos com o IBGE | não; sem exemplo |
| 37 | A classe mais clara se distingue do fundo (contorno do país) | não, ver exemplo 8 | não; sem exemplo |

## Produção

| # | Item | R | Python |
|---|---|---|---|
| 38 | Tema definido uma vez no script; nenhum ajuste manual depois da exportação [28] | sim, `usar_tema_dv()` | sim, `usar_tema_dv()` |
| 39 | Vetor (PDF, SVG) quando o destino aceita; PNG a 300 dpi caso contrário [29] | sim, pela extensão do arquivo | sim, pela extensão do arquivo |
| 40 | A figura foi aberta no tamanho final e conferida: rótulos sem sobreposição, nada cortado | não | não |
| 41 | Todo número citado no título ou na anotação confere com o dado | não | não |

## Divergências em relação às regras

- **Teto de cores.** As regras põem oito como teto (Okabe-Ito). A paleta do
  tema tem seis: o amarelo, o laranja claro, o azul-céu e o rosa da Okabe-Ito
  ficam abaixo de 3:1 de contraste sobre branco, e só seis cores passaram
  juntas no validador de contraste e de separação sob simulação de
  daltonismo.
- **Tons de cinza.** A exigência de contraste estreita a faixa de
  luminosidade da paleta, e as cores se confundem em cinza. A regra 21 fica
  atendida pela metade; rótulo direto resolve.
- **Título e fonte fora da imagem.** As fontes das regras põem fonte e notas
  abaixo do gráfico, e parte delas põe o título na imagem. Aqui os quatro
  textos ficam no documento, e o script os guarda em comentário.
- **Fonte.** O Urban Institute usa Lato. O tema usa a primeira instalada
  entre Lato, Source Sans 3, Noto Sans e Liberation Sans.
