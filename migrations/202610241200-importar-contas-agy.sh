#!/usr/bin/env bash
# Oferece cópia das contas antigas, sem alterar ou remover o estado do Catamarã.
# Sem confirmação interativa, não cria catálogo nem contas; pode ser repetida.
set -euo pipefail
JANGADA_CORE_PATH="${JANGADA_CORE_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=install/lib.sh
source "$JANGADA_CORE_PATH/install/lib.sh"

origem="${XDG_STATE_HOME:-$HOME/.local/state}/catamara/contas"
destino="$JANGADA_ESTADO/contas"
[[ -d "$origem/conta1/antigravity-cli" && -d "$origem/conta2/antigravity-cli" ]] || exit 0
[[ ! -e "$destino/agy.json" && ! -L "$destino/agy.json" ]] || exit 0
if simulando; then
  info "ofereceria importar conta1 e conta2 de $origem, mediante confirmação e indicação de Argon"
  exit 0
fi
if ! confirmar "Copiar as contas do agy do Catamarã para o jangada?" n; then
  info "importação não confirmada; nenhuma conta copiada. Para importar depois, execute em terminal: bash $JANGADA_CORE_PATH/migrations/202610241200-importar-contas-agy.sh"
  exit 0
fi
argon1=false; argon2=false
if confirmar "A conta1 tem Argon?" n; then argon1=true; fi
if confirmar "A conta2 tem Argon?" n; then argon2=true; fi
python3 -I - "$origem" "$destino" "$argon1" "$argon2" <<'PY'
import json, os, pathlib, shutil, sys, tempfile
origem, destino = map(pathlib.Path, sys.argv[1:3])
os.umask(0o077)
pulados = []
def especial(pasta):
    # Links dentro da conta não são seguidos nem copiados; outro arquivo especial recusa.
    with os.scandir(pasta) as itens:
        for item in itens:
            if item.is_symlink():
                continue
            if item.is_dir(follow_symlinks=False):
                especial(item.path)
            elif not item.is_file(follow_symlinks=False):
                raise ValueError("arquivo especial na conta de origem")
def sem_links(pasta, nomes):
    achados = [n for n in nomes if os.path.islink(os.path.join(pasta, n))]
    pulados.extend(pathlib.Path(pasta, n) for n in achados)
    return achados
try:
    if origem.resolve() != origem or destino.resolve() != destino:
        raise ValueError("link na pasta de contas")
    for nome in ("conta1", "conta2"):
        fonte = origem / nome / "antigravity-cli"
        if fonte.resolve() != fonte or not fonte.is_dir():
            raise ValueError("link ou pasta inválida na conta de origem")
        especial(fonte)
        if (destino / nome).exists() or (destino / nome).is_symlink():
            raise ValueError("conta de destino já existe; confira antes de importar")
    if destino.exists() and any(destino.iterdir()):
        raise ValueError("pasta de contas já contém dados; confira antes de importar")
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".contas-agy-importar-", dir=destino.parent) as temporaria:
        pasta = pathlib.Path(temporaria)
        contas = []
        for nome, argon in zip(("conta1", "conta2"), sys.argv[3:]):
            shutil.copytree(origem / nome / "antigravity-cli", pasta / nome, ignore=sem_links)
            contas.append({"nome": nome, "pasta": str(destino / nome), "argon": argon == "true"})
        modelo = pasta / "agy.json"
        modelo.write_text(json.dumps(contas, ensure_ascii=False, indent=2) + "\n")
        # Contas e catálogo aparecem juntos; uma interrupção permite tentar de novo.
        os.rename(pasta, destino)
    for p in pulados:
        print("link pulado, não copiado: " + ascii(str(p.relative_to(origem))))
except (OSError, ValueError) as erro:
    sys.exit("importação de contas recusada: " + str(erro))
PY
info "contas copiadas; a origem do Catamarã foi preservada"
