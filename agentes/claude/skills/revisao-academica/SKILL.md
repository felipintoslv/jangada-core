---
name: revisao-academica
description: >
  Use ao revisar como orientador um TCC, artigo, dissertação ou relatório em
  PDF ou DOCX e devolver o arquivo original com comentários curtos inseridos.
  Conduz as etapas do projeto jangada-academic-review (pasta com projeto.yaml
  de id academic-review): intake, extração, mapa do documento, cinco revisores,
  consolidação, critical gate, estilo do orientador, anotação, QA estrutural,
  QA visual e entrega, com estado e rastreabilidade em .jangada/ e validacao/.
  Não use para escrever ou reescrever o texto (veja a skill
  relatorio-academico).
---

# Protocolo: revisão acadêmica com comentários no documento

Esta skill conduz. Os scripts, prompts, esquemas e a política são do projeto,
e valem sobre o que está aqui se houver diferença.

## 1. Antes de começar

1. **Pasta do projeto:** a que tem `projeto.yaml` com `project.id:
   academic-review` (em geral `~/Projetos/jangada-academic-review`). Rode
   tudo a partir dela. Sem essa pasta, pare e avise.
2. **Leia, nesta ordem:** `projeto.yaml`, `contexto/instrucoes.md`,
   `contexto/estilo_orientador.md`, `contexto/decisoes.md`,
   `config/review_policy.yaml`. O `projeto.yaml` é o contrato: etapas,
   dependências, risco e saída de cada uma.
3. **Ambiente:** os scripts rodam com `.venv/bin/python`. Se `.venv` não
   existir: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`,
   depois `make init` para criar as pastas de `work/`.
4. **Documento:** um PDF ou DOCX em `fontes/primarias/`. Se o usuário passou um
   caminho de fora, copie para lá; nunca mova nem altere o original.
5. **Retomada:** leia `.jangada/state.json`. Se `completed` não está vazio,
   confira que `work/intake/manifest.json` é do mesmo documento e que a saída
   de cada etapa concluída existe; continue da primeira etapa pendente. Se
   `work/` guarda outro documento, pergunte antes de sobrescrever.

## 2. Regras que não mudam

- **O original é imutável.** A entrega é uma cópia em `entregas/`.
- **Finding não é comentário.** O finding traz o diagnóstico completo e fica em
  `work/`; o comentário é o texto curto que vai ao documento.
- **Nada entra no documento sem critical gate**, e quem aprova não é quem
  escreveu o finding. O condutor não aprova finding que ele mesmo produziu.
- **Modelo local ou barato produz candidato, nunca aprovação.** Toda saída
  delegada é conferida pelo condutor antes de servir de entrada.
- **Não invente.** Se o documento não informa um dado, o comentário pede que o
  autor informe ou justifique. Não sugira referência que não foi verificada.
- **Âncora literal.** O `anchor` é um trecho copiado do documento, contíguo, na
  página (PDF) ou no parágrafo (DOCX) indicado. Prefira de 4 a 12 palavras.
- **Envio a modelo remoto fora da sessão** (agy por `jangada-delegar
  --permitir-remoto`) só com autorização do usuário para este documento: o
  trabalho de um aluno é documento de terceiro.
- **Não encha para bater a meta.** `target_comments` é um intervalo de
  referência. Abaixo do mínimo, informe; acima do máximo, o gate corta os de
  menor prioridade.

## 3. Etapas

| Etapa | Quem executa | Como | Saída |
|---|---|---|---|
| `intake` | condutor | comandos da seção 4 | `work/intake/manifest.json`, `work/intake/fonte.sha256` |
| `extract` | script | `scripts/extract_document.py` | `work/extracoes/documento.jsonl` |
| `map_structure` | subagente `leitor` ou o condutor | seção 5 | `work/evidencias/mapa_documento.json` |
| `methodology_review`, `statistics_review`, `inference_review` | um subagente por revisor, no modelo principal | `prompts/<nome>.md` | `work/analises/metodologia.jsonl`, `estatistica.jsonl`, `inferencia.jsonl` |
| `writing_review`, `references_review` | um subagente por revisor, modelo intermediário serve | `prompts/<nome>.md` | `work/analises/redacao.jsonl`, `referencias.jsonl` |
| `consolidate` | condutor | seção 6 | `work/drafts/candidates.jsonl` |
| `critical_gate` | subagente novo, no modelo principal, que não escreveu finding | `prompts/critical_gate.md` | `work/drafts/approved_findings.jsonl` |
| `style` | condutor ou subagente | `prompts/style_adapter.md` | `work/annotations/review.jsonl` |
| `annotate` | script | `scripts/annotate_pdf.py` ou `annotate_docx.py` | `entregas/<arquivo>_comentado_<Nome>.<ext>` |
| `structural_qa` | script e condutor | `scripts/qa_artifact.py` e conferência do hash | `validacao/pareceres/qa_estrutural.json` |
| `visual_qa` | subagente novo, no modelo principal | `prompts/visual_qa.md` | `validacao/pareceres/qa_visual.json` |
| `deliver` | condutor | seção 9 | rastreabilidade, parecer, métricas |

Os cinco revisores dependem só do mapa e rodam em paralelo. As demais etapas
são sequenciais.

Ao concluir cada etapa, acrescente o `id` a `completed` em
`.jangada/state.json` (com `status` e `updated_at`) e uma linha em
`.jangada/trace.jsonl`:

```json
{"ts": "2026-10-02T14:03:00-03:00", "step": "extract", "executor": "script", "status": "PASS", "outputs": ["work/extracoes/documento.jsonl"], "note": "412 registros"}
```

Etapa que falha não entra em `completed`: registre em `blocked` com o motivo.

## 4. Intake e extração

```bash
F=fontes/primarias/TCC.pdf
sha256sum "$F" > work/intake/fonte.sha256
.venv/bin/python scripts/extract_document.py "$F" work/extracoes/documento.jsonl
```

O `manifest.json` registra `source`, `sha256`, `bytes`, `format`, `pages`
(PDF), `prior_annotations` (anotações que o PDF já trazia, contadas como em
`scripts/qa_artifact.py`) e `created_at`.

Confira a extração antes de seguir: número de registros coerente com o tamanho
do documento e texto legível. PDF escaneado devolve poucos registros ou
nenhum; nesse caso pare e avise, porque o MVP não faz OCR.

## 5. Mapa do documento

O mapa orienta os revisores. Registre, com página ou parágrafo de cada item:
seções e subseções; pergunta de pesquisa e objetivos; desenho, amostra, fonte
dos dados e variáveis; métodos e testes usados; resultados principais;
conclusões; limitações que o autor já reconhece; tabelas e figuras; onde está
a lista de referências. O que o documento não traz fica como `null`, não como
suposição.

As limitações reconhecidas importam: o gate rejeita comentário que repete o
que o autor já admitiu, salvo contradição posterior.

## 6. Revisores e consolidação

Cada revisor recebe: o prompt dele, `contexto/instrucoes.md`,
`config/review_policy.yaml`, o mapa e a extração. Devolve uma linha JSON por
finding, conforme `schemas/finding.schema.json`, com `status: "CANDIDATE"`,
`author` igual ao papel (`revisor_metodologico`, `revisor_estatistico`,
`revisor_inferencial`, `revisor_textual`, `revisor_referencias`) e `id` com
prefixo próprio (`MET-001`, `EST-001`, `INF-001`, `RED-001`, `REF-001`).
O revisor não escreve o comentário final.

Antes de consolidar, valide cada arquivo contra o esquema e confira por busca
na extração que cada `anchor` existe na localização declarada. Finding com
âncora que não existe volta ao revisor ou é descartado com registro no trace.

A consolidação junta os cinco arquivos em `candidates.jsonl`:

- funde duplicatas (mesmo trecho e mesmo problema), mantendo o finding mais
  completo e o `author` dele;
- quando dois findings distintos usam a mesma âncora, troca a âncora de um
  deles por outro trecho do mesmo parágrafo, porque o validador recusa âncora
  repetida;
- ordena pela prioridade de `review_policy.yaml` (`priorities`);
- não muda o diagnóstico nem cria finding novo.

## 7. Critical gate e estilo

O gate roda num subagente novo, que recebe os candidatos, o mapa, a extração e
a política, sem o raciocínio dos revisores. Para cada candidato ele grava
`status` (`APPROVE`, `REJECT` ou `REVISE`), `reviewer: "revisor_critico"` e
`review_reason`. Os motivos de rejeição estão em `reject_when`.

`REVISE` volta uma vez ao revisor de origem com o motivo e passa de novo pelo
gate; se continuar sem aprovação, vira `REJECT`. `approved_findings.jsonl` traz
todos os candidatos com a decisão, não só os aprovados: os rejeitados entram
no parecer.

O estilo transforma só os `APPROVE` em comentários conforme
`contexto/estilo_orientador.md` e `schemas/comment.schema.json`. No comentário
o `status` é `APPROVED` (com D), `author` é o papel que escreveu o finding e
`reviewer` é `revisor_critico`. Depois:

```bash
.venv/bin/python scripts/validate_review.py work/annotations/review.jsonl
```

O validador confere esquema, duplicata, 65 palavras e `author != reviewer`.
Confira à parte o que ele não cobre: `category` dentro da lista de
`review_policy.yaml`, quantidade de comentários frente a `target_comments` e
tamanho preferido de 5 a 35 palavras.

Antes de anotar, mostre ao usuário a tabela dos comentários (id, página ou
seção, categoria, texto) e os rejeitados em uma linha cada. Ele pode cortar ou
editar. Um comentário editado passa de novo pelo validador. Se o usuário pediu
execução sem pausa, siga e registre isso no trace.

## 8. Anotação e QA

Os scripts de anotação gravam o campo `author` como autor do balão. Para o
balão sair com o nome do orientador e não com o papel do agente, anote a
partir de uma cópia derivada; `review.jsonl` continua sendo a fonte de verdade:

```bash
NOME=$(.venv/bin/python -c "import yaml; print(yaml.safe_load(open('config/review_policy.yaml'))['review']['reviewer_name'])")
jq -c --arg n "$NOME" '.author = $n' work/annotations/review.jsonl > work/annotations/review.anotar.jsonl
SAIDA="entregas/TCC_comentado_${NOME}.pdf"
.venv/bin/python scripts/annotate_pdf.py "$F" work/annotations/review.anotar.jsonl "$SAIDA"
```

Para DOCX, `scripts/annotate_docx.py` com os mesmos argumentos.

`REVIEW_REQUIRED` significa âncora não encontrada (lista em
`<saida>.annotations.json` ou `<saida>.comments.json`). Corrija a âncora em
`review.jsonl` para um trecho literal e contíguo (no PDF, sem atravessar
página nem quebra por hífen), valide de novo e reanote. Não entregue com
comentário faltando sem avisar.

QA estrutural:

```bash
sha256sum -c work/intake/fonte.sha256
.venv/bin/python scripts/qa_artifact.py "$F" "$SAIDA" work/annotations/review.anotar.jsonl > validacao/pareceres/qa_estrutural.json
```

Os dois precisam passar. Se o original já trazia anotações
(`prior_annotations` maior que zero), o script acusa a diferença na contagem;
aceite só se a diferença for exatamente esse número e registre no trace.

QA visual: renderize o original e o comentado e entregue as imagens, o
relatório da anotação e `prompts/visual_qa.md` a um subagente novo.

```bash
.venv/bin/python - "$SAIDA" work/render/comentado <<'PY'
import sys, pathlib, fitz
doc = fitz.open(sys.argv[1]); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
for i, p in enumerate(doc, 1):
    p.get_pixmap(dpi=110).save(out / f"p{i:03d}.png")
PY
```

Repita com `"$F" work/render/original`. Para DOCX, converta antes com
`soffice --headless --convert-to pdf --outdir work/render <arquivo>`; a
conversão não mostra os balões, então ela serve para conferir que o corpo do
texto não mudou, e os comentários se conferem pelo `.comments.json`.

No PDF a imagem mostra o realce, não o texto do balão: o realce confere a
posição, o relatório confere o conteúdo. Todas as páginas são inspecionadas.
O subagente grava `qa_visual.json` com `status` (`PASS` ou `FAIL`),
`pages_inspected` e `defects`. Com `FAIL`, corrija a causa e refaça a partir
de `annotate`; não promova a entrega.

## 9. Entrega

1. **Rastreabilidade:** uma linha por comentário em
   `validacao/rastreabilidade.csv`, nas colunas do cabeçalho existente, com
   `artifact` igual ao caminho da entrega. Escreva com o módulo `csv` do
   Python (os textos têm vírgula) e remova antes as linhas antigas do mesmo
   `source`.
2. **Parecer:** `validacao/pareceres/parecer.md` com o documento e o hash,
   contagem de candidatos, aprovados, rejeitados e revisados, os problemas de
   prioridade alta em uma linha cada, os rejeitados com motivo, as pendências
   e o resultado dos dois QA.
3. **Métricas:** uma linha em `.jangada/metrics.jsonl` com `ts`, `source`,
   findings por revisor, candidatos, aprovados, rejeitados, comentários
   inseridos, âncoras corrigidas e o status dos QA.
4. **Estado:** `status: "DELIVERED"` em `.jangada/state.json`.
5. **Checklist:** percorra `validacao/checklist.md` e relate ao usuário cada
   item que não passou.

Na resposta ao usuário: caminho da entrega, número de comentários por
categoria, o que foi rejeitado e por quê, e as pendências. Se algum critério
de `acceptance` do `projeto.yaml` não foi cumprido, diga qual; não declare a
entrega concluída.
