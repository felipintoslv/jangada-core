#!/usr/bin/env python3
"""Confere o seletor em terminal sem executar modelos ou criar sessões reais."""

import os
import pathlib
import pty
import subprocess
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]


class Seletor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.bin = self.pasta / 'bin'
        self.bin.mkdir()
        for arquivo in pathlib.Path('/usr/bin').iterdir():
            if arquivo.name not in {'claude', 'agy', 'codex', 'ollama', 'fzf', 'column'}:
                (self.bin / arquivo.name).symlink_to(arquivo)
        self.script('fzf', 'printf "%s\\n" "$@" >"$TESTE_PASTA/argumentos"\n'
                    'cat >"$TESTE_PASTA/opcoes"\nexit 1\n')
        self.script('column', 'cat\n')
        for agente in ('claude', 'agy', 'codex', 'ollama'):
            self.script(agente, 'exit 0\n')
        config = self.pasta / 'config/jangada'
        config.mkdir(parents=True)
        self.config = config
        self.ambiente = {chave: valor for chave, valor in os.environ.items()
                         if not chave.startswith('JANGADA_')}
        self.ambiente.update(PATH=str(self.bin), HOME=str(self.pasta),
                             XDG_CONFIG_HOME=str(self.pasta / 'config'),
                             XDG_STATE_HOME=str(self.pasta / 'estado'),
                             JANGADA_CORE_PATH=str(RAIZ), TESTE_PASTA=str(self.pasta))

    def script(self, nome, corpo):
        arquivo = self.bin / nome
        if arquivo.is_symlink():
            arquivo.unlink()
        arquivo.write_text('#!/bin/bash\n' + corpo)
        arquivo.chmod(0o755)

    def menu(self, *args):
        mestre, escravo = pty.openpty()
        try:
            resultado = subprocess.run([str(RAIZ / 'bin/jangada-agente'), *args],
                                       stdin=escravo, capture_output=True, text=True,
                                       env=self.ambiente, timeout=15)
        finally:
            os.close(mestre)
            os.close(escravo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        return (self.pasta / 'opcoes').read_text()

    def test_revisor_global_e_autorrevisao(self):
        self.ambiente['JANGADA_VALIDAR_REVISOR'] = 'codex'
        perfis = self.config / 'agentes'
        perfis.mkdir()
        (perfis / 'codex-global.conf').write_text('COMANDO=codex\n')
        opcoes = self.menu()
        padrao = next(linha for linha in opcoes.splitlines() if linha.startswith('padrão'))
        self.assertIn('claude implementa; codex revisa', padrao)
        perfil = next(linha for linha in opcoes.splitlines() if linha.startswith('codex-global'))
        self.assertIn('codex implementa; codex revisa', perfil)
        self.assertIn('autorrevisão pelo mesmo provedor', perfil)
        self.assertNotIn('economiza', opcoes)
        self.assertIn('Fila e orçamento', (self.pasta / 'argumentos').read_text())

    def test_revisao_cruzada_por_padrao(self):
        perfis = self.config / 'agentes'
        perfis.mkdir()
        (perfis / 'claude-flash.conf').write_text(
            'COMANDO=claude\nJANGADA_VALIDAR_REVISOR=agy\n'
            'JANGADA_VALIDAR_MODELO=gemini-3.8-flash-high\nJANGADA_DELEGAR=agy\n')
        opcoes = self.menu().splitlines()
        padrao = next(linha for linha in opcoes if linha.startswith('padrão'))
        self.assertIn('claude implementa; codex revisa', padrao)
        self.assertIn('leitor e redator no Ollama, demais papéis no agy', padrao)
        perfil = next(linha for linha in opcoes if linha.startswith('claude-flash\t'))
        self.assertIn('claude implementa; agy revisa (gemini-3.8-flash-high)', perfil)
        self.assertIn('leitor e redator no Ollama, demais papéis no agy', perfil)
        self.assertEqual([linha.split('\t')[0] for linha in opcoes],
                         ['padrão', 'claude-codex', 'claude-flash', 'codex-claude'])
        perfil = next(linha for linha in opcoes if linha.startswith('claude-codex\t'))
        self.assertIn('claude implementa; codex revisa;', perfil)
        self.assertIn('leitor e redator no Ollama, demais papéis no agy', perfil)
        perfil = next(linha for linha in opcoes if linha.startswith('codex-claude\t'))
        self.assertIn('codex implementa; claude revisa;', perfil)
        self.assertIn('leitor e redator no Ollama, demais papéis no agy', perfil)
        self.assertNotIn('autorrevisão', '\n'.join(opcoes))
        (self.config / 'jangada.conf').write_text('JANGADA_AGENTE=codex\n')
        padrao = next(linha for linha in self.menu().splitlines()
                      if linha.startswith('padrão'))
        self.assertIn('codex implementa; claude revisa', padrao)
        self.assertIn('leitor e redator no Ollama, demais papéis no agy', padrao)

    def test_opcao_explicita_prevalece_sobre_perfis(self):
        opcoes = self.menu('--revisor', 'mesmo')
        for linha in opcoes.splitlines():
            self.assertIn('autorrevisão pelo mesmo provedor', linha)

    def test_delegacao_explicita_prevalece_na_descricao_dos_perfis(self):
        for linha in self.menu('--delegacao', 'local').splitlines():
            self.assertIn('leitor e redator no Ollama, demais papéis nesta sessão', linha)

    def test_perfil_personalizado_usa_valores_efetivos(self):
        perfis = self.config / 'agentes'
        perfis.mkdir()
        (perfis / 'codex-claude.conf').write_text(
            'COMANDO=codex\nDESCRICAO=descrição antiga\n'
            'JANGADA_VALIDAR_REVISOR=agy\nJANGADA_DELEGAR=local\n')
        linha = next(linha for linha in self.menu().splitlines()
                     if linha.startswith('codex-claude'))
        self.assertIn('agy revisa', linha)
        self.assertIn('demais papéis nesta sessão', linha)
        self.assertNotIn('descrição antiga', linha)

    def test_programas_ausentes_sao_indicados(self):
        (self.bin / 'codex').unlink()
        (self.bin / 'ollama').unlink()
        opcoes = self.menu()
        self.assertIn('INDISPONÍVEL: codex não instalado', opcoes)
        self.assertNotIn('Ollama não instalado', opcoes)
        self.assertIn('Ollama não instalado', self.menu('--delegacao', 'local'))

    def test_revisor_ausente_nao_troca_delegacao(self):
        (self.bin / 'agy').unlink()
        (self.bin / 'codex').unlink()
        padrao = next(linha for linha in self.menu().splitlines()
                      if linha.startswith('padrão'))
        self.assertIn('revisão indisponível: codex não instalado', padrao)
        self.assertIn('delegação indisponível: agy não instalado', padrao)
        self.assertNotIn('subagentes do Claude', padrao)

    def test_agente_ausente_recusa_antes_de_criar_estado(self):
        (self.bin / 'codex').unlink()
        resultado = subprocess.run([str(RAIZ / 'bin/jangada-agente'), '--perfil', 'codex-claude',
                                   '--projeto', str(self.pasta), '--nome', 'tarefa'],
                                  capture_output=True, text=True, env=self.ambiente, timeout=15)
        self.assertEqual(resultado.returncode, 1)
        self.assertIn('nenhuma sessão criada', resultado.stderr)
        self.assertFalse((self.pasta / 'estado').exists())

    def test_revisor_ausente_preserva_protocolo_e_isolamento(self):
        (self.bin / 'codex').unlink()
        self.script('tmux', '[[ " $* " == *" has-session "* ]] && exit 1\nexit 0\n')
        resultado = subprocess.run([str(RAIZ / 'bin/jangada-agente'), '--agente', 'claude',
                                   '--projeto', str(self.pasta), '--direto'],
                                  capture_output=True, text=True, env=self.ambiente, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn('revisão indisponível', resultado.stderr)
        pasta = self.pasta / 'estado/jangada/agentes'
        protocolo = next(pasta.glob('protocolo-*.md')).read_text()
        self.assertIn('jangada-validar', protocolo)
        self.assertIn('7. Escrita', protocolo)
        self.assertIn('não declare aprovação', protocolo)
        estado = next(arquivo for arquivo in pasta.glob('*.json')
                      if arquivo.name != 'historico.json')
        self.assertIn('jangada-isolar', estado.read_text())

    def regra_de_delegacao(self, perfil):
        self.script('tmux', '[[ " $* " == *" has-session "* ]] && exit 1\nexit 0\n')
        pasta = self.pasta / 'estado/jangada/agentes'
        for antigo in pasta.glob('protocolo-*.md') if pasta.exists() else ():
            antigo.unlink()
        resultado = subprocess.run([str(RAIZ / 'bin/jangada-agente'), '--perfil', perfil,
                                   '--projeto', str(self.pasta), '--direto'],
                                  capture_output=True, text=True, env=self.ambiente, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        texto = next(pasta.glob('protocolo-*.md')).read_text()
        return texto[texto.index('8. '):texto.index('Cada relatório cita')]

    def test_dois_perfis_padrao_recebem_a_mesma_regra_de_delegacao(self):
        corpos = {}
        for perfil in ('claude-codex', 'codex-claude'):
            regra = self.regra_de_delegacao(perfil)
            self.assertIn('--destino local --arquivos FONTES', regra, perfil)
            self.assertIn('--destino agy --permitir-remoto', regra, perfil)
            self.assertIn('Não reencaminhe ao agy', regra, perfil)
            self.assertIn('inclusive leitor e redator', regra, perfil)
            self.assertNotIn('Os papéis incluem', regra, perfil)
            corpos[perfil] = regra[regra.index('   - Todos os papéis'):regra.index('   - Falha local')]
        self.assertEqual(corpos['claude-codex'], corpos['codex-claude'])

    def test_padrao_codex_e_perfil_codex_tem_identificadores_distintos(self):
        (self.config / 'jangada.conf').write_text('JANGADA_AGENTE=codex\n')
        opcoes = self.menu().splitlines()
        self.assertTrue(any(linha.startswith('padrão\t') for linha in opcoes))
        self.assertTrue(any(linha.startswith('codex-claude\t') for linha in opcoes))


if __name__ == '__main__':
    unittest.main()
