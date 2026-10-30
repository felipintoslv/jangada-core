#!/usr/bin/env python3
"""Verifica o contrato das referências documentais."""

import importlib.util
import json
import os
import shutil
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("validar", RAIZ / "delegacao/validar.py")
VALIDAR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDAR)


class Referencias(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.fonte = pathlib.Path(self.pasta.name) / "fonte.txt"
        self.fonte.write_text("primeira\nsegunda\n")

    def test_caminho_absoluto_e_intervalo(self):
        VALIDAR.verificar(f"Resultado em {self.fonte}:1-2", [str(self.fonte)])

    def test_posicoes_inexistentes(self):
        for referencia in ("fonte.txt:0", "fonte.txt:3", "fonte.txt:1-3", "fonte.txt:2-1"):
            with self.subTest(referencia=referencia), self.assertRaises(ValueError):
                VALIDAR.verificar(referencia, [str(self.fonte)])

    def test_exige_cobertura_das_fontes(self):
        outra = pathlib.Path(self.pasta.name) / "outra.txt"
        outra.write_text("conteúdo\n")
        with self.assertRaises(ValueError):
            VALIDAR.verificar("fonte.txt:1", [str(self.fonte), str(outra)])

    def test_nome_ambiguo_nao_identifica_duas_fontes(self):
        outra = pathlib.Path(self.pasta.name) / "outra" / "fonte.txt"
        outra.parent.mkdir()
        outra.write_text("conteúdo\n")
        with self.assertRaises(ValueError):
            VALIDAR.verificar("fonte.txt:1", [str(self.fonte), str(outra)])
        VALIDAR.verificar(f"{self.fonte}:1; {outra}:1", [str(self.fonte), str(outra)])

    def test_pdf_confere_paginas(self):
        fonte = pathlib.Path(self.pasta.name) / "fonte.pdf"
        fonte.write_text("arquivo simulado")
        with patch.object(VALIDAR.subprocess, "run") as executar:
            executar.side_effect = [
                subprocess.CompletedProcess([], 0, "application/pdf\n"),
                subprocess.CompletedProcess([], 0, "primeira\fsegunda\f"),
            ]
            VALIDAR.verificar("fonte.pdf, p. 2", [str(fonte)])
            executar.side_effect = [
                subprocess.CompletedProcess([], 0, "application/pdf\n"),
                subprocess.CompletedProcess([], 0, "primeira\fsegunda\f"),
            ]
            with self.assertRaises(ValueError):
                VALIDAR.verificar("fonte.pdf, p. 3", [str(fonte)])

    def test_requisito_exige_explicacao_com_referencia(self):
        VALIDAR.verificar(
            "## Destino\nUse o modelo local para ler os documentos. fonte.txt:1",
            [str(self.fonte)], ["Destino"],
        )
        for texto in (
            "Destino: fonte.txt:1",
            "## Destino\nfonte.txt:1",
            "## Destino\nDestino: fonte.txt:1",
            "fonte.txt:1\n## Destino\nUse o modelo local para ler os documentos.",
            "## Destino\nUse o modelo local para ler os documentos. fonte.txt:1\n"
            "## Destino\nUse o modelo local para ler os documentos. fonte.txt:1",
        ):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                VALIDAR.verificar(texto, [str(self.fonte)], ["Destino"])

    def test_requisito_omitido_reprova(self):
        with self.assertRaises(ValueError):
            VALIDAR.verificar(
                "## Destino\nUse o modelo local para ler os documentos. fonte.txt:1",
                [str(self.fonte)], ["Destino", "Permissão"],
            )

    def test_requisito_com_varias_fontes(self):
        outra = pathlib.Path(self.pasta.name) / "outra.txt"
        outra.write_text("conteúdo\n")
        texto = "## Destino\nUse o modelo local para ler as duas fontes. fonte.txt:1; outra.txt:1"
        VALIDAR.verificar(texto, [str(self.fonte), str(outra)], ["Destino"])
        with self.assertRaises(ValueError):
            VALIDAR.verificar(texto.replace("outra.txt:1", ""), [str(self.fonte), str(outra)], ["Destino"])


class PadraoAgy(unittest.TestCase):
    """Roteamento com transporte falso, sem rede nem execução do isolamento."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.bin = self.pasta / 'bin'
        self.bin.mkdir()
        self.home = self.pasta / 'home'
        self.projeto = self.pasta / 'projeto'
        self.projeto.mkdir()
        self.fonte = self.projeto / 'fonte.txt'
        self.fonte.write_text('Conteúdo autorizado.\n')
        shutil.copyfile(RAIZ / 'bin/jangada-config', self.bin / 'jangada-config')
        shutil.copyfile(RAIZ / 'bin/jangada-delegar', self.bin / 'jangada-delegar')
        for pasta in ('agentes', 'nucleo', 'orquestracao', 'delegacao', 'provedores', 'validacao'):
            (self.pasta / pasta).symlink_to(RAIZ / pasta)
        # Este transporte só executa o provedor falso da própria fixture.
        # O delegar concede ao isolamento só o login do agy.
        self.script('jangada-isolar', '[[ "$1 $2" == "--provedor agy" ]] || exit 97\n'
                    'shift 2\n[[ "$1" == -- ]] && shift\nexec "$@"\n')
        self.script('agy', """if [[ "$1" == agents ]]; then echo leitor; echo redator; exit 0; fi
if [[ "${2:-}" == /usage ]]; then
  printf '{"command":{"data":{"groups":[{"buckets":[{"id":"gemini-5h","remaining_fraction":%s}]}]}}}\n' "${COTA_FALSA:-0.9}"
  exit 0
fi
printf '%s\n' "$@" >>"$HOME/.gemini/antigravity-cli/agy.log"
jq -n --arg r 'Informação conferida em fonte.txt:1' '{status:"SUCCESS",response:$r}'
""")
        for nome in ('ollama', 'curl'):
            self.script(nome, 'echo local >>"$LOG_LOCAL"\nexit 99\n')
        conf = self.home / '.gemini/antigravity-cli/settings.json'
        conf.parent.mkdir(parents=True)
        conf.write_text(json.dumps({'trustedWorkspaces': [str(self.projeto)]}))
        hooks = self.home / '.gemini/config/hooks.json'
        hooks.parent.mkdir(parents=True)
        hooks.write_text(json.dumps({'hooks': {'PreToolUse': [{
            'matcher': 'run_command', 'hooks': [{'command': str(self.bin / 'jangada-hook-leitor') + ' --agy'}]
        }]}}))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('JANGADA_')}
        self.env.update(HOME=str(self.home), PATH=str(self.bin) + ':/usr/bin:/bin',
                        XDG_CONFIG_HOME=str(self.pasta / 'config'),
                        XDG_STATE_HOME=str(self.pasta / 'estado'),
                        XDG_CACHE_HOME=str(self.pasta / 'cache'), JANGADA_CORE_PATH=str(self.pasta),
                        LOG_FALSO=str(self.pasta / 'agy.log'), LOG_LOCAL=str(self.pasta / 'local.log'))

    def script(self, nome, corpo):
        arquivo = self.bin / nome
        arquivo.write_text('#!/usr/bin/bash\n' + corpo)
        arquivo.chmod(0o755)

    def delegar(self, *opcoes, papel='leitor'):
        resultado = subprocess.run(['bash', str(self.bin / 'jangada-delegar'), papel,
                                    'Confira a fonte autorizada', *opcoes, '--json',
                                    '--arquivos', str(self.fonte)], cwd=self.projeto,
                                   env=self.env, text=True, capture_output=True, timeout=15)
        self.assertIn(resultado.returncode, (0, 4), resultado.stderr)
        self.assertFalse((self.pasta / 'local.log').exists(), 'houve chamada local automática')
        dados = json.loads(resultado.stdout)
        if dados.get('registro_ferramentas'):
            privado = pathlib.Path(dados['registro_ferramentas']) / 'agy.log'
            if privado.is_file():
                shutil.copyfile(privado, self.pasta / 'agy.log')
        return dados

    def test_autores_sem_perfil_incluem_leitor_e_redator(self):
        for autor in ('claude', 'codex'):
            self.env['JANGADA_AGENTE'] = autor
            for papel in ('leitor', 'redator'):
                with self.subTest(autor=autor, papel=papel):
                    r = self.delegar('--permitir-remoto', papel=papel)
                    self.assertEqual((r['destino'], r['codigo_saida']), ('agy', 0))
        self.assertIn(str(self.fonte), (self.pasta / 'agy.log').read_text())

    def test_capacidades_padrao_sem_alternativa_local(self):
        for capacidade in ('leitura_documental', 'resumo_curto', 'analise_documental'):
            with self.subTest(capacidade=capacidade):
                r = self.delegar('--capacidade', capacidade, '--permitir-remoto')
                self.assertEqual((r['destino'], r['verificacao']), ('agy', 'referencias_validas'))
                self.assertEqual([t['destino'] for t in r['tentativas']], ['agy'])

    def test_autorizacao_exigida_tambem_sem_capacidade(self):
        for opcoes in ((), ('--capacidade', 'resumo_curto')):
            r = self.delegar(*opcoes)
            self.assertEqual(r['codigo_saida'], 4)
            self.assertEqual(r['tentativas'][0]['motivo_codigo'], 'destino_proibido')
            self.assertFalse((self.pasta / 'agy.log').exists())

    def test_cota_baixa_bloqueia_sem_ollama(self):
        self.env['COTA_FALSA'] = '0.1'
        r = self.delegar('--capacidade', 'resumo_curto', '--permitir-remoto')
        self.assertEqual(r['motivo_codigo'], 'sem_executor')
        self.assertEqual(len(r['tentativas']), 1)
        self.assertEqual(r['tentativas'][0]['motivo_codigo'], 'cota_insuficiente')
        self.assertFalse((self.pasta / 'agy.log').exists())

    def test_falta_de_confianca_bloqueia(self):
        (self.home / '.gemini/antigravity-cli/settings.json').write_text('{"trustedWorkspaces":[]}')
        r = self.delegar('--capacidade', 'resumo_curto', '--permitir-remoto')
        self.assertEqual(r['tentativas'][0]['motivo_codigo'], 'destino_proibido')
        self.assertFalse((self.pasta / 'agy.log').exists())

    def test_agy_ausente_preserva_destino_e_registra_recusa(self):
        (self.bin / 'agy').unlink()
        r = self.delegar('--permitir-remoto')
        self.assertEqual((r['destino'], r['motivo_codigo']), ('agy', 'indisponivel'))

    def test_catalogo_falho_nao_e_confundido_com_papel_ausente(self):
        for saida in ('', 'echo leitor;'):
            with self.subTest(saida=saida):
                self.script('agy', f'{saida} echo "soquete local proibido" >&2; exit 1\n')
                r = self.delegar('--permitir-remoto')
                self.assertEqual(r['motivo_codigo'], 'indisponivel')
                self.assertIn('código 1', r['motivo'])
                self.assertIn('soquete local proibido', r['motivo'])
                self.assertEqual(r['chamadas_executor'], 0)

    def test_catalogo_completo_evita_saida_antecipada_do_grep(self):
        arquivo = self.bin / 'agy'
        corpo = arquivo.read_text().replace(
            'then echo leitor; echo redator; exit 0; fi',
            'then echo leitor; sleep 0.05; printf "outro\\n%.0s" {1..100000}; exit 0; fi')
        arquivo.write_text(corpo)
        r = self.delegar('--permitir-remoto')
        self.assertEqual((r['destino'], r['codigo_saida']), ('agy', 0))

    def test_catalogo_valido_sem_papel_recusa_antes_da_geracao(self):
        self.script('agy', 'echo explorador\n')
        r = self.delegar('--permitir-remoto')
        self.assertEqual(r['motivo_codigo'], 'capacidade_incompativel')
        self.assertEqual(r['chamadas_executor'], 0)

    def test_codex_sem_escolha_local_nao_encaminha_ao_ollama(self):
        self.env['JANGADA_AGENTE'] = 'codex'
        for preferencia in ('claude', 'nativo', 'desconhecido'):
            self.env['JANGADA_DELEGAR'] = preferencia
            with self.subTest(preferencia=preferencia):
                r = self.delegar()
                self.assertEqual(r['codigo_saida'], 4)
                self.assertEqual(r['motivo_codigo'], 'destino_proibido')
                self.assertFalse((self.pasta / 'agy.log').exists())

    def test_codex_preferencia_desconhecida_exige_autorizacao_para_agy(self):
        self.env.update(JANGADA_AGENTE='codex', JANGADA_DELEGAR='desconhecido')
        r = self.delegar('--permitir-remoto')
        self.assertEqual((r['destino'], r['codigo_saida']), ('agy', 0))

    def test_delegacao_codex_preserva_somente_local_explicito(self):
        for preferencia in ('', 'agy', 'claude', 'nativo', 'desconhecido', 'local'):
            with self.subTest(preferencia=preferencia):
                r = subprocess.run(
                    ['bash', '-c', 'source "$1"; jangada_delegacao codex "$2"', '_',
                     str(self.bin / 'jangada-config'), preferencia], env=self.env,
                    text=True, capture_output=True, check=True)
                self.assertEqual(r.stdout.strip(), 'local' if preferencia == 'local' else 'agy')

    def test_sessao_agy_restaurada_recusa_destino_nativo(self):
        self.env['JANGADA_AGENTE'] = 'agy'
        for opcoes in ((), ('--capacidade', 'resumo_curto', '--permitir-remoto')):
            with self.subTest(opcoes=opcoes):
                r = self.delegar(*opcoes)
                self.assertEqual(r['motivo_codigo'], 'destino_proibido')
                self.assertIn('invoke_subagent', r['motivo'])
                self.assertEqual(r['chamadas_executor'], 0)
                self.assertFalse((self.pasta / 'agy.log').exists())

    def test_configuracao_local_explicita_nao_autoriza_agy(self):
        config = self.pasta / 'config/jangada/jangada.conf'
        config.parent.mkdir(parents=True)
        config.write_text('JANGADA_DELEGAR=local\n')
        r = self.delegar('--destino', 'agy', '--permitir-remoto')
        self.assertEqual(r['motivo_codigo'], 'destino_proibido')
        self.assertFalse((self.pasta / 'agy.log').exists())

    def test_configuracao_antiga_vazia_herda_agy(self):
        config = self.pasta / 'config/jangada/jangada.conf'
        config.parent.mkdir(parents=True)
        config.write_text('JANGADA_DELEGAR=\n')
        r = self.delegar('--permitir-remoto')
        self.assertEqual((r['destino'], r['codigo_saida']), ('agy', 0))


if __name__ == "__main__":
    unittest.main()
