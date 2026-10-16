# Exemplos dos tipos de gráfico mais usados, com o tema de tema_dv.R.
# Todos os dados são simulados; os números não descrevem nenhuma UF ou setor.
# Título, subtítulo, nota e fonte não entram na imagem: ficam em comentário
# acima de cada gráfico, para serem escritos no documento.
#
# Uso: Rscript exemplos.R [PASTA_DE_SAIDA] [MALHA_DE_UF]
#   PASTA_DE_SAIDA  onde gravar as figuras (padrão: figuras)
#   MALHA_DE_UF     arquivo que o sf leia, com um polígono por UF (padrão:
#                   dados/uf_2020.gpkg). Sem ele, o mapa não é gerado.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(forcats)
  library(ggrepel)
  library(sf)
})
argumentos <- commandArgs(trailingOnly = TRUE)
pasta_saida <- if (length(argumentos) >= 1) argumentos[1] else "figuras"
arquivo_malha <- if (length(argumentos) >= 2) argumentos[2] else "dados/uf_2020.gpkg"
pasta_script <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(pasta_script, "tema_dv.R"))
usar_tema_dv()
set.seed(20261003)

setores <- c("Agropecuária", "Indústria", "Comércio e serviços")
cores_setor <- dv_cores_por(setores)
ufs_ne <- c("Maranhão", "Piauí", "Ceará", "Rio Grande do Norte", "Paraíba",
            "Pernambuco", "Alagoas", "Sergipe", "Bahia")

# 1. Linha: mudança no tempo ---------------------------------------------------

serie <- expand_grid(setor = setores, ano = 2010:2024) |>
  mutate(
    inclinacao = c("Agropecuária" = 1.2, "Indústria" = -0.3,
                   "Comércio e serviços" = 2.2)[setor],
    indice = 100 + inclinacao * (ano - 2010) +
      if_else(ano == 2010, 0, rnorm(n(), 0, 1.1)),
    setor = factor(setor, levels = setores)
  )
ponta <- filter(serie, ano == max(ano))

# Título: Comércio e serviços cresceu mais que os outros setores
# Subtítulo: Emprego formal por setor, índice (2010 = 100)
# Fonte: dados simulados para demonstração do tema.
g_linha <- ggplot(serie, aes(ano, indice, colour = setor)) +
  geom_line() +
  geom_point(data = ponta, size = 1.8) +
  geom_text(data = ponta, aes(label = setor), colour = dv_tinta[["texto"]],
            hjust = 0, nudge_x = 0.3) +
  scale_colour_manual(values = cores_setor, guide = "none") +
  scale_x_continuous(breaks = seq(2010, 2024, 2)) +
  scale_y_continuous(labels = rotulo_num()) +
  coord_cartesian(clip = "off") +
  labs(x = NULL, y = "Emprego formal (2010 = 100)") +
  theme(plot.margin = margin(6, 95, 6, 6))

# 2. Barras ordenadas: comparação entre categorias -----------------------------

barras <- tibble(
  uf = ufs_ne,
  valor = c(6.1, 7.4, 15.8, 11.2, 12.9, 13.5, 14.6, 12.1, 10.3)
) |>
  mutate(uf = fct_reorder(uf, valor), foco = if_else(uf == "Ceará", "foco", "contexto"))

# Título: O Ceará tem a maior participação da indústria no Nordeste
# Subtítulo: Participação da indústria no emprego formal, em %
# Fonte: dados simulados para demonstração do tema.
g_barras <- ggplot(barras, aes(valor, uf, fill = foco)) +
  geom_col(width = 0.7) +
  geom_text(aes(label = rotulo_num(0.1)(valor)), hjust = 0, nudge_x = 0.2) +
  scale_fill_manual(values = dv_destaque, guide = "none") +
  escala_barras("x") +
  labs(x = "Participação da indústria no emprego formal (%)", y = NULL) +
  theme(panel.grid.major = element_blank(), axis.text.x = element_blank(),
        axis.text.y = element_text(colour = dv_tinta[["texto"]]))

# 3. Colunas empilhadas a 100%: composição -------------------------------------

composicao <- tibble(
  ano = rep(c(2004, 2009, 2014, 2019, 2024), each = 3),
  setor = rep(setores, 5),
  parte = c(6, 24, 70,  5.5, 23, 71.5,  5, 21, 74,  4.8, 19, 76.2,  4.5, 18, 77.5) / 100
) |>
  mutate(ano = factor(ano), setor = factor(setor, levels = setores))

# geom_col empilha o primeiro nível do fator no topo; o rótulo segue essa ordem.
rotulo_comp <- composicao |>
  filter(ano == "2024") |>
  arrange(desc(setor)) |>
  mutate(meio = cumsum(parte) - parte / 2)

# Título: A indústria perdeu seis pontos de participação em vinte anos
# Subtítulo: Composição do emprego formal por setor
# Fonte: dados simulados para demonstração do tema.
g_composicao <- ggplot(composicao, aes(ano, parte, fill = setor)) +
  geom_col(width = 0.7, colour = dv_tinta[["fundo"]], linewidth = 0.5) +
  geom_text(data = rotulo_comp, aes(x = 5.45, y = meio, label = setor), hjust = 0) +
  scale_fill_manual(values = cores_setor, guide = "none") +
  scale_y_continuous(labels = rotulo_pct(), expand = expansion(0),
                     breaks = seq(0, 1, 0.25)) +
  coord_cartesian(clip = "off") +
  labs(x = NULL, y = "Participação no emprego formal") +
  theme(plot.margin = margin(6, 95, 6, 6))

# 4. Dispersão: relação entre duas variáveis -----------------------------------

dispersao <- tibble(municipio = paste("Município", LETTERS[1:26])) |>
  mutate(
    renda = exp(runif(n(), log(850), log(3400))),
    formal = pmin(78, 42 + 21 * log(renda / 850) + rnorm(n(), 0, 3.5)),
    # Rótulo vazio nos demais pontos: o ggrepel só desvia de pontos que recebe.
    rotulo = if_else(min_rank(renda) <= 2 | min_rank(desc(renda)) <= 2 |
                       min_rank(desc(formal - 21 * log(renda))) == 1,
                     municipio, "")
  )

# Título: A formalização é maior onde a renda é maior
# Subtítulo: Municípios; rótulo nos extremos de renda e no maior desvio da tendência
# Fonte: dados simulados para demonstração do tema.
g_dispersao <- ggplot(dispersao, aes(renda, formal)) +
  geom_point(shape = 21, size = 2.4, stroke = 0.4,
             fill = dv_cores[["azul"]], colour = dv_tinta[["fundo"]]) +
  geom_text_repel(aes(label = rotulo), seed = 1, point.padding = 0.2,
                  box.padding = 0.6, min.segment.length = 0,
                  segment.colour = dv_tinta[["secundario"]], segment.size = 0.25) +
  scale_x_log10(labels = rotulo_num(), breaks = c(1000, 1500, 2000, 3000)) +
  scale_y_continuous(labels = rotulo_num()) +
  labs(x = "Renda domiciliar per capita (R$, escala logarítmica)",
       y = "Trabalhadores formais (%)") +
  tema_dv(grade = "xy")

# 5. Distribuição: resumo e pontos ---------------------------------------------

# Semente própria: o título abaixo depende desta amostra.
set.seed(21)
salarios <- tibble(
  setor = rep(setores, each = 60),
  salario = c(rlnorm(60, 7.5, 0.30), rlnorm(60, 8.0, 0.45), rlnorm(60, 7.7, 0.38))
) |>
  mutate(setor = fct_reorder(setor, salario, median))

# Título: A indústria tem a maior mediana e a maior dispersão de salários
# Subtítulo: Salário mensal por estabelecimento, em R$. Cada ponto é um estabelecimento
# Nota: a caixa marca os quartis e a mediana; as hastes vão até 1,5 vez o
#   intervalo interquartil.
# Fonte: dados simulados para demonstração do tema.
g_distribuicao <- ggplot(salarios, aes(salario, setor)) +
  geom_point(aes(colour = setor), size = 1.1, alpha = 0.55,
             position = position_jitter(height = 0.16, width = 0, seed = 1)) +
  geom_boxplot(width = 0.5, fill = NA, colour = dv_tinta[["texto"]],
               linewidth = 0.35, outlier.shape = NA) +
  scale_colour_manual(values = cores_setor, guide = "none") +
  scale_x_continuous(labels = rotulo_num()) +
  labs(x = "Salário mensal (R$)", y = NULL) +
  tema_dv(grade = "x") +
  theme(axis.text.y = element_text(colour = dv_tinta[["texto"]]))

# 6. Pequenos múltiplos: muitas séries -----------------------------------------

regioes <- c("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul")
desocupacao <- expand_grid(regiao = regioes, ano = 2012:2024) |>
  mutate(
    nivel = c(Norte = 9.5, Nordeste = 12, `Centro-Oeste` = 7, Sudeste = 9, Sul = 5.5)[regiao],
    taxa = nivel + 3.5 * exp(-((ano - 2019) / 3.2)^2) + rnorm(n(), 0, 0.3),
    regiao = factor(regiao, levels = regioes)
  )
fundo_multiplos <- desocupacao |>
  rename(serie = regiao) |>
  crossing(regiao = factor(regioes, levels = regioes))

# Título: O Nordeste manteve a maior taxa de desocupação em todo o período
# Subtítulo: Taxa de desocupação por região, em %
# Nota: em cinza, as demais regiões.
# Fonte: dados simulados para demonstração do tema.
g_multiplos <- ggplot(desocupacao, aes(ano, taxa)) +
  geom_line(data = fundo_multiplos, aes(group = serie),
            colour = dv_tinta[["contexto"]], linewidth = 0.3) +
  geom_line(linewidth = 0.9) +
  facet_wrap(vars(regiao), nrow = 1) +
  scale_x_continuous(breaks = c(2014, 2022)) +
  scale_y_continuous(labels = rotulo_num(), limits = c(0, NA),
                     expand = expansion(mult = c(0, 0.05))) +
  labs(x = NULL, y = "Taxa de desocupação (%)")

# 7. Pontos ligados: dois momentos por categoria -------------------------------

dois_anos <- tibble(
  uf = ufs_ne,
  `2014` = c(41, 38, 47, 52, 46, 55, 43, 50, 49),
  `2024` = c(48, 47, 61, 58, 51, 63, 45, 57, 56)
) |>
  mutate(uf = fct_reorder(uf, `2024`))
dois_longos <- pivot_longer(dois_anos, c(`2014`, `2024`), names_to = "ano",
                            values_to = "valor")
topo <- filter(dois_longos, uf == levels(dois_anos$uf)[nlevels(dois_anos$uf)])

# Título: O Ceará teve o maior avanço entre 2014 e 2024
# Subtítulo: Domicílios com acesso à internet por banda larga fixa, em %
# Fonte: dados simulados para demonstração do tema.
g_pontos <- ggplot(dois_anos, aes(y = uf)) +
  geom_segment(aes(x = `2014`, xend = `2024`, yend = uf),
               colour = dv_tinta[["contexto"]], linewidth = 0.6) +
  geom_point(data = dois_longos, aes(valor, uf, fill = ano), shape = 21,
             size = 2.6, stroke = 0.6, colour = dv_cores[["azul"]]) +
  geom_text(data = topo, aes(valor, uf, label = ano), vjust = -1.1) +
  scale_fill_manual(values = c(`2014` = dv_tinta[["fundo"]],
                               `2024` = dv_cores[["azul"]]), guide = "none") +
  scale_x_continuous(labels = rotulo_num()) +
  scale_y_discrete(expand = expansion(add = c(0.6, 1.1))) +
  labs(x = "Domicílios com banda larga fixa (%)", y = NULL) +
  tema_dv(grade = "x") +
  theme(axis.text.y = element_text(colour = dv_tinta[["texto"]]))

# 8. Mapa coroplético: padrão espacial de uma taxa -----------------------------

# Cônica equivalente de Albers: preserva área, que é o que o coroplético pede.
# Os parâmetros são os usuais para a América do Sul; falta conferir com o IBGE.
albers <- "+proj=aea +lat_0=-12 +lon_0=-54 +lat_1=-2 +lat_2=-22 +ellps=GRS80 +units=m"

tem_malha <- file.exists(arquivo_malha)
if (!tem_malha) message("Malha de UF ausente (", arquivo_malha, "); mapa não gerado.")
if (tem_malha) {
  mapa <- st_read(arquivo_malha, quiet = TRUE) |>
    mutate(taxa = round(rlnorm(n(), log(38), 0.45), 1)) |>
    st_transform(albers)
  quebras <- classInt::classIntervals(mapa$taxa, n = 5, style = "fisher")$brks
  num1 <- rotulo_num(0.1)
  rotulos_classe <- paste(num1(head(quebras, -1)), "a", num1(quebras[-1]))
  mapa$classe <- cut(mapa$taxa, quebras, include.lowest = TRUE, labels = rotulos_classe)

  # Título: As taxas mais altas não se concentram em uma região
  # Subtítulo: Estabelecimentos por 10 mil habitantes, por Unidade da Federação
  # Nota: cinco classes por quebras naturais (Fisher). Projeção cônica
  #   equivalente de Albers.
  # Fonte: dados simulados para demonstração do tema.
  #
  # A primeira camada deixa um contorno do país por baixo dos estados: a classe
  # mais clara não tem 3:1 de contraste com o fundo.
  g_mapa <- ggplot(mapa) +
    geom_sf(fill = NA, colour = dv_tinta[["secundario"]], linewidth = 0.7) +
    geom_sf(aes(fill = classe), colour = dv_tinta[["fundo"]], linewidth = 0.25) +
    scale_fill_manual(values = dv_seq(5), drop = FALSE,
                      guide = guide_legend(reverse = TRUE)) +
    coord_sf(datum = NA) +
    labs(fill = "Estabelecimentos\npor 10 mil\nhabitantes") +
    tema_dv(grade = "nenhuma") +
    theme(legend.position = "right", legend.justification = "center",
          legend.title = element_text(size = 8.5, colour = dv_tinta[["secundario"]]),
          legend.key.size = grid::unit(11, "pt"))
  salvar_figura(g_mapa, file.path(pasta_saida, "08_mapa.png"), altura = 11)
}

# Exportação -------------------------------------------------------------------

figuras <- list(
  "01_linha" = g_linha, "02_barras" = g_barras, "03_composicao" = g_composicao,
  "04_dispersao" = g_dispersao, "05_distribuicao" = g_distribuicao,
  "06_multiplos" = g_multiplos, "07_pontos" = g_pontos
)
for (nome in names(figuras)) {
  salvar_figura(figuras[[nome]], file.path(pasta_saida, paste0(nome, ".png")))
}

# Em vetor, quando o destino aceita.
salvar_figura(g_linha, file.path(pasta_saida, "01_linha.pdf"))
