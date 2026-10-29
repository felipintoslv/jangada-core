"""Orçamento de espera compartilhado por execução e sondagens."""

import time


def restante(prazo, limite):
    """Sem prazo global, conserva inclusive o tipo do limite anterior."""
    return limite if prazo is None else max(0, min(limite, prazo - time.monotonic()))
