# Preservação e recuperação

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Estado operacional: sessão, documentos temporários e marca corrente. Limpeza somente após arquivo histórico verificado. Remover a marca evita reutilização; sua cópia histórica não autoriza integração.

Histórico em `$JANGADA_ESTADO/revisoes/`:

- inicios/<sessao>/<sha256>.json: prompt, protocolo e autoria antes de iniciar/retomar; não afirma revisão realizada.
- validacao-<sessao>-rN.contexto.json: pedido integral, candidato, árvore/base, rodada, sessão e identidades conforme contexto.
- arquivo/<sha256>.json: documentos integrais base64, hashes, vínculos, confiança e registros de início; inclui reprovações/rodadas intermediárias.
- espelhos/*.git/refs/jangada/historico/*: bases/candidatos e objetos de rodadas anteriores.
- falhas-isolamento/*.json: erros de processos iniciados. Recusas da fila em agentes/projetos/<chave>/recusas/.

SQLite, eventos, execuções e artefatos da fila persistem em agentes/projetos/<chave>; encerramento não os apaga. Pareceres estruturados/humanos ficam em resultados/eventos. O backup precisa preservar a pasta de estado completa.

## Protocolo

Adquirir trava por sessão e parar agente; ler arquivos regulares sem aliases, conferir estabilidade e contexto da aprovação; publicar JSON canônico por conteúdo sem sobrescrita, com fsync de arquivo/diretório e conferência dos bytes. Falha preserva originais. Contexto incompleto publica arquivo com pendências e impede limpeza. Somente depois do sucesso são removidos documentos operacionais.

Repetição do mesmo conteúdo reutiliza o mesmo arquivo. Agente vê diretório vazio no namespace e não modifica o histórico no host. Conteúdo local é declarado pelo executor: preservá-lo não aumenta sua confiança. Registros iniciais mantêm metadados para distinguir execuções com nome de sessão reutilizado.

O teste FG decodifica e compara cada documento com os bytes anteriores ao encerramento. G recupera o prompt original após adulteração/remoção local. A amostra integral está em evidencias/arquivo-sintetico.json.

## Recuperação em diretório novo

```sh
python3 - <<'PY'
import base64, hashlib, json, pathlib, tempfile
origem = pathlib.Path('docs/estabilizacao/correcao-p0/evidencias/arquivo-sintetico.json')
doc = json.loads(origem.read_bytes())
destino = pathlib.Path(tempfile.mkdtemp(prefix='jangada-evidencias-'))
for nome, item in doc['documentos'].items():
    relativo = pathlib.Path(nome)
    assert not relativo.is_absolute() and '..' not in relativo.parts
    bruto = base64.b64decode(item['conteudo_base64'], validate=True)
    assert hashlib.sha256(bruto).hexdigest() == item['sha256']
    arquivo = destino / relativo
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(bruto)
print(destino)
PY
```

Não restaurar marcas sobre sessões reais. Não há rotação automática do histórico. Limites de 64 MiB por documento e 256 MiB por conjunto bloqueiam limpeza quando excedidos. Registros iniciais legados ausentes não são inventados.
