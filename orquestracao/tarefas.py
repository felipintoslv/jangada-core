"""Contratos e regras das tarefas, sem persistência nem execução de provedores."""

import json
import re


ESTADOS = {
    'QUEUED', 'RUNNING', 'COMPLETED', 'REVIEW_REQUIRED', 'REVISION_REQUIRED',
    'WAITING_PROVIDER', 'WAITING_QUOTA', 'WAITING_REVIEWER', 'FAILED', 'CANCELLED', 'PAUSED', 'BLOCKED',
}
FINAIS = {'COMPLETED', 'FAILED', 'CANCELLED'}
IDENTIFICADOR = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$')
PRIORIDADES = ('critical', 'high', 'normal', 'low', 'background')


def serializar(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, allow_nan=False)


def intermediaria(tarefa):
    return (tarefa.get('intermediaria') is True
            and tarefa.get('risco') == 1 and tarefa.get('qualidade') in {'low', 'medium'}
            and tarefa.get('papel') == 'leitor'
            and tarefa.get('capacidade') in {'leitura_documental', 'resumo_curto', 'analise_documental'})


def elegivel_supervisao(tarefa):
    return tarefa.get('supervisao_automatica') is True and intermediaria(tarefa)


def amostravel(tarefa):
    return tarefa.get('amostragem') is True and intermediaria(tarefa)


def tarefa_valida(tarefa):
    if not isinstance(tarefa, dict):
        raise ValueError('tarefa deve ser um objeto')
    obrigatorios = {'id', 'pedido', 'papel', 'capacidade', 'risco', 'qualidade', 'fontes'}
    if not obrigatorios <= tarefa.keys():
        raise ValueError('campos obrigatórios ausentes na tarefa')
    if not isinstance(tarefa['id'], str) or not IDENTIFICADOR.fullmatch(tarefa['id']):
        raise ValueError('identificador inválido')
    for campo in ('pedido', 'papel', 'capacidade'):
        if not isinstance(tarefa[campo], str) or not tarefa[campo].strip():
            raise ValueError(f'{campo} deve ser texto não vazio')
    if 'atividade' in tarefa and (not isinstance(tarefa['atividade'], str)
            or not re.fullmatch(r'atv-[0-9a-f]{12}', tarefa['atividade'])):
        raise ValueError('atividade inválida')
    for campo in ('criterios_aceite', 'entradas', 'saidas', 'contexto'):
        if campo in tarefa and (not isinstance(tarefa[campo], list) or any(
                not isinstance(item, str) or not item.strip() for item in tarefa[campo])
                or len(tarefa[campo]) != len(set(tarefa[campo]))):
            raise ValueError(f'{campo} deve ser lista de textos sem repetição')
    if type(tarefa['risco']) is not int or not 0 <= tarefa['risco'] <= 4:
        raise ValueError('risco deve estar entre 0 e 4')
    if tarefa['qualidade'] not in ('low', 'medium', 'high', 'critical'):
        raise ValueError('qualidade inválida')
    if tarefa.get('prioridade', 'normal') not in PRIORIDADES:
        raise ValueError('prioridade inválida')
    if not isinstance(tarefa['fontes'], list) or not tarefa['fontes'] or any(
        not isinstance(fonte, str) or not fonte for fonte in tarefa['fontes']
    ):
        raise ValueError('fontes devem ser uma lista não vazia de caminhos')
    dependencias = tarefa.get('dependencias', [])
    if not isinstance(dependencias, list) or any(
        not isinstance(dep, str) or not IDENTIFICADOR.fullmatch(dep) for dep in dependencias
    ) or len(dependencias) != len(set(dependencias)):
        raise ValueError('dependências inválidas ou repetidas')
    if tarefa['id'] in dependencias:
        raise ValueError('tarefa não pode depender de si mesma')
    requisitos = tarefa.get('requisitos', [])
    if not isinstance(requisitos, list) or any(
        not isinstance(item, str) or not item.strip() or item.startswith('-') or '\n' in item
        for item in requisitos
    ) or len(requisitos) != len(set(requisitos)):
        raise ValueError('requisitos inválidos ou repetidos')
    for campo, padrao in (('max_tentativas', 2), ('tempo_total', 600), ('max_chamadas', 8)):
        valor = tarefa.get(campo, padrao)
        if type(valor) is not int or not 1 <= valor <= 999999:
            raise ValueError(f'{campo} deve ser inteiro positivo')
    for campo in ('permitir_remoto', 'permitir_codex', 'intermediaria', 'supervisao_automatica', 'amostragem'):
        if campo in tarefa and type(tarefa[campo]) is not bool:
            raise ValueError(f'{campo} deve ser booleano')
    if tarefa.get('supervisao_automatica') and not elegivel_supervisao(tarefa):
        raise ValueError('supervisão automática exige leitor intermediário, risco 1 e qualidade baixa ou média')
    if tarefa.get('amostragem') and not amostravel(tarefa):
        raise ValueError('amostragem exige leitor intermediário, risco 1 e qualidade baixa ou média')
    if 'esquema' in tarefa and (tarefa['capacidade'] != 'validacao_json' or not isinstance(tarefa['esquema'], str)
                                or not tarefa['esquema'] or not isinstance(tarefa.get('hash_esquema'), str)):
        raise ValueError('esquema exige validação JSON, caminho e resumo do arquivo')
    serializar(tarefa)


def prioridades_efetivas(tarefas, estados):
    mapa = {t['id']: t for t in tarefas}
    prioridades = {t['id']: PRIORIDADES.index(t['especificacao'].get('prioridade', 'normal')) for t in tarefas}

    propagadas = {}
    pendentes = [(t['id'], prioridades[t['id']]) for t in tarefas if estados[t['id']] == 'QUEUED']
    while pendentes:
        identificador, prioridade = pendentes.pop()
        if estados[identificador] != 'QUEUED':
            continue
        prioridade = min(prioridades[identificador], prioridade)
        if propagadas.get(identificador, len(PRIORIDADES)) <= prioridade:
            continue
        prioridades[identificador] = prioridade
        propagadas[identificador] = prioridade
        pendentes.extend((dep, prioridade) for dep in mapa[identificador]['especificacao'].get('dependencias', []))
    return prioridades


def validar_dependencias(mapa):
    """Confere ciclos e referências em especificações já validadas, sem recursão."""
    visitados = set()
    for identificador in mapa:
        if identificador in visitados:
            continue
        # A pilha explícita evita o limite de recursão em planos longos.
        caminho = {identificador}
        pilha = [(identificador, iter(mapa[identificador].get('dependencias', [])))]
        while pilha:
            atual, dependencias = pilha[-1]
            dep = next(dependencias, None)
            if dep is None:
                pilha.pop()
                caminho.remove(atual)
                visitados.add(atual)
            elif dep in caminho:
                raise ValueError('ciclo nas dependências')
            elif dep not in mapa:
                raise ValueError(f'dependência inexistente: {dep}')
            elif dep not in visitados:
                caminho.add(dep)
                pilha.append((dep, iter(mapa[dep].get('dependencias', []))))
