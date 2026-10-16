"""Cinco dos exemplos de exemplos.R refeitos com o tema de tema_dv.py.

Todos os dados são simulados; os números não descrevem nenhuma UF ou setor.
Título, subtítulo, nota e fonte não entram na imagem: ficam em comentário
acima de cada gráfico, para serem escritos no documento. As séries com ruído
(1 e 6) não repetem os valores do R, só a forma.

Uso: python exemplos.py [PASTA_DE_SAIDA]   (padrão: figuras)
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from tema_dv import (DV_CORES, DV_DESTAQUE, DV_TINTA, dv_cores_por, escala_barras, grade_dv,
                     rotulo_num, rotulo_pct, salvar_figura, usar_tema_dv)

pasta_saida = Path(sys.argv[1] if len(sys.argv) > 1 else "figuras")
usar_tema_dv()
sorteio = np.random.default_rng(20261003)

setores = ["Agropecuária", "Indústria", "Comércio e serviços"]
cores_setor = dv_cores_por(setores)
ufs_ne = ["Maranhão", "Piauí", "Ceará", "Rio Grande do Norte", "Paraíba",
          "Pernambuco", "Alagoas", "Sergipe", "Bahia"]


def rotulo_direto(eixos, texto, x, y, dx=6, dy=0, **opcoes):
    """Rótulo ao lado da marca, em preto; o layout abre a margem para ele."""
    eixos.annotate(texto, (x, y), xytext=(dx, dy), textcoords="offset points",
                   va="center", annotation_clip=False, **opcoes)


# 1. Linha: mudança no tempo

anos = np.arange(2010, 2025)
inclinacao = {"Agropecuária": 1.2, "Indústria": -0.3, "Comércio e serviços": 2.2}

# Título: Comércio e serviços cresceu mais que os outros setores
# Subtítulo: Emprego formal por setor, índice (2010 = 100)
# Fonte: dados simulados para demonstração do tema.
fig, ax = plt.subplots()
for setor in setores:
    ruido = np.concatenate([[0], sorteio.normal(0, 1.1, len(anos) - 1)])
    indice = 100 + inclinacao[setor] * (anos - 2010) + ruido
    ax.plot(anos, indice, color=cores_setor[setor])
    ax.plot(anos[-1], indice[-1], "o", color=cores_setor[setor])
    rotulo_direto(ax, setor, anos[-1], indice[-1], dx=8)
ax.set_xticks(range(2010, 2025, 2))
ax.yaxis.set_major_formatter(rotulo_num())
ax.set_ylabel("Emprego formal (2010 = 100)")
salvar_figura(fig, pasta_saida / "01_linha.png")
# Em vetor, quando o destino aceita.
salvar_figura(fig, pasta_saida / "01_linha.pdf")

# 2. Barras ordenadas: comparação entre categorias

participacao = sorted(zip([6.1, 7.4, 15.8, 11.2, 12.9, 13.5, 14.6, 12.1, 10.3], ufs_ne))
valores = [valor for valor, _ in participacao]
nomes = [uf for _, uf in participacao]

# Título: O Ceará tem a maior participação da indústria no Nordeste
# Subtítulo: Participação da indústria no emprego formal, em %
# Fonte: dados simulados para demonstração do tema.
fig, ax = plt.subplots()
ax.barh(nomes, valores, height=0.7,
        color=[DV_DESTAQUE["foco" if uf == "Ceará" else "contexto"] for uf in nomes])
for uf, valor in zip(nomes, valores):
    rotulo_direto(ax, rotulo_num(1)(valor), valor, uf, dx=4)
escala_barras(ax, "x")
ax.margins(y=0.03)
ax.grid(False)
ax.set_xticks([])
ax.tick_params(axis="y", labelcolor=DV_TINTA["texto"])
ax.set_xlabel("Participação da indústria no emprego formal (%)")
salvar_figura(fig, pasta_saida / "02_barras.png")

# 3. Colunas empilhadas a 100%: composição

anos_comp = ["2004", "2009", "2014", "2019", "2024"]
partes = {
    "Agropecuária": [0.06, 0.055, 0.05, 0.048, 0.045],
    "Indústria": [0.24, 0.23, 0.21, 0.19, 0.18],
    "Comércio e serviços": [0.70, 0.715, 0.74, 0.762, 0.775],
}

# Título: A indústria perdeu seis pontos de participação em vinte anos
# Subtítulo: Composição do emprego formal por setor
# Fonte: dados simulados para demonstração do tema.
fig, ax = plt.subplots()
base = np.zeros(len(anos_comp))
# A primeira categoria fica no topo, como no R: empilha da última para a primeira.
for setor in reversed(setores):
    ax.bar(anos_comp, partes[setor], bottom=base, width=0.7, color=cores_setor[setor],
           edgecolor=DV_TINTA["fundo"], linewidth=1.07)
    rotulo_direto(ax, setor, len(anos_comp) - 1 + 0.35, base[-1] + partes[setor][-1] / 2, dx=8)
    base += partes[setor]
ax.set_ylim(0, 1)
ax.set_yticks(np.arange(0, 1.01, 0.25))
ax.yaxis.set_major_formatter(rotulo_pct())
ax.set_ylabel("Participação no emprego formal")
salvar_figura(fig, pasta_saida / "03_composicao.png")

# 6. Pequenos múltiplos: muitas séries

regioes = {"Norte": 9.5, "Nordeste": 12, "Centro-Oeste": 7, "Sudeste": 9, "Sul": 5.5}
anos_des = np.arange(2012, 2025)
taxas = {regiao: nivel + 3.5 * np.exp(-((anos_des - 2019) / 3.2) ** 2)
         + sorteio.normal(0, 0.3, len(anos_des)) for regiao, nivel in regioes.items()}

# Título: O Nordeste manteve a maior taxa de desocupação em todo o período
# Subtítulo: Taxa de desocupação por região, em %
# Nota: em cinza, as demais regiões.
# Fonte: dados simulados para demonstração do tema.
fig, paineis = plt.subplots(1, len(regioes), sharey=True)
for painel, regiao in zip(paineis, regioes):
    for outra in regioes:
        if outra != regiao:
            painel.plot(anos_des, taxas[outra], color=DV_TINTA["contexto"], linewidth=0.64)
    painel.plot(anos_des, taxas[regiao], linewidth=1.9)
    painel.set_title(regiao)
    painel.set_xticks([2014, 2022])
painel.set_ylim(0, max(map(max, taxas.values())) * 1.05)
paineis[0].yaxis.set_major_formatter(rotulo_num())
paineis[0].set_ylabel("Taxa de desocupação (%)")
salvar_figura(fig, pasta_saida / "06_multiplos.png")

# 7. Pontos ligados: dois momentos por categoria

internet = sorted(zip([48, 47, 61, 58, 51, 63, 45, 57, 56],
                      [41, 38, 47, 52, 46, 55, 43, 50, 49], ufs_ne))
em_2024 = [depois for depois, _, _ in internet]
em_2014 = [antes for _, antes, _ in internet]
nomes = [uf for _, _, uf in internet]

# Título: O Ceará teve o maior avanço entre 2014 e 2024
# Subtítulo: Domicílios com acesso à internet por banda larga fixa, em %
# Fonte: dados simulados para demonstração do tema.
fig, ax = plt.subplots()
ax.hlines(nomes, em_2014, em_2024, color=DV_TINTA["contexto"], linewidth=1.28)
ax.plot(em_2014, nomes, "o", markersize=7.2, markerfacecolor=DV_TINTA["fundo"],
        markeredgecolor=DV_CORES["azul"], markeredgewidth=0.9)
ax.plot(em_2024, nomes, "o", markersize=7.2, markeredgecolor=DV_CORES["azul"], markeredgewidth=0.9)
for ano, valor in (("2014", em_2014[-1]), ("2024", em_2024[-1])):
    rotulo_direto(ax, ano, valor, nomes[-1], dx=0, dy=11, ha="center")
grade_dv(ax, "x")
ax.set_ylim(-0.6, len(nomes) - 1 + 0.9)
ax.xaxis.set_major_formatter(rotulo_num())
ax.tick_params(axis="y", labelcolor=DV_TINTA["texto"])
ax.set_xlabel("Domicílios com banda larga fixa (%)")
salvar_figura(fig, pasta_saida / "07_pontos.png")
