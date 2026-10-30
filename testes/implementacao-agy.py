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
import shutil
import socket
import subprocess
import time
import signal
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("implementacao", REPO / "delegacao/implementacao.py")
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


KEYRING_FALSO = """import dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
nome = dbus.service.BusName("org.freedesktop.secrets", bus)
RAIZ = "/org/freedesktop/secrets"
ITENS = {RAIZ + "/collection/login/1": "agy-teste", RAIZ + "/collection/login/2": "outro"}


def achar(atributos):
    return [dbus.ObjectPath(c) for c, s in ITENS.items() if atributos.get("service", s) == s]


class Servico(dbus.service.Object):
    @dbus.service.method("org.freedesktop.Secret.Service", in_signature="a{ss}", out_signature="aoao")
    def SearchItems(self, atributos):
        return dbus.Array(achar(atributos), signature="o"), dbus.Array([], signature="o")


class Colecao(dbus.service.Object):
    @dbus.service.method("org.freedesktop.Secret.Collection", in_signature="a{ss}", out_signature="ao")
    def SearchItems(self, atributos):
        return dbus.Array(achar(atributos), signature="o")


    @dbus.service.method("org.freedesktop.Secret.Collection", in_signature="a{sv}(oayays)b", out_signature="oo")
    def CreateItem(self, propriedades, segredo, substituir):
        return dbus.ObjectPath("/"), dbus.ObjectPath("/")


class Item(dbus.service.Object):
    @dbus.service.method("org.freedesktop.Secret.Item", in_signature="o", out_signature="s")
    def GetSecret(self, sessao):
        return "segredo de " + self._object_path


objetos = [Servico(bus, RAIZ), Colecao(bus, RAIZ + "/collection/login")] + [Item(bus, c) for c in ITENS]
open(__file__ + ".pronto", "w").close()
GLib.MainLoop().run()
"""


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
        compile(codigo, str(p), "exec")
        p.write_text("#!/usr/bin/python3\n" + codigo)
        p.chmod(0o755)


    def contas(self, saldos=(0.4, 0.8), fora_da_casa=False):
        capacidade = subprocess.run(["/usr/bin/bwrap", "--ro-bind", "/", "/", "--unshare-pid", "true"],
                                    capture_output=True)
        if capacidade.returncode:
            self.skipTest("Bubblewrap indisponível")
        (self.bin / "bwrap").unlink(missing_ok=True)
        contas = []
        if fora_da_casa:
            # O estado do jangada, e com ele as contas, fora da casa. /var/tmp não é
            # coberto pelos tmpfs de /tmp, da casa nem da pasta do projeto.
            try:
                estado = Path(tempfile.mkdtemp(dir="/var/tmp", prefix="jangada-estado-"))
            except OSError:
                self.skipTest("/var/tmp sem escrita")
            self.addCleanup(shutil.rmtree, estado, ignore_errors=True)
            self.env.update(JANGADA_ESTADO=str(estado / "jangada"), XDG_STATE_HOME=str(estado))
        base = Path(self.env["JANGADA_ESTADO"]) / "contas"
        for i, saldo in enumerate(saldos, 1):
            pasta = base / f"conta{i}"
            pasta.mkdir(parents=True)
            (pasta / "segredo").write_text(f"conta{i}")
            (pasta / "antigravity-oauth-token").write_text(f"conta{i}")
            (pasta / "settings.json").write_text(json.dumps({"trustedWorkspaces": [str(self.raiz)],
                "permissions": {"deny": [f"read_url(conta{i}.example)"]}}))
            buckets = [{"id": "gemini-weekly", "remaining_fraction": saldo}]
            if i == 1:
                buckets.append({"id": "gemini-argon-wtu-weekly", "remaining_fraction": 0.6})
            (pasta / "usage.json").write_text(json.dumps({"command": {"data": {"groups": [{"buckets": buckets}]}}}))
            contas.append({"nome": f"conta{i}", "pasta": str(pasta), "argon": i == 1})
        catalogo = base / "agy.json"
        catalogo.write_text(json.dumps(contas))
        self.script("agy", r'''import json,os,sys
from pathlib import Path
cli=Path.home()/".gemini/antigravity-cli"
for origem in filter(None, os.environ.get("CONTAS_ORIGENS", "").split(":")):
 assert not (Path(origem)/"segredo").exists(), "origem de conta visível: "+origem
if sys.argv[1:]==["agents"]:
 print("explorador\nimplementador\nleitor\npesquisador"); sys.exit()
if "/usage" in sys.argv:
 with (cli/"consultas").open("a") as arq: arq.write("usage\n")
 print((cli/"usage.json").read_text()); sys.exit()
conta=(cli/"antigravity-oauth-token").read_text()
if not (cli/"usage.json").exists():
 try: (cli/"antigravity-oauth-token").write_text("alterado")
 except OSError: pass
 else: raise AssertionError("login gravável no executor privado")
 (cli/"identidade.json").write_text(json.dumps({"conta":conta,"settings":json.loads((cli/"settings.json").read_text())}))
print(json.dumps({"status":"SUCCESS","response":"dados.txt:1 fonte.txt:1 identidade="+conta}))
''')
        self.env["CONTAS_ORIGENS"] = ":".join(c["pasta"] for c in contas)
        # O ambiente mínimo do isolamento só deixa passar o nome pedido.
        self.env["JANGADA_ISOLAR_AMBIENTE_MANTER"] = "CONTAS_ORIGENS"
        return contas, catalogo

    def delegar_conta(self, *args, sucesso=True):
        p = self.chamar("explorador", "Leia dados.txt", "--destino", "agy", "--permitir-remoto",
                        "--modelo", "gemini-3.8-flash-high", "--json", *args, sucesso=sucesso)
        self.assertNotIn("AUTORIZACAO_RECUSADA", p.stderr, p.stderr)
        return p

    def test_contas_escolha_saldo_argon_e_registro(self):
        contas, _ = self.contas()
        resultado = json.loads(self.delegar_conta().stdout)
        self.assertEqual(resultado["conta"], "conta2")
        self.assertEqual(resultado["cota_antes"], 80)
        for c in contas:
            n = len((Path(c["pasta"]) / "consultas").read_text().splitlines())
            self.assertEqual(n, 2 if c["nome"] == "conta2" else 1)
        resultado = json.loads(self.chamar("explorador", "Leia", "--destino", "agy", "--permitir-remoto",
            "--modelo", "gemini-4-argon-high", "--json").stdout)
        self.assertEqual(resultado["conta"], "conta1")
        self.assertEqual(resultado["cota_antes"], 60)
        self.assertTrue(all(m.get("conta") == "conta1" for m in resultado["cotas_modelos"]))
        bloqueada = self.chamar("explorador", "Leia", "--destino", "agy", "--permitir-remoto",
            "--modelo", "gemini-4-argon-high", "--conta", "conta2", "--json", sucesso=False)
        self.assertEqual(json.loads(bloqueada.stdout)["chamadas_executor"], 0)
        self.assertIn("nenhuma conta habilitada", bloqueada.stderr)

    def test_escolha_exclui_conta_sem_confianca_antes_da_cota(self):
        contas, _ = self.contas((0.4, 0.95))
        pasta = Path(contas[1]["pasta"])
        (pasta / "settings.json").write_text('{"trustedWorkspaces": []}')
        cache = Path(self.env["XDG_CACHE_HOME"]) / "jangada/agy-usage-conta2.json"
        cache.parent.mkdir(parents=True)
        cache.write_bytes((pasta / "usage.json").read_bytes())
        resultado = json.loads(self.delegar_conta().stdout)
        self.assertEqual(resultado["conta"], "conta1")
        self.assertEqual(resultado["cota_antes"], 40)
        self.assertTrue(all(c["conta"] == "conta1" for c in resultado["cotas_modelos"]))
        self.assertFalse((pasta / "consultas").exists())
        for c in contas:
            (Path(c["pasta"]) / "settings.json").write_text('{"trustedWorkspaces": []}')
        erro = self.delegar_conta(sucesso=False)
        self.assertIn("nenhuma conta elegível confia", erro.stderr)
        self.assertEqual(json.loads(erro.stdout)["chamadas_executor"], 0)

    def test_capacidade_conta_chega_ao_agy_depois_do_local(self):
        self.contas()
        config = Path(self.env["XDG_CONFIG_HOME"]) / "jangada"
        config.mkdir(parents=True)
        (config / "delegacao.json").write_text('{"leitura_documental":["local","agy"]}')
        self.env["JANGADA_OLLAMA_URL"] = "http://127.0.0.1:1"
        resultado = json.loads(self.chamar("leitor", "Leia", "--capacidade", "leitura_documental", "--conta", "conta2",
            "--permitir-remoto", "--arquivos", "fonte.txt", "--json").stdout)
        self.assertEqual(resultado["conta"], "conta2")
        self.assertEqual([t["destino"] for t in resultado["tentativas"]], ["local", "agy"])
        self.assertNotEqual(resultado["tentativas"][0]["motivo_codigo"], "entrada_invalida")
        self.assertEqual(resultado["codigo_saida"], 0)

    def test_contas_sem_dado_zero_e_inexistente(self):
        self.contas((None, 0))
        resultado = json.loads(self.delegar_conta(sucesso=False).stdout)
        self.assertEqual(resultado["conta"], "conta2")
        self.assertEqual(resultado["cota_antes"], 0)
        self.assertEqual(resultado["motivo_codigo"], "cota_insuficiente")
        medidas = [m for m in resultado["cotas_modelos"] if m.get("conta") == "conta1"]
        self.assertTrue(medidas)
        self.assertTrue(all(m["percentual"] is None for m in medidas))
        erro = self.delegar_conta("--conta", "ausente", sucesso=False)
        self.assertIn("inexistente", erro.stderr)
        cache = Path(self.env["XDG_CACHE_HOME"]) / "jangada"
        self.assertFalse((cache / "agy-usage-conta1.json").exists())

    def test_contas_cache_expirado_nao_vira_cota(self):
        contas, _ = self.contas()
        cache = Path(self.env["XDG_CACHE_HOME"]) / "jangada/agy-usage-conta1.json"
        cache.parent.mkdir(parents=True)
        cache.write_bytes((Path(contas[0]["pasta"]) / "usage.json").read_bytes())
        os.utime(cache, (0, 0))
        (Path(contas[0]["pasta"]) / "usage.json").write_text("{}")
        resultado = json.loads(self.delegar_conta("--conta", "conta1", sucesso=False).stdout)
        self.assertIsNone(resultado["cota_antes"])
        self.assertEqual(resultado["motivo_codigo"], "cota_desconhecida")
        self.assertEqual(resultado["chamadas_executor"], 0)

    def test_contas_isolamento_real_oculta_origens_e_nao_altera_outra(self):
        contas, _ = self.contas()
        self.env["JANGADA_ISOLAR_ESCRITA"] = contas[0]["pasta"]
        codigo = ("from pathlib import Path; import os; cli=Path.home()/'.gemini/antigravity-cli'; "
                  "assert (cli/'segredo').read_text()=='conta2'; "
                  "assert all(not (Path(p)/'segredo').exists() for p in os.environ['CONTAS_ORIGENS'].split(':')); "
                  "(cli/'gravado').write_text('ok')")
        p = subprocess.run([str(REPO / "bin/jangada-isolar"), "--provedor", "agy", "--conta", "conta2", "--", "python3", "-c", codigo],
                           cwd=self.raiz, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((Path(contas[1]["pasta"]) / "gravado").read_text(), "ok")
        self.assertFalse((Path(contas[0]["pasta"]) / "gravado").exists())
        # O isolamento cria o bin vazio na conta, que fica no estado do jangada.
        self.assertEqual(list((Path(contas[1]["pasta"]) / "bin").iterdir()), [])

    def test_isolar_real_conta_secundaria_nao_grava_bin_na_origem(self):
        contas, _ = self.contas()
        origem = Path(contas[1]["pasta"])
        # O agente grava um executável em bin: pode falhar (somente leitura) ou
        # ficar em memória, mas não pode sobrar na pasta da conta.
        codigo = ("from pathlib import Path; cli=Path.home()/'.gemini/antigravity-cli'\n"
                  "print((cli/'bin'/'antigo').read_text() if (cli/'bin'/'antigo').exists() else 'sem-antigo')\n"
                  "try: (cli/'bin'/'agentapi').write_text('x')\n"
                  "except OSError: pass\n"
                  "(cli/'gravado').write_text('ok')")
        comando = [str(REPO / "bin/jangada-isolar"), "--provedor", "agy", "--conta", "conta2", "--", "python3", "-c", codigo]
        # Sem bin na conta: a pasta é criada vazia pelo isolamento e nada sobra nela.
        p = subprocess.run(comando, cwd=self.raiz, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "sem-antigo")
        self.assertEqual(list((origem / "bin").iterdir()), [])
        self.assertEqual((origem / "gravado").read_text(), "ok")
        # Com bin na conta: o conteúdo aparece na caixa e a origem fica intacta.
        (origem / "bin/antigo").write_text("velho")
        p = subprocess.run(comando, cwd=self.raiz, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "velho")
        self.assertEqual([a.name for a in (origem / "bin").iterdir()], ["antigo"])
        # bin que é link a agente deixou na conta: recusa, sem seguir o link.
        shutil.rmtree(origem / "bin")
        (origem / "bin").symlink_to(self.tmp)
        p = subprocess.run(comando, cwd=self.raiz, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("bin da conta conta2 é link", p.stderr)

    def test_delegar_dentro_da_caixa_ignora_cache_de_outra_conta(self):
        contas, _ = self.contas((0.4, 0.95))
        cache = Path(self.env["XDG_CACHE_HOME"]) / "jangada/agy-usage-conta2.json"
        cache.parent.mkdir(parents=True)
        cache.write_bytes((Path(contas[1]["pasta"]) / "usage.json").read_bytes())
        # O caminho do cache fica visível, mas não autoriza escolher a outra conta.
        self.env["JANGADA_ISOLAR_CASA_LER"] = self.env["XDG_CACHE_HOME"]
        self.env["JANGADA_ISOLAR_ESCRITA"] = self.env["XDG_CACHE_HOME"]
        self.env["JANGADA_TESTE_REPO"] = str(REPO)
        codigo = r'''import json,os,subprocess
from pathlib import Path
raiz=Path(os.environ["JANGADA_TESTE_REPO"])
args=[str(raiz/"bin/jangada-delegar"),"explorador","Leia","--destino","agy","--permitir-remoto","--modelo","gemini-3.8-flash-high","--json"]
p=subprocess.run(args,capture_output=True,text=True)
assert p.returncode==0,p.stderr
r=json.loads(p.stdout)
assert r["conta"]=="conta1",r
assert "identidade=conta1" in r["relatorio"],r
assert all(c["conta"]=="conta1" for c in r["cotas_modelos"]),r
p=subprocess.run(args+["--conta","conta2"],capture_output=True,text=True)
assert p.returncode==4 and "indisponível nesta sessão" in p.stderr,p.stderr
p=subprocess.run([str(raiz/"bin/jangada-isolar"),"--conta","conta2","--","true"],capture_output=True,text=True)
assert p.returncode!=0 and "indisponível nesta sessão" in p.stderr,p.stderr
'''
        p = subprocess.run([str(REPO / "bin/jangada-isolar"), "--provedor", "agy", "--conta", "conta1", "--", "python3", "-c", codigo],
                           cwd=self.raiz, env=self.env, capture_output=True, text=True, timeout=25)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((Path(contas[1]["pasta"]) / "consultas").exists())

    def test_login_privado_recusa_links_sem_ler_credencial(self):
        origem, destino = self.tmp / "origem", self.tmp / "destino"
        origem.mkdir()
        token = origem / "antigravity-oauth-token"
        alvo = self.tmp / "login-falso"
        alvo.write_text("identidade sintética")
        token.symlink_to(alvo)
        with mock.patch.dict(os.environ, JANGADA_AGY_CONTA_MONTADA="conta1"), self.assertRaisesRegex(ValueError, "sem links"):
            modulo.montar_login(origem, destino)
        token.unlink()
        token.hardlink_to(alvo)
        with mock.patch.dict(os.environ, JANGADA_AGY_CONTA_MONTADA="conta1"), self.assertRaisesRegex(ValueError, "sem links"):
            modulo.montar_login(origem, destino)

    def test_contas_verificacao_nao_expoe_conta_escolhida(self):
        self.contas()
        codigo = ("from pathlib import Path; import os; "
                  "assert not (Path.home()/'.gemini/antigravity-cli/segredo').exists(); "
                  "assert all(not (Path(p)/'segredo').exists() for p in os.environ['CONTAS_ORIGENS'].split(':'))")
        p = subprocess.run([str(REPO / "bin/jangada-isolar"), "--provedor", "agy", "--conta", "conta2", "--", "python3", "-c", codigo],
                           cwd=self.raiz, env=dict(self.env, JANGADA_ISOLAR_PERFIL="verificacao"),
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_contas_confianca_derivada_exige_raiz_em_cada_conta(self):
        contas, _ = self.contas()
        worktree = self.tmp / "worktree"
        self.git("worktree", "add", "-qb", "outra", str(worktree))
        outro = Path(contas[1]["pasta"]) / "settings.json"
        outro.write_text('{"trustedWorkspaces": []}')
        codigo = 'source "$JANGADA_CORE_PATH/bin/jangada-config"; jangada_agy_sincronizar_worktree "$1" "$2"'
        p = subprocess.run(["bash", "-c", codigo, "teste", str(self.raiz), str(worktree)],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        primeiro = Path(contas[0]["pasta"]) / "settings.json"
        self.assertIn(str(worktree), json.loads(primeiro.read_text())["trustedWorkspaces"])
        self.assertNotIn(str(worktree), json.loads(outro.read_text())["trustedWorkspaces"])
        self.assertTrue(primeiro.with_suffix('.json.jangada-orig').is_file())
        # Remover a confiança derivada não pode deixar autorização em outra conta.
        outro.write_text(json.dumps({"trustedWorkspaces": [str(worktree)]}))
        p = subprocess.run(["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; jangada_agy_ajustar_confianca remover "$1"',
                            "teste", str(worktree)], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        for c in contas:
            self.assertNotIn(str(worktree), json.loads((Path(c["pasta"]) / "settings.json").read_text())["trustedWorkspaces"])

    def test_contas_mod03_recebe_permissoes_selecionadas(self):
        self.contas()
        p = self.chamar("leitor", "Leia", "--destino", "agy", "--permitir-remoto", "--conta", "conta2",
                       "--modelo", "gemini-3.8-flash-high", "--arquivos", "fonte.txt", "--json")
        resultado = json.loads(p.stdout)
        registro = Path(resultado["registro_ferramentas"])
        self.assertEqual(resultado["conta"], "conta2")
        identidade = json.loads((registro / "identidade.json").read_text())
        self.assertEqual(identidade["conta"], "conta2")
        self.assertEqual(identidade["settings"]["permissions"]["deny"], ["read_url(conta2.example)"])
        # O implementador usa a mesma seleção antes de gerar sua configuração privada.
        (self.casa / ".gemini/antigravity-cli/settings.json").write_text('{"trustedWorkspaces": []}')
        resultado = json.loads(self.executar("--conta", "conta2").stdout)
        self.assertEqual(json.loads((Path(resultado["pasta"]) / "registro.json").read_text())["conta"], "conta2")
        # O caminho exato da execução vem do registro, sem inferir sua estrutura.
        settings = list(Path(self.env["JANGADA_ESTADO"]).rglob("runtime/settings.json"))
        self.assertEqual(len(settings), 1)
        self.assertEqual(json.loads(settings[0].read_text())["permissions"]["deny"], ["read_url(conta2.example)"])
        self.assertIn("identidade=conta2", (Path(resultado["pasta"]) / "relatorio.md").read_text())

    def test_executores_privados_ocultam_conta_fora_da_casa(self):
        contas, _ = self.contas(fora_da_casa=True)
        # O agy falso falha se a origem de qualquer conta continuar visível.
        resultado = json.loads(self.executar("--conta", "conta2").stdout)
        self.assertIn("identidade=conta2", (Path(resultado["pasta"]) / "relatorio.md").read_text())
        p = self.chamar("leitor", "Leia", "--destino", "agy", "--permitir-remoto", "--conta", "conta1",
                        "--modelo", "gemini-3.8-flash-high", "--arquivos", "fonte.txt", "--json")
        self.assertEqual(json.loads(p.stdout)["conta"], "conta1")

    def test_ocultar_contas_so_as_de_fora_da_casa(self):
        fora = [self.tmp / "fora" / f"conta{i}" for i in (1, 2, 3)]
        dentro = self.casa / "contas/conta4"
        for pasta in (*fora, dentro):
            pasta.mkdir(parents=True)
        catalogo = Path(self.env["JANGADA_ESTADO"]) / "contas/agy.json"
        catalogo.parent.mkdir(parents=True)
        catalogo.write_text(json.dumps([{"nome": f"conta{i}", "pasta": str(p), "argon": False}
                                        for i, p in enumerate((*fora, dentro), 1)]))
        escolhida = {"JANGADA_AGY_PASTA": str(fora[1]), "JANGADA_AGY_CONTA_MONTADA": "conta2"}
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.dict(os.environ, escolhida):
            self.assertEqual(modulo.ocultar_contas(self.casa),
                             [a for p in fora for a in ("--tmpfs", str(p))])
            catalogo.write_text(json.dumps([{"nome": "x", "pasta": "relativa", "argon": False}]))
            with self.assertRaises(ValueError):
                modulo.ocultar_contas(self.casa)
        catalogo.unlink()
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(modulo.ocultar_contas(self.casa), [])

    def test_isolar_conta_secundaria_sempre_monta_bin_em_memoria_ou_leitura(self):
        contas, _ = self.contas()
        ambiente = dict(self.env, JANGADA_ISOLAR_PERFIL="agente")
        comando = [str(REPO / "bin/jangada-isolar"), "--mostrar", "--conta", "conta2", "--", "agy"]
        destino = str(self.casa / ".gemini/antigravity-cli/bin")
        origem_bin = Path(contas[1]["pasta"]) / "bin"
        for _ in range(2):
            p = subprocess.run(comando, cwd=self.raiz, env=ambiente, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            linhas = p.stdout.splitlines()
            self.assertTrue(any((linhas[k] == "--tmp-overlay" and linhas[k + 1] == destino)
                                or (linhas[k] == "--ro-bind" and linhas[k + 2] == destino)
                                for k in range(len(linhas) - 2)), p.stdout)
            self.assertTrue(origem_bin.is_dir())
            shutil.rmtree(origem_bin)
            origem_bin.mkdir()

    def test_recusa_anterior_a_selecao_nao_registra_conta(self):
        self.contas()
        estado = Path(self.env["JANGADA_ESTADO"]) / "agentes"
        estado.mkdir(parents=True)
        with (estado / ".agy-execucao.lock").open("w") as arq:
            fcntl.flock(arq, fcntl.LOCK_EX | fcntl.LOCK_NB)
            resultado = json.loads(self.delegar_conta(sucesso=False).stdout)
        self.assertEqual(resultado["motivo_codigo"], "execucao_ocupada")
        self.assertIsNone(resultado["conta"])
        self.assertIsNone(json.loads((Path(self.env["JANGADA_ESTADO"]) / "delegacoes.jsonl").read_text().splitlines()[-1])["conta"])

    def test_recusa_depois_de_candidatas_sem_confianca_nao_registra_conta(self):
        contas, _ = self.contas()
        for c in contas:
            (Path(c["pasta"]) / "settings.json").write_text('{"trustedWorkspaces": []}')
        resultado = json.loads(self.delegar_conta(sucesso=False).stdout)
        self.assertIn("nenhuma conta elegível confia", resultado["motivo"])
        self.assertIsNone(resultado["conta"])

    def test_confianca_pendente_nomeia_so_a_conta_sem_confianca(self):
        contas, _ = self.contas()
        (Path(contas[1]["pasta"]) / "settings.json").write_text('{"trustedWorkspaces": []}')
        comando = ["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; jangada_agy_conferir_tarefa "$1" "" 0 teste',
                   "teste", str(self.raiz)]
        p = subprocess.run(comando, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("pendente na conta conta2", p.stderr)
        self.assertNotIn("conta1.", p.stderr)
        self.assertNotIn("indisponíveis", p.stderr)
        (Path(contas[0]["pasta"]) / "settings.json").write_text('{"trustedWorkspaces": []}')
        p = subprocess.run(comando, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("pendente na conta conta1", p.stderr)
        self.assertIn("pendente na conta conta2", p.stderr)
        self.assertEqual(p.stderr.count("indisponíveis nesta tarefa"), 1)
        # Só a configuração informada, sem nome de conta: nada de indisponibilidade geral.
        (Path(contas[0]["pasta"]) / "settings.json").write_text(json.dumps({"trustedWorkspaces": [str(self.raiz)]}))
        pasta = Path(contas[1]["pasta"]) / "settings.json"
        p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_SETTINGS=str(pasta)), capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("pendente na configuração em JANGADA_AGY_SETTINGS", p.stderr)
        self.assertNotIn("indisponíveis", p.stderr)
        self.assertIn("--conta NOME -- agy", p.stderr + "--conta NOME -- agy")

    def test_confianca_da_tarefa_confere_todas_as_contas(self):
        contas, _ = self.contas()
        outro = Path(contas[1]["pasta"]) / "settings.json"
        outro.write_text('{"trustedWorkspaces": []}')
        comando = ["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; jangada_agy_conferir_tarefa "$1" "" 0 teste',
                   "teste", str(self.raiz)]
        p = subprocess.run(comando, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("conta2", p.stderr)
        outro.write_text(json.dumps({"trustedWorkspaces": [str(self.raiz)]}))
        p = subprocess.run(comando, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_pergunta_de_confianca_abre_a_conta_pendente(self):
        import pty
        import shutil
        contas, _ = self.contas()
        outro = Path(contas[1]["pasta"]) / "settings.json"
        outro.write_text('{"trustedWorkspaces": []}')
        arvore = self.tmp / "pergunta"
        (arvore / "bin").mkdir(parents=True)
        shutil.copyfile(REPO / "bin/jangada-config", arvore / "bin/jangada-config")
        isolador = arvore / "bin/jangada-isolar"
        isolador.write_text('''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
assert sys.argv[1:]==["--conta","conta2","--","agy"],sys.argv
contas=json.loads((Path(os.environ["JANGADA_ESTADO"])/"contas/agy.json").read_text())
pasta=Path(next(c["pasta"] for c in contas if c["nome"]=="conta2"))
(pasta/"settings.json").write_text(json.dumps({"trustedWorkspaces":[os.environ["RAIZ_TESTE"]]}))
''')
        isolador.chmod(0o755)
        ambiente = dict(self.env, JANGADA_CORE_PATH=str(arvore), RAIZ_TESTE=str(self.raiz))
        mestre, escravo = pty.openpty()
        try:
            os.write(mestre, b"s\n")
            p = subprocess.run(["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; jangada_agy_conferir_tarefa "$1" "" 1 teste',
                                "teste", str(self.raiz)], env=ambiente, stdin=escravo, stderr=escravo,
                               stdout=subprocess.PIPE, text=True, timeout=10)
            os.set_blocking(mestre, False)
            diagnostico = os.read(mestre, 65536).decode()
        finally:
            os.close(mestre)
            os.close(escravo)
        self.assertEqual(p.returncode, 0, p.stdout + diagnostico)
        self.assertEqual(json.loads(outro.read_text())["trustedWorkspaces"], [str(self.raiz)])
        padrao = self.casa / ".gemini/antigravity-cli/settings.json"
        self.assertNotIn("conta2", padrao.read_text())

    def argumentos_sem_catalogo(self, fontes=None, extra=None):
        arvore = self.tmp / "montagem"
        (arvore / "bin").mkdir(parents=True)
        (arvore / "orquestracao").mkdir()
        for nome in ("jangada-isolar", "jangada-config"):
            texto = fontes[nome] if fontes else (REPO / "bin" / nome).read_text()
            (arvore / "bin" / nome).write_text(texto)
        # Só construção de argumentos: o controlador e qualquer carga são falsos.
        (arvore / "orquestracao/confianca.py").write_text(
            'import sys; assert sys.argv[1]=="preparar-isolamento"; sys.exit(0)\n')
        self.script("bwrap", "import sys; sys.exit(1)")
        ambiente = {k: self.env[k] for k in ("HOME", "PATH", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")}
        ambiente.update(JANGADA_CORE_PATH=str(arvore), LANG="C.UTF-8", JANGADA_SESSAO="sintetica", **(extra or {}))
        p = subprocess.run(["bash", str(arvore / "bin/jangada-isolar"), "--mostrar", "--", "agy"],
                           cwd=self.raiz, env=ambiente, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.replace(str(self.tmp), "${TMP}")

    def test_sem_catalogo_bwrap_igual_a_base_0f82006(self):
        # Os padrões novos (casa mínima, ambiente mínimo, keyring por item e
        # só o login do provedor do comando) mudam a chamada. As variáveis de
        # transição documentadas voltam à de 0f82006; a única diferença é a
        # lista de provedores concedidos que o isolamento aninhado lê.
        base = (REPO / "testes/contratos/isolar-sem-contas-0f82006.txt").read_text()
        marca = "--setenv\nJANGADA_ISOLADO\n"
        self.assertEqual(base.count(marca), 1)
        esperado = base.replace(marca, "--setenv\nJANGADA_ISOLAR_CONCEDIDOS\nagy claude codex\n" + marca)
        transicao = dict(JANGADA_ISOLAR_CASA="inteira", JANGADA_ISOLAR_AMBIENTE="herdado",
                         JANGADA_ISOLAR_KEYRING="servico", JANGADA_ISOLAR_PROVEDORES="claude:codex")
        self.assertEqual(self.argumentos_sem_catalogo(extra=transicao), esperado)

    def test_sem_catalogo_padrao_esconde_casa_e_login_de_outros_provedores(self):
        args = self.argumentos_sem_catalogo().splitlines()
        seguidos = ["\n".join(args[i:i + 3]) for i in range(len(args))]
        self.assertIn("--tmpfs\n${TMP}/casa\n--ro-bind", seguidos)
        self.assertIn("--ro-bind\n${TMP}/casa/.gemini\n${TMP}/casa/.gemini", seguidos)
        self.assertIn("--tmpfs\n${TMP}/casa/.claude\n--tmpfs", seguidos)
        self.assertIn("--setenv\nJANGADA_ISOLAR_CONCEDIDOS\nagy", seguidos)

    def argumentos_privados_sem_catalogo(self, codigo_base=None):
        import re
        import types
        executor = modulo
        if codigo_base:
            executor = types.ModuleType("base_implementacao")
            exec(compile(codigo_base, "implementacao-base.py", "exec"), executor.__dict__)
        (self.casa / ".gemini/antigravity-cli/antigravity-oauth-token").write_text("login principal sintético")
        resultado = json.loads(self.executar().stdout)
        execucao = Path(resultado["pasta"])
        agentes = Path(self.env["JANGADA_ESTADO"]) / "agentes"
        resolver = Path.resolve
        def resolver_fixo(p, *args, **kwargs):
            return p if str(p) == "/etc/resolv.conf" else resolver(p, *args, **kwargs)
        argumentos = {}
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(Path, "home", return_value=self.casa), \
                mock.patch.object(Path, "cwd", return_value=self.raiz), mock.patch.object(Path, "resolve", resolver_fixo):
            argumentos["implementador"] = executor.montagem(str(execucao / "contrato.json"))
            for papel in ("pesquisador", "leitor"):
                entrada = ["--papel", papel, "--registro", str(agentes / ("comparacao-" + papel))]
                entrada += ["--url", "https://ai.google.dev/docs"] if papel == "pesquisador" else ["--fonte", str(self.raiz / "fonte.txt")]
                with mock.patch.object(executor.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as chamada, \
                        self.assertRaises(SystemExit) as fim:
                    executor.pesquisa([*entrada, "--", "agy", "-p", "Leia"])
                self.assertEqual(fim.exception.code, 0)
                argumentos[papel] = chamada.call_args.args[0]
        for papel, comando in argumentos.items():
            argumentos[papel] = [re.sub(re.escape(str(agentes)) + r"/apoio-runtime-[^/]+", "${RUNTIME}", a)
                                .replace(str(execucao), "${EXECUCAO}").replace(str(self.tmp), "${TMP}") for a in comando]
        return argumentos

    def test_sem_catalogo_executores_privados_iguais_a_base_com_login_existente(self):
        esperado = json.loads((REPO / "testes/contratos/privados-sem-contas-0f82006.json").read_text())
        self.assertEqual(self.argumentos_privados_sem_catalogo(), esperado)

    def test_sem_catalogo_delegar_preserva_argumentos_isolamento(self):
        import shutil
        arvore = self.tmp / "arvore"
        (arvore / "bin").mkdir(parents=True)
        for nome in ("jangada-delegar", "jangada-config"):
            shutil.copyfile(REPO / "bin" / nome, arvore / "bin" / nome)
        isolador = arvore / "bin/jangada-isolar"
        isolador.write_text("#!/usr/bin/python3\nimport json,os,sys\n"
                            "from pathlib import Path\n"
                            "Path(os.environ['FALSO_ARGUMENTOS']).write_text(json.dumps(sys.argv[1:]))\n"
                            "os.execvp('agy',sys.argv[sys.argv.index('--')+1:])\n")
        isolador.chmod(0o755)
        agy = self.bin / "agy"
        agy.write_text(agy.read_text().replace('print("implementador")', 'print("explorador")'))
        ambiente = dict(self.env, JANGADA_CORE_PATH=str(arvore), FALSO_ARGUMENTOS=str(self.tmp / "argumentos.json"))
        # Lista conferida na base de T1, antes de acrescentar contas.
        # Desde o lote de credenciais, o provedor vai explícito na frente.
        esperado = ["--provedor", "agy", "--", "agy", "-p", "Leia\n\nSe uma ferramenta ou comando for negado, pare e informe qual ação foi negada.",
                    "--agent", "explorador", "--model", "gemini-3.8-flash-high", "--sandbox",
                    "--output-format", "json", "--print-timeout", "300s"]
        for conta in ([], ["--conta", "principal"]):
            p = subprocess.run(["bash", str(arvore / "bin/jangada-delegar"), "explorador", "Leia",
                                "--destino", "agy", "--permitir-remoto", "--modelo", "gemini-3.8-flash-high", *conta],
                               cwd=self.raiz, env=ambiente, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(Path(ambiente["FALSO_ARGUMENTOS"]).read_text()), esperado)

    def test_catalogo_recusa_pastas_sobrepostas_links_e_nomes_repetidos(self):
        contas, catalogo = self.contas()
        for defeito in ("sobreposta", "nome", "link", "relativa", "invalido"):
            valor = json.loads(json.dumps(contas))
            if defeito == "sobreposta": valor[1]["pasta"] = valor[0]["pasta"] + "/filha"
            elif defeito == "nome": valor[1]["nome"] = valor[0]["nome"]
            elif defeito == "link":
                link = self.casa / "ligacao"
                link.symlink_to(valor[0]["pasta"])
                valor[0]["pasta"] = str(link)
            elif defeito == "relativa": valor[0]["pasta"] = "relativa"
            else: valor = {}
            catalogo.write_text(json.dumps(valor))
            erro = self.delegar_conta(sucesso=False)
            self.assertIn("catálogo de contas do agy inválido", erro.stderr)

    def test_catalogo_so_aceita_principal_ou_area_de_contas_do_estado(self):
        contas, catalogo = self.contas()
        area = catalogo.parent
        principal = self.casa / ".gemini/antigravity-cli"
        recusadas = [self.casa / "contas/fora", self.tmp / "fora", self.casa / ".gemini", area, area.parent / "outra",
                     self.casa / ".gemini/antigravity-cli/filha"]
        for pasta in recusadas:
            pasta.mkdir(parents=True, exist_ok=True)
            valor = json.loads(json.dumps(contas))
            valor[1]["pasta"] = str(pasta)
            catalogo.write_text(json.dumps(valor))
            # Qualquer escrita de confiança numa conta fora da área é recusada antes de tocar o arquivo.
            settings = pasta / "settings.json"
            settings.write_text('{"trustedWorkspaces": []}')
            erro = self.delegar_conta(sucesso=False)
            self.assertIn("catálogo de contas do agy inválido", erro.stderr, pasta)
            self.assertIn("ou ficar dentro de", erro.stderr, pasta)
            p = subprocess.run(["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; '
                                'jangada_agy_ajustar_confianca adicionar "$1"', "teste", str(self.raiz)],
                               env=self.env, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0, pasta)
            self.assertEqual(settings.read_text(), '{"trustedWorkspaces": []}', pasta)
            self.assertFalse((pasta / "settings.json.jangada-orig").exists(), pasta)
        valor = json.loads(json.dumps(contas))
        valor[1] = {"nome": "principal", "pasta": str(principal), "argon": False}
        principal.mkdir(parents=True, exist_ok=True)
        catalogo.write_text(json.dumps(valor))
        p = subprocess.run(["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; jangada_contas_agy'],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"principal\t{principal}\tfalse", p.stdout)

    def test_catalogo_recusa_pasta_de_contas_que_e_link(self):
        contas, catalogo = self.contas()
        externa = self.tmp / "externa"
        shutil.copytree(catalogo.parent, externa)
        shutil.rmtree(catalogo.parent)
        catalogo.parent.symlink_to(externa)
        valor = json.loads(catalogo.read_text())
        for conta in valor:
            conta["pasta"] = str(externa / conta["nome"])
        catalogo.write_text(json.dumps(valor))
        erro = self.delegar_conta(sucesso=False)
        self.assertIn("catálogo de contas do agy inválido", erro.stderr)
        self.assertIn("links no caminho", erro.stderr)

    def test_confianca_com_catalogo_nao_grava_em_settings_externo(self):
        contas, _ = self.contas()
        externo = self.tmp / "externo.json"
        externo.write_text('{"trustedWorkspaces": []}')
        comando = ["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; '
                   'jangada_agy_ajustar_confianca adicionar "$1"', "teste", str(self.raiz)]
        p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_SETTINGS=str(externo)),
                           capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("fora da conta escolhida", p.stderr)
        self.assertEqual(externo.read_text(), '{"trustedWorkspaces": []}')
        self.assertFalse(Path(str(externo) + ".jangada-orig").exists())
        # Nem o de outra conta do catálogo: só o da escolhida.
        outra = Path(contas[1]["pasta"]) / "settings.json"
        outra.write_text('{"trustedWorkspaces": []}')
        p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_SETTINGS=str(outra), JANGADA_AGY_CONTA="conta1"),
                           capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(outra.read_text(), '{"trustedWorkspaces": []}')
        # O settings.json da conta escolhida continua aceito.
        propria = Path(contas[0]["pasta"]) / "settings.json"
        propria.write_text('{"trustedWorkspaces": []}')
        p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_SETTINGS=str(propria)),
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(propria.read_text())["trustedWorkspaces"], [str(self.raiz)])

    def test_confianca_com_catalogo_so_de_secundarias_nao_grava_na_principal_externa(self):
        contas, _ = self.contas()
        externa = self.tmp / "externa"
        externa.mkdir()
        (externa / "settings.json").write_text('{"trustedWorkspaces": []}')
        principal = self.casa / ".gemini/antigravity-cli"
        shutil.rmtree(principal)
        principal.symlink_to(externa)
        comando = ["bash", "-c", 'source "$JANGADA_CORE_PATH/bin/jangada-config"; '
                   'jangada_agy_ajustar_confianca adicionar "$1"', "teste", str(self.raiz)]
        p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_CONTA="conta1",
                           JANGADA_AGY_SETTINGS=str(principal / "settings.json")), capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual((externa / "settings.json").read_text(), '{"trustedWorkspaces": []}')
        self.assertFalse((externa / "settings.json.jangada-orig").exists())
        # Montada outra conta, ou a variável definida por engano fora da caixa com a
        # principal sendo link: recusa, e nada externo muda.
        for montada in ("conta2", "conta1"):
            p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_CONTA="conta1", JANGADA_AGY_CONTA_MONTADA=montada,
                               JANGADA_AGY_SETTINGS=str(principal / "settings.json")), capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0, montada)
            self.assertEqual((externa / "settings.json").read_text(), '{"trustedWorkspaces": []}')
            self.assertFalse((externa / "settings.json.jangada-orig").exists())
        # Dentro da caixa a principal é uma pasta real montada para a conta escolhida.
        principal.unlink()
        principal.mkdir()
        (principal / "settings.json").write_text('{"trustedWorkspaces": []}')
        p = subprocess.run(comando, env=dict(self.env, JANGADA_AGY_CONTA="conta1", JANGADA_AGY_CONTA_MONTADA="conta1",
                           JANGADA_AGY_SETTINGS=str(principal / "settings.json")), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(str(self.raiz), (principal / "settings.json").read_text())
        self.assertEqual((externa / "settings.json").read_text(), '{"trustedWorkspaces": []}')

    def test_migracao_recusa_sem_terminal_e_preserva_origem(self):
        origem = self.tmp / "estado/catamara/contas"
        for nome in ("conta1", "conta2"):
            (origem / nome / "antigravity-cli").mkdir(parents=True)
            (origem / nome / "antigravity-cli/settings.json").write_text("segredo " + nome)
            (origem / nome / "antigravity-cli/antigravity-oauth-token").write_text("login falso " + nome)
        migracao = REPO / "migrations/202610241200-importar-contas-agy.sh"
        def rodar(env=None, entrada=None):
            return subprocess.run(["bash", str(migracao)], env=env or self.env, stdin=entrada or subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=10)
        p = rodar()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("importação não confirmada", p.stdout)
        destino = Path(self.env["JANGADA_ESTADO"]) / "contas"
        self.assertFalse(destino.exists())
        p = rodar(dict(self.env, JANGADA_SIMULAR="1"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(destino.exists())
        import pty
        mestre, escravo = pty.openpty()
        try:
            os.write(mestre, b"n\n")
            recusa = rodar(entrada=escravo)
        finally:
            os.close(mestre)
            os.close(escravo)
        self.assertEqual(recusa.returncode, 0, recusa.stderr)
        self.assertFalse(destino.exists())
        mestre, escravo = pty.openpty()
        try:
            os.write(mestre, b"s\ns\nn\n")
            p = rodar(entrada=escravo)
        finally:
            os.close(mestre)
            os.close(escravo)
        self.assertEqual(p.returncode, 0, p.stderr)
        contas = json.loads((destino / "agy.json").read_text())
        self.assertEqual([c["argon"] for c in contas], [True, False])
        for conta in contas:
            self.assertEqual((Path(conta["pasta"]) / "settings.json").read_text(),
                             (origem / conta["nome"] / "antigravity-cli/settings.json").read_text())
            self.assertEqual((Path(conta["pasta"]) / "antigravity-oauth-token").read_text(),
                             "login falso " + conta["nome"])
        antes = (destino / "agy.json").read_bytes()
        self.assertEqual(rodar().returncode, 0)
        self.assertEqual((destino / "agy.json").read_bytes(), antes)

    def test_migracao_pula_links_da_conta_e_recusa_arquivo_especial(self):
        import pty
        origem = self.tmp / "estado/catamara/contas"
        externo = self.tmp / "externo"
        externo.mkdir()
        (externo / "conteudo.txt").write_text("conteudo de fora")
        for nome in ("conta1", "conta2"):
            pasta = origem / nome / "antigravity-cli"
            (pasta / "log").mkdir(parents=True)
            (pasta / "settings.json").write_text("segredo " + nome)
            (pasta / "log/cli-x.log").write_text("registro " + nome)
            (pasta / "cli.log").symlink_to("log/cli-x.log")
        pasta1 = origem / "conta1/antigravity-cli"
        (pasta1 / "fora.txt").symlink_to("/etc/hostname")
        (pasta1 / "pasta-fora").symlink_to(externo)
        (pasta1 / "log/solto.txt").symlink_to(externo / "conteudo.txt")
        migracao = REPO / "migrations/202610241200-importar-contas-agy.sh"
        destino = Path(self.env["JANGADA_ESTADO"]) / "contas"

        def rodar():
            mestre, escravo = pty.openpty()
            try:
                os.write(mestre, b"s\ns\nn\n")
                return subprocess.run(["bash", str(migracao)], env=self.env, stdin=escravo,
                                      capture_output=True, text=True, timeout=10)
            finally:
                os.close(mestre)
                os.close(escravo)

        antes = sorted(str(p.relative_to(origem)) for p in origem.rglob("*"))
        fifo = pasta1 / "fila"
        os.mkfifo(fifo)
        p = rodar()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("arquivo especial", p.stderr)
        self.assertFalse(destino.exists())
        fifo.unlink()

        p = rodar()
        self.assertEqual(p.returncode, 0, p.stderr)
        for nome in ("conta1", "conta2"):
            copia = destino / nome
            self.assertFalse((copia / "cli.log").exists() or (copia / "cli.log").is_symlink())
            self.assertEqual((copia / "log/cli-x.log").read_text(), "registro " + nome)
            self.assertEqual((copia / "settings.json").read_text(), "segredo " + nome)
            self.assertIn(f"{nome}/antigravity-cli/cli.log", p.stdout)
        copia1 = destino / "conta1"
        self.assertFalse((copia1 / "fora.txt").exists() or (copia1 / "fora.txt").is_symlink())
        self.assertFalse((copia1 / "pasta-fora").exists() or (copia1 / "pasta-fora").is_symlink())
        self.assertFalse((copia1 / "log/solto.txt").exists() or (copia1 / "log/solto.txt").is_symlink())
        self.assertIn("conta1/antigravity-cli/fora.txt", p.stdout)
        self.assertIn("conta1/antigravity-cli/pasta-fora", p.stdout)
        self.assertIn("conta1/antigravity-cli/log/solto.txt", p.stdout)
        self.assertNotIn("/etc/hostname", p.stdout + p.stderr)
        self.assertNotIn(str(externo), p.stdout + p.stderr)
        for arquivo in destino.rglob("*"):
            self.assertFalse(arquivo.is_symlink(), arquivo)
            if arquivo.is_file():
                self.assertNotIn("conteudo de fora", arquivo.read_text())
        self.assertEqual(sorted(str(p.relative_to(origem)) for p in origem.rglob("*")), antes)
        self.assertEqual((externo / "conteudo.txt").read_text(), "conteudo de fora")

    def test_migracao_recusa_link_na_pasta_da_conta(self):
        import pty
        origem = self.tmp / "estado/catamara/contas"
        real = self.tmp / "real"
        (real / "log").mkdir(parents=True)
        (real / "settings.json").write_text("de fora")
        (origem / "conta1").mkdir(parents=True)
        (origem / "conta1/antigravity-cli").symlink_to(real)
        (origem / "conta2/antigravity-cli").mkdir(parents=True)
        mestre, escravo = pty.openpty()
        try:
            os.write(mestre, b"s\ns\nn\n")
            p = subprocess.run(["bash", str(REPO / "migrations/202610241200-importar-contas-agy.sh")],
                               env=self.env, stdin=escravo, capture_output=True, text=True, timeout=10)
        finally:
            os.close(mestre)
            os.close(escravo)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("importação de contas recusada", p.stderr)
        self.assertFalse((Path(self.env["JANGADA_ESTADO"]) / "contas").exists())

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

    def test_leitura_preparada_nao_reabre_fonte_oculta_no_executor(self):
        fonte = self.tmp / "fonte-temporaria.txt"
        fonte.write_text("texto autorizado antes do isolamento\n")
        registro = Path(self.env["JANGADA_ESTADO"]) / "agentes/leitura-preparada"
        registro.parent.mkdir(parents=True)
        argumentos = ["--registro", str(registro), "--papel", "leitor", "--fonte", str(fonte)]
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            modulo.pesquisa(argumentos + ["--preparar", "--", "agy", "-p", "Leia"])
        self.assertFalse(registro.exists())
        fonte.unlink()

        def conferir(comando, **_):
            pedido = comando[comando.index("-p")+1]
            self.assertEqual(pedido.count("1: texto autorizado antes do isolamento"), 1)
            self.assertIn(str(fonte), pedido)
            return subprocess.CompletedProcess(comando, 0)

        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(Path, "home", return_value=self.casa), \
                mock.patch.object(Path, "cwd", return_value=self.raiz), \
                mock.patch.object(modulo.subprocess, "run", side_effect=conferir) as chamada, \
                self.assertRaises(SystemExit) as fim:
            modulo.pesquisa(argumentos + ["--preparado", "--", "agy", "-p", saida.getvalue().rstrip("\n")])
        self.assertEqual(fim.exception.code, 0)
        chamada.assert_called_once()

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

    def preparar_keyring_falso(self, nega_busca_do_servico, pasta_run="run"):
        """Fakes de proxy, gdbus e bwrap para o jangada-isolar; devolve os registros."""
        self.manifesto = str(Path(json.loads(self.executar().stdout)["pasta"]) / "contrato.json")
        runtime = self.tmp / pasta_run
        runtime.mkdir(exist_ok=True)
        proxies = self.tmp / "proxies.log"
        chamada = self.tmp / "bwrap.args"
        self.script("xdg-dbus-proxy", "import socket, sys\n"
                    f"open({str(proxies)!r}, 'a').write(sys.argv[1] + '|' + sys.argv[2] + '|' + ' '.join(sys.argv[3:]) + '\\n')\n"
                    "socket.socket(socket.AF_UNIX).bind(sys.argv[2])\nprint('x')")
        self.script("gdbus", "import sys\n"
                    + ("if 'org.freedesktop.Secret.Service.SearchItems' in sys.argv:\n"
                       " sys.stderr.write('AccessDenied'); sys.exit(1)\n" if nega_busca_do_servico else "")
                    + "print(\"'/org/freedesktop/secrets/collection/login/14'\")")
        self.script("bwrap", "import sys\nfrom pathlib import Path\n"
                    f"Path({str(chamada)!r}).write_text('\\n'.join(sys.argv[1:]))")
        return runtime, proxies, chamada

    def sem_dependencia(self, motivo):
        # Com o isolamento real exigido, dependência ausente reprova em vez de pular.
        if os.environ.get("JANGADA_TESTES_EXIGIR_ISOLAMENTO") == "1":
            self.fail("isolamento real exigido, mas: " + motivo)
        self.skipTest(motivo)

    def exigir_bwrap(self):
        if not os.access("/usr/bin/bwrap", os.X_OK):
            self.sem_dependencia("Bubblewrap indisponível")
        capacidade = subprocess.run(["/usr/bin/bwrap", "--dev-bind", "/", "/", "true"], capture_output=True)
        if capacidade.returncode:
            self.sem_dependencia("Bubblewrap indisponível: " + capacidade.stderr.decode()[:200])

    def isolar_implementacao(self, runtime, extras=None, montado=None):
        """Roda o isolar; `montado` é o soquete que o bwrap monta no lugar, como faz o isolar de fora."""
        ambiente = {**self.env, "JANGADA_ISOLAR_PERFIL": "implementacao",
                    "JANGADA_IMPLEMENTACAO_MANIFESTO": self.manifesto, "XDG_RUNTIME_DIR": str(runtime),
                    "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(runtime / "bus"),
                    "JANGADA_ISOLAR_KEYRING_ITEM": "service=gemini username=antigravity", **(extras or {})}
        comando = [str(REPO / "bin/jangada-isolar"), "--", "agy"]
        if montado:
            comando = ["/usr/bin/bwrap", "--dev-bind", "/", "/", "--bind", str(montado), str(montado), "--"] + comando
        return subprocess.run(comando, cwd=self.raiz, env=ambiente, input="", capture_output=True, text=True)

    def test_chamada_aninhada_usa_o_soquete_do_implementador_sem_subir_proxy(self):
        # Dentro da sessão do autor o proxy dele nega Service.SearchItems e não
        # aceita outro xdg-dbus-proxy atrás de si (serial 0xFFFF0000 das
        # chamadas falsas). O soquete do implementador vem pronto de fora.
        self.exigir_bwrap()
        # Espaço no caminho: o mountinfo o escreve como \040.
        runtime, proxies, chamada = self.preparar_keyring_falso(nega_busca_do_servico=True, pasta_run="run com espaço")
        soquete = runtime / "bus-implementacao"
        servidor = socket.socket(socket.AF_UNIX)
        self.addCleanup(servidor.close)
        servidor.bind(str(soquete))
        p = self.isolar_implementacao(runtime, {"JANGADA_ISOLADO": "1", "JANGADA_MARCA_ISOLADO": "/"}, montado=soquete)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(proxies.exists(), "a chamada aninhada subiu outro proxy")
        argumentos = chamada.read_text().splitlines()
        i = argumentos.index(str(soquete))
        self.assertEqual(argumentos[i - 1:i + 2], ["--ro-bind", str(soquete), str(runtime / "bus")])
        self.assertIn("unix:path=" + str(runtime / "bus"), argumentos)

    def test_chamada_aninhada_sem_soquete_do_implementador_recusa_com_codigo_proprio(self):
        runtime, proxies, chamada = self.preparar_keyring_falso(nega_busca_do_servico=True)
        alvo = runtime / "bus-implementacao"
        outro = runtime / "bus"
        outro.touch()
        for preparo in (lambda: None, lambda: alvo.symlink_to(outro),
                        lambda: (alvo.unlink(), alvo.write_text(""))):
            preparo()
            p = self.isolar_implementacao(runtime, {"JANGADA_ISOLADO": "1", "JANGADA_MARCA_ISOLADO": "/"})
            self.assertEqual(p.returncode, 69, p.stderr)
            self.assertIn("sem login do agy no keyring", p.stderr)
            self.assertFalse(proxies.exists())
            self.assertFalse(chamada.exists())

    def test_chamada_aninhada_recusa_soquete_que_o_autor_criou_e_repassa_ao_bus_dele(self):
        # O autor cria o soquete na pasta em memória dele e repassa ao próprio
        # bus (que aceita CreateItem). Só um ponto de montagem, trazido de fora, vale.
        runtime, proxies, chamada = self.preparar_keyring_falso(nega_busca_do_servico=True)
        repasse = runtime / "bus"
        servidor = socket.socket(socket.AF_UNIX)
        self.addCleanup(servidor.close)
        servidor.bind(str(repasse))
        servidor.listen()
        forjado = runtime / "bus-implementacao"
        forjado2 = socket.socket(socket.AF_UNIX)
        self.addCleanup(forjado2.close)
        forjado2.bind(str(forjado))
        forjado2.listen()
        p = self.isolar_implementacao(runtime, {"JANGADA_ISOLADO": "1", "JANGADA_MARCA_ISOLADO": "/"})
        self.assertEqual(p.returncode, 69, p.stderr)
        self.assertIn("sem login do agy no keyring", p.stderr)
        self.assertFalse(chamada.exists(), "o implementador chegou a ser isolado com o soquete forjado")
        self.assertFalse(proxies.exists())

    def test_autor_recebe_segundo_soquete_com_o_filtro_do_implementador(self):
        runtime, proxies, chamada = self.preparar_keyring_falso(nega_busca_do_servico=False)
        ambiente = {**self.env, "XDG_RUNTIME_DIR": str(runtime),
                    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/inexistente",
                    "JANGADA_ISOLAR_KEYRING_ITEM": "service=gemini username=antigravity"}
        # A sessão do autor é a de um Claude que delega ao agy: só assim ela
        # recebe o login do agy e, com ele, o keyring.
        p = subprocess.run([str(REPO / "bin/jangada-isolar"), "--provedor", "claude", "--delegar", "agy", "--", "true"],
                           cwd=self.raiz, env=ambiente, input="", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        registros = [linha.split("|") for linha in proxies.read_text().splitlines()]
        self.assertEqual(len(registros), 2, registros)
        autor, implementador = (r[2] for r in registros)
        item = "/org/freedesktop/secrets/collection/login/14"
        self.assertIn("=*@" + item, autor)
        self.assertIn("org.freedesktop.Secret.Item.GetSecret@" + item, implementador)
        for proibido in ("CreateItem", "=*@", "--talk=org.freedesktop.secrets"):
            self.assertNotIn(proibido, implementador)
        argumentos = chamada.read_text().splitlines()
        destino = str(runtime / "bus-implementacao")
        self.assertIn(destino, argumentos)
        i = argumentos.index(destino)
        self.assertEqual(argumentos[i - 2], "--ro-bind")
        self.assertEqual(registros[1][1], argumentos[i - 1])
        self.assertNotEqual(registros[0][1], registros[1][1])

    def test_implementador_sem_login_do_agy_tem_motivo_proprio(self):
        # Chamada aninhada sem o soquete do implementador: antes era erro_execucao
        # com "o agy saiu com código 1" depois de ~65 s.
        runtime = self.tmp / "run"
        runtime.mkdir()
        self.env.update(JANGADA_ISOLADO="1", JANGADA_MARCA_ISOLADO="/", XDG_RUNTIME_DIR=str(runtime))
        p = self.executar(sucesso=False)
        resultado = json.loads(p.stdout)
        self.assertEqual(resultado["estado"], "falhou")
        self.assertEqual(resultado["motivo_codigo"], "sem_login_agy")
        self.assertIn("sem login", resultado["diagnostico"])
        registro = json.loads((self.tmp / "estado/jangada/delegacoes.jsonl").read_text().splitlines()[-1])
        self.assertEqual(registro["motivo_codigo"], "sem_login_agy")
        self.assertEqual(registro["motivo"],
                         "o agy do implementador ficou sem login: item do keyring ausente ou inacessível nesta sessão")
        self.assertEqual(registro["codigo_saida"], 4)

    def test_fronteira_real_aninhada_le_so_o_item_do_agy_pelo_soquete_de_fora(self):
        # A cadeia inteira com bwrap, xdg-dbus-proxy e barramento reais: o autor
        # roda o delegar dentro do jangada-isolar e o implementador, aninhado,
        # lê o item do agy pelo soquete que o isolar de fora trouxe. Antes, o
        # xdg-dbus-proxy interno era derrubado pelo proxy do autor.
        self.exigir_bwrap()
        if not all(shutil.which(nome) for nome in ("xdg-dbus-proxy", "dbus-daemon", "gdbus")):
            self.sem_dependencia("sem xdg-dbus-proxy, dbus-daemon ou gdbus")
        if subprocess.run(["python3", "-c", "import dbus, gi"], capture_output=True).returncode:
            self.sem_dependencia("sem dbus-python")
        (self.bin / "bwrap").unlink()
        kr = self.tmp / "kr"
        kr.mkdir()
        # Fora de self.tmp: a pasta gravável do autor cobriria os soquetes montados.
        runtime = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, runtime, True)
        (kr / "keyring.py").write_text(KEYRING_FALSO)
        barramento = "unix:path=" + str(kr / "bus")
        daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--address=" + barramento],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(daemon.wait)
        self.addCleanup(daemon.terminate)
        for _ in range(50):
            if (kr / "bus").exists():
                break
            time.sleep(0.1)
        servico = subprocess.Popen(["python3", str(kr / "keyring.py")], env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": barramento},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(servico.wait)
        self.addCleanup(servico.terminate)
        for _ in range(50):
            if (kr / "keyring.py.pronto").exists():
                break
            time.sleep(0.1)
        self.assertTrue((kr / "keyring.py.pronto").exists(), "keyring falso não subiu")
        self.script("agy", r'''import json,subprocess,sys
from pathlib import Path
if sys.argv[1:] == ["agents"]: print("implementador"); sys.exit()
if "/usage" in sys.argv:
 print(json.dumps({"command":{"data":{"groups":[{"buckets":[{"id":"gemini-weekly","remaining_fraction":0.9}]}]}}})); sys.exit()
RAIZ = "/org/freedesktop/secrets"
def gdbus(caminho, metodo, *args):
 r = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets", "--object-path", caminho,
                     "--method", metodo, *args], capture_output=True, text=True, timeout=20)
 return "ok" if r.returncode == 0 else "negado"
item = lambda n: RAIZ + "/collection/login/" + str(n)
resumo = [
 "item1=" + gdbus(item(1), "org.freedesktop.Secret.Item.GetSecret", "/"),
 "item2=" + gdbus(item(2), "org.freedesktop.Secret.Item.GetSecret", "/"),
 "busca=" + gdbus(RAIZ + "/collection/login", "org.freedesktop.Secret.Collection.SearchItems", "@a{ss} {}"),
 "criar=" + gdbus(RAIZ + "/collection/login", "org.freedesktop.Secret.Collection.CreateItem", "@a{sv} {}", "(objectpath '/', @ay [], @ay [], '')", "false"),
]
Path("dados.txt").write_text("valor=2\n" + "\n".join(resumo) + "\n")
print(json.dumps({"status":"SUCCESS","response":"dados.txt:1 valor atualizado","conversation_id":"sintetica"}))
''')
        ambiente = {**self.env, "XDG_RUNTIME_DIR": str(runtime), "DBUS_SESSION_BUS_ADDRESS": barramento,
                    "JANGADA_ISOLAR_KEYRING_ITEM": "service=agy-teste",
                    "JANGADA_ISOLAR_ESCRITA": str(self.tmp)}
        p = subprocess.run([str(REPO / "bin/jangada-isolar"), "--provedor", "claude", "--delegar", "agy", "--",
                            str(REPO / "bin/jangada-delegar"), "implementador",
                            "Mudar valor para 2", "--permitir-remoto", "--base", self.base, "--arquivos", "fonte.txt",
                            "--permitidos", "dados.txt", "--criterio", "O teste do autor exige valor=2"],
                           cwd=self.raiz, env=ambiente, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        resultado = json.loads(p.stdout)
        self.assertEqual(resultado["estado"], "aguarda_autor", p.stdout)
        self.assertEqual((Path(resultado["pasta"]) / "arquivos/dados.txt").read_text(),
                         "valor=2\nitem1=ok\nitem2=negado\nbusca=ok\ncriar=negado\n")

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
    import isolamento
    isolamento.instalar()
    unittest.main()
