"""Cadastro, consulta e vínculos operacionais de projetos."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

sys.dont_write_bytecode = True
from consultas import consultar, catalogos
from estado import Estado
from projetos import cadastrar, chave, ler_json, ler_projeto, reassociar, executor_permitido
from roteamento import decidir, MODOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--projeto', type=Path, default=Path.cwd())
    comandos = parser.add_subparsers(dest='acao', required=True)
    consulta = comandos.add_parser('consultar')
    consulta.add_argument('--todos', action='store_true')
    consulta.add_argument('--sem-catalogos', action='store_true')
    cadastro = comandos.add_parser('cadastrar')
    cadastro.add_argument('--politica', type=Path)
    mover = comandos.add_parser('reassociar')
    mover.add_argument('novo', type=Path)
    atividade = comandos.add_parser('atividade')
    atividade.add_argument('--titulo', required=True)
    atividade.add_argument('--objetivo', required=True)
    atividade.add_argument('--criterio', action='append', required=True)
    rota = comandos.add_parser('rotear')
    rota.add_argument('tarefa')
    rota.add_argument('--modo', choices=MODOS, default='manual')
    rota.add_argument('--executor')
    rota.add_argument('--confirmar', action='store_true')
    rota.add_argument('--perfil', choices=['balanced', 'quality', 'offline'], default='balanced')
    rota.add_argument('--permitir-remoto', action='store_true')
    rota.add_argument('--permitir-codex', action='store_true')
    for acao in ('sessao-iniciar', 'sessao-conferir'):
        sessao = comandos.add_parser(acao)
        sessao.add_argument('nome')
        sessao.add_argument('--executor', required=True)
        sessao.add_argument('--atividade')
        sessao.add_argument('--tarefa-id')
    fim = comandos.add_parser('sessao-encerrar')
    fim.add_argument('nome')
    fim.add_argument('--integrada', action='store_true')
    aborto = comandos.add_parser('sessao-abortar')
    aborto.add_argument('nome')
    aborto.add_argument('--execucao', required=True)
    args = parser.parse_args()
    if os.environ.get('JANGADA_ISOLADO') and (args.acao in {
            'reassociar', 'sessao-iniciar', 'sessao-abortar', 'sessao-encerrar'}
            or args.acao == 'cadastrar' and args.politica):
        raise ValueError('operação exige execução fora do isolamento')
    raiz = Path(os.environ['JANGADA_ESTADO'])
    projeto = args.projeto.resolve()
    if args.acao == 'consultar':
        resultado = consultar(raiz, None if args.todos else projeto)
        if not args.sem_catalogos:
            publico = catalogos(os.environ['JANGADA_CORE_PATH'])
            resultado['erros'].extend(publico.pop('erros'))
            resultado.update(publico)
    elif args.acao == 'sessao-conferir':
        if not projeto.is_dir():
            raise ValueError('projeto não existe')
        dados = consultar(raiz, projeto)
        if dados['erros']:
            raise ValueError('; '.join(dados['erros']))
        cadastro = dados['projetos'][0] if dados['projetos'] else None
        if not executor_permitido(cadastro, args.executor):
            raise ValueError('política do projeto impede este executor')
        if cadastro and cadastro['politica'].get('orcamento'):
            raise ValueError('sessão interativa não garante teto de chamadas ou custo; use a fila')
        if args.atividade and not any(a['id'] == args.atividade for a in dados['atividades']):
            raise ValueError('atividade inexistente')
        if args.tarefa_id and not any(t['id'] == args.tarefa_id for t in dados['tarefas']):
            raise ValueError('tarefa inexistente')
        resultado = {'permitida': True}
    elif args.acao == 'rotear':
        resultado = decidir(raiz, projeto, os.environ['JANGADA_CORE_PATH'], os.environ['JANGADA_CONFIG'],
                            args.tarefa, args.modo, args.executor, args.confirmar, args.perfil,
                            args.permitir_remoto, args.permitir_codex)
    elif args.acao == 'reassociar':
        resultado = reassociar(raiz, projeto, args.novo)
    else:
        if not projeto.is_dir():
            raise ValueError('projeto não existe')
        estado = Estado(raiz / 'agentes/projetos' / chave(projeto), raiz=raiz)
        try:
            resultado = cadastrar(estado, projeto, ler_json(args.politica) if args.acao == 'cadastrar' and args.politica else None)
            if args.acao == 'atividade':
                resultado = {'atividade': estado.criar_atividade(args.titulo, args.objetivo, args.criterio)}
            elif args.acao == 'sessao-iniciar':
                if not estado.permite_executor(args.executor):
                    raise ValueError('política do projeto impede este executor')
                if args.atividade and not estado.db.execute('SELECT 1 FROM atividades WHERE id=?', (args.atividade,)).fetchone():
                    raise ValueError('atividade inexistente')
                if args.tarefa_id and not estado.db.execute('SELECT 1 FROM tarefas WHERE id=?', (args.tarefa_id,)).fetchone():
                    raise ValueError('tarefa inexistente')
                with estado.transacao():
                    if not estado.permite_executor(args.executor):
                        raise ValueError('política do projeto impede este executor')
                    politica = ler_projeto(estado.pasta)['politica']
                    if politica.get('orcamento'):
                        raise ValueError('sessão interativa não garante teto de chamadas ou custo; use a fila')
                    estado.db.execute("UPDATE execucoes SET fim=?,status='REVISION_REQUIRED' WHERE sessao=? AND status='RUNNING'",
                                      (time.time(), args.nome))
                    identificador = 'exe-' + uuid.uuid4().hex[:16]
                    estado.db.execute('''INSERT INTO execucoes
                        (id,sessao,tarefa,atividade,funcao,agente,provedor,inicio,status)
                        VALUES(?,?,?,?,?,?,?,?,?)''', (identificador, args.nome, args.tarefa_id, args.atividade,
                        'execucao', args.executor, args.executor, time.time(), 'RUNNING'))
                    resultado = {'execucao': identificador}
            elif args.acao == 'sessao-abortar':
                with estado.transacao():
                    estado.db.execute("UPDATE execucoes SET fim=?,status='CANCELLED' WHERE sessao=? AND id=? AND status='RUNNING'",
                                      (time.time(), args.nome, args.execucao))
                resultado = {'sessao': args.nome, 'execucao': args.execucao, 'status': 'CANCELLED'}
            elif args.acao == 'sessao-encerrar':
                with estado.transacao():
                    estado.db.execute("UPDATE execucoes SET fim=?,status=? WHERE sessao=? AND status='RUNNING'",
                                      (time.time(), 'COMPLETED' if args.integrada else 'CANCELLED', args.nome))
                resultado = {'sessao': args.nome, 'encerrada': True}
        finally:
            estado.fechar()
    print(json.dumps(resultado, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as erro:
        print(f'jangada-projeto: {erro}', file=sys.stderr)
        sys.exit(2)
