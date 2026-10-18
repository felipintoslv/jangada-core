#!/usr/bin/env bash
# Codex falso: lançamento, protocolo e argumentos sem rede nem login real.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=testes/isolamento.sh
source testes/isolamento.sh
repo_jangada="$PWD"
codex_real="$(command -v codex || true)"
tmp="$(mktemp -d)"
erros_dos_pulados "$tmp"
trap 'rm -rf "$tmp"' EXIT
falhas=0
conferir() {
  local nome="$1"; shift
  if "$@" >/dev/null; then printf 'ok    %s\n' "$nome"
  elif ! pulado_se_recusado "${tmp:-}" "$nome"; then printf 'FALHA %s\n' "$nome"; falhas=$((falhas + 1)); fi
}
# Conferência que só vale com a sessão "tarefa" criada adiante.
conferir_da_sessao() {
  local nome="$1"; shift
  if "$@" >/dev/null; then printf 'ok    %s\n' "$nome"
  elif ! pulado_sem_o_passo "${tmp:-}" tarefa "$nome"; then printf 'FALHA %s\n' "$nome"; falhas=$((falhas + 1)); fi
}
mkdir -p "$tmp/bin" "$tmp/config/jangada" "$tmp/state/jangada/agentes" "$tmp/projeto" "$tmp/codex"
python3 - "$tmp/codex/config.toml" "$repo_jangada" <<'PY'
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text('[projects.' + json.dumps(sys.argv[2]) + ']\ntrust_level = "trusted"\n')
PY
cat >"$tmp/bin/codex" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == app-server ]]; then
    exec python3 "$JANGADA_CORE_PATH/testes/falso-codex-hooks.py" "$@"
  fi
done
if [[ "${1:-}" == --help ]]; then
  [[ "${FALSO_ANTIGO:-0}" == 1 ]] || echo --no-daemon
  exit 0
fi
printf '%s\0' "$@" >"$FALSO_DIR/codex.args"
EOF
cat >"$tmp/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case " $* " in
  *" has-session "*) [[ "${FALSO_TMUX_EXISTENTE:-0}" == 1 ]] ;;
  *" new-session "*) [[ "${FALSO_TMUX_FALHAR:-0}" == 1 ]] && exit 1; printf '%s\n' "$@" >"$FALSO_DIR/tmux.ambiente" ;;
  *" send-keys "*) printf '%s' "${*: -2:1}" >"$FALSO_DIR/tmux.comando" ;;
esac
EOF
for c in claude agy notify-send pkill; do
  printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/$c"
done
chmod +x "$tmp/bin/"*
rodar() {
  executar "$tmp" env -u JANGADA_SESSAO -u JANGADA_ISOLADO -u JANGADA_DELEGAR -u JANGADA_VALIDAR_REVISOR \
    PATH="$tmp/bin:$PATH" FALSO_DIR="$tmp" JANGADA_CORE_PATH="$repo_jangada" \
    CODEX_HOME="$tmp/codex" XDG_CONFIG_HOME="$tmp/config" XDG_STATE_HOME="$tmp/state" "$@"
}
git init -q -b main "$tmp/projeto"
git -C "$tmp/projeto" -c user.name=t -c user.email=t@t commit -q --allow-empty -m inicio
printf 'JANGADA_WORKTREES=%s\n' "$tmp/worktrees" >"$tmp/config/jangada/jangada.conf"
# Autorrevisão e revisor agy não são perfis padrão: ficam em perfis do usuário.
mkdir -p "$tmp/config/jangada/agentes"
printf 'COMANDO=codex\nJANGADA_VALIDAR_REVISOR=codex\nJANGADA_DELEGAR=local\n' \
  >"$tmp/config/jangada/agentes/codex-mesmo.conf"
printf 'COMANDO=codex\nJANGADA_VALIDAR_REVISOR=agy\nJANGADA_VALIDAR_MODELO=gemini-3.8-flash-high\nJANGADA_DELEGAR=agy\n' \
  >"$tmp/config/jangada/agentes/codex-flash.conf"
rodar "$repo_jangada/bin/jangada-agente" --perfil codex-mesmo --projeto "$tmp/projeto" \
  --nome tarefa --prompt $'primeira linha\nsegunda linha' >"$tmp/saida" 2>&1
conferir "perfil de autorrevisão do Codex cria a sessão" [ "$?" = 0 ]
# Dentro do isolamento esta sessão é recusada: as conferências adiante que só
# valem com ela usam o conferir_da_sessao.
guardar_recusa "$tmp" tarefa
conferir "worktree próprio" test -f "$tmp/worktrees/projeto/tarefa/.git"
conferir "revisor e delegação no estado" jq -e '.agente == "codex" and .revisor == "codex" and .delegar == "local" and .isolar' \
  "$tmp/state/jangada/agentes/projeto--tarefa.json"
conferir "protocolo compatível com Codex" grep -q 'Não tente chamar subagentes do Claude' \
  "$tmp/state/jangada/agentes/protocolo-projeto--tarefa.md"
conferir "lançamento isolado pelo adaptador" grep -q 'jangada-isolar -- .*jangada-codex --protocolo .* -- codex' "$tmp/tmux.comando"
conferir "metadados externos para revisão" jq -e '.revisor == "codex" and .agente == "codex"' \
  "$tmp/state/jangada/revisoes/projeto--tarefa.json"

rodar "$repo_jangada/bin/jangada-agente" --perfil codex-flash --projeto "$tmp/projeto" \
  --nome tarefa-agy --prompt "Implemente a tarefa" >"$tmp/saida" 2>&1
conferir "perfil do Codex com revisor agy cria a sessão" [ "$?" = 0 ]
conferir "Codex com revisor e delegação agy" jq -e '.agente == "codex" and .revisor == "agy" and .delegar == "agy" and .isolar' \
  "$tmp/state/jangada/agentes/projeto--tarefa-agy.json"
conferir "revisor Flash explícito no ambiente" grep -q 'JANGADA_VALIDAR_MODELO=gemini-3.8-flash-high' "$tmp/tmux.ambiente"

rodar "$repo_jangada/bin/jangada-agente" --perfil codex-claude --projeto "$tmp/projeto" \
  --nome tarefa-padrao --prompt "Implemente a tarefa" >"$tmp/saida" 2>&1
conferir "perfil codex-claude cria a sessão" [ "$?" = 0 ]
conferir "codex-claude: revisor Claude e delegação agy" jq -e '.agente == "codex" and .perfil == "codex-claude" and .revisor == "claude" and .delegar == "agy" and .isolar' \
  "$tmp/state/jangada/agentes/projeto--tarefa-padrao.json"
conferir "codex-claude: sem modelo de revisor do agy no ambiente" \
  bash -c '! grep -q JANGADA_VALIDAR_MODELO "$1"' _ "$tmp/tmux.ambiente"

conferir "codex-claude: protocolo manda leitor e redator ao agy" grep -q 'inclusive leitor e redator' \
  "$tmp/state/jangada/agentes/protocolo-projeto--tarefa-padrao.md"
rodar JANGADA_AGENTE_ARGS=--version "$repo_jangada/bin/jangada-agente" --perfil codex-claude \
  --autor-modelo gpt-6-luna --projeto "$tmp/projeto" --nome tarefa-piloto --prompt "Piloto explícito" >"$tmp/saida" 2>&1
conferir "piloto: perfil ignora argumentos globais que não utiliza" [ "$?" = 0 ]
conferir "piloto: autor Luna medium e revisor Opus high protegidos" jq -e \
  '.modelos_tarefa.autor == {provedor:"codex", modelo:"gpt-6-luna", esforco:"medium"}
   and .modelos_tarefa.revisor == {provedor:"claude", modelo:"opus", esforco:"high"}' \
  "$tmp/state/jangada/revisoes/projeto--tarefa-piloto.json"
conferir "piloto: modelo do agy separado do revisor Opus" \
  bash -c 'grep -q JANGADA_VALIDAR_MODELO=opus "$1" && ! grep -q JANGADA_VALIDAR_MODELO=gemini "$1"' _ "$tmp/tmux.ambiente"
conferir "piloto: modelo e esforço chegam ao autor" \
  bash -c 'grep -q -- "--model gpt-6-luna" "$1" && grep -q model_reasoning_effort "$1"' _ "$tmp/tmux.comando"
rodar "$repo_jangada/bin/jangada-agente" --agente codex --projeto "$tmp/projeto" \
  --nome tarefa-sem-perfil --prompt "Implemente a tarefa" >"$tmp/saida" 2>&1
conferir "Codex sem perfil lança sessão nova" [ "$?" = 0 ]
conferir "Codex sem perfil cria sessão com agy" jq -e '.agente == "codex" and (has("perfil") | not) and .delegar == "agy" and .isolar' \
  "$tmp/state/jangada/agentes/projeto--tarefa-sem-perfil.json"
conferir "Codex sem perfil entrega protocolo com leitor e redator" grep -q 'inclusive leitor e redator' \
  "$tmp/state/jangada/agentes/protocolo-projeto--tarefa-sem-perfil.md"

rodar "$repo_jangada/bin/jangada-codex" -- codex >"$tmp/saida" 2>&1
conferir "adaptador sem isolamento recusa antes de chamar CLI" [ "$?" != 0 ]
conferir "recusa não executa Codex" test ! -e "$tmp/codex.args"

protocolo="$tmp/protocolo com espaço.md"
printf 'Regra com aspas: "texto"\nSegunda linha\n' >"$protocolo"
rodar JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ "$repo_jangada/bin/jangada-codex" --protocolo "$protocolo" -- codex --model modelo 'pedido com espaço'
conferir "adaptador executa Codex" [ "$?" = 0 ]
# Confere o TOML que o CLI realmente receberá, incluindo comandos dos hooks.
python3 - "$tmp/codex.args" "$protocolo" "$repo_jangada" "$tmp/state/jangada" <<'PY'
import pathlib, sys, tomllib
args = pathlib.Path(sys.argv[1]).read_bytes().decode().split("\0")[:-1]
cfg = {}
for i, arg in enumerate(args):
    if arg == "-c":
        cfg.update(tomllib.loads(args[i + 1]))
assert cfg["developer_instructions"] == pathlib.Path(sys.argv[2]).read_text()
assert cfg["approvals_reviewer"] == "user"
assert cfg["projects"][sys.argv[3]]["trust_level"] == "trusted"
assert "--no-daemon" in args and "workspace-write" in args and "on-request" in args
assert not any("bypass" in arg for arg in args)
# A raiz do estado é somente leitura no isolamento: como raiz gravável, a
# proteção interna do Codex não consegue montá-la e todo comando falha.
assert [args[i + 1] for i, arg in enumerate(args) if arg == "--add-dir"] == [sys.argv[4] + "/agentes"]
assert not any("writable_roots" in arg for arg in args)
assert args.count("pedido com espaço") == 1
hooks = {}
for i, arg in enumerate(args):
    if arg == "-c" and args[i + 1].startswith("hooks.") and not args[i + 1].startswith("hooks.state="):
        hooks.update(tomllib.loads(args[i + 1])["hooks"])
assert set(hooks) == {"SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
                      "PostToolUse", "PermissionRequest", "Stop", "Interrupt"}
assert all(h[0]["hooks"][0]["command"].startswith("'" + sys.argv[3] + "/bin/jangada-hook-codex'")
           for h in hooks.values())
assert len(cfg["hooks"]["state"]) == 8
PY
conferir "TOML, protocolo, permissões e hooks válidos" [ "$?" = 0 ]
uuid=0123abcd-4567-89ab-cdef-0123456789ab
rodar JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ "$repo_jangada/bin/jangada-codex" --conversa "$uuid" -- codex
conferir "retoma pelo UUID" python3 -c 'import pathlib,sys; a=pathlib.Path(sys.argv[1]).read_bytes().split(b"\0"); assert a[-3:-1]==[b"resume",sys.argv[2].encode()]' "$tmp/codex.args" "$uuid"
rodar JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ "$repo_jangada/bin/jangada-codex" --retomar -- codex
conferir "retomada sem UUID usa filtro da pasta" python3 -c 'import pathlib,sys; a=pathlib.Path(sys.argv[1]).read_bytes().split(b"\0"); assert a[-3:-1]==[b"resume",b"--last"]' "$tmp/codex.args"
rm -f "$tmp/codex.args"
rodar JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ FALSO_ANTIGO=1 "$repo_jangada/bin/jangada-codex" -- codex >"$tmp/saida" 2>&1
conferir "versão sem execução própria é recusada" [ "$?" != 0 ]
conferir "versão recusada não abre sessão" test ! -e "$tmp/codex.args"
rodar JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ "$repo_jangada/bin/jangada-codex" --conversa 'id; touch /tmp/invadido' -- codex >"$tmp/saida" 2>&1
conferir "UUID inválido é recusado" [ "$?" != 0 ]
conferir "UUID inválido não executa" test ! -e "$tmp/codex.args"

# Terminal real simulado: recusa, confirmação, retomada e troca de pasta.
rodar JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ python3 - "$repo_jangada" "$tmp" <<'PY'
import json, os, pathlib, pty, select, subprocess, sys, time, tomllib
repo, tmp = map(pathlib.Path, sys.argv[1:])
home = tmp / "codex"
config_before = (home / "config.toml").read_bytes()
saved = home / "jangada-confianca.json"
args_file = tmp / "codex.args"
args_file.unlink(missing_ok=True)
cmd = [str(repo / "bin/jangada-codex"), "--", "codex"]

def terminal(answer):
    master, slave = pty.openpty()
    proc = subprocess.Popen(cmd, cwd=tmp / "projeto", stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = b""
    sent = False
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 8192)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
                if b"[s/N]" in output and not sent:
                    os.write(master, answer.encode() + b"\n")
                    sent = True
            if proc.poll() is not None:
                break
        return proc.wait(timeout=2), output
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)

rc, output = terminal("n")
assert rc != 0 and b"[s/N]" in output
assert not saved.exists() and not args_file.exists()
rc, output = terminal("s")
assert rc == 0, output
folder = str((tmp / "projeto").resolve())
assert json.loads(saved.read_text()) == {"pasta": folder, "confiavel": True}
assert saved.stat().st_mode & 0o777 == 0o600
args = args_file.read_bytes().decode().split("\0")[:-1]
cfg = {}
for i, arg in enumerate(args):
    if arg == "-c":
        cfg.update(tomllib.loads(args[i + 1]))
assert cfg["projects"][folder]["trust_level"] == "trusted"
(tmp / "codex-confianca.args").write_bytes(args_file.read_bytes())
rc, output = terminal("n")
assert rc == 0 and b"[s/N]" not in output
args_file.unlink()
other = tmp / 'outra pasta "com aspas"'
other.mkdir()
proc = subprocess.run(cmd, cwd=other, stdin=subprocess.DEVNULL, capture_output=True)
assert proc.returncode != 0 and not args_file.exists()
saved.write_text('{"pasta": "outra", "confiavel": true}')
proc = subprocess.run(cmd, cwd=tmp / "projeto", stdin=subprocess.DEVNULL, capture_output=True)
assert proc.returncode != 0 and not args_file.exists()
assert (home / "config.toml").read_bytes() == config_before
PY
conferir "confiança exige confirmação, persiste por pasta e preserva configuração global" [ "$?" = 0 ]

rodar FALSO_HOOKS_NAO_CONFIADOS=1 FALSO_HOOKS_EXTERNOS=1 python3 - "$repo_jangada" "$tmp" "$codex_real" <<'PY'
import json, os, pathlib, pty, select, signal, subprocess, sys, time, tomllib
repo, tmp = map(pathlib.Path, sys.argv[1:3])
args = (tmp / "codex-confianca.args").read_bytes().decode().split("\0")[:-1]
hook_args = []
for i, arg in enumerate(args):
    if arg == "-c" and args[i + 1].startswith("hooks.") and not args[i + 1].startswith("hooks.state="):
        hook_args += ["-c", args[i + 1]]
saved = tmp / "hooks-aprovados.json"
helper = ["bash", str(repo / "bin/jangada-codex-hooks")]
command = helper + [str(tmp / "bin/codex"), str(saved)] + hook_args
proc = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True)
assert proc.returncode != 0 and not saved.exists()
def terminal(cmd, answer):
    master, slave = pty.openpty()
    proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = b""
    sent = False
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
                if b"[s/N]" in output and not sent:
                    os.write(master, answer.encode() + b"\n")
                    sent = True
            if proc.poll() is not None:
                break
        return proc.wait(timeout=2), output
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)
rc, output = terminal(command, "n")
assert rc != 0 and not saved.exists()
rc, output = terminal(command, "s")
assert rc == 0, output
states = json.loads(saved.read_text())
assert len(states) == 8 and "externo:nao-aprovado" not in states
assert saved.stat().st_mode & 0o777 == 0o600
rc, output = terminal(command, "n")
assert rc == 0 and b"[s/N]" not in output
cfg = tomllib.loads(output.decode().strip())
assert "externo:nao-aprovado" not in cfg["hooks"]["state"]
changed = command.copy()
changed[-1] = changed[-1].replace("concluido", "trabalhando")
rc, output = terminal(changed, "n")
assert rc != 0 and b"[s/N]" in output
assert json.loads(saved.read_text()) == states

os.environ["FALSO_HOOK_DESABILITADO"] = "1"
rc, output = terminal(command, "s")
assert rc == 0, output
cfg = tomllib.loads(next(line for line in output.decode().splitlines() if line.startswith("hooks.state=")))
assert cfg["hooks"]["state"]["teste:SessionStart"]["enabled"] is False
assert json.loads(saved.read_text())["teste:SessionStart"]["enabled"] is False
os.environ.pop("FALSO_HOOK_DESABILITADO")

if sys.argv[3]:
    # As mesmas definições aprovadas pelo helper precisam ser reconhecidas
    # como confiáveis pelo motor de hooks real, sem modificar config.toml.
    before = (tmp / "codex/config.toml").read_bytes()
    real_saved = tmp / "hooks-reais.json"
    real_command = helper + [sys.argv[3], str(real_saved)] + hook_args
    rc, output = terminal(real_command, "s")
    assert rc == 0, output
    state_arg = next(line for line in output.decode().splitlines() if line.startswith("hooks.state="))
    assert len(tomllib.loads(state_arg)["hooks"]["state"]) == 8
    session = "projeto--hook-real"
    live_state = tmp / "state/jangada/agentes" / (session + ".json")
    live_state.write_text(json.dumps({"estado": "iniciado", "raiz": str(repo)}))
    proc = subprocess.Popen([sys.argv[3], *hook_args, "-c", state_arg,
                             "-c", 'model_provider="teste"',
                             "-c", 'model_providers.teste={name="teste",base_url="http://127.0.0.1:9/v1",wire_api="responses",requires_openai_auth=false}',
                             "app-server", "--stdio"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env={**os.environ, "JANGADA_SESSAO": session},
                            start_new_session=True)
    buffer = b""
    def request(ident, method, params):
        global buffer
        proc.stdin.write(json.dumps({"id": ident, "method": method, "params": params}).encode() + b"\n")
        proc.stdin.flush()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                result = json.loads(line)
                if result.get("id") == ident:
                    assert "error" not in result, result
                    return result["result"]
            elif select.select([proc.stdout], [], [], 0.1)[0]:
                buffer += os.read(proc.stdout.fileno(), 65536)
        raise AssertionError("Codex não respondeu")
    try:
        request(1, "initialize", {"clientInfo": {"name": "jangada-test", "version": "1"},
                                  "capabilities": {"experimentalApi": True}})
        result = request(2, "hooks/list", {"cwds": [str(repo)]})
        hooks = [h for e in result["data"] for h in e["hooks"] if h["source"] == "sessionFlags"]
        assert len(hooks) == 8 and all(h["trustStatus"] == "trusted" for h in hooks)
        started = request(3, "thread/start", {"cwd": str(repo), "ephemeral": True,
                                            "sessionStartSource": "startup",
                                            "approvalPolicy": "never", "sandbox": "read-only"})
        # SessionStart roda no primeiro turno; o provedor local recusa sem consumir tokens.
        request(4, "turn/start", {"threadId": started["thread"]["id"],
                                  "input": [{"type": "text", "text": "teste"}]})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not json.loads(live_state.read_text()).get("conversa"):
            time.sleep(0.05)
        assert json.loads(live_state.read_text()).get("conversa") == started["thread"]["id"], json.loads(live_state.read_text())
        assert (tmp / "codex/config.toml").read_bytes() == before
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
PY
conferir "aprovação de hooks: recusa, persistência, mudança, externos e hashes no Codex real" [ "$?" = 0 ]

# O parser de -c do CLI divide a chave por pontos sem interpretar aspas
# TOML. Só verificar o argumento com tomllib não detecta esse comportamento.
if [[ -n "$codex_real" ]]; then
  python3 - "$codex_real" "$tmp" <<'PY'
import json, os, pathlib, select, signal, subprocess, sys, time
exe, tmp = sys.argv[1], pathlib.Path(sys.argv[2])
home = tmp / "codex-real"
home.mkdir()
config = home / "config.toml"
config.write_text("check_for_update_on_startup = false\n")
before = config.read_bytes()
project = tmp / 'projeto.com pontos "e aspas"'
project.mkdir()
args = (tmp / "codex-confianca.args").read_bytes().decode().split("\0")[:-1]
override = next(args[i + 1] for i, arg in enumerate(args)
                if arg == "-c" and args[i + 1].startswith("projects"))
override = override.replace(json.dumps(str((tmp / "projeto").resolve())), json.dumps(str(project)))
proc = subprocess.Popen([exe, "-c", override, "app-server", "--stdio"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, env={**os.environ, "CODEX_HOME": str(home)},
                        start_new_session=True)
buffer = b""
def request(ident, method, params):
    global buffer
    proc.stdin.write(json.dumps({"id": ident, "method": method, "params": params}).encode() + b"\n")
    proc.stdin.flush()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            result = json.loads(line)
            if result.get("id") == ident:
                assert "error" not in result, result
                return result["result"]
        elif select.select([proc.stdout], [], [], 0.1)[0]:
            chunk = os.read(proc.stdout.fileno(), 65536)
            assert chunk, "Codex encerrou sem responder"
            buffer += chunk
    raise AssertionError("Codex não respondeu em 10 segundos")
try:
    request(1, "initialize", {"clientInfo": {"name": "jangada-test", "version": "1"}})
    result = request(2, "config/read", {"includeLayers": False, "cwd": str(project)})
    assert result["config"]["projects"][str(project)]["trust_level"] == "trusted"
    assert config.read_bytes() == before
finally:
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=5)
PY
  conferir "Codex real reconhece confiança com pontos, espaços e aspas sem gravar configuração" [ "$?" = 0 ]
else
  echo "Codex CLI ausente; conferência do parser real ignorada"
fi

# Hooks não aprovam permissões, repetição não duplica eventos e subagentes
# não marcam o principal como concluído.
hook() {
  printf '%s' "$2" | rodar JANGADA_SESSAO=projeto--tarefa "$repo_jangada/bin/jangada-hook-codex" "$1" >"$tmp/hook.saida"
  conferir "hook $1 sai com 0" [ "$?" = 0 ]
}
hook inicio "{\"session_id\":\"$uuid\"}"
hook trabalhando '{}'
hook trabalhando '{}'
hook aguardando '{"tool_input":{"description":"permissão"}}'
conferir "pedido de permissão mantém saída vazia" test ! -s "$tmp/hook.saida"
conferir_da_sessao "permissão registra aguardando" jq -e '.estado == "aguardando"' "$tmp/state/jangada/agentes/projeto--tarefa.json"
hook concluido '{"agent_id":"filho"}'
conferir_da_sessao "subagente não conclui a sessão" jq -e '.estado == "aguardando"' "$tmp/state/jangada/agentes/projeto--tarefa.json"
hook trabalhando '{}'
hook concluido '{"last_assistant_message":"feito"}'
hook fim '{}'
conferir_da_sessao "conversa registrada" jq -e --arg c "$uuid" '.conversa == $c and .estado == "concluido"' "$tmp/state/jangada/agentes/projeto--tarefa.json"
conferir_da_sessao "eventos sem repetição" jq -se '[.[] | select(.agente == "codex" and .sessao == "projeto--tarefa") | .estado] == ["inicio", "trabalhando", "aguardando", "trabalhando", "concluido", "fim"]' "$tmp/state/jangada/eventos-agentes.jsonl"
antes="$(sha256sum "$tmp/state/jangada/agentes/projeto--tarefa.json")"
hook trabalhando 'não é JSON'
conferir "JSON inválido não altera o estado" [ "$(sha256sum "$tmp/state/jangada/agentes/projeto--tarefa.json")" = "$antes" ]
rm -f "$tmp/state/jangada/agentes/projeto--tarefa.json"
hook inicio '{}'
conferir "hook não recria sessão encerrada" test ! -e "$tmp/state/jangada/agentes/projeto--tarefa.json"

# Cópia da árvore: o comando registrado no Codex é o de bin/ e, chamado como
# o Codex chama, muda o estado da sessão.
arvore="$tmp/arvore"
mkdir -p "$arvore/bin" "$arvore/testes"
cp -a "$repo_jangada/bin" "$repo_jangada/agentes" "$repo_jangada/nucleo" "$repo_jangada/orquestracao" \
  "$repo_jangada/delegacao" "$repo_jangada/provedores" "$repo_jangada/validacao" "$arvore/"
cp "$repo_jangada/testes/falso-codex-hooks.py" "$arvore/testes/"
rm -f "$tmp/codex.args"
rodar JANGADA_CORE_PATH="$arvore" JANGADA_ISOLADO=1 JANGADA_MARCA_ISOLADO=/ "$arvore/bin/jangada-codex" -- codex >"$tmp/saida" 2>&1
conferir "adaptador executa pelo link" [ "$?" = 0 ]
python3 - "$tmp/codex.args" >"$tmp/hook-link.comando" <<'PY'
import pathlib, sys, tomllib
args = pathlib.Path(sys.argv[1]).read_bytes().decode().split("\0")[:-1]
arg = next(args[i + 1] for i, a in enumerate(args) if a == "-c" and args[i + 1].startswith("hooks.UserPromptSubmit="))
print(tomllib.loads(arg)["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"])
PY
conferir "hook registrado pela fachada, sem resolver o link" \
  [ "$(cat "$tmp/hook-link.comando")" = "'$arvore/bin/jangada-hook-codex' trabalhando" ]
jq -n --arg r "$tmp/projeto" '{estado: "novo", agente: "codex", raiz: $r}' >"$tmp/state/jangada/agentes/projeto--link.json"
printf '{}' | rodar JANGADA_CORE_PATH="$arvore" JANGADA_SESSAO=projeto--link sh -c "$(cat "$tmp/hook-link.comando")"
conferir "hook registrado muda o estado da sessão" jq -e '.estado == "trabalhando" and .atualizado' \
  "$tmp/state/jangada/agentes/projeto--link.json"
conferir "hook registrado grava o evento" jq -se 'any(.[]; .sessao == "projeto--link" and .estado == "trabalhando")' \
  "$tmp/state/jangada/eventos-agentes.jsonl"
mkdir -p "$tmp/pasta-falha" "$tmp/pasta-anexar"
FALSO_TMUX_FALHAR=1 rodar "$repo_jangada/bin/jangada-agente" --agente codex \
  --projeto "$tmp/pasta-falha" --direto >"$tmp/falha-sessao" 2>&1
conferir "falha do tmux recusa lançamento" [ "$?" != 0 ]
conferir "falha cancela a execução criada" python3 - "$tmp/state/jangada" <<'PY'
from pathlib import Path
import sqlite3
import sys
linhas = []
for p in Path(sys.argv[1]).glob('agentes/projetos/*/tarefas.sqlite'):
    with sqlite3.connect(p) as db:
        linhas += db.execute("SELECT status FROM execucoes WHERE sessao='pasta-falha'").fetchall()
assert linhas == [('CANCELLED',)], linhas
PY
mkdir -p "$tmp/recusa-bin"
cat >"$tmp/recusa-bin/python3" <<'EOF'
#!/usr/bin/env bash
if [[ " $* " == *"/nucleo/cli.py "* && " $* " == *" sessao-iniciar "* ]]; then
  echo "política alterada depois da conferência" >&2
  exit 2
fi
exec "$PYTHON_REAL" "$@"
EOF
chmod +x "$tmp/recusa-bin/python3"
for nome_recusa in recusa-nova tarefa; do
  rodar PATH="$tmp/recusa-bin:$tmp/bin:$PATH" PYTHON_REAL="$(command -v python3)" \
    "$repo_jangada/bin/jangada-agente" --agente codex --projeto "$tmp/projeto" \
    --nome "$nome_recusa" >"$tmp/recusa-registro" 2>&1
  conferir "falha de registro recusa lançamento ($nome_recusa)" [ "$?" != 0 ]
  conferir "falha de registro preserva causa ($nome_recusa)" grep -q 'política alterada' "$tmp/recusa-registro"
  conferir "falha de registro explica recusa ($nome_recusa)" grep -q 'não foi possível registrar' "$tmp/recusa-registro"
done
conferir "falha remove worktree novo" test ! -e "$tmp/worktrees/projeto/recusa-nova"
conferir "falha remove ramo novo" test -z "$(git -C "$tmp/projeto" branch --list agente/recusa-nova)"
conferir_da_sessao "falha preserva worktree reaproveitado" test -f "$tmp/worktrees/projeto/tarefa/.git"
conferir_da_sessao "falha preserva ramo reaproveitado" git -C "$tmp/projeto" show-ref --verify --quiet refs/heads/agente/tarefa
printf '{"orcamento":{"chamadas":1}}\n' >"$tmp/politica.json"
rodar "$repo_jangada/bin/jangada-projeto" --projeto "$tmp/pasta-anexar" \
  cadastrar --politica "$tmp/politica.json" >/dev/null
rodar "$repo_jangada/bin/jangada-agente" --agente codex \
  --projeto "$tmp/pasta-anexar" --direto >"$tmp/recusa-orcamento" 2>&1
conferir "orçamento recusa nova sessão interativa" [ "$?" != 0 ]
conferir "recusa orienta conferir política e usar fila controlada" \
  grep -q 'confira a política e o orçamento. Use a fila' "$tmp/recusa-orcamento"
FALSO_TMUX_EXISTENTE=1 rodar "$repo_jangada/bin/jangada-agente" --agente codex \
  --projeto "$tmp/pasta-anexar" --direto >"$tmp/anexar" 2>&1
conferir "sessão existente reanexa sem conferir orçamento de nova sessão" [ "$?" = 0 ]
((falhas == 0))
