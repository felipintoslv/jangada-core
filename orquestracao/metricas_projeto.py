"""Resume observações da fila, sem transformar registros em autorização."""

import collections
import hashlib
import json
import math

from supervisao import REMOTOS


def inteiro(valor):
    return type(valor) is int and valor >= 0


def identidade(resultado):
    registro = resultado.get('delegacao')
    registro = registro if isinstance(registro, dict) else {}
    executor = resultado.get('executor') or registro.get('destino')
    executor = executor if isinstance(executor, str) and executor else 'nao_informado'
    modelo = registro.get('modelo')
    modelo = modelo if isinstance(modelo, str) and modelo else None
    return executor, modelo


def grupo_executor(executores, executor, modelo):
    return executores.setdefault((executor, modelo), dict(executor=executor, modelo=modelo,
        execucoes_registradas=0, processamentos_confirmados=0, reservas_expiradas=0, reservas_em_aberto=0,
        chamadas_do_fluxo_confirmadas=0, chamadas_do_fluxo_desconhecidas=0,
        segundos_do_fluxo_confirmados=0, duracoes_do_fluxo_desconhecidas=0,
        custo_estimado_confirmado=0, execucoes_sem_custo=0))


def ler_precos(caminho):
    """Lê a tabela declarada pelo usuário; sem o arquivo, nenhum custo é estimado."""
    try:
        dados = json.loads(caminho.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None

    def valor(preco, campo):
        return type(preco.get(campo)) in (int, float) and math.isfinite(preco[campo]) and preco[campo] >= 0

    if (not isinstance(dados, dict) or dados.keys() != {'moeda', 'precos'}
            or not isinstance(dados['moeda'], str) or not 1 <= len(dados['moeda']) <= 8
            or not isinstance(dados['precos'], dict)
            or any(not isinstance(modelos, dict) for modelos in dados['precos'].values())
            or any(not isinstance(preco, dict) or preco.keys() != {'entrada_por_milhao', 'saida_por_milhao'}
                   or not valor(preco, 'entrada_por_milhao') or not valor(preco, 'saida_por_milhao')
                   for modelos in dados['precos'].values() for preco in modelos.values())):
        raise ValueError(f'{caminho}: esperado moeda e precos[executor][modelo] com '
                         'entrada_por_milhao e saida_por_milhao não negativos')
    return dados


def amostragem(estado, tarefa, resultado, artefato):
    """Sorteia pelo conteúdo se o relatório entra na revisão, na taxa do histórico do grupo."""
    executor, modelo = identidade(resultado)
    chave = (tarefa['capacidade'], executor, modelo, tarefa['risco'])
    grupo = next((g for g in calcular(estado)['desempenho']
                  if (g['capacidade'], g['executor'], g['modelo'], g['risco']) == chave), None)
    # O Ollama nunca conclui sem revisão, qualquer que seja o histórico.
    taxa = grupo['amostragem_sugerida'] if grupo and executor in REMOTOS else 1.0
    semente = f'{tarefa["id"]}\0{hashlib.sha256(artefato.encode()).hexdigest()}'
    sorteio = int(hashlib.sha256(semente.encode()).hexdigest()[:8], 16) / 2 ** 32
    return {'executor': executor, 'modelo': modelo, 'taxa': taxa, 'sorteio': sorteio,
            'revisoes_na_janela': grupo['revisoes_na_janela'] if grupo else 0,
            'selecionada': sorteio < taxa}


def resumir(estado, precos=None):
    estado.db.execute('BEGIN')
    try:
        return calcular(estado, precos)
    finally:
        estado.db.execute('ROLLBACK')


def calcular(estado, precos=None):
    tarefas = {t['id']: t for t in estado.listar()}
    totais = dict(tarefas=len(tarefas), estados=dict(collections.Counter(t['status'] for t in tarefas.values())),
                  execucoes_registradas=0, processamentos_confirmados=0, recusas_sem_chamadas=0,
                  reservas_expiradas=0, reservas_em_aberto=0, repeticoes_solicitadas=0, retomadas=0,
                  chamadas=0, chamadas_confirmadas=0, chamadas_desconhecidas=0,
                  segundos=0, segundos_confirmados=0, duracoes_desconhecidas=0,
                  tokens_entrada=0, tokens_saida=0, tokens_entrada_confirmados=0,
                  tokens_saida_confirmados=0, mudancas_entre_candidatos=0,
                  revisoes_aprovadas=0, revisoes_reprovadas=0, revisoes_sem_saida=0,
                  supervisoes_aprovadas=0, supervisoes_reprovadas=0, supervisoes_inconclusivas=0, esperas_supervisao=0,
                  conclusoes_fora_da_amostra=0, selecionadas_na_amostra=0,
                  custo_estimado=0 if precos else None, custo_estimado_confirmado=0, execucoes_sem_custo=0,
                  moeda=precos['moeda'] if precos else None)
    executores, janelas, saidas = {}, {}, {}
    eventos = estado.db.execute('SELECT tarefa,evento,dados FROM eventos ORDER BY seq')
    for evento in eventos:
        identificador = evento['tarefa']
        dados = json.loads(evento['dados'])
        tipo = evento['evento']
        if tipo == 'retomar':
            totais['retomadas'] += 1
        elif tipo == 'repetir':
            totais['repeticoes_solicitadas'] += 1
        elif tipo == 'reserva_expirada':
            totais['reservas_expiradas'] += 1
            totais['chamadas_desconhecidas'] += 1
            totais['duracoes_desconhecidas'] += 1
            grupo = grupo_executor(executores, 'nao_informado', None)
            grupo['reservas_expiradas'] += 1
            grupo['chamadas_do_fluxo_desconhecidas'] += 1
            grupo['duracoes_do_fluxo_desconhecidas'] += 1
            grupo['execucoes_sem_custo'] += 1
            totais['execucoes_sem_custo'] += 1
            for campo in ('chamadas', 'segundos', 'tokens_entrada', 'tokens_saida', 'custo_estimado'):
                totais[campo] = None
            saidas.pop(identificador, None)
        elif tipo == 'execucao_encerrada':
            resultado = dados.get('resultado')
            resultado = resultado if isinstance(resultado, dict) else {}
            metricas = resultado.get('metricas')
            metricas = metricas if isinstance(metricas, dict) else {}
            quantidade, segundos = metricas.get('chamadas'), metricas.get('segundos')
            iniciou = resultado.get('execucao_iniciada') is True or inteiro(quantidade) and quantidade > 0
            totais['execucoes_registradas'] += 1
            supervisao = resultado.get('supervisao')
            if isinstance(supervisao, dict):
                campo = 'esperas_supervisao' if supervisao.get('aguardando') is True else {
                    'APPROVED': 'supervisoes_aprovadas', 'REVISE': 'supervisoes_reprovadas'}.get(
                        supervisao.get('decisao'), 'supervisoes_inconclusivas')
                totais[campo] += 1
            sorteada = resultado.get('amostragem')
            if isinstance(sorteada, dict):
                totais['selecionadas_na_amostra' if sorteada.get('selecionada') is not False
                       else 'conclusoes_fora_da_amostra'] += 1
            totais['processamentos_confirmados'] += int(iniciou)
            totais['recusas_sem_chamadas'] += int(inteiro(quantidade) and quantidade == 0 and resultado.get('execucao_iniciada') is False)
            for campo, valor, desconhecido in (('chamadas', quantidade, 'chamadas_desconhecidas'),
                                               ('segundos', segundos, 'duracoes_desconhecidas')):
                if inteiro(valor):
                    totais[campo + '_confirmadas' if campo == 'chamadas' else campo + '_confirmados'] += valor
                    if totais[campo] is not None:
                        totais[campo] += valor
                else:
                    totais[campo] = None
                    totais[desconhecido] += 1
            executor, modelo = identidade(resultado)
            grupo = grupo_executor(executores, executor, modelo)
            grupo['execucoes_registradas'] += 1
            grupo['processamentos_confirmados'] += int(iniciou)
            if inteiro(quantidade):
                grupo['chamadas_do_fluxo_confirmadas'] += quantidade
            else:
                grupo['chamadas_do_fluxo_desconhecidas'] += 1
            if inteiro(segundos):
                grupo['segundos_do_fluxo_confirmados'] += segundos
            else:
                grupo['duracoes_do_fluxo_desconhecidas'] += 1
            registro = resultado.get('delegacao')
            registro = registro if isinstance(registro, dict) else {}
            tentativas = registro.get('tentativas')
            tentativas = tentativas if isinstance(tentativas, list) else []
            if not inteiro(quantidade):
                parcial = sum(t['chamadas'] for t in tentativas
                              if isinstance(t, dict) and inteiro(t.get('chamadas')))
                totais['chamadas_confirmadas'] += parcial
                grupo['chamadas_do_fluxo_confirmadas'] += parcial
            destinos = [t.get('destino') for t in tentativas if isinstance(t, dict)
                        and isinstance(t.get('destino'), str) and t['destino']]
            totais['mudancas_entre_candidatos'] += sum(a != b for a, b in zip(destinos, destinos[1:]))
            preco = (precos['precos'].get(executor, {}).get(modelo) if precos else None)
            custo = 0 if quantidade == 0 else None if preco is None else 0
            for campo, origem in (('tokens_entrada', 'tokens_codex_entrada'), ('tokens_saida', 'tokens_codex_saida')):
                valor = registro.get(origem)
                if inteiro(valor):
                    totais[campo + '_confirmados'] += valor
                completo = inteiro(quantidade) and (quantidade == 0 or (
                    quantidade == 1 and executor in {'codex-economico', 'codex-principal'} and inteiro(valor)))
                if not completo:
                    totais[campo] = None
                    custo = None
                elif totais[campo] is not None:
                    totais[campo] += valor if quantidade else 0
                if custo is not None and quantidade:
                    custo += valor * preco[campo.removeprefix('tokens_') + '_por_milhao'] / 1e6
            # Sem preço declarado ou sem tokens de toda a cadeia, o custo é desconhecido, não zero.
            if custo is None:
                totais['custo_estimado'] = None
                totais['execucoes_sem_custo'] += 1
                grupo['execucoes_sem_custo'] += 1
            else:
                totais['custo_estimado_confirmado'] += custo
                grupo['custo_estimado_confirmado'] += custo
                if totais['custo_estimado'] is not None:
                    totais['custo_estimado'] += custo
            saidas.pop(identificador, None)
            if dados.get('status') == 'REVIEW_REQUIRED' and dados.get('artefato'):
                spec = tarefas[identificador]['especificacao']
                saidas[identificador] = (spec['capacidade'], executor, modelo, spec['risco'])
        elif tipo == 'revisada':
            status = dados.get('status')
            if status not in {'COMPLETED', 'REVISION_REQUIRED'}:
                continue
            aprovado = status == 'COMPLETED'
            totais['revisoes_aprovadas' if aprovado else 'revisoes_reprovadas'] += 1
            chave = saidas.pop(identificador, None)
            if chave is None:
                totais['revisoes_sem_saida'] += 1
            else:
                janelas.setdefault(chave, collections.deque(maxlen=50)).append(aprovado)
    abertas = sum(t['status'] == 'RUNNING' for t in tarefas.values())
    if abertas:
        totais['reservas_em_aberto'] = abertas
        totais['chamadas_desconhecidas'] += abertas
        totais['duracoes_desconhecidas'] += abertas
        for campo in ('chamadas', 'segundos', 'tokens_entrada', 'tokens_saida', 'custo_estimado'):
            totais[campo] = None
        totais['execucoes_sem_custo'] += abertas
        grupo = grupo_executor(executores, 'nao_informado', None)
        grupo['reservas_em_aberto'] += abertas
        grupo['execucoes_sem_custo'] += abertas
        grupo['chamadas_do_fluxo_desconhecidas'] += abertas
        grupo['duracoes_do_fluxo_desconhecidas'] += abertas
    for grupo in (totais, *executores.values()):
        for campo in ('custo_estimado', 'custo_estimado_confirmado'):
            if grupo.get(campo) is not None:
                grupo[campo] = round(grupo[campo], 6)
    desempenho = []
    for (capacidade, executor, modelo, risco), janela in sorted(janelas.items(), key=lambda item: str(item[0])):
        n = len(janela)
        erros = n - sum(janela)
        taxa = erros / n
        amostra = 1.0
        if n >= 20 and risco <= 1 and executor not in {'nao_informado', 'deterministico'} and modelo:
            amostra = 1.0 if taxa > 0.15 else (0.5 if taxa > 0.05 else 0.1)
        desempenho.append(dict(capacidade=capacidade, executor=executor, modelo=modelo, risco=risco,
            revisoes_na_janela=n, aprovadas=sum(janela), reprovadas=erros,
            taxa_reprovacao=taxa, amostragem_sugerida=amostra))
    return {**totais, 'por_executor': sorted(executores.values(), key=lambda item: str((item['executor'], item['modelo']))),
            'desempenho': desempenho}
