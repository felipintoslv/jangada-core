"""Candidatos explicados, sem consultar serviços nem autorizar novos destinos."""

from pathlib import Path
import shutil
import sqlite3
import time

if __package__:
    from .consultas import consultar, banco_leitura
else:
    from consultas import consultar, banco_leitura
from projetos import provedor_de, chave
from estado import Estado
from saude import candidatos_elegiveis, preferencias_delegacao

MODOS = ('manual', 'assistido', 'automatico_supervisionado')


def decidir(raiz_estado, projeto, raiz, config, identificador, modo='manual', executor=None,
            confirmar=False, perfil='balanced', permitir_remoto=False, permitir_codex=False):
    if modo not in MODOS or perfil not in {'balanced', 'quality', 'offline'}:
        raise ValueError('modo ou perfil inválido')
    consulta = consultar(raiz_estado, projeto)
    if consulta['erros']:
        raise ValueError('; '.join(consulta['erros']))
    item = next((t for t in consulta['tarefas'] if t['id'] == identificador), None)
    if item is None:
        raise ValueError('tarefa inexistente')
    tarefa = item['especificacao']
    politica = next(p['politica'] for p in consulta['projetos'] if p['id'] == item['projeto'])
    principais = tarefa['risco'] == 3 or tarefa['qualidade'] in {'high', 'critical'}
    preferencias = preferencias_delegacao(Path(raiz), config)
    elegiveis = ([] if modo == 'automatico_supervisionado' else ['claude', 'codex']) if principais else candidatos_elegiveis(
        tarefa, preferencias, perfil, permitir_remoto, permitir_codex)
    if tarefa['risco'] == 4 or item['estado'] != 'Pronta':
        elegiveis = []
    saude = {}
    banco = Path(raiz_estado) / 'agentes/runtime/tarefas.sqlite'
    if banco.exists() and not banco.is_symlink() and not banco.parent.is_symlink():
        with banco_leitura(banco) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='provedores'").fetchone():
                saude = {r['id']: dict(r) for r in db.execute('SELECT * FROM provedores')}
    candidatos = []
    for candidato in (['claude', 'codex'] if principais else preferencias.get(tarefa['capacidade'], [])):
        provedor = provedor_de(candidato)
        observacao = saude.get('local' if candidato == 'local' else provedor, {})
        disponivel = observacao.get('status') == 'AVAILABLE' and observacao.get('valido_ate', 0) > time.time()
        motivo = 'capacidade ou autorização não permite este executor'
        permitido = candidato in elegiveis
        if permitido:
            motivo = 'capacidade e autorização compatíveis'
        if ('provedores' in politica and provedor not in politica['provedores']
                or politica.get('dados') == 'local' and provedor != 'ollama'):
            permitido, motivo = False, 'política de dados impede este provedor'
        if candidato in {'claude', 'codex'} and not shutil.which(candidato):
            permitido, motivo = False, 'programa não instalado'
        if observacao.get('pausado') or observacao and not disponivel:
            permitido, motivo = False, 'provedor em espera ou com observação vencida'
        elif modo == 'automatico_supervisionado' and not disponivel:
            permitido, motivo = False, 'disponibilidade não verificada'
        candidatos.append(dict(executor=candidato, provedor=provedor, elegivel=permitido, motivo=motivo,
                               disponibilidade='AVAILABLE' if disponivel else 'UNKNOWN'))
    banco_projeto = Path(raiz_estado) / 'agentes/projetos' / chave(projeto) / 'tarefas.sqlite'
    with banco_leitura(banco_projeto) as db:
        consulta_orcamento = object.__new__(Estado)
        consulta_orcamento.db = db
        consulta_orcamento.pasta = banco_projeto.parent
        try:
            limite = consulta_orcamento.limite_projeto(tarefa)
            motivo_orcamento = 'orçamento do projeto esgotado' if limite == 0 else None
        except (ValueError, sqlite3.Error) as erro:
            motivo_orcamento = str(erro)
    if motivo_orcamento:
        for candidato in candidatos:
            candidato.update(elegivel=False, motivo=motivo_orcamento)
    selecionado = None
    if modo == 'automatico_supervisionado':
        selecionado = next((c['executor'] for c in candidatos if c['elegivel']), None)
    elif executor is not None:
        if not any(c['executor'] == executor and c['elegivel'] for c in candidatos):
            raise ValueError('executor escolhido não é elegível')
        if modo == 'assistido' and not confirmar:
            raise ValueError('modo assistido exige confirmação da escolha')
        selecionado = executor
    return dict(tarefa=identificador, modo=modo, executor=selecionado, candidatos=candidatos,
                confirmado=confirmar, custo_estimado=None,
                motivo='escolha explícita' if modo != 'automatico_supervisionado' else 'primeiro elegível na preferência configurada')
