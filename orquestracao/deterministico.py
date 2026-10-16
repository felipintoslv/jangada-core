"""Critérios locais de formato, sem executar instruções das fontes."""

import hashlib
import json
import math
import os
import pathlib
import stat

CAPACIDADE = 'validacao_json'


def elegivel(tarefa):
    return (tarefa['capacidade'] == CAPACIDADE and tarefa['papel'] == 'verificador'
            and tarefa['risco'] == 0 and not tarefa.get('requisitos'))


def objeto_sem_repeticoes(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            raise ValueError('chave repetida no objeto JSON')
        objeto[chave] = valor
    return objeto


def conferir_valores(valor):
    pendentes = [(valor, 0)]
    while pendentes:
        item, profundidade = pendentes.pop()
        if profundidade > 64:
            raise ValueError('JSON excede 64 níveis de profundidade')
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError('número JSON fora do intervalo finito')
        if isinstance(item, str) and any(0xD800 <= ord(c) <= 0xDFFF for c in item):
            raise ValueError('texto JSON contém substituto Unicode isolado')
        if isinstance(item, dict):
            pendentes.extend((v, profundidade + 1) for v in item.values())
            pendentes.extend((k, profundidade + 1) for k in item)
        elif isinstance(item, list):
            pendentes.extend((v, profundidade + 1) for v in item)


def constante_invalida(_):
    raise ValueError('constante não permitida em JSON')


TIPOS = {'null': type(None), 'boolean': bool, 'object': dict, 'array': list, 'string': str}
ANOTACOES = {'$schema', 'title', 'description'}
CONTAGENS = {'minItems', 'maxItems', 'minLength', 'maxLength'}


def numero(valor):
    return type(valor) in (int, float)


def do_tipo(valor, tipo):
    if tipo == 'number':
        return numero(valor)
    if tipo == 'integer':
        return numero(valor) and valor == int(valor)
    return isinstance(valor, TIPOS[tipo])


def igual(a, b):
    """Igualdade de JSON: true não é 1, e 1 é igual a 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(igual(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(map(igual, a, b))
    return (numero(a) and numero(b) or type(a) is type(b)) and a == b


def esquema_valido(esquema):
    """Aceita só o subconjunto conferido por `validar`; o restante passaria sem ser aplicado."""
    if not isinstance(esquema, dict):
        raise ValueError('esquema deve ser um objeto')
    for chave, regra in esquema.items():
        if chave in ANOTACOES:
            continue
        if chave == 'type':
            tipos = regra if isinstance(regra, list) else [regra]
            valido = bool(tipos) and all(isinstance(t, str) and t in {*TIPOS, 'number', 'integer'} for t in tipos)
        elif chave == 'enum':
            valido = isinstance(regra, list) and bool(regra)
        elif chave == 'const':
            valido = True
        elif chave == 'required':
            valido = (isinstance(regra, list) and all(isinstance(c, str) for c in regra)
                      and len(set(regra)) == len(regra))
        elif chave == 'properties':
            valido = isinstance(regra, dict)
            for item in regra.values() if valido else ():
                esquema_valido(item)
        elif chave == 'items' or chave == 'additionalProperties' and not isinstance(regra, bool):
            esquema_valido(regra)
            valido = True
        elif chave == 'additionalProperties':
            valido = True
        elif chave in CONTAGENS:
            valido = type(regra) is int and regra >= 0
        elif chave in ('minimum', 'maximum'):
            valido = numero(regra)
        else:
            raise ValueError(f'esquema usa palavra-chave não aceita: {chave[:40]}')
        if not valido:
            raise ValueError(f'esquema com valor inválido em {chave}')


def validar(valor, esquema, caminho='$'):
    def falha(motivo):
        raise ValueError(f'{caminho[:200]}: {motivo}')

    if 'type' in esquema:
        tipos = esquema['type'] if isinstance(esquema['type'], list) else [esquema['type']]
        if not any(do_tipo(valor, tipo) for tipo in tipos):
            falha(f'tipo diferente de {" ou ".join(tipos)}')
    if 'enum' in esquema and not any(igual(valor, opcao) for opcao in esquema['enum']):
        falha('valor fora de enum')
    if 'const' in esquema and not igual(valor, esquema['const']):
        falha('valor diferente de const')
    if numero(valor):
        if 'minimum' in esquema and valor < esquema['minimum']:
            falha(f'menor que {esquema["minimum"]}')
        if 'maximum' in esquema and valor > esquema['maximum']:
            falha(f'maior que {esquema["maximum"]}')
    elif isinstance(valor, (str, list)):
        minimo, maximo = ('minLength', 'maxLength') if isinstance(valor, str) else ('minItems', 'maxItems')
        if len(valor) < esquema.get(minimo, 0):
            falha(f'comprimento menor que {esquema[minimo]}')
        if maximo in esquema and len(valor) > esquema[maximo]:
            falha(f'comprimento maior que {esquema[maximo]}')
        if isinstance(valor, list) and 'items' in esquema:
            for indice, item in enumerate(valor):
                validar(item, esquema['items'], f'{caminho}[{indice}]')
    elif isinstance(valor, dict):
        for chave in esquema.get('required', []):
            if chave not in valor:
                falha(f'falta a propriedade {json.dumps(chave, ensure_ascii=False)}')
        propriedades = esquema.get('properties', {})
        adicionais = esquema.get('additionalProperties', True)
        for chave, item in valor.items():
            local = f'{caminho}[{json.dumps(chave, ensure_ascii=False)}]'
            if chave in propriedades:
                validar(item, propriedades[chave], local)
            elif adicionais is False:
                raise ValueError(f'{local[:200]}: propriedade não prevista')
            elif adicionais is not True:
                validar(item, adicionais, local)


def ler(nome, esperado):
    descritor = os.open(pathlib.Path(nome), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descritor, 'rb') as arquivo:
        if not stat.S_ISREG(os.fstat(arquivo.fileno()).st_mode):
            raise ValueError('fonte JSON deve ser arquivo regular')
        bruto = arquivo.read(1024 * 1024 + 1)
    if len(bruto) > 1024 * 1024:
        raise ValueError('fontes JSON excedem 1 MiB por arquivo ou 4 MiB no total')
    resumo = hashlib.sha256(bruto).hexdigest()
    if resumo != esperado:
        raise ValueError('fonte JSON mudou após a importação')
    try:
        valor = json.loads(bruto.decode('utf-8'), object_pairs_hook=objeto_sem_repeticoes,
                           parse_constant=constante_invalida)
        conferir_valores(valor)
    except (ValueError, UnicodeError, RecursionError) as erro:
        if isinstance(erro, json.JSONDecodeError):
            motivo = f'JSON inválido na linha {erro.lineno}, coluna {erro.colno}'
        elif isinstance(erro, UnicodeError):
            motivo = 'fonte JSON não está em UTF-8'
        elif isinstance(erro, RecursionError):
            motivo = 'JSON excede a profundidade do analisador'
        else:
            motivo = str(erro)
        raise ValueError(f'{nome}: {motivo}') from None
    return valor, {'arquivo': nome, 'sha256': resumo, 'bytes': len(bruto)}


def conferir(tarefa):
    if not elegivel(tarefa):
        raise ValueError('conclusão automática exige validação JSON de risco zero sem requisitos adicionais')
    if len(tarefa['fontes']) > 32:
        raise ValueError('validação JSON aceita até 32 fontes')
    relatorio = {'task_id': tarefa['id'], 'capacidade': CAPACIDADE, 'criterio': criterio(tarefa), 'resultado': 'PASS'}
    esquema = None
    if 'esquema' in tarefa:
        esquema, relatorio['esquema'] = ler(tarefa['esquema'], tarefa.get('hash_esquema'))
        try:
            esquema_valido(esquema)
        except ValueError as erro:
            raise ValueError(f'{tarefa["esquema"]}: {erro}') from None
    fontes, total = [], 0
    for nome in tarefa['fontes']:
        valor, fonte = ler(nome, tarefa.get('hashes_fontes', {}).get(nome))
        total += fonte['bytes']
        if total > 4 * 1024 * 1024:
            raise ValueError('fontes JSON excedem 1 MiB por arquivo ou 4 MiB no total')
        if esquema is not None:
            try:
                validar(valor, esquema)
            except ValueError as erro:
                raise ValueError(f'{nome}: fora do esquema em {erro}') from None
        fontes.append(fonte)
    return json.dumps({**relatorio, 'fontes': fontes}, ensure_ascii=False, sort_keys=True, allow_nan=False)


def criterio(tarefa):
    return 'sintaxe_json_estrita_e_esquema' if 'esquema' in tarefa else 'sintaxe_json_estrita'
