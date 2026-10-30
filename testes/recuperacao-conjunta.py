#!/usr/bin/env python3
"""Matriz de recuperação conjunta pelos comandos reais, com sessão vizinha ativa.

Cada cenário (término normal, erro do cliente, tempo esgotado, cancelamento
por SIGINT, SIGTERM e SIGKILL do controlador) roda o jangada-executar num
projeto com um delegado simulado, enquanto outro projeto executa ao lado. Depois
confere descendentes, estado da tarefa, artefato confirmado, temporários e a
sessão vizinha, recupera duas vezes e exige o mesmo resultado, e roda o
executor de novo para provar que a retomada não repete a chamada nem aprova.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import unittest

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_executor', RAIZ / 'testes/executor.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
sys.path.insert(0, str(RAIZ / 'orquestracao'))
from projetos import chave

ERRO = "modo = os.environ.get('MODO_TESTE', 'ok')\n"
SIMULADO = fixture.SIMULADO.replace(ERRO, ERRO + (
    "if modo == 'erro':\n"
    "    print('falha simulada do cliente', file=sys.stderr)\n"
    "    sys.exit(1)\n"), 1)
assert SIMULADO != fixture.SIMULADO

# cenário: (modo do delegado, campos da tarefa, sinal ao controlador, status esperado)
MATRIZ = {
    'normal': ('ok', {}, None, 'REVIEW_REQUIRED'),
    'erro_cliente': ('erro', {}, None, 'REVISION_REQUIRED'),
    'tempo_esgotado': ('demorado', {'tempo_total': 1}, None, 'REVISION_REQUIRED'),
    'cancelamento': ('demorado', {}, signal.SIGINT, 'REVISION_REQUIRED'),
    'sigterm': ('demorado', {}, signal.SIGTERM, 'REVISION_REQUIRED'),
    'sigkill': ('demorado', {}, signal.SIGKILL, 'REVISION_REQUIRED'),
}


class RecuperacaoConjunta(unittest.TestCase):
    setUp_base = fixture.Execucao.setUp
    tarefa = fixture.Execucao.tarefa

    def setUp(self):
        self.setUp_base()
        (self.raiz / 'bin/jangada-delegar').write_text(SIMULADO, encoding='utf-8')
        shutil.copytree(RAIZ / 'orquestracao', self.raiz / 'orquestracao')
        shutil.copytree(RAIZ / 'nucleo', self.raiz / 'nucleo')
        shutil.copyfile(RAIZ / 'delegacao/roteamento.json', self.raiz / 'delegacao/roteamento.json')
        self.estado_cli = self.pasta / 'estado-cli'
        self.base = dict(os.environ, JANGADA_CORE_PATH=str(self.raiz), XDG_STATE_HOME=str(self.estado_cli),
                         XDG_CONFIG_HOME=str(self.pasta / 'config-cli'))
        self.processos = []
        self.addCleanup(self.matar_tudo)

    def matar_tudo(self):
        for pid in self.processos:
            for matar in (os.killpg, os.kill):
                try:
                    matar(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass

    def comando(self, projeto, *argumentos, ambiente=None, timeout=30):
        return subprocess.run([str(RAIZ / 'bin' / argumentos[0]), *argumentos[1:]], cwd=projeto,
                              env=ambiente or self.base, text=True, capture_output=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)

    def pasta_estado(self, projeto):
        return self.estado_cli / 'jangada/agentes/projetos' / chave(projeto)

    def esperar(self, condicao, limite=8):
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            if condicao():
                return True
            time.sleep(0.02)
        return condicao()

    def novo_projeto(self, nome):
        projeto = self.pasta / nome
        projeto.mkdir()
        fonte = projeto / 'fonte.md'
        fonte.write_text(f'regra de {nome}', encoding='utf-8')
        return projeto, fonte

    def tarefa_de(self, fonte, identificador='T1', **campos):
        return dict(self.tarefa(identificador, **campos), fontes=[str(fonte)],
                    hashes_fontes={str(fonte): hashlib.sha256(fonte.read_bytes()).hexdigest()})

    def importar(self, projeto, tarefas):
        plano = projeto / 'plano.json'
        plano.write_text(json.dumps(tarefas), encoding='utf-8')
        resposta = self.comando(projeto, 'jangada-fila', '--importar', str(plano))
        self.assertEqual(resposta.returncode, 0, resposta.stderr)

    def iniciar_vizinho(self):
        """Outra sessão: projeto próprio, controlador e delegado vivos durante o cenário."""
        projeto, fonte = self.novo_projeto('vizinho')
        self.importar(projeto, [self.tarefa_de(fonte)])
        registro = self.pasta / 'vizinho.json'
        ambiente = dict(self.base, MODO_TESTE='demorado', REGISTRO_TESTE=str(registro))
        controlador = subprocess.Popen([str(RAIZ / 'bin/jangada-executar'), '--perfil', 'offline'], cwd=projeto,
                                       env=ambiente, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
        self.processos.append(controlador.pid)
        self.addCleanup(lambda: controlador.poll() is None and controlador.kill() or controlador.wait(timeout=5))
        filho = Path(str(registro) + '.filho')
        self.assertTrue(self.esperar(filho.exists), 'delegado vizinho não iniciou')
        delegado = int(Path(str(registro) + '.delegado').read_text())
        descendente = int(filho.read_text())
        self.processos += [delegado, descendente]
        return {'projeto': projeto, 'controlador': controlador, 'pids': (delegado, descendente),
                'temporarios': sorted(p.name for p in self.pasta_estado(projeto).glob('execucao-*'))}

    def foto(self, projeto):
        """Estado observável da recuperação: tarefas pela CLI, eventos e execuções no banco."""
        resposta = self.comando(projeto, 'jangada-fila', '--json')
        self.assertEqual(resposta.returncode, 0, resposta.stderr)
        tarefas = json.loads(resposta.stdout)['tarefas']
        banco = sqlite3.connect(f'file:{self.pasta_estado(projeto) / "tarefas.sqlite"}?mode=ro', uri=True)
        try:
            eventos = banco.execute('SELECT tarefa,evento FROM eventos ORDER BY seq').fetchall()
            execucoes = banco.execute('SELECT status,chamadas,fim IS NOT NULL FROM execucoes ORDER BY inicio').fetchall()
            integridade = banco.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            banco.close()
        return tarefas, eventos, execucoes, integridade

    def dados_evento(self, projeto, evento):
        banco = sqlite3.connect(f'file:{self.pasta_estado(projeto) / "tarefas.sqlite"}?mode=ro', uri=True)
        try:
            return banco.execute('SELECT dados FROM eventos WHERE evento=?', (evento,)).fetchone()[0]
        finally:
            banco.close()

    def cenario(self, nome):
        modo, campos, sinal, esperado = MATRIZ[nome]
        vizinho = self.iniciar_vizinho()
        projeto, fonte = self.novo_projeto('projeto-' + nome)
        self.importar(projeto, [self.tarefa_de(fonte, **campos)])
        registro = self.pasta / f'{nome}.json'
        ambiente = dict(self.base, MODO_TESTE=modo, REGISTRO_TESTE=str(registro))
        controlador = subprocess.Popen([str(RAIZ / 'bin/jangada-executar'), '--perfil', 'offline'], cwd=projeto,
                                       env=ambiente, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.processos.append(controlador.pid)
        pids = []
        if modo == 'demorado':
            filho = Path(str(registro) + '.filho')
            self.assertTrue(self.esperar(filho.exists), 'delegado não iniciou')
            pids = [int(Path(str(registro) + '.delegado').read_text()), int(filho.read_text())]
            self.processos += pids
        if sinal is not None:
            controlador.send_signal(sinal)
        _, erro = controlador.communicate(timeout=15)
        if sinal is None:
            self.assertIn(controlador.returncode, (0, 1), erro)
        elif sinal == signal.SIGKILL:
            self.assertEqual(controlador.returncode, -signal.SIGKILL)
        else:
            self.assertEqual(controlador.returncode, 130, erro)

        # Descendentes: o delegado e o neto dele não sobrevivem ao controlador.
        self.assertTrue(self.esperar(lambda: not any(fixture.processo_vivo(p) for p in pids), 5),
                        f'descendentes vivos: {[p for p in pids if fixture.processo_vivo(p)]}')

        # Primeira e segunda recuperação: o mesmo resultado.
        primeira = self.foto(projeto)
        segunda = self.foto(projeto)
        self.assertEqual(primeira, segunda, 'a segunda recuperação alterou o resultado')
        tarefas, eventos, execucoes, integridade = primeira
        self.assertEqual(integridade, 'ok')
        self.assertEqual([t['status'] for t in tarefas], [esperado], erro)
        tarefa = tarefas[0]
        self.assertEqual(len(execucoes), 1)
        self.assertTrue(execucoes[0][2], 'execução sem fim registrado')
        if esperado == 'REVIEW_REQUIRED':
            # Artefato confirmado: íntegro e legível pelo hash, sem aprovação automática.
            artefato = self.pasta_estado(projeto) / 'artefatos' / f'{tarefa["artefato"]}.txt'
            self.assertEqual(hashlib.sha256(artefato.read_bytes()).hexdigest(), tarefa['artefato'])
            self.assertIn(str(fonte), artefato.read_text(encoding='utf-8'))
            self.assertEqual(execucoes[0][1], 1)
        else:
            # Consumo desconhecido continua desconhecido; nada inventado.
            self.assertIsNone(execucoes[0][1])
            self.assertIsNone(((tarefa['resultado'] or {}).get('metricas') or {}).get('chamadas'))
        self.assertEqual(sum(1 for _, e in eventos if e == 'reserva_expirada'),
                         1 if sinal == signal.SIGKILL else 0)

        # Temporários: só o SIGKILL deixa a pasta de trabalho e a trava, preservadas
        # para conferência (docs/subagentes-e-delegacao.md) e ligadas pelo nome à
        # reserva expirada; a segunda recuperação não as altera.
        estado = self.pasta_estado(projeto)
        sobras = sorted(p.name for p in estado.glob('execucao-*'))
        travas = sorted(p.name for p in (estado / 'reservas').iterdir())
        if sinal == signal.SIGKILL:
            expirada = json.loads(self.dados_evento(projeto, 'reserva_expirada'))['dono']
            self.assertEqual(travas, [expirada])
            self.assertEqual(len(sobras), 1)
            self.assertTrue(sobras[0].startswith(f'execucao-{expirada}-'), sobras)
            conteudo = sorted(p.name for p in (estado / sobras[0]).iterdir())
        else:
            self.assertEqual((sobras, travas), ([], []))

        # Retomada: rodar de novo não chama o delegado nem aprova.
        registro.unlink(missing_ok=True)
        retomada = self.comando(projeto, 'jangada-executar', '--perfil', 'offline', ambiente=ambiente)
        self.assertEqual(retomada.returncode, 0, retomada.stderr)
        self.assertFalse(registro.exists(), 'a retomada repetiu a chamada ao delegado')
        self.assertEqual(self.foto(projeto), primeira, 'a retomada alterou o resultado recuperado')
        self.assertEqual(sorted(p.name for p in estado.glob('execucao-*')), sobras)
        if sinal == signal.SIGKILL:
            self.assertEqual(sorted(p.name for p in (estado / sobras[0]).iterdir()), conteudo)

        # Sessão vizinha: controlador, delegado, neto, tarefa e temporário intactos.
        self.assertIsNone(vizinho['controlador'].poll(), 'controlador vizinho encerrado')
        for pid in vizinho['pids']:
            self.assertTrue(fixture.processo_vivo(pid), f'processo vizinho {pid} encerrado')
        self.assertEqual([t['status'] for t in self.foto(vizinho['projeto'])[0]], ['RUNNING'])
        self.assertEqual(sorted(p.name for p in self.pasta_estado(vizinho['projeto']).glob('execucao-*')),
                         vizinho['temporarios'])
        self.assertTrue(vizinho['temporarios'], 'o vizinho deveria ter temporário de execução ativo')


for _nome in MATRIZ:
    setattr(RecuperacaoConjunta, f'test_{_nome}', lambda self, n=_nome: self.cenario(n))


if __name__ == '__main__':
    unittest.main()
