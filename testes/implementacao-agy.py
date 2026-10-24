#!/usr/bin/env python3
"""Percurso sintético completo, sem modelos remotos, e negativos do contrato."""

import importlib.util
import argparse
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import subprocess
import signal
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("implementacao", REPO / "delegacao/implementacao.py")
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


class Implementacao(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.raiz = self.tmp / "projeto"
        self.raiz.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.casa = self.tmp / "casa"
        cfg = self.casa / ".gemini/config"
        cfg.mkdir(parents=True)
        cli = self.casa / ".gemini/antigravity-cli"
        cli.mkdir()
        agentes = self.tmp / "agentes/implementador"
        agentes.mkdir(parents=True)
        (agentes / "agent.md").write_text((REPO / "agentes/agy/agents/implementador/agent.md").read_text())
        (cfg / "agents.json").write_text(json.dumps({"entries": [{"path": str(agentes.parent)}]}))
        (cli / "settings.json").write_text(json.dumps({"trustedWorkspaces": [str(self.raiz)]}))
        (self.raiz / "dados.txt").write_text("valor=1\n")
        (self.raiz / "fonte.txt").write_text("Critério: valor deve ser 2\n")
        self.git("init", "-q")
        self.git("add", "dados.txt", "fonte.txt")
        self.git("-c", "user.name=Teste", "-c", "user.email=t@t", "commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("JANGADA_", "XDG_"))}
        self.env.pop("DBUS_SESSION_BUS_ADDRESS", None)
        self.env.update(HOME=str(self.casa), PATH=str(self.bin) + ":/usr/bin:/bin", JANGADA_CORE_PATH=str(REPO),
                        XDG_STATE_HOME=str(self.tmp / "estado"), JANGADA_ESTADO=str(self.tmp / "estado/jangada"), XDG_CONFIG_HOME=str(self.tmp / "config"),
                        XDG_CACHE_HOME=str(self.tmp / "cache"), JANGADA_SESSAO="sintetica")
        self.script("agy", '''import json,sys
if sys.argv[1:] == ["agents"]: print("implementador"); sys.exit()
if "/usage" in sys.argv:
 print(json.dumps({"command":{"data":{"groups":[{"buckets":[{"id":"gemini-weekly","remaining_fraction":0.9}]}]}}})); sys.exit()
print(json.dumps({"status":"SUCCESS","response":"dados.txt:1 valor atualizado","conversation_id":"sintetica"}))
''')
        # Imita apenas o cliente e a montagem. O teste de kernel é separado.
        self.script("bwrap", '''import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
alvos=[(Path(args[i+1]),args[i+2]) for i,x in enumerate(args) if x=="--bind"]
assert len(alvos) in (1,2), args
assert all("/arquivos/" in str(a) for a,b in alvos), args
assert all(a.parent.name=="arquivos" and a.name in ("dados.txt","novo.txt") for a,b in alvos), args
pasta=alvos[0][0].parent
modo=os.environ.get("FALSO_MODO","")
if modo=="prazo": time.sleep(4)
if modo=="falha": sys.exit(7)
if modo=="cota":
 sys.stderr.write("x"*1000000+"RESOURCE_EXHAUSTED"); sys.exit(7)
alvos[0][0].write_text("valor=2\\n")
if modo=="fora": (pasta/"indevido.txt").write_text("fora")
if modo=="link":
 alvos[0][0].unlink(); alvos[0][0].symlink_to(pasta/"fonte.txt")
if modo=="hardlink":
 alvos[0][0].unlink(); os.link(pasta/"fonte.txt", alvos[0][0])
print(json.dumps({"status":"SUCCESS","response":"dados.txt:1 valor atualizado","conversation_id":"sintetica"}))
''')

    def script(self, nome, codigo):
        p = self.bin / nome
        p.write_text("#!/usr/bin/python3\n" + codigo)
        p.chmod(0o755)

    def test_pesquisa_autoriza_so_dominio_na_copia(self):
        settings = self.casa / ".gemini/antigravity-cli/settings.json"
        original = {"trustedWorkspaces": [str(self.raiz)],
                    "permissions": {"allow": ["command(cp)"], "deny": ["read_url(negado.example)"]}}
        settings.write_text(json.dumps(original))
        registro = Path(self.env["JANGADA_ESTADO"]) / "agentes/pesquisa-teste"
        registro.parent.mkdir(parents=True)

        def conferir(comando, **_):
            self.assertEqual(comando[0], "bwrap")
            destino = str(settings)
            i = comando.index(destino)
            runtime = Path(comando[i-1]).parent
            self.assertEqual(runtime.parent, registro.parent)
            self.assertFalse(runtime.is_relative_to(registro))
            privado = json.loads(Path(comando[i-1]).read_text())
            self.assertEqual(privado["permissions"], {"allow": ["read_url(ai.google.dev)"],
                                                     "deny": ["read_url(negado.example)"]})
            self.assertIn(["--tmpfs", str(self.raiz)], [comando[i:i+2] for i in range(len(comando)-1)])
            self.assertIn(["--tmpfs", str(self.casa)], [comando[i:i+2] for i in range(len(comando)-1)])
            self.assertNotIn("--dangerously-skip-permissions", comando)
            return subprocess.CompletedProcess(comando, 0)

        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(Path, "home", return_value=self.casa), \
                mock.patch.object(Path, "cwd", return_value=self.raiz), \
                mock.patch.object(modulo.subprocess, "run", side_effect=conferir), \
                self.assertRaises(SystemExit) as fim:
            modulo.pesquisa(["--registro", str(registro), "--url", "https://ai.google.dev/gemini-api/docs",
                             "--", "agy", "-p", "Busque e abra a documentação"])
        self.assertEqual(fim.exception.code, 0)
        self.assertEqual(json.loads(settings.read_text()), original)
        self.assertEqual(list(registro.parent.glob("apoio-runtime-*")), [])

    def test_pesquisa_respeita_settings_explicitamente_selecionado(self):
        padrao = self.casa / ".gemini/antigravity-cli/settings.json"
        original = {"trustedWorkspaces": [], "permissions": {"deny": ["read_url(outro.example)"]}}
        padrao.write_text(json.dumps(original))
        alternativo = self.tmp / "settings-alternativo.json"
        escolhido = {"trustedWorkspaces": [str(self.raiz)],
                     "permissions": {"deny": ["read_url(negado.example)"]}}
        alternativo.write_text(json.dumps(escolhido))
        registro = Path(self.env["JANGADA_ESTADO"]) / "agentes/pesquisa-settings"
        registro.parent.mkdir(parents=True)

        def conferir(comando, **_):
            i = comando.index(str(padrao))
            privado = json.loads(Path(comando[i-1]).read_text())
            self.assertEqual(privado["permissions"]["deny"], escolhido["permissions"]["deny"])
            return subprocess.CompletedProcess(comando, 0)

        ambiente = dict(self.env, JANGADA_AGY_SETTINGS=str(alternativo))
        argumentos = ["--registro", str(registro), "--url", "https://ai.google.dev/docs", "--", "agy", "-p", "Leia"]
        with mock.patch.dict(os.environ, ambiente, clear=True), \
                mock.patch.object(Path, "home", return_value=self.casa), \
                mock.patch.object(Path, "cwd", return_value=self.raiz), \
                mock.patch.object(modulo.subprocess, "run", side_effect=conferir) as chamada:
            with self.assertRaises(SystemExit) as fim:
                modulo.pesquisa(argumentos)
            self.assertEqual(fim.exception.code, 0)
            chamada.assert_called_once()
            alternativo.write_text(json.dumps({"trustedWorkspaces": []}))
            argumentos[1] += "-negado"
            with self.assertRaisesRegex(ValueError, "confiança existente"):
                modulo.pesquisa(argumentos)
            chamada.assert_called_once()
            self.assertFalse(Path(argumentos[1]).exists())
        self.assertEqual(json.loads(padrao.read_text()), original)
        self.assertEqual(json.loads(alternativo.read_text()), {"trustedWorkspaces": []})

    def test_pesquisa_nao_cria_registro_com_settings_invalidos(self):
        settings = self.tmp / "settings-invalido.json"
        ambiente = dict(self.env, JANGADA_AGY_SETTINGS=str(settings))
        registros = Path(self.env["JANGADA_ESTADO"]) / "agentes"
        registros.mkdir(parents=True)
        for i, conteudo in enumerate((None, "{", json.dumps({"trustedWorkspaces": []}))):
            registro = registros / ("pesquisa-negada-" + str(i))
            with self.subTest(conteudo=conteudo):
                if conteudo is not None:
                    settings.write_text(conteudo)
                with mock.patch.dict(os.environ, ambiente, clear=True), \
                        mock.patch.object(Path, "home", return_value=self.casa), \
                        mock.patch.object(Path, "cwd", return_value=self.raiz), \
                        mock.patch.object(modulo.subprocess, "run") as chamada:
                    with self.assertRaises((ValueError, OSError)):
                        modulo.pesquisa(["--registro", str(registro), "--url", "https://ai.google.dev/docs",
                                         "--", "agy", "-p", "Leia"])
                    chamada.assert_not_called()
                self.assertFalse(registro.exists())

    def test_pesquisa_rejeita_enderecos_locais_credenciais_e_portas(self):
        for url in ("http://ai.google.dev", "https://localhost/x", "https://127.0.0.1/",
                    "https://nas-casa/", "https://roteador-admin/", "https://impressora.local/",
                    "https://git.internal/", "https://servidor.lan/", "https://host.home.arpa/",
                    "https://home.arpa/", "https://sub.localhost/", "https://[::1]/",
                    "https://[2001:db8::1]/", "https://dominio.123/", "https://-site.example/",
                    "https://u:p@ai.google.dev/", "https://ai.google.dev:443/", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                modulo.dominios_pesquisa([url])

    def test_pesquisa_aceita_subdominio_publico_com_hifen(self):
        self.assertEqual(modulo.dominios_pesquisa(["https://DOCS-API.Example.com/guia"]), ["docs-api.example.com"])

    def test_pesquisa_le_so_corpo_baixado_da_propria_conversa(self):
        corpo = self.casa / ".gemini/antigravity-cli/brain/conversa/.system_generated/steps/4/content.md"
        corpo.parent.mkdir(parents=True)
        corpo.write_text("documentação pública")
        for alvo, conversa, decisao in ((corpo, "conversa", "ask"),
                                       (corpo, "outra", "deny"),
                                       (self.raiz / "fonte.txt", "conversa", "deny")):
            evento = {"conversationId": conversa, "toolCall": {"args": {"AbsolutePath": str(alvo)}}}
            p = subprocess.run(["python3", "-c", modulo.GANCHO_PESQUISA], env=self.env,
                               input=json.dumps(evento), capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(p.stdout)["decision"], decisao)
        corpo.unlink()
        corpo.symlink_to(self.raiz / "fonte.txt")
        p = subprocess.run(["python3", "-c", modulo.GANCHO_PESQUISA], env=self.env,
                           input=json.dumps({"conversationId": "conversa", "toolCall": {
                               "args": {"AbsolutePath": str(corpo)}}}), capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(p.stdout)["decision"], "deny")

    def test_leitura_remota_recebe_apenas_faixa_sem_ferramentas(self):
        fonte = self.raiz / "fonte.txt"
        fonte.write_text("público\nnão autorizado nesta faixa\n")
        registro = Path(self.env["JANGADA_ESTADO"]) / "agentes/leitura-teste"
        registro.parent.mkdir(parents=True)

        def conferir(comando, **_):
            texto = comando[comando.index("-p")+1]
            self.assertIn("Fonte: " + str(fonte) + "\n1: público", texto)
            self.assertNotIn("não autorizado nesta faixa", texto)
            i = comando.index("/tmp/jangada-pesquisa-agentes")
            papel = (Path(comando[i-1]) / "leitor/agent.md").read_text()
            self.assertIn("tools: []", papel)
            self.assertIn("inheritMcp: false", papel)
            return subprocess.CompletedProcess(comando, 0)

        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(Path, "home", return_value=self.casa), \
                mock.patch.object(Path, "cwd", return_value=self.raiz), \
                mock.patch.object(modulo.subprocess, "run", side_effect=conferir), \
                self.assertRaises(SystemExit):
            modulo.pesquisa(["--registro", str(registro), "--papel", "leitor", "--fonte", str(fonte)+":1-1",
                             "--", "agy", "-p", "Leia a fonte"])

    def test_fontes_aceitam_acento_espaco_e_sufixo_literal(self):
        for nome in ("relatório final.txt", "literal.txt:1-1"):
            fonte = self.raiz / nome
            fonte.write_text("primeira\nsegunda\n")
            texto = modulo.texto_fontes([str(fonte)])
            self.assertIn("Fonte: " + str(fonte), texto)
            self.assertIn("2: segunda", texto)

    def test_fontes_abrem_sem_seguir_links_e_rejeitam_arquivo_especial(self):
        fonte = self.raiz / "fonte.txt"
        abrir = os.open
        with mock.patch.object(modulo.os, "open", wraps=abrir) as chamada:
            modulo.texto_fontes([str(fonte)])
            self.assertTrue(chamada.call_args.args[1] & os.O_NOFOLLOW)
        link = self.raiz / "atalho.txt"
        link.symlink_to(fonte)
        with self.assertRaises(ValueError):
            modulo.texto_fontes([str(link)])
        link.unlink()
        os.mkfifo(link)
        with self.assertRaises(ValueError):
            modulo.texto_fontes([str(link)])

    def test_conferencia_recusa_faixa_antes_de_executar_modelo(self):
        registro = self.tmp / "registro-ausente"
        argumentos = ["--registro", str(registro), "--conferir", "--papel", "leitor",
                      "--fonte", str(self.raiz / "fonte.txt"), "--", "agy", "-p", "Leia"]
        with mock.patch.object(modulo.subprocess, "run") as chamada:
            modulo.pesquisa(argumentos)
            chamada.assert_not_called()
            self.assertFalse(registro.exists())
            argumentos[argumentos.index("--fonte")+1] += ":9-10"
            with self.assertRaises(modulo.EntradaApoioInvalida):
                modulo.pesquisa(argumentos)
            chamada.assert_not_called()

    def test_apoio_fronteira_real_sem_modelo_remoto(self):
        capacidade = subprocess.run(["/usr/bin/bwrap", "--ro-bind", "/", "/", "--unshare-pid", "true"],
                                    capture_output=True)
        if capacidade.returncode:
            self.skipTest("Bubblewrap indisponível")
        (self.bin / "bwrap").unlink()
        self.script("agy", '''import json,sys
from pathlib import Path
if sys.argv[1:] == ["agents"]: print("pesquisador"); sys.exit()
cfg=Path.home()/".gemini"
cli=cfg/"antigravity-cli"
settings=json.loads((cli/"settings.json").read_text())
assert settings["permissions"]["allow"]==["read_url(ai.google.dev)"]
assert not list(cli.glob("*runtime-*"))
assert not [p for p in cli.rglob("*") if p.name in ("hooks.json","agents.json","agent.md","gancho.py")]
for alvo in (cli/"settings.json", cfg/"config/hooks.json", cfg/"config/agents.json",
             Path("/tmp/jangada-pesquisa-agentes/pesquisador/agent.md"), Path("/tmp/jangada-pesquisa-gancho.py")):
 try:
  with alvo.open("r+b"): pass
 except OSError: pass
 else: raise AssertionError("controle gravável: "+str(alvo))
assert not Path("fonte.txt").exists()
assert not Path(".git").exists()
assert not (Path.home()/"segredo.txt").exists()
assert json.loads((cfg/"config/hooks.json").read_text())["jangada-pesquisa"]["PreToolUse"][0]["matcher"] == "view_file"
print(json.dumps({"status":"SUCCESS","response":"fronteira conferida sem modelo"}))
''')
        (self.casa / "segredo.txt").write_text("privado")
        registro = Path(self.env["JANGADA_ESTADO"]) / "agentes/pesquisa-real"
        registro.parent.mkdir(parents=True)
        p = subprocess.run(["python3", str(REPO / "delegacao/implementacao.py"), "pesquisa",
                            "--registro", str(registro), "--url", "https://ai.google.dev/gemini-api/docs",
                            "--", "agy", "-p", "Pesquise"], cwd=self.raiz, env=self.env,
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(json.loads(p.stdout)["status"], "SUCCESS")
        self.assertEqual(list(registro.parent.glob("apoio-runtime-*")), [])

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.raiz), *args], text=True)

    def chamar(self, *args, sucesso=True):
        p = subprocess.run([str(REPO / "bin/jangada-delegar"), *args], cwd=self.raiz,
                           env=self.env, capture_output=True, text=True, timeout=20)
        if sucesso:
            self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout)
        return p

    def executar(self, *extras, sucesso=True):
        return self.chamar("implementador", "Mudar valor para 2", "--permitir-remoto", "--base", self.base,
                           "--arquivos", "fonte.txt", "--permitidos", "dados.txt", "--criterio",
                           "O teste do autor exige valor=2", *extras, sucesso=sucesso)

    def test_percurso_autor_executor_aceite_teste(self):
        resultado = json.loads(self.executar().stdout)
        self.assertEqual(resultado["estado"], "aguarda_autor")
        self.assertEqual((self.raiz / "dados.txt").read_text(), "valor=1\n")
        pasta = Path(resultado["pasta"])
        self.assertEqual((pasta / "arquivos/dados.txt").read_text(), "valor=2\n")
        contrato = json.loads((pasta / "contrato.json").read_text())
        self.assertEqual(contrato["base"], self.base)
        self.assertEqual(contrato["modelo"], modulo.MODELO)
        aceite = self.chamar("--aceitar", resultado["id"], "--base", self.base, "--entrega", resultado["entrega"])
        self.assertEqual(json.loads(aceite.stdout)["estado"], "aceita_pelo_autor")
        teste = subprocess.run(["python3", "-c", "from pathlib import Path; assert Path('dados.txt').read_text()=='valor=2\\n'"],
                               cwd=self.raiz, capture_output=True)
        self.assertEqual(teste.returncode, 0)
        self.assertEqual(self.git("diff", "--name-only").strip(), "dados.txt")
        self.assertFalse((pasta / ".aprovado").exists())
        global_md = (self.tmp / "agentes/implementador/agent.md").read_text()
        privado_md = (pasta / "runtime/agentes/implementador/agent.md").read_text()
        for ferramenta in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
            self.assertNotIn("  - " + ferramenta, global_md)
            self.assertIn("  - " + ferramenta, privado_md)
        self.assertIn("subagent: true", global_md)
        self.assertIn("subagent: false", privado_md)

    def test_resultado_alterado_nao_aceito(self):
        r = json.loads(self.executar().stdout)
        (Path(r["pasta"]) / "arquivos/dados.txt").write_text("alterado")
        self.chamar("--aceitar", r["id"], "--base", self.base, "--entrega", r["entrega"], sucesso=False)
        self.assertEqual((self.raiz / "dados.txt").read_text(), "valor=1\n")

    def test_artefatos_fora_do_git_mesmo_com_jangada_versionada(self):
        (self.raiz / ".jangada").mkdir()
        (self.raiz / ".jangada/validar.sh").write_text("true\n")
        self.git("add", ".jangada/validar.sh")
        self.git("-c", "user.name=Teste", "-c", "user.email=t@t", "commit", "-qm", "portão")
        self.base = self.git("rev-parse", "HEAD").strip()
        resultado = json.loads(self.executar().stdout)
        pasta = Path(resultado["pasta"])
        self.assertTrue(pasta.is_relative_to(self.tmp / "estado/jangada/agentes/implementacoes"))
        self.assertFalse(pasta.is_relative_to(self.raiz))
        self.git("add", "-A")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_preparacao_invalida_preserva_falha_terminal(self):
        args = argparse.Namespace(base=self.base, permitidos=["dados.txt"], novos=[],
                                  arquivos=["fonte.txt"], pedido="atividade", criterio=["valor=2"], prazo=30)
        registro = self.casa / ".gemini/config/agents.json"
        valido = registro.read_text()
        for falha in ("path", "JANGADA_CORE_PATH"):
            with self.subTest(falha=falha):
                registro.write_text('{"entries":[{}]}' if falha == "path" else valido)
                ambiente = dict(self.env)
                if falha == "JANGADA_CORE_PATH":
                    ambiente.pop("JANGADA_CORE_PATH")
                saida = io.StringIO()
                with mock.patch.dict(os.environ, ambiente, clear=True), \
                        mock.patch.object(Path, "home", return_value=self.casa), \
                        contextlib.redirect_stdout(saida), self.assertRaises(KeyError):
                    modulo.executar(args, self.raiz)
                resultado = json.loads(saida.getvalue())
                estado = json.loads((Path(resultado["pasta"]) / "estado.json").read_text())
                self.assertEqual(estado["estado"], "falhou")
                self.assertIn(falha, estado["diagnostico"])
                self.assertNotIn("entrega", estado)

    def test_dns_resolvido_em_run_volta_somente_leitura(self):
        resultado = json.loads(self.executar().stdout)
        resolver = Path.resolve
        def resolvido(pasta, *args, **kwargs):
            if str(pasta) == "/etc/resolv.conf":
                return Path("/run/systemd/resolve/stub-resolv.conf")
            return resolver(pasta, *args, **kwargs)
        with mock.patch.dict(os.environ, self.env), mock.patch.object(Path, "resolve", resolvido):
            args = modulo.montagem(str(Path(resultado["pasta"]) / "contrato.json"))
        dns = "/run/systemd/resolve/stub-resolv.conf"
        indice = args.index(dns)
        self.assertEqual(args[indice-1:indice+2], ["--ro-bind", dns, dns])
        self.assertLess(args.index("/run"), indice)

    def test_config_do_agy_grava_so_projects(self):
        resultado = json.loads(self.executar().stdout)
        with mock.patch.dict(os.environ, self.env):
            args = modulo.montagem(str(Path(resultado["pasta"]) / "contrato.json"))
        cfg = str(self.casa / ".gemini/config")
        runtime = Path(resultado["pasta"]) / "runtime/config"
        pares = [args[i:i+2] for i in range(len(args) - 1)]
        self.assertIn(["--tmpfs", cfg], pares)
        for nome in ("agents.json", "hooks.json"):
            indice = args.index(cfg + "/" + nome)
            self.assertEqual(args[indice-2:indice+1], ["--ro-bind", str(runtime / nome), cfg + "/" + nome])
        projetos = args.index(cfg + "/projects")
        self.assertEqual(args[projetos-1], "--tmpfs")
        self.assertLess(args.index(cfg), projetos)
        self.assertEqual(args[projetos+1:projetos+3], ["--remount-ro", cfg])
        self.assertNotIn(["--ro-bind", str(runtime), cfg], pares)

    def test_escrita_liberada_so_nos_permitidos(self):
        resultado = json.loads(self.executar().stdout)
        pasta = Path(resultado["pasta"])
        contrato = json.loads((pasta / "contrato.json").read_text())
        settings = json.loads((pasta / "runtime/settings.json").read_text())
        escrita = [r for r in settings["permissions"]["allow"] if r.startswith("write_file(")]
        self.assertEqual(escrita, ["write_file(" + str(Path(contrato["raiz"]) / nome) + ")"
                                   for nome in contrato["permitidos"]])

    def test_perfil_isolamento_limita_keyring_e_limpa_ambiente(self):
        resultado = json.loads(self.executar().stdout)
        manifesto = str(Path(resultado["pasta"]) / "contrato.json")
        ambiente = {**self.env, "JANGADA_ISOLAR_PERFIL": "implementacao",
                    "JANGADA_IMPLEMENTACAO_MANIFESTO": manifesto}
        comando = [str(REPO / "bin/jangada-isolar")]
        mostrar = subprocess.run([*comando, "--mostrar", "--", "agy"], cwd=self.raiz,
                                 env=ambiente, capture_output=True, text=True)
        self.assertEqual(mostrar.returncode, 0, mostrar.stderr)
        self.assertIn("--clearenv", mostrar.stdout.splitlines())
        self.assertNotIn("--bind\n" + str(self.raiz), mostrar.stdout)
        runtime = self.tmp / "run"
        runtime.mkdir()
        politica = self.tmp / "proxy.args"
        self.script("xdg-dbus-proxy", "import sys\nfrom pathlib import Path\nPath(" +
                    repr(str(politica)) + ").write_text('\\n'.join(sys.argv[1:]))\nprint('x')")
        self.script("gdbus", "print(\"'/org/freedesktop/secrets/collection/cofre/7'\")")
        ambiente.update(XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS="unix:path=/inexistente")
        recusa = subprocess.run([*comando, "--", "agy"], cwd=self.raiz, env=ambiente,
                                input="", capture_output=True, text=True)
        self.assertNotEqual(recusa.returncode, 0)
        self.assertIn("exige atributos de keyring", recusa.stderr)
        self.assertFalse(politica.exists())
        ambiente["JANGADA_ISOLAR_KEYRING_ITEM"] = "service=agy-teste"
        processo = subprocess.run([*comando, "--", "agy"], cwd=self.raiz, env=ambiente,
                                  input="", capture_output=True, text=True)
        self.assertEqual(processo.returncode, 0, processo.stderr)
        chamadas = politica.read_text()
        self.assertIn("org.freedesktop.Secret.Item.GetSecret@/org/freedesktop/secrets/collection/cofre/7", chamadas)
        self.assertNotIn("CreateItem", chamadas)
        self.assertNotIn("=*@", chamadas)
        self.assertNotIn("--talk=org.freedesktop.secrets", chamadas)

    def test_base_divergente_e_arquivo_do_autor_alterado(self):
        r = json.loads(self.executar().stdout)
        self.chamar("--aceitar", r["id"], "--base", "0" * 40, "--entrega", r["entrega"], sucesso=False)
        (self.raiz / "dados.txt").write_text("edição concorrente")
        self.chamar("--aceitar", r["id"], "--base", self.base, "--entrega", r["entrega"], sucesso=False)
        self.assertEqual((self.raiz / "dados.txt").read_text(), "edição concorrente")

    def test_negativos_da_entrega(self):
        diagnosticos = {"fora": "arquivos fora do contrato", "link": "link recusado",
                       "hardlink": "link recusado", "falha": "delegação recusada ou falhou"}
        for modo in ("fora", "link", "hardlink", "falha", "prazo"):
            with self.subTest(modo=modo):
                self.env["FALSO_MODO"] = modo
                extras = ("--prazo", "1") if modo == "prazo" else ()
                p = self.executar(*extras, sucesso=False)
                resultado = json.loads(p.stdout)
                if modo == "prazo":
                    self.assertEqual(resultado["estado"], "interrompida")
                    self.assertEqual(resultado["codigo"], 124)
                else:
                    self.assertEqual(resultado["estado"], "falhou")
                    self.assertIn(diagnosticos[modo], resultado["diagnostico"])
                self.assertNotIn("entrega", resultado)
                self.assertEqual((self.raiz / "dados.txt").read_text(), "valor=1\n")

    def test_ajuda_preserva_opcoes_de_leitura(self):
        p = self.chamar("--help", sucesso=False)
        for opcao in ("--requisito", "--extrair", "--permitir-remoto", "implementador"):
            self.assertIn(opcao, p.stderr)

    def test_caminhos_modelo_e_concorrencia_recusados(self):
        for nome in ("/tmp/fora", "../fora", "x/../../fora", ".git/config", "x//y"):
            self.executar("--permitidos", nome, sucesso=False)
        self.executar("--modelo", "gemini-outro", sucesso=False)
        with mock.patch.dict(os.environ, self.env):
            pasta = modulo.pasta_execucoes(self.raiz)
        fd = modulo.trava(pasta)
        try:
            self.executar(sucesso=False)
        finally:
            os.close(fd)

    def test_trava_global_cota_desconhecida_e_papel_ausente(self):
        estado = self.tmp / "estado/jangada/agentes"
        estado.mkdir(parents=True)
        with (estado / ".agy-execucao.lock").open("w") as arq:
            fcntl.flock(arq, fcntl.LOCK_EX | fcntl.LOCK_NB)
            p = self.executar(sucesso=False)
            self.assertEqual(json.loads(p.stdout)["motivo_codigo"], "execucao_ocupada")
        self.script("agy", 'import sys; print("implementador" if sys.argv[1:]==["agents"] else "{}")')
        p = self.executar(sucesso=False)
        self.assertEqual(json.loads(p.stdout)["motivo_codigo"], "cota_desconhecida")
        self.script("agy", 'print("leitor")')
        p = self.executar(sucesso=False)
        self.assertEqual(json.loads(p.stdout)["motivo_codigo"], "capacidade_incompativel")

    def test_arquivo_novo_escopo_exato(self):
        r = json.loads(self.executar("--permitidos", "dados.txt", "novo.txt", "--novos", "novo.txt").stdout)
        self.chamar("--aceitar", r["id"], "--base", self.base, "--entrega", r["entrega"])
        self.assertTrue((self.raiz / "novo.txt").is_file())
        self.assertEqual(self.git("status", "--short", "dados.txt", "novo.txt").splitlines(),
                         [" M dados.txt", "?? novo.txt"])

    def test_erro_do_executor_aguarda_captura_e_preserva_cota(self):
        self.env["FALSO_MODO"] = "cota"
        p = self.executar(sucesso=False)
        self.assertEqual(json.loads(p.stdout)["motivo_codigo"], "cota_insuficiente")

    def test_filho_do_catalogo_nao_herda_trava(self):
        pid_arquivo = self.tmp / "filho.pid"
        original = (self.bin / "agy").read_text().split("\n", 1)[1]
        prefixo = ("import subprocess,sys\nfrom pathlib import Path\n"
                   "if sys.argv[1:] == ['agents']:\n"
                   " filho=subprocess.Popen(['sleep','5'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                   " Path(" + repr(str(pid_arquivo)) + ").write_text(str(filho.pid))\n")
        self.script("agy", prefixo + original)
        try:
            self.executar()
            with (self.tmp / "estado/jangada/agentes/.agy-execucao.lock").open() as arq:
                fcntl.flock(arq, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if pid_arquivo.exists():
                try:
                    os.kill(int(pid_arquivo.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_submodulo_e_link_na_base_recusados(self):
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",modulo")
        (self.raiz / "atalho").symlink_to("fonte.txt")
        self.git("add", "atalho")
        self.git("-c", "user.name=Teste", "-c", "user.email=t@t", "commit", "-qm", "links")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.executar("--permitidos", "modulo/novo.txt", "--novos", "modulo/novo.txt", sucesso=False)
        self.executar("--arquivos", "atalho", sucesso=False)

    def test_devolver_preserva_artefato(self):
        r = json.loads(self.executar().stdout)
        p = self.chamar("--devolver", r["id"], "--base", self.base, "--motivo", "critério incompleto")
        self.assertEqual(json.loads(p.stdout)["estado"], "devolvida")
        self.assertTrue((Path(r["pasta"]) / "arquivos/dados.txt").exists())

    def test_fronteira_real_sem_modelo_remoto(self):
        capacidade = subprocess.run(["/usr/bin/bwrap", "--ro-bind", "/", "/", "--unshare-pid", "true"],
                                    capture_output=True)
        if capacidade.returncode:
            self.skipTest("Bubblewrap indisponível: " + capacidade.stderr.decode()[:200])
        (self.bin / "bwrap").unlink()
        self.script("agy", '''import json,sys
from pathlib import Path
if sys.argv[1:] == ["agents"]: print("implementador"); sys.exit()
if "/usage" in sys.argv:
 print(json.dumps({"command":{"data":{"groups":[{"buckets":[{"id":"gemini-weekly","remaining_fraction":0.9}]}]}}})); sys.exit()
Path("dados.txt").write_text("valor=2\\n")
for alvo in ("fonte.txt", "indevido.txt", "../outra-tarefa.txt", ".git/config"):
 try: Path(alvo).write_text("indevido")
 except OSError: pass
 else: raise AssertionError("fronteira liberou " + alvo)
assert not Path(".git").exists()
print(json.dumps({"status":"SUCCESS","response":"dados.txt:1; fronteiras conferidas sem modelo remoto"}))
''')
        resultado = json.loads(self.executar().stdout)
        self.assertEqual(resultado["estado"], "aguarda_autor")
        self.assertEqual((self.raiz / "dados.txt").read_text(), "valor=1\n")
        self.assertEqual((Path(resultado["pasta"]) / "arquivos/dados.txt").read_text(), "valor=2\n")
        self.script("agy", '''import json,os,sys
if sys.argv[1:] == ["agents"]:
 print("leitor" if os.environ.get("JANGADA_ISOLADO") else "implementador"); sys.exit()
if "/usage" in sys.argv:
 print(json.dumps({"command":{"data":{"groups":[{"buckets":[{"id":"gemini-weekly","remaining_fraction":0.9}]}]}}})); sys.exit()
raise AssertionError("modelo chamado sem papel privado")
''')
        falha = json.loads(self.executar(sucesso=False).stdout)
        self.assertEqual(falha["estado"], "falhou")
        self.assertEqual((Path(falha["pasta"]) / "arquivos/dados.txt").read_text(), "valor=1\n")


if __name__ == "__main__":
    unittest.main()
