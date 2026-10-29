#!/usr/bin/env python3
"""Caracteriza os contratos das tarefas sem executar agentes ou provedores."""

import copy
import itertools
import pathlib
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from tarefas import (tarefa_valida, serializar, prioridades_efetivas, validar_dependencias,
                     intermediaria, elegivel_supervisao as elegivel, amostravel)


def tarefa(**campos):
    return dict(id='T1', pedido='Leia a fonte', papel='leitor', capacidade='resumo_curto',
                risco=1, qualidade='medium', fontes=['fonte.md']) | campos


class Regras(unittest.TestCase):
    def test_contratos_carregam_sem_banco_nem_componentes_de_execucao(self):
        codigo = '''import sys
sys.path.insert(0,sys.argv[1])
import tarefas
proibidos={'sqlite3','subprocess','estado','supervisao','executor','saude','processos','projetos','confianca'}
assert not (proibidos & set(sys.modules)), proibidos & set(sys.modules)
'''
        resposta = subprocess.run([sys.executable, '-I', '-B', '-c', codigo, str(RAIZ / 'orquestracao')],
                                  capture_output=True, text=True, timeout=5)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)

    def test_interfaces_anteriores_apontam_para_as_mesmas_regras(self):
        import estado
        import supervisao
        import tarefas
        for nome in ('ESTADOS', 'FINAIS', 'IDENTIFICADOR', 'PRIORIDADES', 'serializar',
                     'tarefa_valida', 'prioridades_efetivas'):
            with self.subTest(nome=nome):
                self.assertIs(getattr(estado, nome), getattr(tarefas, nome))
        self.assertIs(supervisao.intermediaria, intermediaria)
        self.assertIs(supervisao.elegivel, elegivel)
        self.assertIs(supervisao.amostravel, amostravel)

    def test_saude_e_acompanhamento_carregam_sem_inicializar_estado(self):
        codigo = '''import sys
sys.path.insert(0,sys.argv[1])
__import__(sys.argv[2])
assert 'estado' not in sys.modules
'''
        for modulo in ('saude', 'acompanhamento'):
            with self.subTest(modulo=modulo):
                resposta = subprocess.run([sys.executable, '-I', '-B', '-c', codigo,
                                           str(RAIZ / 'orquestracao'), modulo],
                                          capture_output=True, text=True, timeout=5)
                self.assertEqual(resposta.returncode, 0, resposta.stderr)

    def test_dependencias_compartilhadas_sao_validas_e_erros_nao_alteram_o_plano(self):
        mapa = {nome: tarefa(id=nome, dependencias=deps) for nome, deps in (
            ('FINAL', ['A', 'B']), ('A', ['BASE']), ('B', ['BASE']), ('BASE', []))}
        antes = copy.deepcopy(mapa)
        self.assertIsNone(validar_dependencias(mapa))
        self.assertEqual(mapa, antes)
        for destino, erro in (('FINAL', 'ciclo'), ('AUSENTE', 'inexistente')):
            plano = copy.deepcopy(mapa)
            plano['BASE']['dependencias'] = [destino]
            antes = copy.deepcopy(plano)
            with self.subTest(destino=destino), self.assertRaisesRegex(ValueError, erro):
                validar_dependencias(plano)
            self.assertEqual(plano, antes)

    def test_tarefa_completa_e_metadados_sao_preservados(self):
        documento = tarefa(dependencias=['BASE'], prioridade='critical', requisitos=['Evidências'],
                           criterios_aceite=['Fidelidade'], contexto=['contexto.md'],
                           entradas=['documento'], saidas=['resumo'], atividade='atv-' + 'a' * 12,
                           intermediaria=True, supervisao_automatica=True, amostragem=True,
                           permitir_remoto=True, permitir_codex=True, max_chamadas=3,
                           tempo_total=30, max_tentativas=1, metadados={'origem': 'usuário'})
        antes = copy.deepcopy(documento)
        self.assertIsNone(tarefa_valida(documento))
        self.assertEqual(documento, antes)

    def test_campos_obrigatorios_e_identificadores_invalidos_sao_recusados(self):
        for campo in ('id', 'pedido', 'papel', 'capacidade', 'risco', 'qualidade', 'fontes'):
            documento = tarefa()
            del documento[campo]
            with self.subTest(campo=campo), self.assertRaisesRegex(ValueError, 'obrigatórios'):
                tarefa_valida(documento)
        for campos in ({'id': '../T1'}, {'id': 'T' * 97}, {'pedido': ' '},
                       {'fontes': []}, {'fontes': ['']}, {'qualidade': 'desconhecida'},
                       {'prioridade': 'urgente'}, {'atividade': 'inexistente'}):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                tarefa_valida(tarefa(**campos))

    def test_booleanos_nao_substituem_limites_numericos(self):
        for campo in ('risco', 'max_tentativas', 'tempo_total', 'max_chamadas'):
            for valor in (True, False, '1', 1.0, None, -1, 1000000):
                with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                    tarefa_valida(tarefa(**{campo: valor}))

    def test_listas_recusam_repeticoes_e_dependencia_propria(self):
        for campo in ('dependencias', 'requisitos', 'criterios_aceite', 'entradas', 'saidas', 'contexto'):
            for valor in ('texto', ['item', 'item'], [None]):
                with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                    tarefa_valida(tarefa(**{campo: valor}))
        with self.assertRaisesRegex(ValueError, 'si mesma'):
            tarefa_valida(tarefa(dependencias=['T1']))

    def test_elegibilidade_exige_todas_as_condicoes_do_intermediario(self):
        for risco, qualidade, papel, capacidade in itertools.product(
                (0, 1, 2), ('low', 'medium', 'high'), ('leitor', 'implementador'),
                ('resumo_curto', 'leitura_documental', 'analise_documental', 'implementacao')):
            documento = tarefa(risco=risco, qualidade=qualidade, papel=papel, capacidade=capacidade,
                               intermediaria=True, supervisao_automatica=True, amostragem=True)
            esperado = risco == 1 and qualidade in ('low', 'medium') and papel == 'leitor' and capacidade != 'implementacao'
            with self.subTest(risco=risco, qualidade=qualidade, papel=papel, capacidade=capacidade):
                self.assertEqual(intermediaria(documento), esperado)
                self.assertEqual(elegivel(documento), esperado)
                self.assertEqual(amostravel(documento), esperado)
                if esperado:
                    tarefa_valida(documento)
                else:
                    with self.assertRaises(ValueError):
                        tarefa_valida(documento)
        self.assertFalse(elegivel(tarefa(intermediaria=True)))
        self.assertFalse(amostravel(tarefa(intermediaria=True)))

    def test_permissoes_e_opcoes_exigem_booleanos(self):
        for campo in ('permitir_remoto', 'permitir_codex', 'intermediaria', 'supervisao_automatica', 'amostragem'):
            for valor in (0, 1, 'true', None):
                with self.subTest(campo=campo, valor=valor), self.assertRaisesRegex(ValueError, 'booleano'):
                    tarefa_valida(tarefa(**{campo: valor}))
        for campo in ('supervisao_automatica', 'amostragem'):
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                tarefa_valida(tarefa(**{campo: True}))

    def test_json_canonico_preserva_unicode_e_recusa_numeros_nao_finitos(self):
        self.assertEqual(serializar({'z': 'ação', 'a': 1}), '{"a": 1, "z": "ação"}')
        for valor in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                tarefa_valida(tarefa(metadados={'valor': valor}))

    def test_prioridade_herdada_nao_altera_especificacoes_nem_promove_pausadas(self):
        tarefas = [{'id': nome, 'especificacao': tarefa(id=nome, prioridade=prioridade, dependencias=deps)}
                   for nome, prioridade, deps in (('BASE', 'low', []), ('MEIO', 'normal', ['BASE']),
                                                  ('FINAL', 'critical', ['MEIO']), ('PAUSADA', 'background', []))]
        antes = copy.deepcopy(tarefas)
        estados = {'BASE': 'QUEUED', 'MEIO': 'QUEUED', 'FINAL': 'QUEUED', 'PAUSADA': 'PAUSED'}
        self.assertEqual(prioridades_efetivas(tarefas, estados), {'BASE': 0, 'MEIO': 0, 'FINAL': 0, 'PAUSADA': 4})
        estados['FINAL'] = 'PAUSED'
        self.assertEqual(prioridades_efetivas(tarefas, estados), {'BASE': 2, 'MEIO': 2, 'FINAL': 0, 'PAUSADA': 4})
        self.assertEqual(tarefas, antes)


if __name__ == '__main__':
    unittest.main()
