# Alterações

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

| Componentes | Correção | Evidência |
|---|---|---|
| bin/jangada-isolar | Isolamento obrigatório, autoridade somente leitura, histórico oculto, recusa de aliases/canais, fechamento de descritores | Grupos A/J, Bubblewrap real |
| default/orquestracao/confianca.py | Guarda física, recibos por conteúdo, leitura estável e arquivo integral | Grupos B a J |
| estado.py, nucleo/consultas.py, painel/orquestracao.py | Conferir COMPLETED, dependências e artefatos; reconferência manual de legado | B/C e suites operacional/executor/painel |
| supervisao.py, executor.py | Comprovante ligado a execução, tarefa, digest e modelos distintos | B e supervisao.py |
| bin/jangada-delegar | Agente agy efetivo em Bubblewrap | Executor simulado no comando real |
| bin/jangada-agente e jangada-agentes | Criação/retomada isoladas e registro inicial protegido | restaurar.sh e G |
| bin/jangada-validar | Contexto por rodada, refs Git históricas, trava, revisores isolados e saída coletada pelo controlador | F/G e revisor simulado no comando real |
| bin/jangada-agente-fim | Arquivar antes da limpeza e bloquear --integrar também sem ramo próprio | F a L e fim.sh |

Nenhum serviço permanente, provedor, armazenamento externo ou sistema genérico de autorização foi adicionado. Integração automática permanece bloqueada.

## Compatibilidade necessária

--sem-isolar e configuração antiga igual a zero não desativam Bubblewrap. Ausência do isolador impede lançamento.

`jangada-task revisar --revisor <modelo>` com texto/rótulo fornecidos é recusado: não comprova execução. Revisão humana autorizada, rejeição, reservas e retomada continuam. Política independente não é satisfeita por declaração humana. Supervisão intermediária mantém o protocolo executado; criar uma API nova de revisão final por modelos fica fora do escopo.

Conclusões legadas sem recibo aparecem como REVIEW_REQUIRED. Não há migração que legitime estados antigos. Reconferência humana nova só pode aprovar quando a política permitir. Arquivamento legado com contexto obrigatório ausente conserva originais e exige reconferência.

Expectativas dos testes foram ajustadas para identidades distintas e bloqueio antecipado de dependências adulteradas; nenhum caso foi removido. Uma regressão temporária na consulta do painel foi corrigida e seus três testes voltaram a passar.
