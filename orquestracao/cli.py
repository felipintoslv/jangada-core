"""Comandos da fila do jangada. Os arquivos de plano contêm somente dados."""

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys

sys.dont_write_bytecode = True
from estado import Estado
from executor import executar, assumir_principal, entregar_principal
from acompanhamento import acompanhar
from metricas_projeto import identidade, ler_precos, resumir
from saude import Saude, retomar
from principal import executar_principal
from projetos import cadastrar, chave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from nucleo.roteamento import decidir, MODOS


def interromper_execucao(*_):
    # O delegado tem sessão própria; o sinal deve passar pela limpeza do
    # executor também no modo sequencial, antes de o controlador sair.
    raise KeyboardInterrupt


def especificacoes(caminho, projeto):
    tarefas = json.loads(pathlib.Path(caminho).read_text(encoding='utf-8'))
    if not isinstance(tarefas, list):
        raise ValueError('plano deve ser uma lista de tarefas')
    resultado = []
    for original in tarefas:
        if not isinstance(original, dict) or not isinstance(original.get('fontes'), list):
            raise ValueError('tarefa deve informar fontes')
        tarefa = dict(original)

        def resolver(nome):
            if not isinstance(nome, str):
                raise ValueError('fonte deve ser um caminho')
            fonte = (projeto / nome).resolve()
            if not fonte.is_relative_to(projeto) or not fonte.is_file():
                raise ValueError(f'fonte ausente ou fora do projeto: {nome}')
            return str(fonte), hashlib.sha256(fonte.read_bytes()).hexdigest()

        contexto = tarefa.get('contexto', [])
        if not isinstance(contexto, list):
            raise ValueError('contexto deve ser lista de caminhos')
        if any(not isinstance(nome, str) for nome in [*tarefa['fontes'], *contexto]):
            raise ValueError('fontes e contexto devem conter caminhos em texto')
        fontes = [resolver(nome) for nome in dict.fromkeys([*tarefa['fontes'], *contexto])]
        tarefa['fontes'] = [nome for nome, _ in fontes]
        if contexto:
            tarefa['contexto'] = [resolver(nome)[0] for nome in contexto]
        tarefa['hashes_fontes'] = dict(fontes)
        if 'esquema' in tarefa:
            tarefa['esquema'], tarefa['hash_esquema'] = resolver(tarefa['esquema'])
        resultado.append(tarefa)
    return resultado


def executar_em_paralelo(args, projeto):
    """Divide o limite entre processos; cada um reserva tarefas diferentes na mesma fila."""
    comando = [sys.executable, __file__, 'executar', '--projeto', str(projeto), '--perfil', args.perfil,
               '--permitir-remoto', *(opcao for opcao, ativa in (('--permitir-codex', args.permitir_codex),
                                                                ('--supervisionar', args.supervisionar),
                                                                ('--amostrar', args.amostrar)) if ativa)]
    partes = [args.limite // args.paralelo + (i < args.limite % args.paralelo) for i in range(args.paralelo)]
    # Sessão própria: o Ctrl+C do terminal chega só a este processo, que o repassa uma vez a cada filho.
    # Término e fechamento do terminal seguem o mesmo caminho, para não deixar filhos chamando provedores.
    processos = []
    leitores = concurrent.futures.ThreadPoolExecutor(len(partes))
    try:
        for parte in partes:
            processos.append(subprocess.Popen([*comando, '--limite', str(parte)], stdout=subprocess.PIPE, text=True,
                                              start_new_session=True))
        saidas = list(leitores.map(lambda processo: processo.communicate()[0], processos))
    except KeyboardInterrupt:
        for processo in processos:
            if processo.poll() is None:
                processo.send_signal(signal.SIGINT)
        raise
    finally:
        leitores.shutdown()
    resultados = [item for processo, saida in zip(processos, saidas) if processo.returncode == 0
                  for item in json.loads(saida)['resultados']]
    falhas = sum(processo.returncode != 0 for processo in processos)
    if falhas:
        print(json.dumps({'projeto': str(projeto), 'retomadas': [], 'resultados': resultados}, ensure_ascii=False))
        raise ValueError(f'{falhas} processo(s) paralelo(s) falharam; consulte a fila antes de repetir')
    return resultados


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest='comando', required=True)
    fila = comandos.add_parser('fila', help='inspeciona ou importa tarefas')
    fila.add_argument('--projeto', type=pathlib.Path)
    consulta = fila.add_mutually_exclusive_group()
    consulta.add_argument('--importar', type=pathlib.Path)
    consulta.add_argument('--metricas', action='store_true')
    consulta.add_argument('--revisao', action='store_true')
    fila.add_argument('--json', action='store_true')
    execucao = comandos.add_parser('executar', help='executa tarefas elegíveis sem aprová-las')
    execucao.add_argument('--projeto', type=pathlib.Path)
    execucao.add_argument('--perfil', choices=['balanced', 'quality', 'offline'], default='balanced')
    execucao.add_argument('--limite', type=int)
    execucao.add_argument('--acompanhar', action='store_true')
    execucao.add_argument('--intervalo', type=int)
    execucao.add_argument('--duracao', type=int)
    execucao.add_argument('--permitir-remoto', action='store_true')
    execucao.add_argument('--permitir-codex', action='store_true')
    execucao.add_argument('--supervisionar', action='store_true')
    execucao.add_argument('--amostrar', action='store_true')
    execucao.add_argument('--paralelo', type=int, default=1)
    execucao.add_argument('--tarefa')
    execucao.add_argument('--modo', choices=MODOS)
    execucao.add_argument('--executor', choices=['local', 'agy', 'codex-economico'])
    execucao.add_argument('--confirmar', action='store_true')
    retomada = comandos.add_parser('retomar', help='retoma esperas com provedor disponível')
    retomada.add_argument('--projeto', type=pathlib.Path)
    retomada.add_argument('--perfil', choices=['balanced', 'quality', 'offline'], default='balanced')
    retomada.add_argument('--permitir-remoto', action='store_true')
    retomada.add_argument('--permitir-codex', action='store_true')
    retomada.add_argument('--supervisionar', action='store_true')
    retomada.add_argument('--amostrar', action='store_true')
    retomada.add_argument('--atualizar', action='store_true')
    retomada.add_argument('--executar', action='store_true')
    retomada.add_argument('--limite', type=int, default=1)
    router = comandos.add_parser('router', help='consulta provedores de todos os projetos')
    router.add_argument('acao', choices=['status', 'cotas'])
    router.add_argument('--atualizar', action='store_true')
    router.add_argument('--atualizar-codex', action='store_true')
    router.add_argument('--permitir-remoto', action='store_true')
    provedor = comandos.add_parser('provedor', help='pausa ou ativa um provedor')
    provedor.add_argument('acao', choices=['pausar', 'ativar'])
    provedor.add_argument('id')
    tarefa = comandos.add_parser('task', help='gerencia tarefas e entregas das sessões principais')
    tarefa.add_argument('--projeto', type=pathlib.Path)
    tarefa.add_argument('id')
    tarefa.add_argument('acao', choices=['pausar', 'retomar', 'cancelar', 'repetir', 'revisar', 'assumir', 'entregar', 'executar-principal'])
    tarefa.add_argument('--executor', choices=['claude', 'codex'])
    tarefa.add_argument('--modelo')
    tarefa.add_argument('--dono')
    tarefa.add_argument('--arquivo', type=pathlib.Path)
    tarefa.add_argument('--parecer')
    tarefa.add_argument('--revisor', choices=['humano', 'claude', 'codex', 'agy'], default='humano')
    tarefa.add_argument('--modelo-revisor')
    tarefa.add_argument('--contexto-revisao', choices=['diff', 'repositorio'], default='repositorio')
    tarefa.add_argument('--modo', choices=['manual', 'assistido'], default='manual')
    tarefa.add_argument('--confirmar', action='store_true')
    tarefa.add_argument('--permitir-remoto', action='store_true')
    tarefa.add_argument('--permitir-codex', action='store_true')
    decisao = tarefa.add_mutually_exclusive_group()
    decisao.add_argument('--aprovar', action='store_true')
    decisao.add_argument('--reprovar', action='store_true')
    args = parser.parse_args()
    if args.comando == 'task':
        if args.acao != 'revisar' and (args.revisor != 'humano' or args.modelo_revisor or args.contexto_revisao != 'repositorio'):
            parser.error('identidade de revisão exige revisar')
        if args.acao != 'assumir' and (args.modo != 'manual' or args.confirmar):
            parser.error('modo e confirmação exigem assumir')
        if args.acao != 'executar-principal' and (args.permitir_remoto or args.permitir_codex):
            parser.error('autorizações remotas exigem executar-principal')
        if args.acao == 'executar-principal':
            if (args.executor != 'codex' or not args.permitir_remoto or not args.permitir_codex
                    or args.modelo or args.dono or args.arquivo or args.parecer or args.aprovar or args.reprovar):
                parser.error('executar-principal exige --executor codex, --permitir-remoto e --permitir-codex')
        elif args.acao == 'assumir':
            if not args.executor or args.dono or args.arquivo or args.parecer or args.aprovar or args.reprovar:
                parser.error('assumir exige --executor; aceita somente --modelo como opção adicional')
        elif args.acao == 'entregar':
            if not args.dono or not args.arquivo or args.executor or args.modelo or args.parecer or args.aprovar or args.reprovar:
                parser.error('entregar exige --dono e --arquivo, sem opções de revisão')
        elif args.executor or args.modelo or args.dono or args.arquivo:
            parser.error('opções da sessão principal exigem assumir ou entregar')
    if args.comando == 'executar':
        if (args.modo or args.executor or args.confirmar or args.tarefa) and (not args.modo or not args.tarefa
                or args.acompanhar or args.paralelo != 1 or args.limite not in (None, 1)):
            parser.error('roteamento explícito exige --modo e --tarefa, limite 1, sem acompanhar ou paralelo')
        if args.modo == 'automatico_supervisionado' and (args.executor or args.confirmar):
            parser.error('modo automático não recebe escolha manual')
        if args.modo in {'manual', 'assistido'} and not args.executor:
            parser.error('modo manual ou assistido exige --executor')
        if not args.acompanhar and (args.intervalo is not None or args.duracao is not None):
            parser.error('--intervalo e --duracao exigem --acompanhar')
        args.limite = args.limite if args.limite is not None else (100 if args.acompanhar else 1)
        if (not 1 <= args.limite <= 1000
                or args.intervalo is not None and not 1 <= args.intervalo <= 3600
                or args.duracao is not None and not 1 <= args.duracao <= 86400):
            parser.error('limite, intervalo ou duração fora da faixa permitida')
        if args.paralelo != 1 and (not 2 <= args.paralelo <= 4 or args.acompanhar or not args.permitir_remoto
                                   or args.perfil == 'offline' or args.limite < args.paralelo):
            parser.error('--paralelo aceita de 2 a 4 processos, exige --permitir-remoto, perfil com nuvem '
                         'e --limite igual ou maior, e não combina com --acompanhar')
    raiz_estado = pathlib.Path(os.environ['JANGADA_ESTADO'])
    if args.comando == 'router' and args.acao == 'cotas':
        if args.atualizar_codex:
            parser.error('cotas usa --atualizar com --permitir-remoto para o Codex')
        from cotas import executar as executar_cotas
        sys.exit(executar_cotas(raiz_estado, args.atualizar, args.permitir_remoto))
    if args.comando in {'router', 'provedor'}:
        global_estado = Estado(raiz_estado / 'agentes/runtime', raiz=raiz_estado)
        try:
            saude = Saude(global_estado)
            if args.comando == 'provedor':
                saude.pausar(args.id, args.acao == 'pausar')
            elif args.atualizar:
                saude.atualizar(args.permitir_remoto)
            if args.comando == 'router' and args.atualizar_codex:
                saude.atualizar_codex(args.permitir_remoto)
            print(json.dumps({'provedores': saude.listar()}, ensure_ascii=False))
        finally:
            global_estado.fechar()
        return
    raiz = pathlib.Path(os.environ['JANGADA_CORE_PATH'])
    if args.projeto:
        projeto = args.projeto.resolve()
    else:
        git = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
                              'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=False)
        projeto = pathlib.Path(git.stdout.strip()).resolve() if git.returncode == 0 else pathlib.Path.cwd().resolve()
    if not projeto.is_dir():
        raise ValueError('projeto não existe')
    pasta = pathlib.Path(os.environ['JANGADA_ESTADO']) / 'agentes/projetos' / chave(projeto)
    estado = Estado(pasta, raiz=os.environ['JANGADA_ESTADO'])
    try:
        if args.comando != 'fila' or args.importar:
            cadastrar(estado, projeto)
        if args.comando == 'executar' and args.modo:
            estado.selecao = decidir(raiz_estado, projeto, raiz, os.environ['JANGADA_CONFIG'], args.tarefa,
                                    args.modo, args.executor, args.confirmar, args.perfil,
                                    args.permitir_remoto, args.permitir_codex)
            if estado.selecao['executor'] is None:
                raise ValueError('nenhum executor elegível para a escolha solicitada')
        if args.comando == 'fila':
            if args.metricas:
                config = os.environ.get('JANGADA_CONFIG')
                precos = ler_precos(pathlib.Path(config) / 'precos.json') if config else None
                print(json.dumps({'projeto': str(projeto), 'metricas': resumir(estado, precos)}, ensure_ascii=False))
                return
            if args.importar:
                estado.importar(especificacoes(args.importar, projeto))
            tarefas = estado.listar()
            if args.revisao:
                pendentes = []
                for item in tarefas:
                    if item['status'] != 'REVIEW_REQUIRED':
                        continue
                    executor, modelo = identidade(item['resultado'] or {})
                    pendentes.append({'id': item['id'], 'capacidade': item['especificacao']['capacidade'],
                                      'executor': executor, 'modelo': modelo,
                                      'arquivo': str(pasta / 'artefatos' / f'{item["artefato"]}.txt')})
                if args.json:
                    print(json.dumps({'projeto': str(projeto), 'revisao': pendentes}, ensure_ascii=False))
                else:
                    for item in pendentes:
                        print('\t'.join((item['id'], item['capacidade'], item['executor'],
                                         item['modelo'] or '-', item['arquivo'])))
                return
            if args.json:
                print(json.dumps({'projeto': str(projeto), 'estado': str(pasta), 'tarefas': tarefas}, ensure_ascii=False))
            else:
                for item in tarefas:
                    spec = item['especificacao']
                    print(f'{item["id"]}\t{item["status"]}\t{spec["capacidade"]}\t{item["tentativas"]} tentativa(s)'
                          f'\t{spec.get("prioridade", "normal")}')
        elif args.comando in {'executar', 'retomar'}:
            global_estado = Estado(raiz_estado / 'agentes/runtime', raiz=raiz_estado)
            try:
                saude = Saude(global_estado)
                if args.comando == 'executar' and args.acompanhar:
                    def emitir(evento):
                        print(json.dumps({'projeto': str(projeto), **evento}, ensure_ascii=False), flush=True)

                    emitir(acompanhar(estado, projeto, raiz, os.environ['JANGADA_CONFIG'], saude,
                                      args.perfil, args.limite, args.intervalo or 60, args.duracao or 28800,
                                      args.permitir_remoto, args.permitir_codex, emitir, args.supervisionar,
                                      args.amostrar))
                    return
                if args.comando == 'executar' and args.paralelo > 1:
                    print(json.dumps({'projeto': str(projeto), 'retomadas': [],
                                      'resultados': executar_em_paralelo(args, projeto)}, ensure_ascii=False))
                    return
                retomadas, resultados = [], []
                if args.comando == 'retomar':
                    if args.atualizar:
                        saude.atualizar(args.permitir_remoto)
                        if (args.permitir_remoto and args.permitir_codex and args.perfil != 'offline'
                                and (os.environ.get('JANGADA_DELEGAR') or 'agy') == 'agy'
                                and os.environ.get('JANGADA_CODEX_ECONOMICO_MODELO')):
                            saude.atualizar_codex(True)
                    retomadas = retomar(estado, saude, raiz, os.environ['JANGADA_CONFIG'],
                                       args.perfil, args.permitir_remoto, args.permitir_codex)
                if args.comando == 'executar' or args.executar:
                    resultados = executar(estado, projeto, raiz, args.perfil,
                                          args.limite, args.permitir_remoto, saude, args.permitir_codex, args.supervisionar,
                                          args.amostrar)
                print(json.dumps({'projeto': str(projeto), 'retomadas': retomadas,
                                  'resultados': resultados}, ensure_ascii=False))
            finally:
                global_estado.fechar()
        else:
            if args.acao == 'executar-principal':
                global_estado = Estado(raiz_estado / 'agentes/runtime', raiz=raiz_estado)
                try:
                    print(json.dumps(executar_principal(estado, args.id, projeto, raiz, Saude(global_estado),
                                     args.permitir_remoto, args.permitir_codex), ensure_ascii=False))
                finally:
                    global_estado.fechar()
                return
            elif args.acao == 'assumir':
                if args.modo == 'assistido':
                    decidir(raiz_estado, projeto, raiz, os.environ['JANGADA_CONFIG'], args.id,
                            args.modo, args.executor, args.confirmar)
                print(json.dumps(assumir_principal(estado, args.id, projeto, args.executor, args.modelo), ensure_ascii=False))
                return
            elif args.acao == 'entregar':
                print(json.dumps(entregar_principal(estado, args.id, args.dono, projeto,
                                 raiz, args.arquivo), ensure_ascii=False))
                return
            elif args.acao == 'revisar':
                if not args.parecer or not (args.aprovar or args.reprovar):
                    raise ValueError('revisar exige --parecer e --aprovar ou --reprovar')
                estado.revisar_lote(args.id.split(','), args.parecer, args.aprovar,
                                   args.revisor, args.modelo_revisor, args.contexto_revisao)
            else:
                if args.parecer or args.aprovar or args.reprovar:
                    raise ValueError('parecer e decisão só são usados na revisão')
                estado.alterar(args.id, args.acao)
            print(json.dumps({'tarefa': args.id, 'acao': args.acao}, ensure_ascii=False))
    finally:
        estado.fechar()


if __name__ == '__main__':
    for sinal in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sinal, interromper_execucao)
    try:
        main()
    except KeyboardInterrupt:
        print('jangada-executar: execução interrompida; nenhuma outra tarefa iniciada', file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, KeyError, sqlite3.Error) as erro:
        print(f'jangada-fila: {erro}', file=sys.stderr)
        sys.exit(2)
