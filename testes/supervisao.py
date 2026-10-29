#!/usr/bin/env python3
"""Confere supervisão e retomada com executores simulados, sem rede."""

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from estado import Estado
from executor import executar
from metricas_projeto import resumir
from supervisao import parecer_valido, aprovacao_valida
from acompanhamento import acompanhar
from saude import Saude
from projetos import cadastrar

SIMULADO = '''#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys,time
a=sys.argv[1:]
saida=pathlib.Path(a[a.index('--arquivo')+1])
revisao=saida.name=='parecer.json'
fontes=a[a.index('--arquivos')+1:a.index('--')]
destino=a[a.index('--destino')+1] if revisao else os.environ.get('AUTOR_TESTE','local')
with open(os.environ['REGISTRO_SUPERVISAO'],'a') as registro:
    registro.write(json.dumps({'fase':'revisao' if revisao else 'autor','destino':destino,
                              'saldo':os.environ['JANGADA_DELEGAR_CHAMADAS_MAX']})+'\\n')
modo=os.environ.get('MODO_SUPERVISAO','ok')
registro={'destino':destino,'modelo':'revisor-simulado' if revisao else 'autor-simulado','tentativas':[{'destino':destino,'chamadas':1}]}
if revisao and modo=='modelo_ausente':registro.pop('modelo')
if revisao and modo=='modelo_autor':registro['modelo']='autor-simulado'
if revisao and modo=='quota':
    registro.update(motivo_codigo='cota_insuficiente',recusa=True)
    registro['tentativas'][0].update(chamadas=0,motivo_codigo='cota_insuficiente')
    print(json.dumps(registro));sys.exit(4)
if revisao:
    pedido=json.loads(a[-1].split('\\n')[-1])
    justificativa='O conteúdo corresponde às evidências indicadas: '+', '.join(f'{f}:1' for f in fontes)
    parecer={'task_id':pedido['task_id'],'relatorio_sha256':pedido['relatorio_sha256'],
             'decisao':'APPROVED','criterios':{c:{'resultado':'PASS','justificativa':justificativa}
                 for c in ('fidelidade','completude','extrapolacoes')},'observacoes':[]}
    if modo=='erro':
        parecer['decisao']='REVISE';parecer['criterios']['fidelidade']['resultado']='FAIL'
    elif modo=='ambiguo':
        parecer['decisao']='ESCALATE';parecer['criterios']['fidelidade']['resultado']='INDETERMINATE'
    elif modo=='hash':parecer['relatorio_sha256']='0'*64
    elif modo=='referencias':
        for c in parecer['criterios'].values():c['justificativa']='O conteúdo está bom e suficiente para todos.'
    elif modo=='observacao':parecer['observacoes']=['Falta uma verificação.']
    elif modo=='timeout':time.sleep(5)
    elif modo=='desconhecido':registro['tentativas'][0]['chamadas']=None
    elif modo=='fonte_alterada':pathlib.Path(fontes[0]).write_text('alterada')
    saida.write_text('{quebrado' if modo=='json' else json.dumps(parecer,ensure_ascii=False))
else:
    saida.write_text('Resumo da regra conferida: '+', '.join(f'{f}:1' for f in fontes))
    if modo=='autor_sem_tentativas':registro['tentativas']=None
print(json.dumps(registro))
'''


class Supervisao(unittest.TestCase):
    def test_modelo_ausente_ou_igual_ao_autor_nao_aprova(self):
        for modo in ('modelo_ausente', 'modelo_autor'):
            with self.subTest(modo=modo), patch.dict(os.environ, MODO_SUPERVISAO=modo):
                identificador = 'IDENTIDADE-' + modo
                self.estado.importar([self.tarefa(identificador)])
                resultado = self.rodar()[0]
                self.assertNotEqual(resultado['status'], 'COMPLETED')

    def test_json_nao_reconstroi_comprovante_de_execucao(self):
        tarefa = self.tarefa()
        self.estado.importar([tarefa])
        resultado = self.rodar()[0]
        relatorio = self.estado.ler_artefato(self.estado.listar()[0]['hash_artefato'])
        self.assertTrue(aprovacao_valida(tarefa, relatorio, resultado))
        self.assertFalse(aprovacao_valida(tarefa, relatorio, json.loads(json.dumps(resultado))))
        self.assertFalse(aprovacao_valida(tarefa, relatorio + 'alterado', resultado))
        self.assertFalse(aprovacao_valida({**tarefa, 'id': 'OUTRA'}, relatorio, resultado))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.projeto = self.pasta / 'projeto'
        self.projeto.mkdir()
        self.fonte = self.projeto / 'fonte.md'
        self.fonte.write_text('Uma regra documentada.\n')
        self.raiz = self.pasta / 'jangada'
        (self.raiz / 'bin').mkdir(parents=True)
        (self.raiz / 'delegacao').mkdir(parents=True)
        shutil.copyfile(RAIZ / 'delegacao/validar.py', self.raiz / 'delegacao/validar.py')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        comando = self.raiz / 'bin/jangada-delegar'
        comando.write_text(SIMULADO)
        comando.chmod(0o700)
        self.estado = Estado(self.pasta / 'estado')
        self.addCleanup(self.estado.fechar)
        self.log = self.pasta / 'chamadas.jsonl'
        ambiente = patch.dict(os.environ, JANGADA_DELEGAR='agy', JANGADA_CODEX_ECONOMICO_MODELO='',
                              REGISTRO_SUPERVISAO=str(self.log), MODO_SUPERVISAO='ok', AUTOR_TESTE='local')
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def tarefa(self, id='T1', **campos):
        return {'id':id, 'papel':'leitor', 'capacidade':'resumo_curto', 'risco':1, 'qualidade':'medium',
                'pedido':'Resuma a regra sem extrapolar.', 'fontes':[str(self.fonte)],
                'hashes_fontes':{str(self.fonte):hashlib.sha256(self.fonte.read_bytes()).hexdigest()},
                'intermediaria':True, 'supervisao_automatica':True, 'permitir_remoto':True, **campos}

    def rodar(self, **opcoes):
        return executar(self.estado, self.projeto, self.raiz, permitir_remoto=True,
                        supervisao_automatica=True, **opcoes)

    def chamadas(self):
        return [json.loads(linha) for linha in self.log.read_text().splitlines()]

    def test_supervisor_aprova_intermediario_e_libera_dependencia(self):
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        resultado = self.rodar()[0]
        self.assertEqual(resultado['status'], 'COMPLETED')
        self.assertEqual(resultado['metricas']['chamadas'], 2)
        self.assertEqual([c['fase'] for c in self.chamadas()], ['autor', 'revisao'])
        self.assertEqual(self.estado.reservar()[0]['id'], 'T2')
        metricas = resumir(self.estado)
        self.assertEqual(metricas['supervisoes_aprovadas'], 1)
        self.assertEqual(metricas['revisoes_aprovadas'], 0)
        self.assertEqual(metricas['desempenho'], [])

    def test_politica_independente_conclui_com_execucao_comprovada(self):
        cadastrar(self.estado, self.projeto, {'provedores': ['ollama', 'agy'],
                  'revisao_minima': {'1': {'independente': True, 'contexto': 'diff'}}})
        self.estado.importar([self.tarefa(), self.tarefa('T2', dependencias=['T1'])])
        resultado = self.rodar()[0]
        self.assertEqual(resultado['status'], 'COMPLETED')
        self.assertEqual([c['fase'] for c in self.chamadas()], ['autor', 'revisao'])
        self.assertEqual(self.estado.reservar()[0]['id'], 'T2')

    def test_politica_independente_recusa_opcoes_sem_revisao_antes_de_chamar_autor(self):
        cadastrar(self.estado, self.projeto, {'provedores': ['ollama', 'agy'],
                  'revisao_minima': {'1': {'independente': True}}})
        self.estado.importar([self.tarefa()])
        for opcoes in ({'supervisao_automatica': False, 'permitir_remoto': True},
                       {'supervisao_automatica': True, 'permitir_remoto': False},
                       {'supervisao_automatica': True, 'permitir_remoto': True, 'perfil': 'offline'}):
            with self.subTest(opcoes=opcoes), self.assertRaisesRegex(ValueError, 'revisão independente'):
                executar(self.estado, self.projeto, self.raiz, **opcoes)
            self.assertFalse(self.log.exists())
            self.assertEqual(self.estado.listar()[0]['tentativas'], 0)
        self.assertEqual(self.rodar()[0]['status'], 'COMPLETED')

    def test_politica_dependente_de_codex_recusa_execucao_sem_permissao(self):
        cadastrar(self.estado, self.projeto, {'provedores': ['agy', 'codex'],
                  'revisao_minima': {'1': {'independente': True}}})
        self.estado.importar([self.tarefa(permitir_codex=True)])
        with self.assertRaisesRegex(ValueError, 'revisão independente'):
            self.rodar()
        self.assertFalse(self.log.exists())
        self.assertEqual(self.estado.listar()[0]['tentativas'], 0)

    def test_sem_opcao_explicita_nao_supervisiona(self):
        self.estado.importar([self.tarefa()])
        resultado = executar(self.estado, self.projeto, self.raiz, permitir_remoto=True)[0]
        self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')
        self.assertEqual(len(self.chamadas()), 1)

    def test_ollama_nunca_e_revisor(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, JANGADA_DELEGAR='local'):
            self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')
            self.assertEqual(self.rodar(), [])
        self.assertEqual(len(self.chamadas()), 1)

    def test_revisor_igual_ao_autor_nao_aprova(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, AUTOR_TESTE='agy'):
            self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(len(self.chamadas()), 1)

    def test_codex_configurado_revisa_autor_agy(self):
        self.estado.importar([self.tarefa(permitir_codex=True)])
        with patch.dict(os.environ, AUTOR_TESTE='agy', JANGADA_CODEX_ECONOMICO_MODELO='configurado'):
            resultado = self.rodar(permitir_codex=True)[0]
        self.assertEqual(resultado['status'], 'COMPLETED')
        self.assertEqual(resultado['supervisao']['executor'], 'codex-economico')

    def test_quota_retorna_e_revisa_sem_repetir_autor(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_SUPERVISAO='quota'):
            self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')
        artefato = self.estado.listar()[0]['artefato']
        self.assertEqual(self.rodar()[0]['status'], 'COMPLETED')
        self.assertEqual([c['fase'] for c in self.chamadas()], ['autor', 'revisao', 'revisao'])
        self.assertEqual(self.estado.listar()[0]['artefato'], artefato)
        self.assertEqual(self.estado.consumo('T1')['chamadas'], 2)
        self.assertEqual(resumir(self.estado)['chamadas_confirmadas'], 2)
        self.assertEqual(resumir(self.estado)['esperas_supervisao'], 1)
        self.assertEqual(resumir(self.estado)['supervisoes_inconclusivas'], 0)

    def test_autor_sem_lista_de_tentativas_nao_chega_a_supervisao(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_SUPERVISAO='autor_sem_tentativas'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertEqual([c['fase'] for c in self.chamadas()], ['autor'])

    def test_acompanhamento_retoma_supervisao_quando_quota_retorna(self):
        global_estado = Estado(self.pasta / 'saude')
        self.addCleanup(global_estado.fechar)
        saude = Saude(global_estado)
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_SUPERVISAO='quota'):
            self.assertEqual(self.rodar(saude=saude)[0]['status'], 'REVIEW_REQUIRED')
        def atualizar(remoto, prazo=None):
            self.assertTrue(remoto)
            saude.observar('agy', 'AVAILABLE', 'quota simulada retornou', cota=100)
        with patch.object(saude, 'atualizar', side_effect=atualizar) as sonda:
            resultado = acompanhar(self.estado, self.projeto, self.raiz, self.pasta / 'config', saude,
                                  limite=1, duracao=60, permitir_remoto=True, supervisao_automatica=True)
        sonda.assert_called_once_with(True, prazo=ANY)
        self.assertEqual(resultado['estados'], {'COMPLETED':1})
        self.assertEqual([c['fase'] for c in self.chamadas()], ['autor', 'revisao', 'revisao'])

    def test_erro_do_relatorio_exige_correcao(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_SUPERVISAO='erro'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')
        self.assertEqual(self.rodar(), [])

    def test_ambiguidades_nao_sao_repetidas_ate_obter_aprovacao(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_SUPERVISAO='ambiguo'):
            self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(self.rodar(), [])
        self.assertEqual(len(self.chamadas()), 2)

    def test_pareceres_invalidos_nao_aprovam(self):
        for modo in ('json','hash','referencias','observacao','desconhecido'):
            with self.subTest(modo=modo), patch.dict(os.environ, MODO_SUPERVISAO=modo):
                self.estado.importar([self.tarefa(modo)])
                resultado = self.rodar()[0]
                self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')
                self.assertEqual(resultado['tarefa'], modo)
                self.assertFalse(resultado['supervisao']['aguardando'])

    def test_orcamento_inclui_autor_e_revisor(self):
        self.estado.importar([self.tarefa(max_chamadas=1)])
        self.assertEqual(self.rodar()[0]['status'], 'REVIEW_REQUIRED')
        self.assertEqual(len(self.chamadas()), 1)
        self.assertEqual(self.rodar(), [])

    def test_timeout_preserva_relatorio_e_consumo_desconhecido(self):
        self.estado.importar([self.tarefa(tempo_total=3)])
        with patch.dict(os.environ, MODO_SUPERVISAO='timeout'):
            resultado = self.rodar()[0]
        self.assertEqual(resultado['status'], 'REVIEW_REQUIRED')
        self.assertIsNone(self.estado.consumo('T1')['chamadas'])
        self.assertIsNotNone(self.estado.listar()[0]['artefato'])
        self.assertEqual(self.rodar(), [])

    def test_fonte_alterada_pelo_revisor_impede_conclusao(self):
        self.estado.importar([self.tarefa()])
        with patch.dict(os.environ, MODO_SUPERVISAO='fonte_alterada'):
            self.assertEqual(self.rodar()[0]['status'], 'REVISION_REQUIRED')

    def historico(self, reprovadas=0):
        ids = [f'H{i}' for i in range(20)]
        self.estado.importar([self.tarefa(i, supervisao_automatica=False, amostragem=True) for i in ids])
        with patch.dict(os.environ, AUTOR_TESTE='agy'):
            resultados = executar(self.estado, self.projeto, self.raiz, limite=20, permitir_remoto=True, amostrar=True)
        self.assertEqual([r['status'] for r in resultados], ['REVIEW_REQUIRED'] * 20)
        self.assertTrue(all(r['amostragem']['taxa'] == 1 for r in resultados))
        if reprovadas:
            self.estado.revisar_lote(ids[:reprovadas], 'extrapolou a fonte', False)
        self.estado.revisar_lote(ids[reprovadas:], 'conferido com a fonte', True)

    def amostrar(self, quantidade=40, **opcoes):
        self.estado.importar([self.tarefa(f'A{i}', supervisao_automatica=False, amostragem=True)
                              for i in range(quantidade)])
        return executar(self.estado, self.projeto, self.raiz, limite=quantidade, permitir_remoto=True, **opcoes)

    def test_amostragem_conclui_fora_da_amostra_e_revisa_o_restante(self):
        self.historico()
        with patch.dict(os.environ, AUTOR_TESTE='agy'):
            resultados = self.amostrar(amostrar=True)
        for resultado in resultados:
            sorteio = resultado['amostragem']
            self.assertEqual(sorteio['taxa'], 0.1)
            self.assertEqual(sorteio['revisoes_na_janela'], 20)
            self.assertEqual(sorteio['selecionada'], sorteio['sorteio'] < 0.1)
            self.assertEqual(resultado['status'], 'REVIEW_REQUIRED' if sorteio['selecionada'] else 'COMPLETED')
        concluidas = sum(r['status'] == 'COMPLETED' for r in resultados)
        self.assertGreater(concluidas, 0)
        metricas = resumir(self.estado)
        self.assertEqual(metricas['conclusoes_fora_da_amostra'], concluidas)
        self.assertEqual(metricas['selecionadas_na_amostra'], 60 - concluidas)
        self.assertEqual(metricas['desempenho'][0]['revisoes_na_janela'], 20)

    def test_acompanhamento_repassa_a_amostragem(self):
        global_estado = Estado(self.pasta / 'saude')
        self.addCleanup(global_estado.fechar)
        self.historico()
        self.estado.importar([self.tarefa('A1', supervisao_automatica=False, amostragem=True)])
        with patch.dict(os.environ, AUTOR_TESTE='agy'):
            acompanhar(self.estado, self.projeto, self.raiz, self.pasta / 'config', Saude(global_estado),
                       limite=1, duracao=60, permitir_remoto=True, amostrar=True)
        sorteio = self.estado.listar()[-1]['resultado']['amostragem']
        self.assertEqual(sorteio['taxa'], 0.1)
        self.assertEqual(self.estado.listar()[-1]['status'], 'REVIEW_REQUIRED' if sorteio['selecionada'] else 'COMPLETED')

    def test_amostragem_exige_opcao_e_campo_explicitos(self):
        self.historico()
        with patch.dict(os.environ, AUTOR_TESTE='agy'):
            resultados = self.amostrar(10)
            self.estado.importar([self.tarefa(f'S{i}', supervisao_automatica=False) for i in range(10)])
            resultados += executar(self.estado, self.projeto, self.raiz, limite=10, permitir_remoto=True, amostrar=True)
        self.assertEqual([r['status'] for r in resultados], ['REVIEW_REQUIRED'] * 20)
        self.assertFalse(any('amostragem' in r for r in resultados))

    def test_amostragem_nunca_conclui_autor_local_nem_grupo_com_erros(self):
        self.historico(reprovadas=4)
        with patch.dict(os.environ, AUTOR_TESTE='agy'):
            resultados = self.amostrar(amostrar=True)
        self.estado.importar([self.tarefa(f'L{i}', supervisao_automatica=False, amostragem=True) for i in range(10)])
        resultados += executar(self.estado, self.projeto, self.raiz, limite=10, permitir_remoto=True, amostrar=True)
        self.assertEqual([r['status'] for r in resultados], ['REVIEW_REQUIRED'] * 50)
        self.assertTrue(all(r['amostragem']['taxa'] == 1 for r in resultados))

    def test_amostragem_selecionada_segue_para_o_supervisor(self):
        self.historico()
        self.estado.importar([self.tarefa(f'A{i}', amostragem=True, permitir_codex=True) for i in range(40)])
        with patch.dict(os.environ, AUTOR_TESTE='agy', JANGADA_CODEX_ECONOMICO_MODELO='configurado'):
            resultados = executar(self.estado, self.projeto, self.raiz, limite=40, permitir_remoto=True,
                                  permitir_codex=True, supervisao_automatica=True, amostrar=True)
        self.assertEqual([r['status'] for r in resultados], ['COMPLETED'] * 40)
        for resultado in resultados:
            self.assertEqual('supervisao' in resultado, resultado['amostragem']['selecionada'])

    def test_estado_recusa_sorteio_forjado(self):
        self.historico()
        self.estado.importar([self.tarefa('F1', supervisao_automatica=False, amostragem=True),
                              self.tarefa('F2', supervisao_automatica=False)])
        base = {'execucao_iniciada': True, 'verificacao': 'referencias_e_requisitos_validos',
                'metricas': {'chamadas': 1, 'segundos': 1}, 'delegacao': {'destino': 'agy', 'modelo': 'simulado'}}
        forjado = {'executor': 'agy', 'modelo': 'simulado', 'taxa': 0.0, 'sorteio': 0.5,
                   'revisoes_na_janela': 20, 'selecionada': False}
        for _ in range(2):
            tarefa, dono = self.estado.reservar()
            with self.assertRaises(ValueError):
                self.estado.finalizar(tarefa['id'], dono, 'COMPLETED', {**base, 'amostragem': forjado}, 'relatório')
            self.estado.finalizar(tarefa['id'], dono, 'REVIEW_REQUIRED', base, 'relatório')

    def test_nao_importa_amostragem_de_tarefa_final_ou_critica(self):
        for campos in ({'intermediaria':False}, {'risco':2}, {'qualidade':'high'}, {'amostragem':'sim'}):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                self.estado.importar([self.tarefa(**{'supervisao_automatica':False, 'amostragem':True, **campos})])
        self.assertEqual(self.estado.listar(), [])

    def test_nao_importa_supervisao_de_tarefa_final_ou_critica(self):
        for campos in ({'intermediaria':False}, {'risco':3}, {'qualidade':'high'}, {'intermediaria':'sim'}):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                self.estado.importar([self.tarefa(**campos)])
        self.assertEqual(self.estado.listar(), [])

    def test_parecer_com_chave_duplicada_e_rejeitado(self):
        valido = {'task_id':'T1', 'relatorio_sha256':hashlib.sha256(b'texto').hexdigest(),
                  'decisao':'APPROVED', 'criterios':{c:{'resultado':'PASS',
                    'justificativa':'A informação corresponde à fonte indicada em fonte.md:1.'} for c in
                    ('fidelidade','completude','extrapolacoes')}, 'observacoes':[]}
        texto = json.dumps(valido)
        self.assertEqual(parecer_valido(texto, self.tarefa(), 'texto')['decisao'], 'APPROVED')
        duplicado = texto.replace('"task_id": "T1"', '"task_id": "T1", "task_id": "T1"', 1)
        with self.assertRaises(ValueError):
            parecer_valido(duplicado, self.tarefa(), 'texto')

    def test_aprovacao_do_worker_nao_substitui_supervisor(self):
        self.estado.importar([self.tarefa()])
        _, dono = self.estado.reservar()
        with self.assertRaises(ValueError):
            self.estado.finalizar('T1', dono, 'COMPLETED', {'metricas':{'chamadas':1},
                                 'delegacao':{'destino':'local'}, 'confidence':1}, 'texto')
        self.assertFalse(aprovacao_valida(self.tarefa(), 'texto', {'supervisao':[]}))


if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
