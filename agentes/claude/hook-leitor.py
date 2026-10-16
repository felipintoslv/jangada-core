"""Hook PreToolUse do subagente leitor, chamado pelo bin/jangada-hook-leitor:
só deixa passar comandos de leitura no terminal.

Recebe o JSON do evento pela entrada padrão.

- Claude (sem opção): sai com 0 para liberar e com 2, e o motivo na saída de
  erro, para recusar. Só é chamado para o leitor (frontmatter do agente).
- agy (--agy): o hook fica em ~/.gemini/config/hooks.json e dispara em todo
  run_command, de qualquer agente. Responde sempre um JSON na saída padrão:
  "deny" com o motivo para o comando recusado do leitor e "ask" no resto,
  que segue a regra normal de permissões do agy. O leitor é reconhecido pela
  variável JANGADA_AGY_PAPEL=leitor (o jangada-delegar a põe no agy que roda
  o papel) ou, como subagente, pelo arquivo
  brain/*/.system_generated/subagents/CONVERSA.json com o typeName "leitor".

O leitor lê documentos de fora, que podem trazer injeção de prompt; a regra
"não grave" do texto não basta. Vale uma lista de comandos que não gravam
nem executam outro programa, ligados só por "|". Redirecionamento, ";", "&",
substituição de comando e variáveis são recusados. O pdftotext só escreve
na saída padrão ("-" como último argumento).
"""

import glob
import json
import os
import re
import shlex
import sys

PERMITIDOS = {"pdftotext", "pdfinfo", "grep", "head", "tail", "wc", "cut", "tr", "cat", "ls"}
# $( ${ $VAR e crase executam ou expandem; "$'" (texto) e "$" no fim de um
# padrão do grep ficam de fora da recusa.
EXPANSAO = re.compile(r"`|\$[({A-Za-z0-9_@*#?!$-]")
CONVERSA = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def motivo_recusa(comando):
    """None se o comando só lê; senão, o motivo da recusa."""
    if not isinstance(comando, str) or not comando.strip():
        return "comando vazio"
    if "\n" in comando or "\\" in comando:
        return "quebra de linha ou barra invertida no comando"
    if EXPANSAO.search(comando):
        return "substituição de comando ou variável"
    try:
        lexer = shlex.shlex(comando, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        partes = list(lexer)
    except ValueError:
        return "aspas sem fechar"
    trechos = [[]]
    for p in partes:
        if p == "|":
            trechos.append([])
        elif p and set(p) <= set("();<>|&"):
            return f"'{p}' não é permitido"
        else:
            trechos[-1].append(p)
    for t in trechos:
        if not t:
            return "trecho vazio entre '|'"
        if t[0] not in PERMITIDOS:
            return f"'{t[0]}' não está na lista"
        if t[0] == "pdftotext" and t[-1] != "-":
            return "o pdftotext precisa de '-' como último argumento (saída padrão)"
    return None


def explicar(motivo):
    return (f"jangada-hook-leitor: {motivo}. O leitor só roda comandos de leitura "
            f"({', '.join(sorted(PERMITIDOS))}), ligados por '|'.")


def claude():
    try:
        evento = json.load(sys.stdin)
    except ValueError:
        evento = None
    if not isinstance(evento, dict):
        motivo = "evento ilegível"
    elif evento.get("tool_name") != "Bash":
        return
    else:
        motivo = motivo_recusa((evento.get("tool_input") or {}).get("command"))
    if motivo:
        print(explicar(motivo), file=sys.stderr)
        sys.exit(2)


def subagente_leitor(conversa):
    if not isinstance(conversa, str) or not CONVERSA.match(conversa):
        return False
    raiz = os.environ.get("JANGADA_AGY_DIR") or os.path.expanduser("~/.gemini/antigravity-cli")
    for arq in glob.glob(os.path.join(raiz, "brain", "*", ".system_generated", "subagents", conversa + ".json")):
        try:
            with open(arq, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and (d.get("subagentDescriptor") or {}).get("typeName") == "leitor":
            return True
    return False


def agy():
    leitor = os.environ.get("JANGADA_AGY_PAPEL") == "leitor"
    try:
        evento = json.load(sys.stdin)
    except ValueError:
        evento = None
    if not isinstance(evento, dict):
        motivo = "evento ilegível" if leitor else None
    else:
        leitor = leitor or subagente_leitor(evento.get("conversationId"))
        chamada = evento.get("toolCall") or {}
        motivo = None
        if leitor and isinstance(chamada, dict) and chamada.get("name") == "run_command":
            motivo = motivo_recusa((chamada.get("args") or {}).get("CommandLine"))
    if motivo:
        print(json.dumps({"decision": "deny", "reason": explicar(motivo)}, ensure_ascii=False))
    else:
        print('{"decision": "ask"}')


if sys.argv[1:] == ["--agy"]:
    agy()
else:
    claude()
