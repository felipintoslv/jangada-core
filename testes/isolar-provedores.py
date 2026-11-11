#!/usr/bin/env python3
"""Provedores concedidos pelo jangada-isolar, no bwrap de verdade.

Cada caso roda uma sonda com o nome de um provedor numa casa falsa, com
logins, contas do agy, documentos e variáveis fictícias, e confere o que ela
lê de dentro do isolamento. Onde o bwrap não cria namespace, os casos se
pulam; com JANGADA_TESTES_EXIGIR_ISOLAMENTO=1, pular vira falha.

Uso: python3 testes/isolar-provedores.py
"""
import ambiente
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXIGIR = os.environ.get("JANGADA_TESTES_EXIGIR_ISOLAMENTO") == "1"

# Variáveis fictícias: as de cada provedor e as que nunca chegam ao agente.
DO_PROVEDOR = {
    "claude": ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"),
    "codex": ("OPENAI_API_KEY", "CODEX_API_KEY"),
    "agy": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}
SEMPRE_FORA = ("GH_TOKEN", "HF_TOKEN", "MISE_GITHUB_TOKEN", "NODE_AUTH_TOKEN", "SENHA_DO_BANCO",
               "JANGADA_VALIDAR_API_KEY", "AWS_SECRET_ACCESS_KEY")

SONDA = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
casa = Path.home()
arquivos = {}
for nome, caminho in json.loads(os.environ["JANGADA_SONDA_ARQUIVOS"]).items():
    try:
        arquivos[nome] = Path(caminho).read_text()
    except OSError:
        arquivos[nome] = None
nomes = json.loads(os.environ["JANGADA_SONDA_VARIAVEIS"])
saida = {"arquivos": arquivos, "ambiente": sorted(v for v in nomes if v in os.environ),
         "concedidos": os.environ.get("JANGADA_ISOLAR_CONCEDIDOS")}
espera = float(os.environ.get("JANGADA_SONDA_ESPERA", "0"))
if espera:
    cli = casa / ".gemini/antigravity-cli"
    (cli / "marca").write_text(os.urandom(8).hex())
    time.sleep(espera)
    saida["marca"] = (cli / "marca").read_text()
login = os.environ.get("JANGADA_SONDA_LOGIN")
if login:
    (casa / ".gemini/antigravity-cli/antigravity-oauth-token").write_text(login)
confia = os.environ.get("JANGADA_SONDA_CONFIA")
if confia:
    settings = casa / ".gemini/antigravity-cli/settings.json"
    dados = json.loads(settings.read_text())
    dados["trustedWorkspaces"].append(confia)
    settings.write_text(json.dumps(dados))
cache = casa / ".gemini/antigravity-cli/cache"
saida["cache"] = sorted(os.listdir(cache)) if cache.is_dir() else None
assistente = os.environ.get("JANGADA_SONDA_ASSISTENTE")
if assistente:
    try:
        (cache / "onboarding.json").write_text(assistente)
    except OSError:
        pass
aninhado = os.environ.get("JANGADA_SONDA_ANINHADO")
if aninhado:
    ambiente = {**os.environ, "JANGADA_SONDA_ANINHADO": ""}
    if os.environ.get("JANGADA_SONDA_DADOS_ANINHADO"):
        ambiente["JANGADA_ISOLAR_DADOS"] = os.environ["JANGADA_SONDA_DADOS_ANINHADO"]
    if os.environ.get("JANGADA_SONDA_SESSAO_ANTIGA"):
        ambiente.pop("JANGADA_ISOLAR_CONCEDIDOS", None)
    p = subprocess.run([os.environ["JANGADA_CORE_PATH"] + "/bin/jangada-isolar", "--", *json.loads(aninhado)],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, env=ambiente)
    saida["aninhado"] = {"rc": p.returncode, "erro": p.stderr, "saida": p.stdout}
# Sessão viva: avisa que montou e, até o teste mandar sair, troca por link o
# caminho pedido dentro da própria casa, como faria um agente hostil.
viva = os.environ.get("JANGADA_SONDA_VIVA")
if viva:
    import shutil
    controle = Path(viva)
    (controle / "pronto").write_text("")
    prazo = time.time() + 60
    while not (controle / "sair").exists() and time.time() < prazo:
        pedido = controle / "trocar"
        if pedido.exists():
            alvo, destino = pedido.read_text().split("\n")[:2]
            alvo = casa / alvo
            if alvo.is_dir() and not alvo.is_symlink():
                shutil.rmtree(alvo)
            elif alvo.exists() or alvo.is_symlink():
                alvo.unlink()
            alvo.symlink_to(destino)
            pedido.unlink()
            (controle / "trocou").write_text("")
        time.sleep(0.05)
print(json.dumps(saida))
'''

# Substitui cp e mkdir só na segunda abertura. Quando o último argumento é o
# caminho pedido dentro de provedores/, faz a troca por link no meio da
# preparação: pede à sessão viva (que enxerga o caminho montado) ou troca daqui
# de fora (pasta que a sessão viva não alcança, mas a preparação sim). Depois
# roda o comando verdadeiro. Torna determinística a janela entre a conferência
# de link e a gravação.
CORRIDA = r'''#!/usr/bin/python3 -I
import json, os, shutil, sys, time
from pathlib import Path
nome = os.path.basename(sys.argv[0])
for passo in json.loads(os.environ.get("JANGADA_TESTE_CORRIDA", "[]")):
    alvo = sys.argv[-1]
    if passo["comando"] != nome or "/provedores/" not in alvo or not alvo.endswith(passo["sufixo"]):
        continue
    with open(passo["registro"], "a") as r:
        r.write(passo["sufixo"] + "\n")
    if passo.get("controle"):
        c = Path(passo["controle"])
        (c / "trocar").write_text(passo["alvo"] + "\n" + passo["destino"])
        prazo = time.time() + 20
        while not (c / "trocou").exists() and time.time() < prazo:
            time.sleep(0.05)
        (c / "trocou").unlink(missing_ok=True)
    else:
        p = Path(alvo)
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        p.symlink_to(passo["destino"])
os.execv("/usr/bin/" + nome, [nome, *sys.argv[1:]])
'''


# Base anterior à trava da pasta de dados da sessão.
BASE_TRAVA = "ad39d3e"


def bwrap_funciona():
    try:
        return subprocess.run(["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
                              capture_output=True).returncode == 0
    except OSError:
        return False


class Provedores(unittest.TestCase):
    def setUp(self):
        if not bwrap_funciona():
            if EXIGIR:
                self.fail("o isolamento real é exigido e o bwrap não cria namespace aqui")
            self.skipTest("bwrap não cria namespace aqui")
        # Fora do /tmp: o isolamento dá ao agente um /tmp próprio.
        try:
            self.tmp = Path(tempfile.mkdtemp(dir="/var/tmp", prefix="jangada-provedores-"))
        except OSError:
            if EXIGIR:
                self.fail("/var/tmp sem escrita")
            self.skipTest("/var/tmp sem escrita")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.casa = casa = self.tmp / "casa"
        self.raiz = self.tmp / "projeto"
        self.bin = self.tmp / "bin"
        self.estado = casa / ".local/state/jangada"
        for pasta in (casa / ".claude", casa / ".codex", casa / ".gemini/antigravity-cli", casa / "Documentos",
                      self.raiz, self.bin, self.tmp / "config/jangada"):
            pasta.mkdir(parents=True)
        self.arquivos = {
            "claude": casa / ".claude/.credentials.json",
            "claude.json": casa / ".claude.json",
            "codex": casa / ".codex/auth.json",
            "agy": casa / ".gemini/antigravity-cli/antigravity-oauth-token",
            "documento": casa / "Documentos/pessoal.txt",
            "zshrc": casa / ".zshrc",
        }
        for nome, caminho in self.arquivos.items():
            caminho.write_text("falso-" + nome)
        subprocess.run(["git", "init", "-q", str(self.raiz)], check=True)
        subprocess.run(["git", "-C", str(self.raiz), "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "inicio"], check=True)
        sonda = self.bin / "sonda"
        sonda.write_text(SONDA)
        sonda.chmod(0o755)
        for nome in ("claude", "codex", "agy"):
            (self.bin / nome).symlink_to(sonda)
        nomes = [v for vs in DO_PROVEDOR.values() for v in vs] + list(SEMPRE_FORA)
        self.env = {
            "HOME": str(casa), "PATH": f"{self.bin}:/usr/bin:/bin", "LANG": "C.UTF-8",
            "XDG_STATE_HOME": str(casa / ".local/state"), "XDG_CONFIG_HOME": str(self.tmp / "config"),
            "JANGADA_CORE_PATH": str(REPO), "JANGADA_MARCA_ISOLADO": f"/tmp/.jangada-isolado-provedores-{os.getpid()}",
            "JANGADA_SONDA_VARIAVEIS": json.dumps(nomes),
            **{v: "falso-" + v for v in nomes},
        }

    def contas(self):
        """Catálogo do agy com duas contas no estado do jangada."""
        base = self.estado / "contas"
        catalogo = []
        for nome in ("conta1", "conta2"):
            pasta = base / nome
            pasta.mkdir(parents=True)
            (pasta / "antigravity-oauth-token").write_text("falso-" + nome)
            (pasta / "settings.json").write_text(json.dumps({"trustedWorkspaces": [str(self.raiz)]}))
            self.arquivos[nome] = pasta / "antigravity-oauth-token"
            catalogo.append({"nome": nome, "pasta": str(pasta), "argon": False})
        (base / "agy.json").write_text(json.dumps(catalogo))

    def iniciar(self, *args, env=None):
        ambiente = {**self.env, "JANGADA_SONDA_ARQUIVOS": json.dumps({k: str(v) for k, v in self.arquivos.items()}),
                    **(env or {})}
        saida = open(self.tmp / f"saida-{time.monotonic_ns()}", "w+")
        self.addCleanup(saida.close)
        p = subprocess.Popen([str(REPO / "bin/jangada-isolar"), *args], cwd=self.raiz, env=ambiente,
                             stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.PIPE, text=True)
        return p, saida

    def resultado(self, p, saida):
        _, erro = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, erro)
        saida.seek(0)
        return json.loads(saida.read()), erro

    def rodar(self, *args, env=None):
        return self.resultado(*self.iniciar(*args, env=env))[0]

    def conferir(self, r, lidos, ambiente):
        legiveis = {k for k, v in r["arquivos"].items() if v is not None}
        self.assertEqual(legiveis, set(lidos), r)
        for nome in lidos:
            self.assertEqual(r["arquivos"][nome], "falso-" + nome)
        esperadas = sorted(v for p in ambiente for v in DO_PROVEDOR[p])
        self.assertEqual(r["ambiente"], esperadas, r)

    def test_cada_provedor_le_so_o_proprio_login(self):
        for provedor, lidos in (("claude", {"claude", "claude.json"}), ("codex", {"codex"}), ("agy", {"agy"})):
            with self.subTest(provedor=provedor):
                r = self.rodar("--", provedor)
                self.conferir(r, lidos, {provedor})
                self.assertEqual(r["concedidos"], provedor)

    def test_comando_que_nao_e_provedor_nao_recebe_login(self):
        r = self.rodar("--", "sonda")
        self.conferir(r, set(), set())
        self.assertEqual(r["concedidos"], "")

    def test_provedor_explicito_vale_sobre_o_nome_do_comando(self):
        self.conferir(self.rodar("--provedor", "codex", "--", "sonda"), {"codex"}, {"codex"})
        self.conferir(self.rodar("--provedor", "nenhum", "--", "claude"), set(), set())

    def test_delegacao_concede_so_o_destino(self):
        self.conferir(self.rodar("--delegar", "agy", "--", "claude"), {"claude", "claude.json", "agy"}, {"claude", "agy"})
        self.conferir(self.rodar("--delegar", "nativo", "--", "claude"), {"claude", "claude.json"}, {"claude"})
        # O Codex entra só com os modelos do Codex econômico configurados.
        self.conferir(self.rodar("--delegar", "claude", "--", "claude", env={"JANGADA_CODEX_ECONOMICO_MODELO": "m"}),
                      {"claude", "claude.json", "codex"}, {"claude", "codex"})
        # O agy delega a si mesmo: a delegação não abre outro provedor.
        self.conferir(self.rodar("--delegar", "claude", "--", "agy"), {"agy"}, {"agy"})

    def test_extensao_explicita_e_validada(self):
        self.conferir(self.rodar("--", "sonda", env={"JANGADA_ISOLAR_PROVEDORES": "codex:claude"}),
                      {"codex", "claude", "claude.json"}, {"codex", "claude"})
        p, saida = self.iniciar("--", "sonda", env={"JANGADA_ISOLAR_PROVEDORES": "openai"})
        _, erro = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 1)
        self.assertIn("provedor desconhecido", erro)

    def test_transicao_volta_a_casa_e_ao_ambiente_com_aviso_mas_nao_ao_login_de_outro(self):
        p, saida = self.iniciar("--", "claude", env={"JANGADA_ISOLAR_CASA": "inteira", "JANGADA_ISOLAR_AMBIENTE": "herdado"})
        r, erro = self.resultado(p, saida)
        self.assertIn("JANGADA_ISOLAR_CASA=inteira", erro)
        self.assertIn("JANGADA_ISOLAR_AMBIENTE=herdado", erro)
        self.conferir(r, {"claude", "claude.json", "documento", "zshrc"}, {"claude"})

    def test_conta_do_agy_so_a_selecionada(self):
        self.contas()
        for conta, outra in (("conta1", "conta2"), ("conta2", "conta1")):
            with self.subTest(conta=conta):
                r = self.rodar("--conta", conta, "--", "agy")
                self.assertEqual(r["arquivos"]["agy"], "falso-" + conta)
                self.assertIsNone(r["arquivos"][outra])
                self.assertIsNone(r["arquivos"][conta], "a origem da conta aparece fora da pasta montada")
                self.assertIsNone(r["arquivos"]["claude"])
                self.assertIsNone(r["arquivos"]["codex"])
        # Sem o agy concedido, a conta não é montada nem a principal aparece.
        r = self.rodar("--conta", "conta2", "--", "claude")
        for nome in ("agy", "conta1", "conta2"):
            self.assertIsNone(r["arquivos"][nome], nome)

    def barramento(self):
        """D-Bus de sessão próprio, com o proxy real registrando os argumentos."""
        if not shutil.which("dbus-daemon") or not shutil.which("xdg-dbus-proxy"):
            if EXIGIR:
                self.fail("dbus-daemon e xdg-dbus-proxy são exigidos neste caso")
            self.skipTest("dbus-daemon ou xdg-dbus-proxy ausente")
        runtime = self.tmp / "runtime"
        runtime.mkdir(mode=0o700)
        bus = subprocess.run(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1",
                              f"--address=unix:path={runtime}/original"],
                             capture_output=True, text=True, check=True)
        endereco, pid = bus.stdout.splitlines()
        self.addCleanup(os.kill, int(pid), signal.SIGTERM)
        registro = self.tmp / "proxy.jsonl"
        busca = self.tmp / "busca-keyring"
        # O proxy real aplica o filtro; o invólucro registra só argumentos,
        # sem segredos. A busca externa falsa acusa qualquer consulta e, com
        # JANGADA_SONDA_ITEM, devolve esse item como o SearchItems do serviço.
        proxy = self.bin / "xdg-dbus-proxy"
        proxy.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                         "with open(os.environ['JANGADA_SONDA_PROXY'], 'a') as f: "
                         "f.write(json.dumps(sys.argv[1:])+'\\n')\n"
                         f"os.execv({shutil.which('xdg-dbus-proxy')!r}, sys.argv)\n")
        proxy.chmod(0o755)
        gdbus = self.bin / "gdbus"
        gdbus.write_text(f"#!/bin/sh\ntouch '{busca}'\n[ -n \"$JANGADA_SONDA_ITEM\" ] || exit 1\n"
                         "printf \"([objectpath '%s'], @ao [])\\n\" \"$JANGADA_SONDA_ITEM\"\n")
        gdbus.chmod(0o755)
        ambiente = {"XDG_RUNTIME_DIR": str(runtime), "DBUS_SESSION_BUS_ADDRESS": endereco,
                    "JANGADA_SONDA_PROXY": str(registro),
                    "JANGADA_ISOLAR_KEYRING_ITEM": "service=gemini username=antigravity"}
        return ambiente, registro, busca

    def test_login_e_renovacao_da_conta_sem_keyring(self):
        self.contas()
        ambiente, registro, busca = self.barramento()
        # Primeiro login com arquivo ausente; em seguida, renovação no mesmo
        # arquivo, outra conta e modo legado servico com atributos vazios.
        self.arquivos["conta1"].unlink()
        for conta, modo, atributos, login in (
                ("conta1", "itens", ambiente["JANGADA_ISOLAR_KEYRING_ITEM"], "login-ficticio"),
                ("conta1", "servico", ambiente["JANGADA_ISOLAR_KEYRING_ITEM"], "renovado-ficticio"),
                ("conta2", "servico", "", "outro-login-ficticio")):
            with self.subTest(conta=conta, modo=modo, atributos=atributos):
                antes = {n: p.read_bytes() if p.exists() else None for n, p in self.arquivos.items()}
                self.rodar("--conta", conta, "--", "agy", env={**ambiente,
                           "JANGADA_ISOLAR_KEYRING": modo, "JANGADA_ISOLAR_KEYRING_ITEM": atributos,
                           "JANGADA_SONDA_LOGIN": login})
                self.assertEqual(self.arquivos[conta].read_text(), login)
                if conta == "conta1":
                    self.assertEqual(self.arquivos[conta].stat().st_mode & 0o777, 0o600)
                for nome in ("agy", "conta2" if conta == "conta1" else "conta1"):
                    self.assertEqual(self.arquivos[nome].read_bytes(), antes[nome], nome)
                r = self.rodar("--conta", conta, "--", "agy", env=ambiente)
                self.assertEqual(r["arquivos"]["agy"], login, "login perdido ao reabrir")
        filtros = [json.loads(l) for l in registro.read_text().splitlines()]
        self.assertEqual(len(filtros), 6, filtros)
        for filtro in filtros:
            self.assertIn("--talk=org.freedesktop.Notifications", filtro)
            self.assertFalse(any("org.freedesktop.secrets" in arg for arg in filtro), filtro)
        self.assertFalse(busca.exists(), "o catálogo não deve buscar o item global")

    def test_login_da_conta_so_e_criado_na_area_de_contas(self):
        self.contas()
        principal = self.arquivos["agy"]
        catalogo = json.loads((self.estado / "contas/agy.json").read_text())
        catalogo.append({"nome": "principal", "pasta": str(principal.parent), "argon": False})
        (self.estado / "contas/agy.json").write_text(json.dumps(catalogo))
        principal.unlink()
        p, saida = self.iniciar("--conta", "principal", "--", "agy")
        _, erro = self.resultado(p, saida)
        self.assertIn("pasta padrão do agy sem arquivo de login", erro)
        self.assertFalse(principal.exists(), "login criado fora da área de contas")
        conta = self.arquivos["conta1"]
        conta.unlink()
        p, _ = self.iniciar("--mostrar", "--conta", "conta1", "--", "agy")
        p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertFalse(conta.exists(), "--mostrar criou o login")
        alvo = self.tmp / "alvo"
        for preparo, motivo in ((lambda: conta.mkdir(), "não é arquivo regular"),
                                (lambda: (conta.rmdir(), conta.symlink_to(alvo)), "é link")):
            preparo()
            with self.subTest(motivo=motivo):
                p, _ = self.iniciar("--conta", "conta1", "--", "agy")
                _, erro = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 1, erro)
                self.assertIn(motivo, erro)
                self.assertFalse(alvo.exists(), "login criado no destino do link")

    def test_sem_catalogo_igual_ao_main(self):
        # Base anterior ao catálogo fechar o keyring: sem catálogo, o filtro do
        # D-Bus, as mensagens, os códigos e o que o agente lê ficam iguais.
        base = "c3247ac"
        original = subprocess.run(["git", "-C", str(REPO), "show", f"{base}:bin/jangada-isolar"],
                                  capture_output=True, text=True)
        if original.returncode:
            if EXIGIR:
                self.fail(f"commit {base} indisponível")
            self.skipTest(f"commit {base} indisponível")
        pasta_base = self.tmp / "base"
        pasta_base.mkdir()
        (pasta_base / "jangada-isolar").write_text(original.stdout)
        (pasta_base / "jangada-isolar").chmod(0o755)
        (pasta_base / "jangada-config").symlink_to(REPO / "bin/jangada-config")
        ambiente, registro, busca = self.barramento()
        item = "/org/freedesktop/secrets/collection/login/14"
        casos = (("itens sem atributos", {"JANGADA_ISOLAR_KEYRING_ITEM": ""}),
                 ("servico sem atributos", {"JANGADA_ISOLAR_KEYRING_ITEM": "", "JANGADA_ISOLAR_KEYRING": "servico"}),
                 ("atributos com item", {"JANGADA_SONDA_ITEM": item}),
                 ("atributos sem item", {}),
                 ("atributos inválidos", {"JANGADA_ISOLAR_KEYRING_ITEM": "sem-igual"}))

        def executar(isolar, extras, principal_ausente):
            if principal_ausente and self.arquivos["agy"].exists():
                self.arquivos["agy"].unlink()
            registro.unlink(missing_ok=True)
            busca.unlink(missing_ok=True)
            env = {**self.env, **ambiente, **extras,
                   "JANGADA_SONDA_ARQUIVOS": json.dumps({k: str(v) for k, v in self.arquivos.items()})}
            p = subprocess.run([str(isolar), "--", "agy"], cwd=self.raiz, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=60)
            filtros = [[a for a in json.loads(l) if a.startswith("--") and not a.startswith("--fd")]
                       for l in registro.read_text().splitlines()] if registro.exists() else []
            return {"rc": p.returncode, "erro": p.stderr, "saida": p.stdout, "filtros": filtros,
                    "busca": busca.exists(), "login_principal": self.arquivos["agy"].exists()}

        for principal_ausente in (False, True):
            for nome, extras in casos:
                with self.subTest(caso=nome, principal_ausente=principal_ausente):
                    antes = executar(pasta_base / "jangada-isolar", extras, principal_ausente)
                    depois = executar(REPO / "bin/jangada-isolar", extras, principal_ausente)
                    self.assertEqual(depois, antes)
                    self.assertTrue(antes["filtros"], "o proxy não subiu")
                    self.assertEqual(antes["login_principal"], not principal_ausente)
                    if principal_ausente:
                        principal = self.arquivos["agy"]
                        principal.write_text("falso-agy")

    def test_execucoes_simultaneas_ficam_separadas(self):
        self.contas()
        espera = {"JANGADA_SONDA_ESPERA": "2"}
        a = self.iniciar("--conta", "conta1", "--", "agy", env=espera)
        b = self.iniciar("--conta", "conta2", "--", "agy", env=espera)
        c = self.iniciar("--", "claude", env=espera)
        ra, rb, rc = (self.resultado(*x)[0] for x in (a, b, c))
        self.assertEqual(ra["arquivos"]["agy"], "falso-conta1")
        self.assertEqual(rb["arquivos"]["agy"], "falso-conta2")
        self.assertIsNone(rc["arquivos"]["agy"])
        self.assertIsNone(ra["arquivos"]["claude"])
        self.assertEqual(rc["arquivos"]["claude"], "falso-claude")
        # Desde os dados por sessão, cada execução grava numa pasta própria,
        # efêmera sem JANGADA_SESSAO: a marca não chega à conta e não sobra.
        self.assertNotEqual(ra["marca"], rb["marca"])
        for conta in ("conta1", "conta2"):
            self.assertFalse((self.estado / "contas" / conta / "marca").exists(), conta)
        self.assertEqual(list((self.estado / "provedores").glob("*/efemera-*")), [])
        self.assertFalse((self.casa / ".gemini/antigravity-cli/marca").exists(), "a execução do claude gravou no agy")

    def test_oferta_de_confianca_guarda_a_copia_para_o_chamador(self):
        # jangada_agy_conferir_tarefa passa confianca-PID-HEX para ler, depois
        # que o agy sai, a cópia do settings.json que ele usou.
        self.contas()
        chave = f"confianca-{os.getpid()}-0123456789abcdef"
        provedor = self.estado / "provedores/agy-conta1"
        self.rodar("--conta", "conta1", "--", "agy",
                   env={"JANGADA_ISOLAR_DADOS": chave, "JANGADA_SONDA_CONFIA": "/nova/raiz"})
        copia = json.loads((provedor / chave / "settings.json").read_text())
        self.assertEqual(copia["trustedWorkspaces"], [str(self.raiz), "/nova/raiz"])
        conta = json.loads((self.estado / "contas/conta1/settings.json").read_text())
        self.assertEqual(conta["trustedWorkspaces"], [str(self.raiz)], "o isolador gravou a conta")
        for args, outra in ((("--conta", "conta1"), "confianca-x-0123456789abcdef"),
                            (("--conta", "conta1"), "confianca-1-0123"), ((), chave)):
            with self.subTest(args=args, chave=outra):
                p, _ = self.iniciar(*args, "--", "agy", env={"JANGADA_ISOLAR_DADOS": outra})
                _, erro = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 1, erro)
                self.assertIn("JANGADA_ISOLAR_DADOS aceita", erro)
        # De dentro do isolamento a chave é recusada.
        r = self.rodar("--conta", "conta1", "--", "agy",
                       env={"JANGADA_SONDA_ANINHADO": json.dumps(["agy"]), "JANGADA_SONDA_DADOS_ANINHADO": chave})
        self.assertEqual(r["aninhado"]["rc"], 1, r)
        self.assertIn("não vale dentro do isolamento", r["aninhado"]["erro"])
        # A pasta de um chamador morto some na próxima abertura; a de um vivo fica.
        morto = subprocess.Popen(["true"])
        morto.wait()
        sobra = provedor / f"confianca-{morto.pid}-0123456789abcdef"
        sobra.mkdir()
        self.rodar("--conta", "conta1", "--", "agy")
        self.assertFalse(sobra.exists(), "pasta de chamador morto ficou")
        self.assertTrue((provedor / chave).exists(), "pasta de chamador vivo sumiu")

    ASSISTENTE = ('{"consumerOnboardingComplete": true, "enterpriseOnboardingComplete": false, '
                  '"onboardingComplete": true}')

    def preparar_cache(self, pasta):
        """cache/ de uma pasta do agy com a marca do assistente e outros dados."""
        cache = pasta / "cache"
        (cache / "marketplaces").mkdir(parents=True, exist_ok=True)
        (cache / "onboarding.json").write_text(self.ASSISTENTE)
        for nome in ("conversation_metadata.json", "last_conversations.json", "default_project_id.txt",
                     "marketplaces/lista.json"):
            (cache / nome).write_text("falso-" + nome)
        return cache / "onboarding.json"

    def test_assistente_inicial_concluido_vem_da_conta(self):
        # O agy grava em cache/onboarding.json que o assistente inicial (tema e
        # termos) acabou; sem o arquivo, toda pasta nova de sessão o mostra.
        self.contas()
        dentro = self.casa / ".gemini/antigravity-cli/cache/onboarding.json"
        casos = (("catálogo", ("--conta", "conta1"), self.estado / "contas/conta1"),
                 ("sem catálogo", (), self.casa / ".gemini/antigravity-cli"))
        for nome, args, pasta in casos:
            with self.subTest(caso=nome):
                if not args:
                    (self.estado / "contas/agy.json").unlink()
                conta = self.preparar_cache(pasta)
                ambiente = {"JANGADA_SONDA_ARQUIVOS": json.dumps({"assistente": str(dentro)}),
                            "JANGADA_SONDA_ASSISTENTE": "alterado"}
                for _ in range(2):
                    r = self.rodar(*args, "--", "agy", env=ambiente)
                    self.assertEqual(r["arquivos"]["assistente"], self.ASSISTENTE)
                    self.assertEqual(r["cache"], ["onboarding.json"], "outros dados do cache vieram da conta")
                    self.assertEqual(conta.read_text(), self.ASSISTENTE, "a cópia alterada voltou à conta")
                if nome == "catálogo":
                    # Numa sessão que persiste, a cópia é refeita a cada abertura.
                    sessao = {**ambiente, "JANGADA_SESSAO": "tarefa1"}
                    for _ in range(2):
                        r = self.rodar(*args, "--", "agy", env=sessao)
                        self.assertEqual(r["arquivos"]["assistente"], self.ASSISTENTE)
                    copia = self.estado / "provedores/agy-conta1/tarefa1/cache/onboarding.json"
                    self.assertEqual(copia.read_text(), "alterado")
                    self.assertEqual(copia.stat().st_mode & 0o777, 0o600)

    def test_assistente_da_conta_fora_do_formato_nao_e_copiado(self):
        self.contas()
        pasta = self.estado / "contas/conta1"
        # O isolamento cria bin/ na conta a cada abertura; existir antes deixa
        # a comparação da conta inteira valer desde a primeira.
        (pasta / "bin").mkdir()
        dentro = self.casa / ".gemini/antigravity-cli/cache/onboarding.json"
        ambiente = {"JANGADA_SONDA_ARQUIVOS": json.dumps({"assistente": str(dentro), "agy": str(self.arquivos["agy"])})}
        fora = self.tmp / "fora"
        fora.mkdir()
        (fora / "onboarding.json").write_text(self.ASSISTENTE)

        def arquivo_link():
            (pasta / "cache").mkdir()
            (pasta / "cache/onboarding.json").symlink_to(fora / "onboarding.json")

        def cache_link():
            (pasta / "cache").symlink_to(fora)

        def grande():
            (pasta / "cache").mkdir()
            (pasta / "cache/onboarding.json").write_text(" " * 4097)

        def pasta_no_lugar():
            (pasta / "cache/onboarding.json").mkdir(parents=True)

        for nome, preparo in (("arquivo é link", arquivo_link), ("cache é link", cache_link),
                              ("grande demais", grande), ("não é arquivo", pasta_no_lugar)):
            with self.subTest(caso=nome):
                if (pasta / "cache").is_symlink():
                    (pasta / "cache").unlink()
                shutil.rmtree(pasta / "cache", ignore_errors=True)
                preparo()
                antes = sorted((str(p.relative_to(self.tmp)), p.is_symlink(), p.is_file() and p.read_text())
                               for p in [*pasta.rglob("*"), *fora.rglob("*")])
                p, saida = self.iniciar("--conta", "conta1", "--", "agy", env=ambiente)
                r, erro = self.resultado(p, saida)
                self.assertIn("o agy mostra o assistente inicial", erro)
                self.assertIsNone(r["arquivos"]["assistente"])
                self.assertEqual(r["arquivos"]["agy"], "falso-conta1", "a abertura não seguiu")
                depois = sorted((str(p.relative_to(self.tmp)), p.is_symlink(), p.is_file() and p.read_text())
                                for p in [*pasta.rglob("*"), *fora.rglob("*")])
                self.assertEqual(depois, antes, "a conta mudou")
        # Link já posto pelo agente nos dados da sessão: recusa abrir.
        shutil.rmtree(pasta / "cache")
        conta = self.preparar_cache(pasta)
        # Sessão que persiste: arquivo da conta recusado depois não apaga a
        # cópia que a sessão já tem.
        persistente = {**ambiente, "JANGADA_SESSAO": "tarefa2"}
        r = self.rodar("--conta", "conta1", "--", "agy", env=persistente)
        self.assertEqual(r["arquivos"]["assistente"], self.ASSISTENTE)
        conta.write_text(" " * 4097)
        p, saida = self.iniciar("--conta", "conta1", "--", "agy", env=persistente)
        r, erro = self.resultado(p, saida)
        self.assertIn("o agy mostra o assistente inicial", erro)
        self.assertEqual(r["arquivos"]["assistente"], self.ASSISTENTE, "a cópia da sessão sumiu")
        self.assertEqual(conta.read_text(), " " * 4097, "a conta mudou")
        conta.write_text(self.ASSISTENTE)
        sessao = self.estado / "provedores/agy-conta1/tarefa1"
        for alvo in ("cache", "cache/onboarding.json"):
            with self.subTest(destino=alvo):
                shutil.rmtree(sessao, ignore_errors=True)
                (sessao / alvo).parent.mkdir(parents=True, exist_ok=True)
                (sessao / alvo).symlink_to(fora / "copia")
                p, _ = self.iniciar("--conta", "conta1", "--", "agy", env={**ambiente, "JANGADA_SESSAO": "tarefa1"})
                _, erro = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 1, erro)
                self.assertIn("link em", erro)
                self.assertFalse((fora / "copia").exists(), "a cópia seguiu o link")

    def test_conta_sem_assistente_igual_a_base(self):
        # Base anterior à cópia da marca do assistente: sem o arquivo na
        # conta, saída, mensagens e dados da sessão ficam iguais.
        base = "9c399e1"
        original = subprocess.run(["git", "-C", str(REPO), "show", f"{base}:bin/jangada-isolar"],
                                  capture_output=True, text=True)
        if original.returncode:
            if EXIGIR:
                self.fail(f"commit {base} indisponível")
            self.skipTest(f"commit {base} indisponível")
        pasta_base = self.tmp / "base"
        pasta_base.mkdir()
        (pasta_base / "jangada-isolar").write_text(original.stdout)
        (pasta_base / "jangada-isolar").chmod(0o755)
        (pasta_base / "jangada-config").symlink_to(REPO / "bin/jangada-config")
        self.contas()
        for pasta in (self.estado / "contas/conta1", self.casa / ".gemini/antigravity-cli"):
            (pasta / "cache").mkdir()
            (pasta / "cache/last_conversations.json").write_text("falso-cache")
        catalogo = self.estado / "contas/agy.json"
        dentro = self.casa / ".gemini/antigravity-cli/cache/onboarding.json"

        def arvore(pasta):
            return sorted((str(p.relative_to(pasta)), p.is_dir(), p.stat().st_mode & 0o777,
                           p.read_text() if p.is_file() else None) for p in pasta.rglob("*"))

        for nome, args in (("catálogo", ("--conta", "conta1")), ("sem catálogo", ())):
            with self.subTest(caso=nome):
                if nome == "sem catálogo":
                    catalogo.unlink()
                provedor = self.estado / ("provedores/agy-conta1" if args else "provedores/agy-principal")
                resultados = []
                for isolar, sessao in ((pasta_base / "jangada-isolar", "base-" + str(len(args))),
                                       (REPO / "bin/jangada-isolar", "novo-" + str(len(args)))):
                    env = {**self.env, "JANGADA_SESSAO": sessao,
                           "JANGADA_SONDA_ARQUIVOS": json.dumps({"assistente": str(dentro),
                                                                 "agy": str(self.arquivos["agy"])})}
                    p = subprocess.run([str(isolar), *args, "--", "agy"], cwd=self.raiz, env=env,
                                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
                    resultados.append({"rc": p.returncode, "saida": p.stdout, "erro": p.stderr,
                                       "arvore": arvore(provedor / sessao)})
                self.assertEqual(resultados[1], resultados[0])
                self.assertEqual(resultados[0]["rc"], 0, resultados[0]["erro"])
                self.assertIsNone(json.loads(resultados[0]["saida"])["arquivos"]["assistente"])

    def base(self, commit):
        pasta = self.tmp / f"base-{commit}"
        if not pasta.exists():
            original = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:bin/jangada-isolar"],
                                      capture_output=True, text=True)
            if original.returncode:
                if EXIGIR:
                    self.fail(f"commit {commit} indisponível")
                self.skipTest(f"commit {commit} indisponível")
            pasta.mkdir()
            (pasta / "jangada-isolar").write_text(original.stdout)
            (pasta / "jangada-isolar").chmod(0o755)
            (pasta / "jangada-config").symlink_to(REPO / "bin/jangada-config")
        return pasta / "jangada-isolar"

    def viva(self, isolar, args, sessao):
        """Abre a sessão e espera a sonda dizer que está montada e viva."""
        controle = self.raiz / f".controle-{time.monotonic_ns()}"
        controle.mkdir()
        env = {**self.env, "JANGADA_SESSAO": sessao, "JANGADA_SONDA_VIVA": str(controle),
               "JANGADA_SONDA_ARQUIVOS": "{}"}
        saida = open(self.tmp / f"viva-{time.monotonic_ns()}", "w+")
        self.addCleanup(saida.close)
        p = subprocess.Popen([str(isolar), *args], cwd=self.raiz, env=env, stdin=subprocess.DEVNULL,
                             stdout=saida, stderr=saida, text=True)

        def fechar():
            (controle / "sair").write_text("")
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        self.addCleanup(fechar)
        prazo = time.monotonic() + 30
        while not (controle / "pronto").exists():
            if p.poll() is not None:
                saida.seek(0)
                self.fail(f"a sessão viva saiu antes de montar: {saida.read()}")
            if time.monotonic() > prazo:
                self.fail("a sessão viva não montou")
            time.sleep(0.05)
        return controle, fechar

    def segunda(self, isolar, args, sessao, plano=(), arquivos=None):
        """Segunda abertura da mesma sessão, com cp e mkdir substituídos."""
        corrida = self.tmp / "corrida"
        if not corrida.exists():
            corrida.mkdir()
            (corrida / "substituto").write_text(CORRIDA)
            (corrida / "substituto").chmod(0o755)
            for nome in ("cp", "mkdir"):
                (corrida / nome).symlink_to(corrida / "substituto")
        registro = self.tmp / f"registro-{time.monotonic_ns()}"
        env = {**self.env, "PATH": f"{corrida}:{self.env['PATH']}", "JANGADA_SESSAO": sessao,
               "JANGADA_TESTE_CORRIDA": json.dumps([{**passo, "registro": str(registro)} for passo in plano]),
               "JANGADA_SONDA_ARQUIVOS": json.dumps(arquivos or {})}
        inicio = time.monotonic()
        p = subprocess.run([str(isolar), *args], cwd=self.raiz, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        return {"rc": p.returncode, "erro": p.stderr, "saida": p.stdout, "segundos": time.monotonic() - inicio,
                "acionados": registro.read_text().split() if registro.exists() else []}

    def test_segunda_abertura_da_mesma_sessao_e_recusada(self):
        # Na base sem trava a segunda abertura prepara a pasta que a primeira,
        # viva, tem montada. Agora espera 5 s pela trava e recusa.
        self.contas()
        base = self.base(BASE_TRAVA)
        for nome, args in (("claude", ("--", "claude")), ("agy-conta1", ("--conta", "conta1", "--", "agy"))):
            for isolar, versao in ((base, "base"), (REPO / "bin/jangada-isolar", "nova")):
                with self.subTest(provedor=nome, versao=versao):
                    sessao = f"{versao}-{nome}"
                    _, fechar = self.viva(isolar, args, sessao)
                    r = self.segunda(isolar, args, sessao)
                    if versao == "base":
                        fechar()
                        self.assertEqual(r["rc"], 0, r["erro"])
                        continue
                    self.assertEqual(r["rc"], 1, r)
                    self.assertIn(f"os dados do provedor {nome} da sessão {sessao} estão em uso por outra abertura",
                                  r["erro"])
                    self.assertIn("feche a outra abertura", r["erro"])
                    self.assertGreaterEqual(r["segundos"], 4.5)
                    self.assertEqual(r["saida"], "")
                    fechar()
                    # Sem a primeira, a mesma sessão abre de novo.
                    r = self.segunda(isolar, args, sessao)
                    self.assertEqual(r["rc"], 0, r["erro"])

    def test_troca_por_link_com_a_sessao_viva_nao_desvia_a_preparacao(self):
        # A troca entra exatamente entre a conferência de link e a gravação
        # da segunda abertura (CORRIDA). No agy a sessão viva troca o
        # settings.json e a pasta cache, que enxerga montados. No Claude cada
        # subpasta é uma montagem e a sessão não alcança a pasta de cima: a
        # troca de todos/ é feita daqui, para mostrar que a montagem da
        # preparação seguiria o link.
        self.contas()
        (self.estado / "contas/conta1/cache").mkdir()
        (self.estado / "contas/conta1/cache/onboarding.json").write_text('{"concluido": true}')
        base = self.base(BASE_TRAVA)
        for isolar, versao in ((base, "base"), (REPO / "bin/jangada-isolar", "nova")):
            with self.subTest(provedor="agy", versao=versao):
                vitima = self.tmp / f"vitima-{versao}.json"
                vitima.write_text("intocado")
                vitima_pasta = self.tmp / f"vitima-cache-{versao}"
                vitima_pasta.mkdir()
                sessao = f"troca-{versao}-agy"
                args = ("--conta", "conta1", "--", "agy")
                controle, fechar = self.viva(isolar, args, sessao)
                cli = ".gemini/antigravity-cli"
                r = self.segunda(isolar, args, sessao, plano=(
                    {"comando": "cp", "sufixo": "/settings.json", "controle": str(controle),
                     "alvo": f"{cli}/settings.json", "destino": str(vitima)},
                    {"comando": "cp", "sufixo": "/cache/onboarding.json", "controle": str(controle),
                     "alvo": f"{cli}/cache", "destino": str(vitima_pasta)}))
                fechar()
                if versao == "base":
                    self.assertEqual(r["acionados"], ["/settings.json", "/cache/onboarding.json"], r)
                    self.assertNotEqual(vitima.read_text(), "intocado")
                    self.assertEqual(os.listdir(vitima_pasta), ["onboarding.json"])
                    continue
                self.assertEqual(r["rc"], 1, r)
                self.assertEqual(r["acionados"], [])
                self.assertEqual(vitima.read_text(), "intocado")
                self.assertEqual(os.listdir(vitima_pasta), [])
            with self.subTest(provedor="claude", versao=versao):
                vitima_pasta = self.tmp / f"vitima-todos-{versao}"
                vitima_pasta.mkdir()
                (vitima_pasta / "segredo").write_text("fora")
                sessao = f"troca-{versao}-claude"
                _, fechar = self.viva(isolar, ("--", "claude"), sessao)
                r = self.segunda(isolar, ("--", "claude"), sessao,
                                 plano=({"comando": "mkdir", "sufixo": f"/provedores/claude/{sessao}/todos",
                                         "destino": str(vitima_pasta)},),
                                 arquivos={"todos": str(self.casa / ".claude/todos/segredo")})
                fechar()
                self.assertEqual(sorted(os.listdir(vitima_pasta)), ["segredo"])
                self.assertEqual((vitima_pasta / "segredo").read_text(), "fora")
                if versao == "base":
                    self.assertEqual(r["rc"], 0, r["erro"])
                    self.assertEqual(json.loads(r["saida"])["arquivos"]["todos"], "fora")
                    continue
                self.assertEqual(r["rc"], 1, r)
                self.assertEqual(r["acionados"], [])
                todos = self.estado / f"provedores/claude/{sessao}/todos"
                self.assertTrue(todos.is_dir() and not todos.is_symlink())

    def test_abertura_sem_provedor_com_a_sessao_viva_passa(self):
        # A revisar do shell roda jangada-isolar -- jangada-validar com o
        # JANGADA_SESSAO da sessão viva: sem provedor concedido, não há
        # pasta de dados a preparar nem trava a esperar.
        _, fechar = self.viva(REPO / "bin/jangada-isolar", ("--", "claude"), "viva")
        r = self.segunda(REPO / "bin/jangada-isolar", ("--", "sonda"), "viva")
        fechar()
        self.assertEqual(r["rc"], 0, r["erro"])
        self.assertLess(r["segundos"], 4.5)
        self.assertEqual(json.loads(r["saida"])["concedidos"], "")

    def test_pasta_montada_por_processo_sem_trava_e_recusada(self):
        # Um bwrap direto, sem jangada-isolar e logo sem trava, faz o papel do
        # isolamento que sobra quando o isolador morre por SIGKILL, ou de uma
        # sessão aberta por versão sem trava. Não depende do tempo do SIGKILL.
        self.contas()
        base = self.base(BASE_TRAVA)
        casos = (("claude", ("--", "claude"), "claude", "todos", "plans"),
                 ("agy", ("--conta", "conta1", "--", "agy"), "agy-conta1", None, "settings.json"))
        for nome, args, provedor, montada, marca in casos:
            for isolar, versao in ((base, "base"), (REPO / "bin/jangada-isolar", "nova")):
                with self.subTest(provedor=nome, versao=versao):
                    sessao = f"montada-{versao}-{nome}"
                    env = {**self.env, "JANGADA_SESSAO": sessao, "JANGADA_SONDA_ARQUIVOS": "{}"}

                    def abrir():
                        return subprocess.run([str(isolar), *args], cwd=self.raiz, env=env,
                                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
                    r = abrir()
                    self.assertEqual(r.returncode, 0, r.stderr)
                    dados = self.estado / "provedores" / provedor / sessao
                    alvo = dados / montada if montada else dados
                    sinal = self.tmp / f"sinal-{sessao}"
                    sinal.mkdir()
                    preso = subprocess.Popen(
                        ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--unshare-pid",
                         "--die-with-parent", "--bind", str(alvo), str(alvo), "--bind", str(sinal), str(sinal),
                         "sh", "-c", f"touch {sinal}/pronto; exec sleep 60"], stdin=subprocess.DEVNULL)
                    self.addCleanup(preso.wait)
                    self.addCleanup(preso.kill)
                    prazo = time.monotonic() + 30
                    while not (sinal / "pronto").exists():
                        self.assertIsNone(preso.poll(), "o bwrap preso saiu")
                        self.assertLess(time.monotonic(), prazo, "o bwrap preso não montou")
                        time.sleep(0.05)
                    if (dados / marca).is_dir():
                        (dados / marca).rmdir()
                    else:
                        (dados / marca).unlink()
                    r = abrir()
                    if versao == "base":
                        # Sem a conferência, a base prepara a pasta montada.
                        self.assertEqual(r.returncode, 0, r.stderr)
                        self.assertTrue((dados / marca).exists())
                        continue
                    self.assertEqual(r.returncode, 1, r.stderr)
                    self.assertIn(f"os dados do provedor {provedor} da sessão {sessao} ainda estão montados "
                                  "por outro processo", r.stderr)
                    self.assertEqual(r.stdout, "")
                    self.assertFalse((dados / marca).exists(), "a abertura recusada preparou a pasta")
                    preso.kill()
                    preso.wait()
                    r = abrir()
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertTrue((dados / marca).exists())

    def test_trava_que_e_link_e_recusada(self):
        travas = self.estado / "provedores/.travas"
        vitima = self.tmp / "vitima"
        vitima_pasta = self.tmp / "vitima-pasta"
        vitima_pasta.mkdir()
        casos = (("arquivo", travas / "claude/s1", vitima),
                 ("arquivo sem destino", travas / "claude/s2", self.tmp / "nada"),
                 ("pasta do provedor", travas / "claude", vitima_pasta),
                 ("pasta das travas", travas, vitima_pasta))
        for nome, link, destino in casos:
            with self.subTest(caso=nome):
                shutil.rmtree(travas, ignore_errors=True)
                travas.unlink(missing_ok=True)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(destino)
                vitima.write_text("intocado")
                sessao = link.name if link.parent.name == "claude" else "s3"
                p, _ = self.iniciar("--", "claude", env={"JANGADA_SESSAO": sessao})
                _, erro = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 1, erro)
                self.assertIn("trava", erro)
                self.assertEqual(vitima.read_text(), "intocado")
                self.assertFalse((self.tmp / "nada").exists())
                self.assertEqual(os.listdir(vitima_pasta), [])
                self.assertFalse((self.estado / f"provedores/claude/{sessao}").exists())

    def test_trava_de_uso_unico_nao_sobra(self):
        self.contas()
        travas = self.estado / "provedores/.travas"
        (travas / "claude").mkdir(parents=True)
        # Sobra de abertura morta por SIGKILL, sem pasta de dados: sai. A de
        # PID vivo fica.
        (travas / "claude/efemera-999999999").write_text("")
        (travas / "claude" / f"efemera-{os.getpid()}").write_text("")
        self.rodar("--", "claude")
        self.rodar("--conta", "conta1", "--", "agy", env={"JANGADA_ISOLAR_DADOS": f"delegacao-{os.getpid()}-x"})
        self.rodar("--", "claude", env={"JANGADA_SESSAO": "persistente"})
        self.assertEqual(sorted(str(t.relative_to(travas)) for t in travas.glob("*/*")),
                         ["claude/efemera-" + str(os.getpid()), "claude/persistente"])

    def test_sem_concorrencia_igual_a_base(self):
        # Sem outra abertura viva, saída, mensagens e pasta da sessão ficam
        # iguais às da base anterior à trava; só a pasta .travas é nova.
        self.contas()
        (self.estado / "contas/conta1/cache").mkdir()
        (self.estado / "contas/conta1/cache/onboarding.json").write_text('{"concluido": true}')
        base = self.base(BASE_TRAVA)
        catalogo = self.estado / "contas/agy.json"
        provedores = self.estado / "provedores"

        def arvore(pasta):
            return sorted((str(p.relative_to(pasta)), p.is_dir(), p.is_symlink(), p.stat().st_mode & 0o777,
                           p.read_text() if p.is_file() else None) for p in pasta.rglob("*"))

        for nome, args, provedor in (("claude", ("--", "claude"), "claude"),
                                     ("claude efêmera", ("--", "claude"), None),
                                     ("agy com catálogo", ("--conta", "conta1", "--", "agy"), "agy-conta1"),
                                     ("agy sem catálogo", ("--", "agy"), "agy-principal")):
            with self.subTest(caso=nome):
                if nome == "agy sem catálogo":
                    catalogo.unlink()
                resultados = []
                for isolar, versao in ((base, "base"), (REPO / "bin/jangada-isolar", "nova")):
                    sessao = f"{versao}-{len(resultados)}-{nome.replace(' ', '-')}"
                    env = {**self.env, "JANGADA_SONDA_ARQUIVOS": json.dumps({k: str(v) for k, v in self.arquivos.items()})}
                    if provedor:
                        env["JANGADA_SESSAO"] = sessao
                    p = subprocess.run([str(isolar), *args], cwd=self.raiz, env=env, stdin=subprocess.DEVNULL,
                                       capture_output=True, text=True, timeout=60)
                    resultados.append({"rc": p.returncode, "saida": p.stdout, "erro": p.stderr.replace(sessao, "S"),
                                       "arvore": arvore(provedores / provedor / sessao) if provedor else None,
                                       "efemeras": sorted(map(str, provedores.glob("*/efemera-*")))})
                self.assertEqual(resultados[1], resultados[0])
                self.assertEqual(resultados[0]["rc"], 0, resultados[0]["erro"])

    def test_aninhado_recusa_provedor_que_a_sessao_nao_recebeu(self):
        aninhado = {"JANGADA_SONDA_ANINHADO": json.dumps(["codex"])}
        r = self.rodar("--delegar", "agy", "--", "claude", env=aninhado)
        self.assertEqual(r["aninhado"]["rc"], 1, r)
        self.assertIn("não recebeu o login do provedor codex", r["aninhado"]["erro"])
        r = self.rodar("--delegar", "agy", "--", "claude", env={"JANGADA_SONDA_ANINHADO": json.dumps(["agy"])})
        self.assertEqual(r["aninhado"]["rc"], 0, r)

    def test_aninhado_em_sessao_antiga_roda_com_aviso_sem_ganhar_login(self):
        # Sessão aberta antes da concessão por provedor não tem a variável. O
        # comando roda, mas só enxerga o que a montagem de fora deu.
        r = self.rodar("--delegar", "agy", "--", "claude",
                       env={"JANGADA_SONDA_ANINHADO": json.dumps(["codex"]), "JANGADA_SONDA_SESSAO_ANTIGA": "1"})
        self.assertEqual(r["aninhado"]["rc"], 0, r)
        self.assertIn("sessão aberta antes da concessão por provedor", r["aninhado"]["erro"])
        dentro = json.loads(r["aninhado"]["saida"])
        self.assertIsNone(dentro["arquivos"]["codex"])
        self.assertEqual([v for v in dentro["ambiente"] if v in DO_PROVEDOR["codex"]], [])

    def test_valor_desconhecido_nos_modos_e_recusado(self):
        for nome, valor in (("JANGADA_ISOLAR_CASA", "minimo"), ("JANGADA_ISOLAR_AMBIENTE", "nenhum"),
                            ("JANGADA_ISOLAR_KEYRING", "tudo")):
            with self.subTest(nome=nome):
                p, _ = self.iniciar("--", "claude", env={nome: valor})
                _, erro = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 1, erro)
                self.assertIn(nome, erro)


if __name__ == "__main__":
    unittest.main()
