#!/usr/bin/env python3
"""Avaliação com respostas simuladas: qualidade, variação e ausência de envio remoto."""

import fcntl
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "delegacao"))
import avaliar_ollama as avaliacao


class Avaliacao(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.pasta = pathlib.Path(self.temporario.name)
        self.fonte = self.pasta / "fonte.txt"
        self.estado = self.pasta / "estado-original"
        (self.estado / "marcas").mkdir(parents=True)
        (self.estado / "marcas/vram-livre").write_text("8000 1\n")
        self.esperado = {"prazo": [7, 2], "reenvio": [False, 4], "responsavel": [None, None]}
        self.resposta = {"prazo": {"valor": 7, "referencia": "fonte.txt:2"},
                         "reenvio": {"valor": False, "referencia": "fonte.txt:4"},
                         "responsavel": {"valor": None, "referencia": None}}

    def conferir(self, resposta):
        return avaliacao.conferir(json.dumps(resposta), self.esperado, self.fonte)

    def test_referencia_correta_nao_compensa_fato_errado(self):
        self.resposta["prazo"]["valor"] = 15
        self.assertIn("valor divergente: prazo", self.conferir(self.resposta)["problemas"])

    def test_omissao_e_informacao_inventada(self):
        del self.resposta["reenvio"]
        self.resposta["responsavel"]["valor"] = "Helena"
        problemas = self.conferir(self.resposta)["problemas"]
        self.assertIn("campo omitido: reenvio", problemas)
        self.assertIn("valor divergente: responsavel", problemas)

    def test_referencia_precisa_sustentar_o_fato(self):
        self.resposta["prazo"]["referencia"] = "fonte.txt:4"
        self.assertIn("referência divergente: prazo", self.conferir(self.resposta)["problemas"])

    def test_booleano_nao_e_numero(self):
        self.resposta["reenvio"]["valor"] = 0
        self.assertIn("valor divergente: reenvio", self.conferir(self.resposta)["problemas"])

    def test_chaves_repetidas_e_respostas_invalidas(self):
        for texto in ('{"prazo": 15, "prazo": 7}', "[]", "resposta vazia"):
            with self.subTest(texto=texto):
                resultado = avaliacao.conferir(texto, self.esperado, self.fonte)
                self.assertIsNone(resultado["respostas"])
                self.assertTrue(resultado["problemas"])

    def test_formato_e_caminho_equivalentes_nao_contam_como_variacao(self):
        esperado = self.conferir(self.resposta)
        self.resposta["prazo"]["referencia"] = f"{self.fonte}:2"
        texto = "```json\n" + json.dumps(self.resposta, indent=2) + "\n```"
        self.assertEqual(avaliacao.conferir(texto, self.esperado, self.fonte), esperado)

    def simular(self, comando, **opcoes):
        self.assertEqual(comando[comando.index("--destino") + 1], "local")
        self.assertNotIn("--permitir-remoto", comando)
        self.assertNotIn("--permitir-codex", comando)
        self.assertEqual(opcoes["env"]["JANGADA_DELEGAR"], "local")
        self.assertNotIn("JANGADA_DELEGAR_ROTEAMENTO_ID", opcoes["env"])
        self.assertTrue(pathlib.Path(opcoes["env"]["XDG_CONFIG_HOME"]).is_relative_to(self.pasta))
        marca = pathlib.Path(opcoes["env"]["XDG_STATE_HOME"]) / "jangada/marcas/vram-livre"
        self.assertEqual(marca.resolve(), self.estado / "marcas/vram-livre")
        fonte = pathlib.Path(comando[-1])
        self.assertTrue(fonte.is_file())
        gabarito = next(c[2] for c in avaliacao.casos() if c[0] == fonte.stem)
        resposta = {chave: {"valor": valor, "referencia": f"{fonte.name}:{linha}" if linha else None}
                    for chave, (valor, linha) in gabarito.items()}
        chamadas = [{"fase": "documento"}]
        if fonte.stem == "dividido":
            self.assertEqual(opcoes["env"]["JANGADA_LOCAL_CTX"], "3000")
            chamadas = [{"fase": "fatia"}, {"fase": "fatia"}]
        registro = {"modelo": "modelo-simulado", "relatorio": json.dumps(resposta), "chamadas_local": chamadas,
                    "consolidacao": "deterministica" if fonte.stem == "dividido" else ""}
        return subprocess.CompletedProcess(comando, 0, json.dumps(registro), "")

    def rodar(self, simulado):
        with patch.object(avaliacao.subprocess, "run", side_effect=simulado), \
                patch.object(avaliacao, "print"):
            return avaliacao.avaliar(self.pasta / "execucao", 3,
                                    {"JANGADA_CORE_PATH": str(RAIZ), "JANGADA_ESTADO": str(self.estado),
                                     "JANGADA_LOCAL_MODELO": "modelo-simulado",
                                     "JANGADA_DELEGAR_ROTEAMENTO_ID": "herdado"})

    def test_repete_casos_e_persiste_medicoes(self):
        resultado = self.rodar(self.simular)
        self.assertEqual(len(resultado["resultados"]), 9)
        self.assertTrue(resultado["concluida"])
        for caso in resultado["resumo"]:
            self.assertEqual(caso["conformes"], 3)
            self.assertEqual(caso["variantes_interpretaveis"], 1)
        salvo = json.loads((self.pasta / "execucao/resultado.json").read_text())
        self.assertEqual(salvo, resultado)
        self.assertEqual(len(list((self.pasta / "execucao").glob("*-r*.log"))), 9)

    def test_estabilidade_nao_aprova_resposta_errada(self):
        def errado(comando, **opcoes):
            chamada = self.simular(comando, **opcoes)
            registro = json.loads(chamada.stdout)
            resposta = json.loads(registro["relatorio"])
            resposta["prazo_dias"]["valor"] = 99
            registro["relatorio"] = json.dumps(resposta)
            chamada.stdout = json.dumps(registro)
            return chamada
        resultado = self.rodar(errado)
        for caso in resultado["resumo"]:
            self.assertEqual(caso["conformes"], 0)
            self.assertEqual(caso["variantes_interpretaveis"], 1)

    def test_recusas_nao_sao_conformidade_nem_estabilidade(self):
        resultado = self.rodar(lambda comando, **_: subprocess.CompletedProcess(
            comando, 4, json.dumps({"motivo_codigo": "contexto_insuficiente"}), "recusado"))
        for caso in resultado["resumo"]:
            self.assertEqual(caso["conformes"], 0)
            self.assertEqual(caso["recusadas"], 3)
            self.assertEqual(caso["variantes_interpretaveis"], 0)

    def test_consumo_de_recusa_e_preservado(self):
        def recusado(comando, **opcoes):
            log = pathlib.Path(opcoes["env"]["XDG_STATE_HOME"]) / "jangada/delegacoes.jsonl"
            log.write_text(json.dumps({"roteamento_id": "r1", "destino": "local", "modelo": "modelo-simulado",
                                       "contexto": 3000, "chamadas_local": [{"tokens_saida": 1024}]}) + "\n")
            return subprocess.CompletedProcess(comando, 4, json.dumps({"roteamento_id": "r1"}), "recusado")
        resultado = self.rodar(recusado)
        for medida in resultado["resultados"]:
            self.assertEqual(medida["estado"], "recusado")
            self.assertEqual(medida["modelo"], "modelo-simulado")
            self.assertEqual(medida["chamadas_local"][0]["tokens_saida"], 1024)

    def test_vaga_global_ocupada_nao_chama_modelo(self):
        with (self.estado / "local.lock").open("w") as trava:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
            resultado = self.rodar(lambda *_args, **_kwargs: self.fail("não deveria chamar o modelo"))
        self.assertTrue(all(r["estado"] == "recusado" and r["motivo_codigo"] == "ocupado"
                            for r in resultado["resultados"]))

    def test_respostas_diferentes_contam_como_variacao(self):
        chamadas = [0]
        def alternar(comando, **opcoes):
            chamada = self.simular(comando, **opcoes)
            registro = json.loads(chamada.stdout)
            resposta = json.loads(registro["relatorio"])
            if chamadas[0] % 3 == 1:
                resposta["prazo_dias"]["valor"] = 99
            chamadas[0] += 1
            registro["relatorio"] = json.dumps(resposta)
            chamada.stdout = json.dumps(registro)
            return chamada
        resultado = self.rodar(alternar)
        for caso in resultado["resumo"]:
            self.assertEqual(caso["conformes"], 2)
            self.assertEqual(caso["variantes_interpretaveis"], 2)

    def test_interrupcao_preserva_resultado_parcial(self):
        chamadas = [0]
        def interromper(comando, **opcoes):
            if chamadas[0]:
                raise KeyboardInterrupt
            chamadas[0] += 1
            return self.simular(comando, **opcoes)
        with self.assertRaises(KeyboardInterrupt):
            self.rodar(interromper)
        salvo = json.loads((self.pasta / "execucao/resultado.json").read_text())
        self.assertFalse(salvo["concluida"])
        self.assertEqual(len(salvo["resultados"]), 1)

    def test_dividido_precisa_exercitar_a_consolidacao(self):
        def sem_dividir(comando, **opcoes):
            chamada = self.simular(comando, **opcoes)
            registro = json.loads(chamada.stdout)
            registro["chamadas_local"] = [{"fase": "documento"}]
            chamada.stdout = json.dumps(registro)
            return chamada
        resultado = self.rodar(sem_dividir)
        dividido = next(c for c in resultado["resumo"] if c["caso"] == "dividido")
        self.assertEqual(dividido["conformes"], 0)

    def test_comando_recusa_repeticoes_invalidas_sem_criar_estado(self):
        for numero in ("0", "11", "abc"):
            resultado = subprocess.run([str(RAIZ / "bin/jangada-avaliar-ollama"), "--repeticoes", numero],
                                      env={**os.environ, "JANGADA_CORE_PATH": str(RAIZ),
                                           "XDG_STATE_HOME": str(self.pasta / "estado"),
                                           "XDG_CONFIG_HOME": str(self.pasta / "config")},
                                      capture_output=True, text=True, check=False)
            self.assertEqual(resultado.returncode, 2)
            self.assertFalse((self.pasta / "estado").exists())


if __name__ == "__main__":
    unittest.main()
