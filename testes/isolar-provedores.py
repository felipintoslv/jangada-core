#!/usr/bin/env python3
"""Provedores concedidos pelo jangada-isolar, no bwrap de verdade.

Cada caso roda uma sonda com o nome de um provedor numa casa falsa, com
logins, contas do agy, documentos e variáveis fictícias, e confere o que ela
lê de dentro do isolamento. Onde o bwrap não cria namespace, os casos se
pulam; com JANGADA_TESTES_EXIGIR_ISOLAMENTO=1, pular vira falha.

Uso: python3 testes/isolar-provedores.py
"""
import json
import os
import shutil
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
aninhado = os.environ.get("JANGADA_SONDA_ANINHADO")
if aninhado:
    ambiente = {**os.environ, "JANGADA_SONDA_ANINHADO": ""}
    if os.environ.get("JANGADA_SONDA_SESSAO_ANTIGA"):
        ambiente.pop("JANGADA_ISOLAR_CONCEDIDOS", None)
    p = subprocess.run([os.environ["JANGADA_CORE_PATH"] + "/bin/jangada-isolar", "--", *json.loads(aninhado)],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, env=ambiente)
    saida["aninhado"] = {"rc": p.returncode, "erro": p.stderr, "saida": p.stdout}
print(json.dumps(saida))
'''


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
        ambiente = dict(self.env, JANGADA_SONDA_ARQUIVOS=json.dumps({k: str(v) for k, v in self.arquivos.items()}),
                        **(env or {}))
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
