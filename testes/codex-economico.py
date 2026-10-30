#!/usr/bin/env python3
"""Confere alternativa Codex e roteamento com executores inteiramente simulados."""

import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
RAIZ = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('worker_codex', RAIZ / 'delegacao/codex.py')
WORKER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(WORKER)


class Economico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = pathlib.Path(self.tmp.name)
        self.raiz = self.pasta / 'jangada'
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        for nome in ('bin', 'delegacao', 'orquestracao'):
            (self.raiz / nome).mkdir(parents=True)
        for nome in ('bin/jangada-config', 'bin/jangada-delegar', 'delegacao/validar.py',
                     'bin/jangada-retomar', 'bin/jangada-router', 'bin/jangada-isolar', 'delegacao/codex.py',
                     'orquestracao/cota_codex.py', 'orquestracao/cli.py',
                     'orquestracao/estado.py', 'orquestracao/executor.py',
                     'orquestracao/saude.py', 'orquestracao/acompanhamento.py',
                     'orquestracao/deterministico.py', 'orquestracao/metricas_projeto.py',
                     'orquestracao/supervisao.py', 'orquestracao/principal.py',
                     'orquestracao/projetos.py', 'orquestracao/confianca.py', 'orquestracao/prazos.py',
                     'orquestracao/reservas.py', 'orquestracao/processos.py', 'orquestracao/tarefas.py'):
            shutil.copy2(RAIZ / nome, self.raiz / nome)
        self.audit = self.pasta / 'execucao.json'
        self.fonte = self.pasta / 'fonte.md'
        self.fonte.write_text('Regra documentada na primeira linha.\n')
        self.casa = self.pasta / 'codex'
        self.casa.mkdir()
        exp = base64.urlsafe_b64encode(json.dumps({'exp': time.time() + 3600}).encode()).decode().rstrip('=')
        (self.casa / 'auth.json').write_text(json.dumps({'tokens': {
            'access_token': 'h.' + exp + '.s', 'id_token': 'identidade-falsa',
            'refresh_token': 'renovacao-original', 'account_id': 'conta-falsa'}}))
        self.bin = self.pasta / 'bin'
        self.bin.mkdir()
        self.config = self.pasta / 'config/jangada'
        self.config.mkdir(parents=True)
        (self.config / 'delegacao.json').write_text(json.dumps({'analise_documental': ['agy', 'codex-economico']}))
        self.runtime = self.pasta / 'run'
        self.runtime.mkdir(mode=0o700)
        self.ambiente = patch.dict(os.environ, JANGADA_CORE_PATH=str(self.raiz), JANGADA_DELEGAR='agy',
                                   XDG_RUNTIME_DIR=str(self.runtime),
                                   JANGADA_CODEX_ECONOMICO_MODELO='modelo-economico-teste',
                                   JANGADA_CODEX_COTA_MIN='25', CODEX_HOME=str(self.casa),
                                   XDG_STATE_HOME=str(self.pasta / 'state'), XDG_CONFIG_HOME=str(self.pasta / 'config'),
                                   XDG_CACHE_HOME=str(self.pasta / 'cache'),
                                   PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                                   JANGADA_DELEGAR_IMPEDIMENTOS=json.dumps([
                                       {'destino': 'agy', 'motivo_codigo': 'cota_indisponivel', 'motivo': 'cota esgotada'}]))
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)
        self.stub_cota(20)
        self.stub_worker()

    def programa(self, caminho, corpo):
        caminho.write_text('#!' + sys.executable + '\n' + corpo)
        caminho.chmod(0o700)

    def stub_cota(self, usado):
        self.programa(self.bin / 'codex', '''import json, sys, time
assert sys.argv[-2:] == ['app-server', '--stdio']
assert json.loads(sys.stdin.readline())['method'] == 'initialize'
print(json.dumps({'id': 1, 'result': {}}), flush=True)
assert json.loads(sys.stdin.readline())['method'] == 'initialized'
assert json.loads(sys.stdin.readline())['method'] == 'account/rateLimits/read'
print(json.dumps({'id': 2, 'result': {'rateLimits': {'limitId': 'codex',
    'primary': {'usedPercent': ''' + repr(usado) + ''', 'resetsAt': int(time.time()) + 3600}}}}), flush=True)
sys.stdin.read()
''')

    def stub_worker(self, modo='ok', modelo='modelo-economico-teste'):
        self.programa(self.raiz / 'bin/jangada-codex', '''import hashlib, json, os, pathlib, sqlite3, sys, time
args = sys.argv[1:]
assert args[:3] == ['--revisar', '--', 'codex']
assert args[args.index('--model') + 1] == ''' + repr(modelo) + '''
assert os.environ['HOME'] == os.environ['CODEX_HOME']
assert 'SEGREDO_TESTE' not in os.environ
assert json.loads((pathlib.Path(os.environ['CODEX_HOME']) / 'auth.json').read_text())['tokens']['refresh_token'] == ''
entrada = sys.stdin.read()
dados = json.loads(entrada.splitlines()[-1])
pid_worker = os.getppid()
pid_shell = int((pathlib.Path('/proc') / str(pid_worker) / 'stat').read_text().split(') ')[1].split()[1])
pathlib.Path(''' + repr(str(self.audit)) + ''').write_text(json.dumps({'args': args, 'prompt': dados, 'instrucao': entrada.splitlines()[0],
    'pid': os.getpid(), 'casa': os.environ['CODEX_HOME'], 'worker': pid_worker, 'bash': pid_shell}))
modo = ''' + repr(modo) + '''
if modo == 'demorado':
    time.sleep(60)
if modo == 'erro':
    sys.exit(1)
saida = pathlib.Path(args[args.index('--output-last-message') + 1])
texto = 'A regra possui conteúdo documentado na fonte fornecida. ' + dados['fontes'][0]['fonte'] + ':1'
if modo == 'mudou':
    pathlib.Path(dados['fontes'][0]['fonte']).write_text('fonte alterada durante a execução')
if modo == 'mudou_dependencia':
    pasta=pathlib.Path(dados['fontes'][1]['fonte']).parent
    conteudo='novo artefato intermediário'
    sha=hashlib.sha256(conteudo.encode()).hexdigest()
    (pasta / (sha+'.txt')).write_text(conteudo)
    with sqlite3.connect(pasta.parent / 'tarefas.sqlite') as db:
        db.execute('UPDATE tarefas SET artefato=?,hash_artefato=? WHERE id=?',(sha,sha,'D1'))
if modo == 'parecer':
    texto = json.dumps({'task_id':'S1','relatorio_sha256':'0'*64,'decisao':'APPROVED',
                        'criterios':{c:{'resultado':'PASS','justificativa':'Regra conferida na fonte '+dados['fontes'][0]['fonte']+':1'}
                                     for c in ('fidelidade','completude','extrapolacoes')},'observacoes':[]})
if modo == 'sem-fonte':
    texto = 'Texto sem referência.'
if modo == 'gigante':
    texto = 'x' * 64001
saida.write_text(texto)
if modo != 'sem-completo':
    print('invalido' if modo == 'json-invalido' else json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 10, 'output_tokens': 12}}))
if modo == 'duplicado':
    print(json.dumps({'type': 'turn.completed'}))
''')

    def executar(self, tempo=30):
        return WORKER.executar(self.raiz, self.pasta, 'Leia a regra', [str(self.fonte)], tempo)

    def delegar(self, extras=(), candidato=False, papel='leitor'):
        args = [str(self.raiz / 'bin/jangada-delegar'), '--capacidade', 'analise_documental', '--json']
        if candidato:
            args += ['--destino', 'codex-economico']
        args += list(extras) + ['--arquivos', str(self.fonte), '--', papel, 'Leia a regra']
        return subprocess.run(args, cwd=self.pasta, capture_output=True, text=True, timeout=20)

    def test_modelo_explicito_fontes_limitadas_sem_ferramentas(self):
        with patch.dict(os.environ, SEGREDO_TESTE='nao-transmitir'):
            resultado = self.executar()
        self.assertEqual(resultado['motivo_codigo'], '')
        self.assertEqual(resultado['chamadas'], 1)
        self.assertEqual(resultado['tokens_saida'], 12)
        self.assertEqual(resultado['cota_antes'], 80)
        dados = json.loads(self.audit.read_text())['prompt']
        self.assertEqual(dados['fontes'], [{'fonte': str(self.fonte), 'linhas': '1: Regra documentada na primeira linha.'}])

    def preparar_principal(self, **campos):
        from estado import Estado
        from saude import Saude
        ambiente = patch.dict(os.environ, JANGADA_CODEX_PRINCIPAL_MODELO='modelo-principal-teste',
                              JANGADA_ESTADO=str(self.pasta / 'state/jangada'))
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.stub_worker(modelo='modelo-principal-teste')
        estado = Estado(self.pasta / 'principal')
        self.addCleanup(estado.fechar)
        estado.importar([{'id':'P1','pedido':'Sintetize a regra','papel':'redator','capacidade':'sintese',
                          'risco':3,'qualidade':'high','fontes':[str(self.fonte)],
                          'hashes_fontes':{str(self.fonte):hashlib.sha256(self.fonte.read_bytes()).hexdigest()},
                          'permitir_remoto':True,'permitir_codex':True, **campos}])
        return estado, Saude(estado)

    def principal(self, estado, saude, **opcoes):
        from principal import executar_principal
        return executar_principal(estado, 'P1', self.pasta, self.raiz, saude,
                                  **{'permitir_remoto':True, 'permitir_codex':True, **opcoes})

    def test_principal_modelo_explicito_preserva_relatorio_sem_aprovar(self):
        from metricas_projeto import resumir
        estado, saude = self.preparar_principal()
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'REVIEW_REQUIRED',resultado)
        self.assertEqual(resultado['modelo'],'modelo-principal-teste')
        self.assertEqual(estado.consumo('P1')['chamadas'],1)
        self.assertIn(str(self.fonte),estado.ler_artefato(estado.listar()[0]['artefato']))
        self.assertEqual(resumir(estado)['tokens_entrada'],10)
        dados=json.loads(self.audit.read_text())
        self.assertIn('modelo-principal-teste',dados['args'])
        self.assertIn('análise documental principal',dados['instrucao'])
        self.assertEqual(saude.listar()[0]['id'],'agy')
        with self.assertRaises(ValueError):
            self.principal(estado,saude)

    def test_principal_sem_permissao_modelo_ou_perfil_nao_reserva(self):
        estado, saude = self.preparar_principal()
        casos=[({'permitir_remoto':False},{}),({'permitir_codex':False},{}),
               ({},{'JANGADA_DELEGAR':'local'}),({},{'JANGADA_CODEX_PRINCIPAL_MODELO':''}),
               ({},{'JANGADA_CODEX_PRINCIPAL_MODELO':'--premium'})]
        for opcoes, ambiente in casos:
            with self.subTest(opcoes=opcoes,ambiente=ambiente), patch.dict(os.environ,**ambiente):
                with self.assertRaises(ValueError):
                    self.principal(estado,saude,**opcoes)
        self.assertEqual(estado.listar()[0]['status'],'QUEUED')
        self.assertFalse(self.audit.exists())

    def test_principal_sem_pasta_estado_recusa_sem_reserva(self):
        estado, saude = self.preparar_principal()
        with patch.dict(os.environ):
            os.environ.pop('JANGADA_ESTADO')
            with self.assertRaisesRegex(ValueError,'estado'):
                self.principal(estado,saude)
        self.assertEqual(estado.listar()[0]['status'],'QUEUED')

    def test_principal_cota_baixa_nao_gera_e_preserva_orcamento(self):
        estado, saude = self.preparar_principal()
        self.stub_cota(80)
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'WAITING_QUOTA')
        self.assertEqual(resultado['metricas']['chamadas'],0)
        self.assertEqual(estado.listar()[0]['tentativas'],0)
        self.assertFalse(self.audit.exists())
        self.assertEqual(next(i for i in saude.listar() if i['id']=='codex')['status'],'QUOTA_LOW')

    def test_principal_pausa_cooldown_e_trava_compartilhada_nao_geram(self):
        estado, saude = self.preparar_principal()
        saude.pausar('codex',True)
        with self.assertRaises(ValueError):
            self.principal(estado,saude)
        saude.pausar('codex',False)
        saude.observar('codex','COOLDOWN','limite de chamadas')
        with self.assertRaises(ValueError):
            self.principal(estado,saude)
        saude.observar('codex','UNKNOWN','aguarda consulta')
        trava=pathlib.Path(os.environ['JANGADA_ESTADO']) / 'agentes/codex-economico.lock'
        trava.parent.mkdir(parents=True,exist_ok=True)
        with trava.open('w') as arquivo:
            fcntl.flock(arquivo,fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValueError):
                self.principal(estado,saude)
        self.assertEqual(estado.listar()[0]['status'],'QUEUED')
        self.assertFalse(self.audit.exists())

    def test_principal_nao_executa_microtarefa(self):
        estado, saude = self.preparar_principal(risco=1,qualidade='medium')
        with self.assertRaises(ValueError):
            self.principal(estado,saude)
        self.assertFalse(self.audit.exists())

    def test_principal_nao_executa_risco_quatro(self):
        estado, saude = self.preparar_principal(risco=4)
        with self.assertRaises(ValueError):
            self.principal(estado,saude)
        self.assertFalse(self.audit.exists())

    def test_principal_nao_executa_capacidade_de_codigo(self):
        estado, saude = self.preparar_principal(capacidade='coding_complex')
        with self.assertRaises(ValueError):
            self.principal(estado,saude)
        self.assertFalse(self.audit.exists())

    def test_principal_cota_desconhecida_nao_gera(self):
        estado, saude = self.preparar_principal()
        self.programa(self.bin / 'codex','print("cota desconhecida")')
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'WAITING_QUOTA')
        self.assertEqual(resultado['metricas']['chamadas'],0)
        self.assertFalse(self.audit.exists())

    def test_principal_pdf_exige_revisao_sem_esperar_provedor(self):
        self.fonte.write_text('%PDF-1.4\nfonte sem extração')
        estado, saude = self.preparar_principal()
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'REVISION_REQUIRED')
        self.assertEqual(resultado['motivo'],'contexto_insuficiente')
        self.assertEqual(resultado['metricas']['chamadas'],0)
        self.assertFalse(self.audit.exists())

    def test_principal_politica_invalida_exige_revisao(self):
        estado, saude = self.preparar_principal()
        with patch.dict(os.environ,JANGADA_CODEX_COTA_MIN='inválido'):
            resultado=self.principal(estado,saude)
        self.assertEqual(resultado['status'],'REVISION_REQUIRED')
        self.assertEqual(resultado['motivo'],'politica_invalida')
        self.assertEqual(resultado['metricas']['chamadas'],0)
        self.assertFalse(self.audit.exists())

    def test_principal_binario_ausente_aguarda_provedor(self):
        estado, saude = self.preparar_principal()
        with patch.dict(os.environ,PATH=str(self.pasta / 'bin-vazio')):
            resultado=self.principal(estado,saude)
        self.assertEqual(resultado['status'],'WAITING_PROVIDER')
        self.assertEqual(resultado['metricas']['chamadas'],0)
        self.assertFalse(self.audit.exists())

    def test_principal_fonte_alterada_durante_chamada_preserva_relatorio(self):
        estado, saude = self.preparar_principal()
        self.stub_worker('mudou',modelo='modelo-principal-teste')
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'REVISION_REQUIRED')
        self.assertEqual(resultado['metricas']['chamadas'],1)
        self.assertTrue(estado.listar()[0]['artefato'])

    def test_principal_dependencia_trocada_durante_chamada_preserva_relatorio(self):
        from estado import Estado
        from saude import Saude
        inicial, _ = self.preparar_principal()
        tarefa=inicial.listar()[0]['especificacao']
        estado=Estado(self.pasta / 'dependencias')
        self.addCleanup(estado.fechar)
        estado.importar([{**tarefa,'id':'D1'},{**tarefa,'dependencias':['D1']}])
        _, dono, _ = estado.reservar_principal('D1','codex')
        estado.finalizar('D1',dono,'REVIEW_REQUIRED',{'execucao_iniciada':True,
                         'metricas':{'chamadas':1,'segundos':0}},f'Regra documentada: {self.fonte}:1')
        estado.revisar('D1','conferido separadamente',True)
        self.stub_worker('mudou_dependencia',modelo='modelo-principal-teste')
        resultado=self.principal(estado,Saude(estado))
        self.assertEqual(resultado['status'],'REVISION_REQUIRED')
        self.assertIn('artefato adulterado',resultado['motivo'])
        self.assertTrue(next(t for t in estado.listar() if t['id']=='P1')['artefato'])

    def test_principal_requisito_ausente_preserva_saida_reprovada(self):
        estado, saude = self.preparar_principal(requisitos=['Conclusão'])
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'REVISION_REQUIRED',resultado)
        self.assertEqual(estado.consumo('P1')['chamadas'],1)
        self.assertTrue(estado.listar()[0]['artefato'])

    def test_principal_timeout_registra_chamada_e_limpa_credenciais(self):
        estado, saude = self.preparar_principal(tempo_total=1)
        self.stub_worker('demorado',modelo='modelo-principal-teste')
        resultado = self.principal(estado,saude)
        self.assertEqual(resultado['status'],'REVISION_REQUIRED')
        self.assertEqual(estado.consumo('P1')['chamadas'],1)
        self.assertFalse(pathlib.Path(json.loads(self.audit.read_text())['casa']).exists())

    def test_principal_interrupcao_limpa_credenciais_e_exige_revisao(self):
        estado, saude = self.preparar_principal()
        self.stub_worker('demorado',modelo='modelo-principal-teste')
        from processos import Processo
        criar=Processo

        def interromper(*args,**kwargs):
            processo=criar(*args,**kwargs)
            comunicar=processo.communicate
            primeira=True

            def comunicacao(*args,**kwargs):
                nonlocal primeira
                if primeira:
                    primeira=False
                    processo.stdin.write(args[0])
                    processo.stdin.close()
                    processo.stdin=None
                    prazo=time.monotonic()+3
                    while not self.audit.exists() and time.monotonic()<prazo:
                        time.sleep(0.01)
                    raise KeyboardInterrupt
                return comunicar(*args,**kwargs)

            processo.communicate=comunicacao
            return processo

        with patch('principal.Processo',side_effect=interromper):
            with self.assertRaises(KeyboardInterrupt):
                self.principal(estado,saude)
        self.assertEqual(estado.listar()[0]['status'],'REVISION_REQUIRED')
        self.assertIsNone(estado.consumo('P1')['chamadas'])
        self.assertFalse(pathlib.Path(json.loads(self.audit.read_text())['casa']).exists())

    def test_cli_principal_exige_autorizacoes_e_usa_adapter_real_simulado(self):
        estado, _ = self.preparar_principal()
        plano=self.pasta / 'plano-principal.json'
        plano.write_text(json.dumps([estado.listar()[0]['especificacao']]))
        comando=[sys.executable,str(self.raiz / 'orquestracao/cli.py')]
        importar=subprocess.run(comando+['fila','--projeto',str(self.pasta),'--importar',str(plano)],
                                capture_output=True,text=True,timeout=10)
        self.assertEqual(importar.returncode,0,importar.stderr)
        args=['task','P1','executar-principal','--projeto',str(self.pasta),'--executor','codex']
        recusado=subprocess.run(comando+args,capture_output=True,text=True,timeout=10)
        self.assertEqual(recusado.returncode,2)
        for extras in (['--modelo','indevido'],['--dono','indevido'],['--arquivo',str(plano)],
                       ['--aprovar'],['--parecer','indevido']):
            with self.subTest(extras=extras):
                recusado=subprocess.run(comando+args+['--permitir-remoto','--permitir-codex']+extras,
                                        capture_output=True,text=True,timeout=10)
                self.assertEqual(recusado.returncode,2)
        for acao in ('pausar','retomar','cancelar','assumir'):
            for opcao in ('--permitir-remoto','--permitir-codex'):
                with self.subTest(acao=acao,opcao=opcao):
                    recusado=subprocess.run(comando+['task','P1',acao,'--projeto',str(self.pasta),opcao],
                                            capture_output=True,text=True,timeout=10)
                    self.assertEqual(recusado.returncode,2)
        resultado=subprocess.run(comando+args+['--permitir-remoto','--permitir-codex'],
                                 capture_output=True,text=True,timeout=10)
        self.assertEqual(resultado.returncode,0,resultado.stderr)
        self.assertEqual(json.loads(resultado.stdout)['status'],'REVIEW_REQUIRED')

    def test_supervisor_codex_documental_sem_ferramentas_e_local_proibido(self):
        self.stub_worker('parecer')
        resultado = self.delegar(('--permitir-remoto', '--permitir-codex'), candidato=True, papel='supervisor')
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(json.loads(resultado.stdout)['destino'], 'codex-economico')
        registro = json.loads(resultado.stdout)
        self.assertEqual(json.loads(pathlib.Path(registro['artefato']).read_text())['decisao'], 'APPROVED')
        resultado = self.delegar(('--destino', 'local'), papel='supervisor')
        self.assertEqual(resultado.returncode, 4, resultado.stderr)

    def test_pipeline_real_codex_autor_agy_supervisor_com_modelos_simulados(self):
        from estado import Estado
        from executor import executar

        (self.config / 'delegacao.json').write_text(json.dumps({'analise_documental': ['codex-economico', 'agy']}))
        casa = self.pasta / 'home'
        configuracao = casa / '.gemini/antigravity-cli'
        configuracao.mkdir(parents=True)
        (configuracao / 'settings.json').write_text(json.dumps({'trustedWorkspaces':[str(self.pasta)]}))
        self.programa(self.bin / 'agy', '''import json,sys
if sys.argv[1]=='agents':
    print('supervisor');sys.exit(0)
if sys.argv[2]=='/usage':
    print(json.dumps({'status':'SUCCESS','response':'','command':{'name':'usage','data':{'groups':[
        {'name':'Gemini Models','buckets':[{'id':'gemini-5h','remaining_fraction':0.9}]}]}}}));sys.exit(0)
pedido=sys.argv[sys.argv.index('-p')+1]
vinculo=json.loads(next(l for l in pedido.splitlines() if l.startswith('{"task_id":')))
fontes=[l.split(':N (texto);')[0] for l in pedido.splitlines() if ':N (texto);' in l]
justificativa='Informações conferidas e coerentes com as fontes: '+', '.join(f'{f}:1' for f in fontes)
parecer={'task_id':vinculo['task_id'],'relatorio_sha256':vinculo['relatorio_sha256'],'decisao':'APPROVED',
         'criterios':{c:{'resultado':'PASS','justificativa':justificativa} for c in
                     ('fidelidade','completude','extrapolacoes')},'observacoes':[]}
print(json.dumps({'status':'SUCCESS','conversation_id':'sup','response':json.dumps(parecer)}))
''')
        estado = Estado(self.pasta / 'execucao')
        self.addCleanup(estado.fechar)
        estado.importar([{'id':'S1','pedido':'Resuma a regra','papel':'leitor','capacidade':'analise_documental',
                          'risco':1,'qualidade':'medium','fontes':[str(self.fonte)],
                          'hashes_fontes':{str(self.fonte):hashlib.sha256(self.fonte.read_bytes()).hexdigest()},
                          'intermediaria':True,'supervisao_automatica':True,'permitir_remoto':True,'permitir_codex':True}])
        with patch.dict(os.environ, HOME=str(casa), JANGADA_DELEGAR_IMPEDIMENTOS='[]'):
            resultado = executar(estado,self.pasta,self.raiz,permitir_remoto=True,
                                 permitir_codex=True,supervisao_automatica=True)[0]
        self.assertEqual(resultado['status'],'COMPLETED',resultado)
        self.assertEqual(resultado['delegacao']['destino'],'codex-economico')
        self.assertEqual(resultado['supervisao']['executor'],'agy')
        self.assertEqual(resultado['metricas']['chamadas'],2)

    def test_modelo_ausente_ou_invalido_nao_escolhe_padrao(self):
        for modelo in ('', 'modelo com espaços', '--premium'):
            with self.subTest(modelo=modelo), patch.dict(os.environ, JANGADA_CODEX_ECONOMICO_MODELO=modelo):
                resultado = self.executar()
                self.assertEqual(resultado['motivo_codigo'], 'modelo_ausente')
                self.assertEqual(resultado['chamadas'], 0)
        self.assertFalse(self.audit.exists())

    def test_cota_baixa_esgotada_ou_desconhecida_nao_gera(self):
        for usado in (80, 100):
            self.stub_cota(usado)
            self.assertEqual(self.executar()['motivo_codigo'], 'cota_insuficiente')
        with patch.object(WORKER, 'consultar', side_effect=ValueError):
            resultado = self.executar()
            self.assertEqual(resultado['motivo_codigo'], 'cota_desconhecida')
            self.assertEqual(resultado['chamadas'], 0)
        self.assertFalse(self.audit.exists())

    def test_binario_e_contexto_grande_sao_recusados_sem_transmitir(self):
        for conteudo in (b'\x00PDF', b'%PDF-1.4\nobjeto', b'\xff', b'x' * 80001):
            self.fonte.write_bytes(conteudo)
            self.assertEqual(self.executar()['motivo_codigo'], 'contexto_insuficiente')
        self.assertFalse(self.audit.exists())

    def test_erro_conclusao_ausente_duplicada_e_saida_grande_nao_aprovam(self):
        for modo, esperado in (('erro', 'erro_execucao'), ('sem-completo', 'saida_invalida'),
                               ('duplicado', 'saida_invalida'), ('gigante', 'saida_invalida'),
                               ('json-invalido', 'saida_invalida')):
            with self.subTest(modo=modo):
                self.stub_worker(modo)
                resultado = self.executar()
                self.assertEqual(resultado['motivo_codigo'], esperado)
                self.assertEqual(resultado['chamadas'], 1)

    def test_tempo_limita_geracao(self):
        self.stub_worker('demorado')
        resultado = self.executar(1)
        self.assertEqual(resultado['motivo_codigo'], 'limite_tempo')
        self.assertEqual(resultado['chamadas'], 1)
        self.assertEqual(list(self.pasta.glob('.cota-codex-*')), [])
        self.assertEqual(list((self.runtime / 'jangada-credenciais').glob('.cota-codex-*')), [])

    def test_fallback_agy_esgotado_codex_configurado_sem_premium(self):
        resposta = self.delegar(['--permitir-remoto', '--permitir-codex'])
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        dados = json.loads(resposta.stdout)
        self.assertEqual(dados['destino'], 'codex-economico')
        self.assertEqual(dados['modelo'], 'modelo-economico-teste')
        self.assertEqual(dados['tentativas'][0]['motivo_codigo'], 'cota_indisponivel')
        self.assertEqual(dados['verificacao'], 'referencias_validas')
        self.assertEqual(dados['tokens_codex_entrada'], 10)
        self.assertFalse(dados['ferramentas_disponiveis'])

    def test_cada_permissao_e_perfil_local_barram_codex(self):
        for extras in ([], ['--permitir-remoto'], ['--permitir-codex']):
            with self.subTest(extras=extras):
                resposta = self.delegar(extras, candidato=True)
                self.assertEqual(resposta.returncode, 4, resposta.stderr)
        with patch.dict(os.environ, JANGADA_DELEGAR='local'):
            self.assertEqual(self.delegar(['--permitir-remoto', '--permitir-codex'], candidato=True).returncode, 4)
        self.assertFalse(self.audit.exists())

    def test_sem_fontes_na_saida_gate_reprova_e_preserva_relatorio(self):
        self.stub_worker('sem-fonte')
        resposta = self.delegar(['--permitir-remoto', '--permitir-codex'], candidato=True)
        self.assertEqual(resposta.returncode, 4, resposta.stderr)
        dados = json.loads(resposta.stdout)
        self.assertEqual(dados['tentativas'][0]['motivo_codigo'], 'saida_invalida')
        preservados = list((self.pasta / 'state/jangada/agentes').glob('delegacao-reprovada-*'))
        self.assertEqual(len(preservados), 1)
        self.assertEqual(preservados[0].read_text().strip(), 'Texto sem referência.')

    def test_previa_curta_preserva_artefato_conferido_completo(self):
        with patch.dict(os.environ, JANGADA_DELEGAR_PALAVRAS='5'):
            resposta = self.delegar(['--permitir-remoto', '--permitir-codex'], candidato=True)
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        dados = json.loads(resposta.stdout)
        self.assertTrue(dados['relatorio_cortado'])
        self.assertIn('relatório cortado', dados['relatorio'])
        self.assertIn(str(self.fonte) + ':1', pathlib.Path(dados['artefato']).read_text())

    def test_sem_capacidade_codex_e_recusado(self):
        resposta = subprocess.run([str(self.raiz / 'bin/jangada-delegar'), 'leitor', 'Leia',
                                   '--destino', 'codex-economico'], capture_output=True, text=True, timeout=10)
        self.assertEqual(resposta.returncode, 2)
        self.assertFalse(self.audit.exists())

    def test_executor_ocupado_nao_consulta_nem_gera(self):
        pasta = self.pasta / 'state/jangada/agentes'
        pasta.mkdir(parents=True)
        with (pasta / 'codex-economico.lock').open('w') as trava:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
            resposta = self.delegar(['--permitir-remoto', '--permitir-codex'], candidato=True)
        self.assertEqual(resposta.returncode, 4, resposta.stderr)
        self.assertEqual(json.loads(resposta.stdout)['tentativas'][0]['motivo_codigo'], 'ocupado')
        self.assertFalse(self.audit.exists())

    def interromper_geracao(self, matar_shell):
        self.stub_worker('demorado')
        args = [str(self.raiz / 'bin/jangada-delegar'), '--capacidade', 'analise_documental', '--json',
                '--permitir-remoto', '--permitir-codex', '--arquivos', str(self.fonte), '--', 'leitor', 'Leia']
        pai = subprocess.Popen(args, cwd=self.pasta, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        dados = None
        try:
            limite = time.monotonic() + 5
            while time.monotonic() < limite:
                try:
                    dados = json.loads(self.audit.read_text())
                    break
                except (OSError, ValueError):
                    time.sleep(0.01)
            self.assertIsNotNone(dados)
            if matar_shell:
                self.assertNotEqual(dados['bash'], dados['worker'])
                comando = (pathlib.Path('/proc') / str(dados['bash']) / 'cmdline').read_bytes().split(b'\x00')
                self.assertEqual(pathlib.Path(os.fsdecode(comando[0])).name, 'bash')
                self.assertIn(os.fsencode(str(self.raiz / 'bin/jangada-delegar')), comando)
                self.assertIsNone(pai.poll())
                os.kill(dados['bash'], 9)
            else:
                pai.kill()
            pai.communicate(timeout=5)
            limite = time.monotonic() + 5
            proc = pathlib.Path('/proc') / str(dados['pid']) / 'stat'
            while time.monotonic() < limite:
                try:
                    encerrado = proc.read_text().split(') ')[1].startswith('Z')
                except (FileNotFoundError, ProcessLookupError):
                    encerrado = True
                if encerrado and not pathlib.Path(dados['casa']).exists():
                    break
                time.sleep(0.01)
            self.assertTrue(encerrado)
            self.assertFalse(pathlib.Path(dados['casa']).exists())
        finally:
            if pai.poll() is None:
                pai.kill()
            pai.communicate(timeout=5)
            # O jangada-delegar filho sobrevive ao orquestrador morto e ainda grava
            # delegacoes.jsonl: sem esta espera, a limpeza da pasta corre contra ele.
            marca = os.fsencode(str(self.pasta))
            limite = time.monotonic() + 5
            while time.monotonic() < limite and any(self.linha_de_comando(p).find(marca) >= 0
                                                    for p in pathlib.Path('/proc').glob('[0-9]*')):
                time.sleep(0.01)

    @staticmethod
    def linha_de_comando(proc):
        try:
            return (proc / 'cmdline').read_bytes()
        except OSError:
            return b''

    def test_queda_do_orquestrador_encerra_geracao_e_remove_credenciais(self):
        self.interromper_geracao(False)

    def test_kill_no_shell_filho_encerra_geracao_com_orquestrador_vivo(self):
        self.interromper_geracao(True)

    def test_cli_atualiza_cota_codex_com_perfil_remoto_padrao(self):
        self.programa(self.bin / 'agy', 'import json\nprint(json.dumps({"command":{"data":{"groups":[{"buckets":[{"id":"gemini-5h","remaining_fraction":0.5}]}]}}}))\n')
        for perfil in ('', None):
            ambiente = os.environ.copy()
            ambiente['JANGADA_OLLAMA_URL'] = 'url-invalida'
            ambiente['XDG_STATE_HOME'] = str(self.pasta / ('state-vazio' if perfil == '' else 'state-ausente'))
            if perfil is None:
                ambiente.pop('JANGADA_DELEGAR', None)
            else:
                ambiente['JANGADA_DELEGAR'] = perfil
            resultado = subprocess.run([str(self.raiz / 'bin/jangada-retomar'), '--projeto', str(self.pasta),
                                        '--atualizar', '--permitir-remoto', '--permitir-codex'],
                                       env=ambiente, capture_output=True, text=True, timeout=20)
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            status = subprocess.run([str(self.raiz / 'bin/jangada-router'), 'status'], env=ambiente,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(status.returncode, 0, status.stderr)
            item = next(p for p in json.loads(status.stdout)['provedores'] if p['id'] == 'codex')
            self.assertEqual(item['status'], 'AVAILABLE')
            self.assertEqual(item['cota'], 80)



if __name__ == '__main__':
    import isolamento
    isolamento.instalar()
    unittest.main()
