# shellcheck shell=bash
# Etapa 00: confere se o ambiente é adequado antes de mudar qualquer coisa.
# Carregado por install.sh; usa as funções de install/lib.sh.

[[ -f /etc/arch-release ]] || morrer "o jangada foi feito para Arch Linux"
tem_comando pacman || morrer "pacman não encontrado"
tem_comando sudo || [[ $EUID -eq 0 ]] || morrer "sudo não encontrado"

info "raiz em: $(fs_raiz)"
info "carregador de boot: $(carregador_boot)"
info "ajudante do AUR: $(ajudante_aur || true)"

if [[ -z "$(ajudante_aur)" ]]; then
  aviso "nenhum ajudante do AUR (paru ou yay); pacotes que só existem no AUR serão listados e ignorados"
fi
