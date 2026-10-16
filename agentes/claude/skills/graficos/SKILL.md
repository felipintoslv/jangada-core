---
name: graficos
description: >
  Use ao criar gráfico ou figura para relatório, artigo ou apresentação em
  projeto de ciência de dados, em R (ggplot2) ou Python (matplotlib), e ao
  revisar gráfico existente. Traz a escolha do tipo de gráfico pela relação
  a mostrar, o tema padrão (paleta de seis cores, corpos, grade, números em
  português, exportação com 16 cm), o cabeçalho de título, subtítulo, nota e
  fonte em comentário, fora da imagem, e a checklist de 41 itens antes de
  entregar. Não use para tabela, diagrama de arquitetura ou painel
  interativo.
---

# Protocolo: gráficos

Para todo gráfico estático que vai para um documento. Três passos: escolher o
tipo pela relação a mostrar, aplicar o tema e conferir contra a checklist.

| Arquivo desta pasta | Conteúdo |
|---|---|
| `tema_dv.R` | Tema ggplot2, paletas, rótulos numéricos e `salvar_figura()` |
| `tema_dv.py` | O mesmo em matplotlib |
| `exemplos.R` | Oito gráficos de referência, um por relação |
| `exemplos.py` | Cinco deles em Python (1, 2, 3, 6 e 7) |
| `checklist.md` | 41 itens de revisão, com o que o tema já resolve em cada linguagem |
| `regras.md` | As 29 regras de origem, com fontes, divergências e lacunas |

## 1. Antes de começar

1. **Copie o tema para o projeto**, uma vez: `tema_dv.R` em `R/` ou
   `tema_dv.py` junto dos scripts, e inclua no controle de versão. O script
   do gráfico carrega a cópia do projeto, nunca o caminho desta pasta: o
   projeto precisa rodar em outra máquina e dentro do isolamento.
2. **Não edite a cópia.** Cor por categoria, tamanho de figura e ajustes do
   projeto ficam no script do projeto. Se a cópia já existe e difere da
   desta pasta, avise o usuário antes de trocar.
3. **Dependências.** R: `ggplot2`, `scales`, `colorspace`, `ragg` (PNG),
   `svglite` (SVG); `systemfonts` e `ggrepel` são opcionais. Python:
   `matplotlib`. `exemplos.R` carrega também `dplyr`, `tidyr`, `forcats`
   e `ggrepel`, e o mapa pede `sf` e `classInt`; `exemplos.py` pede
   `numpy`. Se faltar pacote, pergunte antes de instalar.
4. **Uma frase.** Escreva a mensagem do gráfico em uma frase antes de
   desenhar. Se não couber em uma, são dois gráficos. Se o leitor precisa do
   valor exato, é tabela.

## 2. Decisões que não mudam

- **Título, subtítulo, nota e fonte ficam fora da imagem.** Vão em
  comentário acima do gráfico no script, neste formato, e são escritos no
  documento de destino. Vale para R e para Python.

  ```
  # Título: o achado em uma frase
  # Subtítulo: o que é medido, e a unidade
  # Nota: o que o leitor precisa saber para ler a figura
  # Fonte: ...
  ```

  Título e fonte são obrigatórios; subtítulo e nota, quando houver o que
  dizer. Como o subtítulo não está na imagem, **a unidade vai no título do
  eixo ou da legenda**.
- **Comércio e serviços agregados.** Em análise setorial aparecem sempre
  como "Comércio e serviços", nunca separados. Se o dado vem separado, some
  antes de desenhar.
- **Paleta qualitativa de seis cores em ordem fixa**, definida no tema.
  Quatro é o alvo. A sétima categoria é erro: agrupe em "Outros", use
  pequenos múltiplos ou destaque uma série com as demais em cinza. Não
  troque nem acrescente cor: a Okabe-Ito original foi descartada porque
  quatro das oito cores ficam abaixo de 3:1 de contraste sobre branco, e
  qualquer troca exige revalidar contraste e separação sob simulação de
  daltonismo.
- **Rótulo direto no lugar de legenda** sempre que couber. Texto em preto ou
  cinza, nunca na cor da série.
- **Figura com 16 cm de largura.** PNG a 300 dpi, ou vetor (PDF, SVG) quando
  o destino aceita. A altura padrão é 8 cm.
- **Números com ponto de milhar e vírgula decimal**, formatados em código.
- **Textos em português**, sem travessões e com pouca adjetivação.
- **Mesma cor para a mesma categoria** em todo o documento: defina
  `dv_cores_por()` uma vez por projeto.

## 3. Escolha do tipo

O tipo sai da relação a mostrar, não do formato do dado. O número remete ao
exemplo em `exemplos.R`.

| Relação | Gráfico | Exemplo |
|---|---|---|
| Mudança no tempo | Linha com rótulo direto na ponta | 1 |
| Comparação entre categorias | Barras horizontais ordenadas pelo valor, uma em destaque | 2 |
| Composição | Colunas empilhadas a 100% | 3 |
| Relação entre duas variáveis | Dispersão com rótulo só nos pontos que importam | 4 |
| Distribuição | Caixa com os pontos por cima | 5 |
| Mais de seis séries | Pequenos múltiplos, com as demais séries em cinza | 6 |
| Dois momentos por categoria | Pontos ligados | 7 |
| Padrão espacial de taxa | Mapa coroplético em classes | 8 |

- Barras e colunas começam em zero. Quando o zero achata a diferença, use
  pontos no lugar de barras.
- Linha pode ter eixo truncado, com o intervalo visível no eixo.
- Duas medidas vão em dois painéis alinhados, não em eixo duplo.
- Coroplético só com taxa, proporção ou valor por habitante. Contagem vai em
  símbolo proporcional.
- Sem pizza, 3D, arco-íris em variável contínua e número em cada ponto de
  uma linha.

## 4. Em R

```r
source("R/tema_dv.R")
usar_tema_dv()
cores_setor <- dv_cores_por(c("Agropecuária", "Indústria", "Comércio e serviços"))

# Título: Comércio e serviços cresceu mais que os outros setores
# Subtítulo: Emprego formal por setor, índice (2010 = 100)
# Fonte: ...
p <- ggplot(dados, aes(ano, indice, colour = setor)) +
  geom_line() +
  geom_text(data = ponta, aes(label = setor), colour = dv_tinta[["texto"]], hjust = 0) +
  scale_colour_manual(values = cores_setor, guide = "none") +
  scale_y_continuous(labels = rotulo_num()) +
  labs(x = NULL, y = "Emprego formal (2010 = 100)")

salvar_figura(p, "figuras/emprego.png")
```

| Função | Para quê |
|---|---|
| `usar_tema_dv()`, `tema_dv(grade = )` | Tema da sessão; grade em `"y"`, `"x"`, `"xy"` ou `"nenhuma"` |
| `scale_colour_dv()`, `scale_fill_dv()`, `dv_cores_por()` | Paleta qualitativa; cor fixa por categoria |
| `dv_destaque` | Uma série em foco, as demais em cinza |
| `dv_seq(n)`, `dv_div(n)`, `scale_fill_dv_seq()`, `scale_fill_dv_div(midpoint = )` | Sequencial e divergente |
| `rotulo_num()`, `rotulo_pct()`, `rotulo_moeda()` | Números em português, em `labels =` ou num valor |
| `escala_barras("y")` | Eixo de valor de barras a partir de zero |
| `salvar_figura(p, arquivo, largura = 16, altura = 8)` | Exporta pela extensão e retira título, subtítulo e texto de rodapé |

## 5. Em Python

```python
import matplotlib.pyplot as plt
from tema_dv import dv_cores_por, rotulo_num, salvar_figura, usar_tema_dv

usar_tema_dv()
cores_setor = dv_cores_por(["Agropecuária", "Indústria", "Comércio e serviços"])

# Título: Comércio e serviços cresceu mais que os outros setores
# Subtítulo: Emprego formal por setor, índice (2010 = 100)
# Fonte: ...
fig, ax = plt.subplots()
for setor, serie in dados.items():
    ax.plot(anos, serie, color=cores_setor[setor])
    ax.annotate(setor, (anos[-1], serie[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", annotation_clip=False)
ax.yaxis.set_major_formatter(rotulo_num())
ax.set_ylabel("Emprego formal (2010 = 100)")

salvar_figura(fig, "figuras/emprego.png")
```

Os nomes são os de R, com estas diferenças:

- **Cor explícita.** A cor padrão de traço, ponto e barra é o azul. Com mais
  de uma série, passe a cor de `pal_dv(n)` ou `dv_cores_por()`; são elas que
  avisam na quinta cor e param na sétima.
- **Eixo numérico sempre com formatador**: `rotulo_num(casas)`,
  `rotulo_pct(casas)` ou `rotulo_moeda(casas)` em `set_major_formatter()`.
  Sem ele o matplotlib escreve ponto decimal. `rotulo_pct()` espera
  proporção entre 0 e 1.
- **Grade por painel**: `grade_dv(ax, "x")`. **Legenda**, quando o rótulo
  direto não couber: `legenda_dv(ax)`. **Barras**: `escala_barras(ax, "y")`
  depois de desenhar.
- **Sequencial e divergente**: `dv_seq(n)` e `dv_div(n)` para 3 a 7 classes;
  `mapa_seq()` e `mapa_div()` para escala contínua.
- **Margem.** O tema usa o layout restrito do matplotlib, que abre espaço
  para o rótulo direto. Não use `bbox_inches="tight"` nem `tight_layout()`:
  mudam a largura de 16 cm.
- **Título.** `salvar_figura()` retira `fig.suptitle()` e o título do eixo
  quando há um painel só. Com mais painéis, `ax.set_title()` é o nome do
  painel e fica. Não escreva nota nem fonte com `fig.text()`.

## 6. Revisão de gráfico existente

1. Leia o script e abra a imagem no tamanho final. Não revise só pelo código.
2. Diga em uma frase o que o gráfico mostra. Se não der, o primeiro achado é
   esse.
3. Passe a `checklist.md` inteira e relate cada item que falha com o número
   dele, o que está errado e a correção. Não relate o que passa.
4. Ordene os achados: primeiro o que distorce a leitura (eixo de barras sem
   zero, tipo errado, coroplético de contagem, número que não confere com o
   dado), depois o padrão da casa (texto na imagem, cores fora da paleta,
   comércio e serviços separados), por último o acabamento.
5. Se o pedido incluir a correção, aplique o tema e gere a figura de novo;
   não retoque a imagem.

## 7. Limites conhecidos

Registre o que se aplicar na entrega; não esconda.

- **Tons de cinza.** As seis cores têm luminosidade parecida e se confundem
  em cinza. A identidade das séries depende do rótulo direto. Confira com
  `magick figura.png -colorspace Gray`.
- **Classe clara do mapa.** A classe mais clara da sequencial não atinge 3:1
  de contraste com o fundo. O exemplo 8 contorna com um contorno do país por
  baixo dos estados.
- **Projeção.** A cônica equivalente de Albers do exemplo 8 usa parâmetros
  não conferidos com o IBGE. Diga isso na nota de um mapa que a use.
- **Malha de UF.** `geobr::read_state()` falhou no download quando o exemplo
  foi escrito. `exemplos.R` lê a malha de um arquivo local, passado como
  segundo argumento, e pula o mapa se ele faltar.
- **Fonte.** O tema usa a primeira instalada entre Lato, Source Sans 3, Noto
  Sans e Liberation Sans. A referência visual foi feita com Noto Sans.
- **Pacotes não usados.** `ggtext` e `ggdist` não entram no tema. Não
  instale pacote sem perguntar ao usuário.
- **Python.** Não há exemplo de dispersão, distribuição nem mapa, e o tema
  não afasta rótulos sobrepostos como o `ggrepel`. As espessuras de traço e
  os tamanhos de ponto foram convertidos das medidas do ggplot2 e conferidos
  a olho contra as figuras em R; o PNG sai com 1.889 pixels de largura, um a
  menos que o de R.
- **Sem conferência automática.** Nenhuma ferramenta confere a checklist;
  quem confere é a revisão.

## 8. Antes de entregar

- [ ] A mensagem cabe em uma frase e o tipo sai da relação (seção 3).
- [ ] Cabeçalho `# Título:` e `# Fonte:` acima do gráfico; nada disso na
      imagem; unidade no eixo ou na legenda.
- [ ] Tema carregado da cópia do projeto; cores da paleta, no máximo seis.
- [ ] Comércio e serviços agregados.
- [ ] Rótulo direto ou legenda no topo; texto em preto ou cinza.
- [ ] Números com ponto de milhar e vírgula decimal em eixos e rótulos.
- [ ] Exportado por `salvar_figura()`, com 16 cm de largura.
- [ ] Imagem aberta no tamanho final: nada cortado, rótulos sem sobreposição,
      no máximo dez linhas de grade.
- [ ] Todo número do título confere com o dado.
- [ ] `checklist.md` conferida; limites da seção 7 que se aplicam relatados.
