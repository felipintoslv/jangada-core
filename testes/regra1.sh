#!/usr/bin/env bash
# Testa a regra 1 do AGENTS.md: todo caminho de fora de ~/.config/jangada,
# ~/.local/share/jangada-core e ~/.local/state/jangada escrito por extenso em bin/,
# install/ e install.sh está
# em "Exceções à regra 1" ou na lista de caminhos só lidos abaixo. Um caminho
# novo reprova até alguém decidir em qual das duas listas ele entra.
#
# Uso: testes/regra1.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
falhas=0
ok()    { printf 'ok    %s\n' "$*"; }
falha() { printf 'FALHA %s\n' "$*"; falhas=$((falhas + 1)); }
conferir() { local d="$1"; shift; if "$@"; then ok "$d"; else falha "$d"; fi; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Caminhos que o jangada só lê ou confere, sem gravar. Um caminho entra aqui
# só se nenhum comando grava nele; se algum grava, vai para o AGENTS.md.
cat >"$tmp/leituras" <<'FIM'
/etc/arch-release
/etc/fstab
/etc/hostname
/etc/locale.gen
/etc/os-release
/etc/systemd/system/display-manager.service
/usr/share/xsessions
/usr/share/icons
/usr/lib/modules
/usr/bin/env
/usr/local/bin
~/.Renviron
~/.Rprofile
~/.cache/hyprland
~/.cache/noctalia
~/.cache/paru
~/.cache/yay
~/.claude.json
~/.claude/projects
~/.codex
~/.config/claude
~/.config/hypr
~/.config/niri
~/.config/noctalia
~/.gemini/GEMINI.md
~/.gemini/settings.json
~/.gemini/antigravity-cli/conversations
~/.gemini/antigravity-cli/log
~/.gnupg
~/.ssh
~/Imagens/Papeis
~/Pictures/Wallpapers
~/Projetos
FIM

# Imprime os caminhos citados em RAIZ que nenhuma das listas cobre, com o
# primeiro arquivo e linha onde aparecem. Se a varredura quebra, a saída
# não fica vazia, e os casos que esperam nada a apontar reprovam.
varrer() {
  python3 - "$1" "$tmp/leituras" <<'PY' || echo "a varredura falhou"
import pathlib, re, sys
raiz, leituras = pathlib.Path(sys.argv[1]), sys.argv[2]

# Exceções: primeira coluna da tabela de "Exceções à regra 1". Um nome sem
# barra depois de um caminho, entre parênteses, é item dentro dele.
permitidos = ["~/.config/jangada", "~/.local/share/jangada-core", "~/.local/state/jangada"]
agents = (raiz / "AGENTS.md").read_text()
secao = agents.split("## Exceções à regra 1", 1)[1]
for linha in secao.splitlines():
    if not linha.startswith("| ") or linha.startswith("| Caminho") or linha.startswith("|---"):
        continue
    base = None
    for item in re.findall(r"`([^`]+)`", linha.split("|")[1]):
        if item.startswith(("~", "/", "$")):
            base = item; permitidos.append(item)
        elif base:
            permitidos.append(base + "/" + item)
permitidos += [l.strip() for l in open(leituras) if l.strip()]

# Com aspas opcionais entre a raiz e o resto, como em "$HOME"/.cache/x.
casa = re.compile(r'(?:\$HOME|\$\{HOME\}|~|\$\{XDG_(?:CACHE|CONFIG|STATE)_HOME:-\$HOME/[.a-z/]+\})"?(?:/[A-Za-z0-9_.-]+)+')
sistema = re.compile(r"(?<![\w.$}-])/(?:etc|usr|opt|\.snapshots)(?:/[A-Za-z0-9_.-]+)*")
xdg = {"CACHE": "~/.cache", "CONFIG": "~/.config", "STATE": "~/.local/state"}

def normal(c):
    c = re.sub(r"^\$\{XDG_(CACHE|CONFIG|STATE)_HOME:-[^}]*\}", lambda m: xdg[m.group(1)], c)
    c = re.sub(r"^(\$HOME|\$\{HOME\})", "~", c).replace('"', "", 1)
    return c.rstrip(".")

def coberto(c):
    # O próprio caminho ou algo dentro de um permitido; ou uma pasta acima de
    # um permitido, que o mkdir -p cria no caminho.
    return any(c == p or c.startswith(p + "/") or p.startswith(c + "/") for p in permitidos)

arqs = [p for d in ("bin", "install") for p in sorted((raiz / d).rglob("*")) if p.is_file()]
arqs += [raiz / "install.sh"]
vistos = {}
for arq in arqs:
    try:
        texto = arq.read_text()
    except (OSError, UnicodeDecodeError):
        continue
    for n, linha in enumerate(texto.splitlines(), 1):
        if linha.lstrip().startswith("#"):
            continue
        for m in list(casa.finditer(linha)) + list(sistema.finditer(linha)):
            c = normal(m.group(0))
            if not coberto(c):
                vistos.setdefault(c, f"{arq.relative_to(raiz)}:{n}")
for c, onde in sorted(vistos.items()):
    print(f"{c} ({onde})")
PY
}

# Caso 1: o repositório como está.
fora="$(varrer .)"
conferir "caso 1: todo caminho de fora está nas exceções ou nas leituras${fora:+: $(tr '\n' ' ' <<<"$fora")}" [ -z "$fora" ]

# Caso 2: uma escrita nova fora das listas reprova.
mkdir -p "$tmp/copia"
cp -r AGENTS.md bin install install.sh "$tmp/copia/"
printf '#!/bin/sh\necho x >"$HOME/.novo/arquivo"\n' >"$tmp/copia/bin/jangada-novo"
fora="$(varrer "$tmp/copia")"
conferir "caso 2: escrita nova em ~/.novo é apontada" grep -q '^~/.novo/arquivo (bin/jangada-novo:2)$' <<<"$fora"

# Caso 3: um nome entre parênteses vale dentro do caminho da linha.
printf '#!/bin/sh\n: >"$HOME/.claude/output-styles/x"\n' >"$tmp/copia/bin/jangada-novo"
fora="$(varrer "$tmp/copia")"
conferir "caso 3: ~/.claude/output-styles vem da linha do ~/.claude" [ -z "$fora" ]

# Caso 4: aspas entre $HOME e o resto do caminho não escondem a escrita.
printf '#!/bin/sh\necho x >"$HOME"/.novo/arquivo\n' >"$tmp/copia/bin/jangada-novo"
fora="$(varrer "$tmp/copia")"
conferir "caso 4: \"\$HOME\"/.novo também é apontado" grep -q '^~/.novo/arquivo (bin/jangada-novo:2)$' <<<"$fora"

# Caso 5: as pastas de instalação também são examinadas.
rm "$tmp/copia/bin/jangada-novo"
printf '#!/bin/sh\necho x >"$HOME/.novo/arquivo"\n' >"$tmp/copia/install/99-novo.sh"
fora="$(varrer "$tmp/copia")"
conferir "caso 5: escrita nova em install/ é apontada" grep -q '^~/.novo/arquivo (install/99-novo.sh:2)$' <<<"$fora"

if ((falhas)); then
  echo "$falhas teste(s) da regra 1 falharam"
  exit 1
fi
echo "todos os testes da regra 1 passaram"
