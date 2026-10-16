#!/usr/bin/env python3
"""Confere critérios locais, persistência e liberação do grafo sem modelos."""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from acompanhamento import acompanhar
from deterministico import conferir
from estado import Estado
from executor import executar
from saude import Saude


class Conferencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.estado = Estado(self.pasta / 'estado')
        self.addCleanup(self.estado.fechar)
        self.fonte = self.pasta / 'dados.json'
        self.fonte.write_text('{"nome":"ação", "valor":42}', encoding='utf-8')

    def tarefa(self, identificador='T1', **campos):
        return {'id': identificador, 'pedido': 'Confira a sintaxe JSON',
                'papel': 'verificador', 'capacidade': 'validacao_json', 'risco': 0,
                'qualidade': 'medium', 'fontes': [str(self.fonte)],
                'hashes_fontes': {str(self.fonte): hashlib.sha256(self.fonte.read_bytes()).hexdigest()},
                **campos}

    def rodar(self, **opcoes):
        with patch('executor.subprocess.Popen') as modelo:
            resultado = executar(self.estado, self.pasta, RAIZ, **opcoes)
        modelo.assert_not_called()
        return resultado

    def test_conclusao_automatica_persistente_com_proveniencia(self):
        self.estado.importar([self.tarefa()])
        resultado = self.rodar(perfil='offline')[0]
        self.assertEqual(resultado['status'], 'COMPLETED')
        self.assertEqual(resultado['executor'], 'deterministico')
        item = self.estado.listar()[0]
        evidencia = json.loads(self.estado.ler_artefato(item['artefato']))
        self.assertEqual(evidencia['fontes'][0]['sha256'], self.tarefa()['hashes_fontes'][str(self.fonte)])
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 0)
        outro = Estado(self.estado.pasta)
        self.addCleanup(outro.fechar)
        self.assertEqual(outro.listar()[0]['status'], 'COMPLETED')
        self.assertIsNone(outro.reservar())

    def test_dependencias_liberadas_sem_aprovacao_de_modelo(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        resultados = self.rodar(limite=2)
        self.assertEqual([r['status'] for r in resultados], ['COMPLETED', 'COMPLETED'])

    def test_rejeita_json_ambiguo_nao_finito_e_unicode_invalido(self):
        for indice, texto in enumerate(('NaN', 'Infinity', '1e999', '{"x":1,"x":2}',
                                       '{"x":1,"\\u0078":2}', '"\\ud800"', '{"\\ud800":0}', '{"x":}', '{} {}')):
            with self.subTest(texto=texto):
                self.fonte.write_text(texto)
                identificador = f'T{indice}'
                self.estado.importar([self.tarefa(identificador)])
                resultado = self.rodar()[0]
                self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
                self.assertNotEqual(self.estado.listar()[-1]['status'], 'COMPLETED')

    def test_utf8_invalido_nao_conclui(self):
        self.fonte.write_bytes(b'{"x":"\xff"}')
        self.estado.importar([self.tarefa()])
        self.assertIn('UTF-8', self.rodar()[0]['motivo'])

    def test_aceita_raizes_json_e_par_unicode_valido(self):
        for texto in ('null', 'true', '42', '"texto"', '[1,2]', '"\\ud83d\\ude00"'):
            with self.subTest(texto=texto):
                self.fonte.write_text(texto)
                self.assertEqual(json.loads(conferir(self.tarefa()))['resultado'], 'PASS')

    def test_fonte_alterada_antes_da_execucao_nao_conclui(self):
        self.estado.importar([self.tarefa()])
        self.fonte.write_text('{}')
        self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')

    def test_estado_repete_conferencia_antes_de_concluir(self):
        tarefa = self.tarefa()
        self.estado.importar([tarefa])
        evidencia = conferir(tarefa)
        def substituir(_):
            self.fonte.write_text('{}')
            return evidencia
        with patch('executor.conferir', side_effect=substituir):
            resultado = self.rodar()[0]
        self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
        self.assertIn('mudou', resultado['motivo'])

    def test_aprovacao_autorreferida_nao_conclui(self):
        self.estado.importar([self.tarefa()])
        _, dono = self.estado.reservar()
        with self.assertRaises(ValueError):
            self.estado.finalizar('T1', dono, 'COMPLETED',
                                 {'execucao_iniciada': True, 'metricas': {'chamadas': 0}},
                                 '{"resultado":"PASS","confidence":1}')
        self.assertEqual(self.estado.listar()[0]['status'], 'RUNNING')

    def test_leitor_nao_pode_contornar_revisao_pela_conclusao_direta(self):
        self.estado.importar([self.tarefa(papel='leitor', capacidade='leitura_documental', risco=1)])
        _, dono = self.estado.reservar()
        with self.assertRaises(ValueError):
            self.estado.finalizar('T1', dono, 'COMPLETED',
                                 {'execucao_iniciada': True, 'metricas': {'chamadas': 0}}, 'relatório')

    def test_risco_papel_ou_requisito_adicional_exigem_revisao(self):
        for indice, campos in enumerate(({'risco': 1}, {'papel': 'leitor'}, {'requisitos': ['Fidelidade']})):
            with self.subTest(campos=campos):
                self.estado.importar([self.tarefa(f'T{indice}', **campos)])
                self.assertEqual(self.rodar()[0]['status'], 'WAITING_REVIEWER')

    def com_esquema(self, esquema, identificador='T1', **campos):
        arquivo = self.pasta / 'esquema.json'
        arquivo.write_text(json.dumps(esquema), encoding='utf-8')
        return self.tarefa(identificador, esquema=str(arquivo),
                           hash_esquema=hashlib.sha256(arquivo.read_bytes()).hexdigest(), **campos)

    ESQUEMA = {'type': 'object', 'required': ['nome', 'valor'], 'additionalProperties': False,
               'properties': {'nome': {'type': 'string', 'minLength': 2, 'maxLength': 10},
                              'valor': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                              'itens': {'type': 'array', 'minItems': 1, 'maxItems': 2,
                                        'items': {'enum': ['a', 1, None]}},
                              'fixo': {'const': {'x': [1]}}, 'extra': {'type': ['null', 'boolean']}}}

    def test_esquema_conclui_com_proveniencia_e_estado_repete_a_conferencia(self):
        self.estado.importar([self.com_esquema(self.ESQUEMA)])
        resultado = self.rodar(perfil='offline')[0]
        self.assertEqual(resultado['status'], 'COMPLETED')
        self.assertEqual(resultado['verificacao'], 'sintaxe_json_estrita_e_esquema')
        evidencia = json.loads(self.estado.ler_artefato(self.estado.listar()[0]['artefato']))
        self.assertEqual(evidencia['criterio'], 'sintaxe_json_estrita_e_esquema')
        self.assertEqual(evidencia['esquema']['sha256'], self.com_esquema(self.ESQUEMA)['hash_esquema'])
        self.estado.importar([self.com_esquema(self.ESQUEMA, 'T2')])
        _, dono = self.estado.reservar()
        with self.assertRaises(ValueError):
            self.estado.finalizar('T2', dono, 'COMPLETED', {'execucao_iniciada': True, 'metricas': {'chamadas': 0}},
                                 conferir(self.tarefa('T2')))

    def test_esquema_aceita_valores_validos(self):
        tarefa = self.com_esquema(self.ESQUEMA)
        for texto in ('{"nome":"ab","valor":0}', '{"nome":"ação","valor":100.0,"itens":["a",1.0]}',
                      '{"nome":"abc","valor":7,"itens":[null],"fixo":{"x":[1]},"extra":true}'):
            with self.subTest(texto=texto):
                self.fonte.write_text(texto, encoding='utf-8')
                tarefa['hashes_fontes'] = self.tarefa()['hashes_fontes']
                self.assertEqual(json.loads(conferir(tarefa))['resultado'], 'PASS')

    def test_esquema_reprova_com_caminho_do_erro(self):
        casos = (('[]', '$: tipo'), ('{"nome":"ab"}', '$: falta a propriedade "valor"'),
                 ('{"nome":"a","valor":1}', '$["nome"]: comprimento menor'),
                 ('{"nome":"abcdefghijk","valor":1}', '$["nome"]: comprimento maior'),
                 ('{"nome":"ab","valor":1.5}', '$["valor"]: tipo'), ('{"nome":"ab","valor":true}', '$["valor"]: tipo'),
                 ('{"nome":"ab","valor":-1}', '$["valor"]: menor'), ('{"nome":"ab","valor":101}', '$["valor"]: maior'),
                 ('{"nome":"ab","valor":1,"outro":0}', '$["outro"]: propriedade não prevista'),
                 ('{"nome":"ab","valor":1,"itens":[]}', '$["itens"]: comprimento menor'),
                 ('{"nome":"ab","valor":1,"itens":["a","a","a"]}', '$["itens"]: comprimento maior'),
                 ('{"nome":"ab","valor":1,"itens":["a",true]}', '$["itens"][1]: valor fora de enum'),
                 ('{"nome":"ab","valor":1,"fixo":{"x":[true]}}', '$["fixo"]: valor diferente de const'),
                 ('{"nome":"ab","valor":1,"extra":0}', '$["extra"]: tipo'))
        for indice, (texto, trecho) in enumerate(casos):
            with self.subTest(texto=texto):
                self.fonte.write_text(texto, encoding='utf-8')
                self.estado.importar([self.com_esquema(self.ESQUEMA, f'T{indice}')])
                resultado = self.rodar()[0]
                self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
                self.assertIn('fora do esquema em ' + trecho, resultado['motivo'])

    def test_esquema_com_regra_nao_aceita_ou_invalida_nao_conclui(self):
        for esquema in ([], True, {'pattern': '^a'}, {'$ref': '#/x'}, {'type': 'texto'}, {'type': []}, {'enum': []},
                        {'required': ['a', 'a']}, {'properties': {'a': {'allOf': []}}}, {'items': {'minItems': -1}},
                        {'additionalProperties': {'maximum': '1'}}, {'minimum': True}, {'maxLength': 1.5}):
            with self.subTest(esquema=esquema), self.assertRaises(ValueError):
                conferir(self.com_esquema(esquema))

    def test_esquema_alterado_ausente_ou_fora_do_projeto_nao_conclui(self):
        tarefa = self.com_esquema(self.ESQUEMA)
        self.estado.importar([tarefa, self.tarefa('T2', esquema=str(self.pasta / 'ausente.json'), hash_esquema='0' * 64)])
        pathlib.Path(tarefa['esquema']).write_text('{}')
        self.assertEqual([r['status'] for r in self.rodar(limite=2)], ['REVISION_REQUIRED'] * 2)
        fora = pathlib.Path(tempfile.mkdtemp(dir=self.pasta.parent))
        self.addCleanup(shutil.rmtree, fora)
        (fora / 'esquema.json').write_text('{}')
        self.estado.importar([self.tarefa('T3', esquema=str(fora / 'esquema.json'),
                                          hash_esquema=hashlib.sha256(b'{}').hexdigest())])
        resultado = self.rodar()[0]
        self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
        self.assertIn('fora do projeto', resultado['motivo'])

    def test_cli_importa_esquema_do_projeto_com_resumo(self):
        (self.pasta / 'esquema.json').write_text('{"type":"object"}')
        plano = self.pasta / 'plano.json'
        ambiente = {**os.environ, 'JANGADA_ESTADO': str(self.pasta / 'cli-estado'),
                    'JANGADA_CORE_PATH': str(RAIZ)}
        comando = [sys.executable, str(RAIZ / 'orquestracao/cli.py'), 'fila', '--projeto', str(self.pasta),
                   '--json', '--importar', str(plano)]
        tarefa = {k: v for k, v in self.tarefa(fontes=['dados.json']).items() if k != 'hashes_fontes'}
        plano.write_text(json.dumps([{**tarefa, 'esquema': '../esquema.json'}]))
        recusa = subprocess.run(comando, env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(recusa.returncode, 2)
        self.assertIn('fora do projeto', recusa.stderr)
        plano.write_text(json.dumps([{**tarefa, 'esquema': 'esquema.json'}]))
        importacao = subprocess.run(comando, env=ambiente, capture_output=True, text=True, timeout=5)
        self.assertEqual(importacao.returncode, 0, importacao.stderr)
        spec = json.loads(importacao.stdout)['tarefas'][0]['especificacao']
        self.assertEqual(spec['esquema'], str((self.pasta / 'esquema.json').resolve()))
        self.assertEqual(spec['hash_esquema'], hashlib.sha256(b'{"type":"object"}').hexdigest())
        self.assertEqual(spec['fontes'], [str(self.fonte.resolve())])

    def test_esquema_so_e_importado_com_validacao_json_e_resumo(self):
        for campos in ({'capacidade': 'leitura_documental', 'papel': 'leitor', 'risco': 1, 'hash_esquema': '0' * 64},
                       {}, {'hash_esquema': 1}):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                self.estado.importar([self.tarefa(esquema='esquema.json', **campos)])
        with self.assertRaises(ValueError):
            self.estado.importar([self.tarefa(esquema='', hash_esquema='0' * 64)])

    def test_limites_de_tamanho_e_profundidade(self):
        for texto in ('"' + 'x' * (1024 * 1024) + '"', '[' * 66 + '0' + ']' * 66):
            with self.subTest(tamanho=len(texto)):
                self.fonte.write_text(texto)
                with self.assertRaises(ValueError):
                    conferir(self.tarefa())

    def test_link_e_arquivo_especial_nao_sao_lidos(self):
        tarefa = self.tarefa()
        original = self.pasta / 'original.json'
        self.fonte.rename(original)
        self.fonte.symlink_to(original)
        with self.assertRaises(OSError):
            conferir(tarefa)
        self.fonte.unlink()
        os.mkfifo(self.fonte)
        with self.assertRaises(ValueError):
            conferir(tarefa)

    def test_consumo_desconhecido_impede_repeticao_automatica(self):
        self.estado.importar([self.tarefa()])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVISION_REQUIRED',
                             {'execucao_iniciada': True, 'metricas': {'chamadas': None, 'segundos': 0}})
        self.estado.alterar('T1', 'repetir')
        with patch('executor.conferir') as conferir_modelo:
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        conferir_modelo.assert_not_called()

    def test_tempo_total_persistido_impede_nova_conferencia(self):
        self.estado.importar([self.tarefa(tempo_total=1)])
        _, dono = self.estado.reservar()
        self.estado.finalizar('T1', dono, 'REVISION_REQUIRED',
                             {'execucao_iniciada': True, 'metricas': {'chamadas': 0, 'segundos': 1}})
        self.estado.alterar('T1', 'repetir')
        with patch('executor.conferir') as criterio:
            self.assertEqual(self.rodar()[0]['status'], 'FAILED')
        criterio.assert_not_called()

    def test_artefato_da_dependencia_adulterado_impede_conclusao(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        self.rodar()
        resumo = self.estado.listar()[0]['artefato']
        (self.estado.pasta / 'artefatos' / f'{resumo}.txt').write_text('alterado')
        self.assertEqual(self.rodar(), [])
        self.assertEqual(self.estado.listar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(self.estado.listar()[1]['tentativas'], 0)

    def test_dependencia_ausente_na_segunda_leitura_nao_deixa_reserva_ativa(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        self.rodar()
        itens = self.estado.listar()
        with patch.object(self.estado, 'listar', side_effect=[[itens[1]]]):
            resultado = self.rodar()[0]
        self.assertEqual(resultado['tarefa'], 'T2')
        self.assertEqual(resultado['status'], 'REVISION_REQUIRED')
        self.assertIsNone(self.estado.listar()[1]['dono'])

    def test_limites_de_fontes_e_tamanho_total(self):
        tarefa = self.tarefa(fontes=[str(self.fonte)] * 33)
        with self.assertRaises(ValueError):
            conferir(tarefa)
        fontes, hashes = [], {}
        for indice in range(5):
            fonte = self.pasta / f'grande-{indice}.json'
            fonte.write_text('"' + 'x' * 900000 + '"')
            fontes.append(str(fonte))
            hashes[str(fonte)] = hashlib.sha256(fonte.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'total'):
            conferir(self.tarefa(fontes=fontes, hashes_fontes=hashes))

    def test_interrupcao_preserva_estado_sem_iniciar_proxima_tarefa(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2')])
        with patch('executor.conferir', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.rodar(limite=2)
        self.assertEqual([i['status'] for i in self.estado.listar()], ['REVISION_REQUIRED', 'QUEUED'])
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 0)

    def test_acompanhamento_conta_execucoes_sem_chamadas(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2')])
        global_estado = Estado(self.pasta / 'global')
        self.addCleanup(global_estado.fechar)
        with patch.object(Saude, 'atualizar') as sonda:
            fim = acompanhar(self.estado, self.pasta, RAIZ, self.pasta, Saude(global_estado),
                              perfil='offline', limite=1)
        sonda.assert_not_called()
        self.assertEqual(fim['execucoes'], 1)
        self.assertEqual(fim['estados'], {'COMPLETED': 1, 'QUEUED': 1})


if __name__ == '__main__':
    unittest.main()
