# Tema ggplot2 e funções de apoio da skill graficos. O par em Python é
# tema_dv.py: cores, corpos e larguras mudam nos dois arquivos juntos.
# Os números entre colchetes remetem às regras de regras.md.
#
# Uso, com o arquivo copiado para o projeto:
#   source("R/tema_dv.R")
#   usar_tema_dv()
#   # Título: o achado em uma frase
#   # Subtítulo: o que é medido, e a unidade
#   # Nota: ...
#   # Fonte: ...
#   p <- ggplot(...) + ... + labs(x = ..., y = ...)
#   salvar_figura(p, "figuras/nome.png")
#
# Título, subtítulo, nota e fonte não entram na imagem [9, 11]: ficam em
# comentário acima do gráfico e são escritos no documento de destino. Por
# isso a unidade vai no título do eixo ou da legenda.

suppressPackageStartupMessages({
  library(ggplot2)
  library(scales)
})

# Tintas e superfícies ---------------------------------------------------------

dv_tinta <- c(
  texto      = "#1A1A1A",
  secundario = "#4D4D4D",
  grade      = "#D9D9D9",
  contexto   = "#B3B3B3",
  fundo      = "#FFFFFF"
)

# Paletas ----------------------------------------------------------------------

# Qualitativa, em ordem fixa [17, 21]. Parte da Okabe-Ito; amarelo, laranja
# claro, azul-céu e rosa saíram ou foram escurecidos porque ficam abaixo de
# 3:1 de contraste sobre branco [22]. As seis passaram juntas, nesta ordem,
# num validador de contraste e de separação sob simulação de daltonismo; não
# troque uma cor sem revalidar as duas coisas.
dv_cores <- c(
  azul    = "#0072B2",
  laranja = "#D55E00",
  verde   = "#009E73",
  roxo    = "#AA4499",
  ocre    = "#B8860B",
  ceu     = "#3C93C2"
)

# Quatro categorias é o alvo; seis é o teto [19]. Acima disso a função para:
# agrupe em "Outros", use facetas ou destaque uma categoria [16].
pal_dv <- function(n) {
  if (n > length(dv_cores)) {
    stop(
      "A paleta qualitativa tem ", length(dv_cores), " cores e o gráfico pede ",
      n, ". Agrupe categorias, use facetas ou dv_destaque().",
      call. = FALSE
    )
  }
  if (n > 4) {
    warning("Mais de quatro categorias de cor; confira se rótulo direto ou ",
            "facetas resolvem melhor.", call. = FALSE)
  }
  unname(dv_cores[seq_len(n)])
}

scale_colour_dv <- function(...) discrete_scale("colour", palette = pal_dv, ...)
scale_color_dv  <- scale_colour_dv
scale_fill_dv   <- function(...) discrete_scale("fill", palette = pal_dv, ...)

# Cor fixa por categoria ao longo do relatório [23]: defina o vetor uma vez e
# passe a scale_*_manual(values = ...) em todas as figuras.
dv_cores_por <- function(categorias) {
  stats::setNames(pal_dv(length(categorias)), categorias)
}

# Uma cor para o foco e cinza para o contexto [16].
dv_destaque <- c(foco = unname(dv_cores["azul"]), contexto = unname(dv_tinta["contexto"]))

# Sequencial de um matiz, do claro ao escuro [17, 18]. Os dois passos mais
# claros são descartados para a primeira classe não sumir no fundo branco.
dv_seq <- function(n) {
  colorspace::sequential_hcl(n + 2, palette = "Blues 3", rev = TRUE)[-(1:2)]
}

# Divergente com centro neutro; o centro deve cair no valor de referência [17].
dv_div <- function(n) {
  colorspace::diverging_hcl(n, palette = "Blue-Red 3")
}

scale_fill_dv_seq <- function(...) {
  scale_fill_gradientn(colours = dv_seq(7), ...)
}
scale_fill_dv_div <- function(..., midpoint = 0) {
  scale_fill_gradient2(
    low = dv_div(3)[1], mid = "#E2E2E2", high = dv_div(3)[3],
    midpoint = midpoint, ...
  )
}

# Rótulos numéricos em português [7] -------------------------------------------

rotulo_num <- function(accuracy = 1, ...) {
  label_number(accuracy = accuracy, big.mark = ".", decimal.mark = ",", ...)
}
rotulo_pct <- function(accuracy = 1, ...) {
  label_percent(accuracy = accuracy, big.mark = ".", decimal.mark = ",", ...)
}
rotulo_moeda <- function(accuracy = 1, ...) {
  label_number(accuracy = accuracy, prefix = "R$ ", big.mark = ".",
               decimal.mark = ",", ...)
}

# Tipografia -------------------------------------------------------------------

# Primeira família sem serifa disponível [12].
dv_familia <- function(preferidas = c("Lato", "Source Sans 3", "Noto Sans",
                                      "Liberation Sans")) {
  if (!requireNamespace("systemfonts", quietly = TRUE)) return("sans")
  instaladas <- unique(systemfonts::system_fonts()$family)
  achada <- intersect(preferidas, instaladas)
  if (length(achada)) achada[1] else "sans"
}

# Tema -------------------------------------------------------------------------

# Corpos pensados para figura de 16 cm de largura em página A4 [27]:
# eixos e legenda 8,5 pt, fonte e notas 8 pt, título 12 pt, subtítulo 10 pt.
# `grade` diz em que eixo ficam as linhas de grade: "y" para colunas e linhas,
# "x" para barras horizontais, "xy" para dispersão, "nenhuma" para mapas.
tema_dv <- function(base_size = 8.5, familia = dv_familia(),
                    grade = c("y", "x", "xy", "nenhuma")) {
  grade <- match.arg(grade)
  linha_grade <- element_line(colour = dv_tinta[["grade"]], linewidth = 0.25)

  tema <- theme_minimal(base_size = base_size, base_family = familia) +
    theme(
      text = element_text(colour = dv_tinta[["texto"]]),
      plot.title = element_text(size = 12, face = "bold",
                                margin = margin(b = 3)),
      plot.subtitle = element_text(size = 10, colour = dv_tinta[["secundario"]],
                                   margin = margin(b = 8)),
      plot.caption = element_text(size = 8, colour = dv_tinta[["secundario"]],
                                  hjust = 0, margin = margin(t = 8)),
      plot.title.position = "plot",
      plot.caption.position = "plot",
      plot.background = element_rect(fill = dv_tinta[["fundo"]], colour = NA),
      plot.margin = margin(6, 10, 6, 6),

      axis.title = element_text(size = base_size, colour = dv_tinta[["secundario"]]),
      axis.text = element_text(size = base_size, colour = dv_tinta[["secundario"]]),
      axis.ticks = element_blank(),
      axis.line = element_blank(),

      panel.grid.minor = element_blank(),
      panel.grid.major = linha_grade,
      panel.spacing = grid::unit(12, "pt"),

      legend.position = "top",
      legend.justification = "left",
      legend.title = element_blank(),
      legend.text = element_text(size = base_size),
      legend.key.size = grid::unit(9, "pt"),
      legend.margin = margin(0, 0, 0, 0),
      legend.box.margin = margin(0, 0, -4, 0),
      legend.background = element_blank(),

      strip.text = element_text(size = base_size, face = "bold", hjust = 0,
                                colour = dv_tinta[["texto"]]),
      strip.background = element_blank()
    )

  tema + switch(
    grade,
    y  = theme(panel.grid.major.x = element_blank()),
    x  = theme(panel.grid.major.y = element_blank()),
    xy = theme(),
    nenhuma = theme(panel.grid.major = element_blank(),
                    axis.text = element_blank(), axis.title = element_blank())
  )
}

# Define o tema e os padrões de traço, ponto e texto para a sessão [28].
usar_tema_dv <- function(...) {
  theme_set(tema_dv(...))
  familia <- theme_get()$text$family
  texto <- list(family = familia, size = 8.5 / .pt, colour = dv_tinta[["texto"]])

  update_geom_defaults("line",  list(linewidth = 0.7, colour = dv_cores[["azul"]]))
  update_geom_defaults("point", list(size = 1.8, colour = dv_cores[["azul"]]))
  update_geom_defaults("col",   list(fill = dv_cores[["azul"]]))
  update_geom_defaults("bar",   list(fill = dv_cores[["azul"]]))
  update_geom_defaults("text",  texto)
  update_geom_defaults("label", texto)
  if (requireNamespace("ggrepel", quietly = TRUE)) {
    update_geom_defaults(ggrepel::GeomTextRepel, texto)
    update_geom_defaults(ggrepel::GeomLabelRepel, texto)
  }
  invisible(theme_get())
}

# Eixo de valor de barras: começa em zero, sem folga na base [5].
escala_barras <- function(eixo = c("y", "x"), ...) {
  eixo <- match.arg(eixo)
  escala <- if (eixo == "y") scale_y_continuous else scale_x_continuous
  escala(expand = expansion(mult = c(0, 0.06)), ...)
}

# Exportação -------------------------------------------------------------------

# Largura padrão de 16 cm: a mancha de texto de uma página A4 com margens de
# 3 cm e 2 cm [27]. Título, subtítulo e legenda inferior são retirados da
# imagem mesmo que estejam em labs(); texto_na_imagem = TRUE os mantém, para
# figura que circula sozinha. PDF e SVG saem em vetor [29]; PNG, a 300 dpi.
salvar_figura <- function(grafico, arquivo, largura = 16, altura = 8,
                          texto_na_imagem = FALSE, dpi = 300) {
  if (!texto_na_imagem) {
    grafico <- grafico + labs(title = NULL, subtitle = NULL, caption = NULL)
  }
  dir.create(dirname(arquivo), showWarnings = FALSE, recursive = TRUE)

  dispositivo <- switch(
    tolower(tools::file_ext(arquivo)),
    png = ragg::agg_png,
    pdf = grDevices::cairo_pdf,
    svg = svglite::svglite,
    stop("Extensão não prevista: use png, pdf ou svg.", call. = FALSE)
  )
  ggsave(arquivo, grafico, device = dispositivo, width = largura,
         height = altura, units = "cm", dpi = dpi)
  invisible(arquivo)
}
