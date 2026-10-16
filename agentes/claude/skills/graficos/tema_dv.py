"""Tema matplotlib e funções de apoio da skill graficos.

O par em R é tema_dv.R: cores, corpos e larguras mudam nos dois arquivos
juntos. Os números entre colchetes remetem às regras de regras.md.

Uso, com o arquivo copiado para o projeto:
    from tema_dv import *
    usar_tema_dv()
    # Título: o achado em uma frase
    # Subtítulo: o que é medido, e a unidade
    # Nota: ...
    # Fonte: ...
    fig, ax = plt.subplots()
    ...
    salvar_figura(fig, "figuras/nome.png")

Título, subtítulo, nota e fonte não entram na imagem [9, 11]: ficam em
comentário acima do gráfico e são escritos no documento de destino. Por isso
a unidade vai no título do eixo ou da legenda.
"""

import warnings
from pathlib import Path

import matplotlib as mpl
from cycler import cycler
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

__all__ = [
    "DV_TINTA", "DV_CORES", "DV_DESTAQUE", "pal_dv", "dv_cores_por", "dv_seq", "dv_div",
    "mapa_seq", "mapa_div", "rotulo_num", "rotulo_pct", "rotulo_moeda", "dv_familia",
    "usar_tema_dv", "grade_dv", "legenda_dv", "escala_barras", "salvar_figura",
]

# Tintas e superfícies

DV_TINTA = {
    "texto": "#1A1A1A",
    "secundario": "#4D4D4D",
    "grade": "#D9D9D9",
    "contexto": "#B3B3B3",
    "fundo": "#FFFFFF",
}

# Paletas

# Qualitativa, em ordem fixa [17, 21]. Parte da Okabe-Ito; amarelo, laranja
# claro, azul-céu e rosa saíram ou foram escurecidos porque ficam abaixo de
# 3:1 de contraste sobre branco [22]. As seis passaram juntas, nesta ordem,
# num validador de contraste e de separação sob simulação de daltonismo; não
# troque uma cor sem revalidar as duas coisas.
DV_CORES = {
    "azul": "#0072B2",
    "laranja": "#D55E00",
    "verde": "#009E73",
    "roxo": "#AA4499",
    "ocre": "#B8860B",
    "ceu": "#3C93C2",
}


def pal_dv(n):
    """Primeiras n cores. Quatro é o alvo; seis é o teto [19]; a sétima é erro [16]."""
    if n > len(DV_CORES):
        raise ValueError(
            f"A paleta qualitativa tem {len(DV_CORES)} cores e o gráfico pede {n}. "
            "Agrupe categorias, use painéis ou DV_DESTAQUE."
        )
    if n > 4:
        warnings.warn(
            "Mais de quatro categorias de cor; confira se rótulo direto ou painéis resolvem melhor.",
            stacklevel=2,
        )
    return list(DV_CORES.values())[:n]


def dv_cores_por(categorias):
    """Cor fixa por categoria ao longo do relatório [23]: defina uma vez por projeto."""
    categorias = list(categorias)
    return dict(zip(categorias, pal_dv(len(categorias))))


# Uma cor para o foco e cinza para o contexto [16].
DV_DESTAQUE = {"foco": DV_CORES["azul"], "contexto": DV_TINTA["contexto"]}

# Saída de dv_seq() e dv_div() em tema_dv.R (colorspace, "Blues 3" sem os dois
# passos mais claros e "Blue-Red 3"), para o Python não depender do pacote.
_SEQ = {
    3: ["#79ABE2", "#0072B4", "#00366C"],
    4: ["#99BFEF", "#5295D4", "#0066A5", "#00366C"],
    5: ["#ADCCF6", "#79ABE2", "#2C86CA", "#005D9A", "#00366C"],
    6: ["#BAD5FA", "#91BAEB", "#5E9BD8", "#007BC0", "#005893", "#00366C"],
    7: ["#C3DBFD", "#A1C4F1", "#79ABE2", "#468FD0", "#0072B4", "#00538E", "#00366C"],
}
_DIV = {
    3: ["#002F70", "#F6F6F6", "#5F1415"],
    4: ["#002F70", "#B4C2EB", "#EDB4B5", "#5F1415"],
    5: ["#002F70", "#879FDB", "#F6F6F6", "#DA8A8B", "#5F1415"],
    6: ["#002F70", "#6889D0", "#D3DBF4", "#F7D3D3", "#CB6F70", "#5F1415"],
    7: ["#002F70", "#517AC9", "#B4C2EB", "#F6F6F6", "#EDB4B5", "#C05D5D", "#5F1415"],
}


def _classes(tabela, n):
    if n not in tabela:
        raise ValueError(f"Use de {min(tabela)} a {max(tabela)} classes; o gráfico pede {n}.")
    return list(tabela[n])


def dv_seq(n):
    """Sequencial de um matiz, do claro ao escuro, em n classes [17, 18]."""
    return _classes(_SEQ, n)


def dv_div(n):
    """Divergente com centro neutro em n classes [17]."""
    return _classes(_DIV, n)


def mapa_seq():
    """Sequencial contínua, para cmap=."""
    return LinearSegmentedColormap.from_list("dv_seq", dv_seq(7))


def mapa_div():
    """Divergente contínua. O centro deve cair no valor de referência [17]:
    passe norm=matplotlib.colors.TwoSlopeNorm(vcenter=referencia)."""
    return LinearSegmentedColormap.from_list("dv_div", [_DIV[3][0], "#E2E2E2", _DIV[3][2]])


# Rótulos numéricos em português [7]. Cada função devolve outra, que serve em
# ax.yaxis.set_major_formatter() e também para formatar um valor de rótulo.


def _formatar(valor, casas, prefixo="", sufixo=""):
    texto = f"{valor:,.{casas}f}".translate(str.maketrans(",.", ".,"))
    return f"{prefixo}{texto}{sufixo}"


def rotulo_num(casas=0, prefixo="", sufixo=""):
    return lambda valor, _posicao=None: _formatar(valor, casas, prefixo, sufixo)


def rotulo_pct(casas=0):
    """Para proporção entre 0 e 1."""
    return lambda valor, _posicao=None: _formatar(valor * 100, casas, sufixo="%")


def rotulo_moeda(casas=0):
    return rotulo_num(casas, prefixo="R$ ")


# Tipografia


def dv_familia(preferidas=("Lato", "Source Sans 3", "Noto Sans", "Liberation Sans")):
    """Primeira família sem serifa disponível [12]."""
    instaladas = {fonte.name for fonte in font_manager.fontManager.ttflist}
    return next((familia for familia in preferidas if familia in instaladas), "sans-serif")


# Tema

_GRADES = {"y": "y", "x": "x", "xy": "both"}


def usar_tema_dv(grade="y"):
    """Define o tema para a sessão [28].

    Corpos pensados para figura de 16 cm de largura em página A4 [27]: eixos,
    legenda e rótulos em 8,5 pt. `grade` diz em que eixo ficam as linhas de
    grade: "y" para colunas e linhas, "x" para barras horizontais, "xy" para
    dispersão, "nenhuma" para mapas. grade_dv() troca a grade de um painel.
    A cor padrão de traço, ponto e barra é o azul; mais de uma série recebe
    cor por pal_dv() ou dv_cores_por(), que param na sétima.
    """
    if grade not in (*_GRADES, "nenhuma"):
        raise ValueError('grade deve ser "y", "x", "xy" ou "nenhuma".')
    texto, secundario, fundo = DV_TINTA["texto"], DV_TINTA["secundario"], DV_TINTA["fundo"]
    mpl.rcParams.update({
        "font.family": dv_familia(),
        "font.size": 8.5,
        "text.color": texto,

        "figure.figsize": (16 / 2.54, 8 / 2.54),
        "figure.facecolor": fundo,
        "figure.constrained_layout.use": True,
        # Margem de 6 pt em volta, em polegadas.
        "figure.constrained_layout.w_pad": 6 / 72,
        "figure.constrained_layout.h_pad": 6 / 72,
        "figure.titlesize": 12,
        "figure.titleweight": "bold",
        "savefig.facecolor": fundo,
        "savefig.dpi": 300,
        # Texto como texto no vetor, para o documento de destino poder buscá-lo.
        "pdf.fonttype": 42,
        "svg.fonttype": "none",

        "axes.facecolor": fundo,
        "axes.spines.left": False,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.spines.bottom": False,
        "axes.labelsize": 8.5,
        "axes.labelcolor": secundario,
        # Título de eixo é nome de painel em pequenos múltiplos.
        "axes.titlesize": 8.5,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlecolor": texto,
        "axes.axisbelow": True,
        "axes.grid": grade != "nenhuma",
        "axes.grid.axis": _GRADES.get(grade, "both"),
        "axes.prop_cycle": cycler(color=[DV_CORES["azul"]]),

        "grid.color": DV_TINTA["grade"],
        "grid.linewidth": 0.53,

        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "xtick.labelcolor": secundario,
        "ytick.labelcolor": secundario,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "xtick.minor.size": 0,
        "ytick.minor.size": 0,

        "lines.linewidth": 1.5,
        "lines.markersize": 5.3,
        "patch.facecolor": DV_CORES["azul"],
        "scatter.edgecolors": "none",

        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "legend.title_fontsize": 8.5,
        "legend.handlelength": 1.0,
    })


def grade_dv(eixos, grade):
    """Troca a grade de um painel: "y", "x", "xy" ou "nenhuma" (mapa, sem eixos)."""
    if grade == "nenhuma":
        eixos.set_axis_off()
        return
    eixos.grid(False)
    eixos.grid(True, axis=_GRADES[grade])


def legenda_dv(eixos, **opcoes):
    """Legenda no topo, à esquerda, em uma linha e na ordem das séries [10].
    Só quando o rótulo direto não couber."""
    marcas, _ = eixos.get_legend_handles_labels()
    return eixos.legend(loc="lower left", bbox_to_anchor=(0, 1), ncols=len(marcas),
                        borderaxespad=0.2, columnspacing=1.2, **opcoes)


def escala_barras(eixos, eixo="y"):
    """Eixo de valor de barras: começa em zero, sem folga na base [5].
    Chame depois de desenhar as barras."""
    topo = eixos.dataLim.y1 if eixo == "y" else eixos.dataLim.x1
    getattr(eixos, f"set_{eixo}lim")(0, topo * 1.06)


# Exportação


def salvar_figura(figura, arquivo, largura=16, altura=8, texto_na_imagem=False, dpi=300):
    """Grava a figura com 16 cm de largura: a mancha de uma página A4 com
    margens de 3 cm e 2 cm [27]. PDF e SVG saem em vetor [29]; PNG, a 300 dpi.

    O título da figura (suptitle) é retirado da imagem, e também o título do
    eixo quando a figura tem um painel só; com mais painéis, o título de cada
    um é o nome do painel e fica. texto_na_imagem=True mantém tudo, para
    figura que circula sozinha.
    """
    arquivo = Path(arquivo)
    if arquivo.suffix.lower() not in {".png", ".pdf", ".svg"}:
        raise ValueError("Extensão não prevista: use png, pdf ou svg.")
    if not texto_na_imagem:
        figura.suptitle("")
        if len(figura.axes) == 1:
            for lado in ("left", "center", "right"):
                figura.axes[0].set_title("", loc=lado)
    figura.set_size_inches(largura / 2.54, altura / 2.54)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(arquivo, dpi=dpi)
    return arquivo
