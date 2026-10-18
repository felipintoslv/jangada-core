# Testes adversariais

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

## Reprodução

A partir da worktree de correção:

```sh
python3 -B docs/estabilizacao/correcao-p0/evidencias/executar.py
```

O executor cria HOME/XDG/Git sintéticos, impede operações Git proibidas e chamadas de instalação/serviços. Não chama modelos reais. --alterados revalida P0, dez casos seguros de baseline, shellcheck e diff, mantendo os logs dos outros grupos. Os comandos exatos e tempos estão em resultados.json.

`testes/verificar.sh` foi efetivamente chamado com esses limites. validar.sh, isolar.sh, versao.sh, update.sh e baseline integral incluem comandos proibidos ou limpeza fixa: são BLOQUEADOS antes do corpo quando alcançados. Dois casos de baseline com merge/reset são excluídos explicitamente da seleção segura e não recebem PASSOU. O agregado atingiu 90 segundos e foi encerrado junto com seus filhos. Não é resultado verde integral.

## Grupos obrigatórios

Condição comum: projeto Git descartável, tarefa T1 com fonte 2,4,6, artefato Média = 4 e REVIEW_REQUIRED. Cada método altera somente sua própria cópia.

| Grupo | Condição e ataque | Resultado esperado e observado | Evidência | Categoria |
|---|---|---|---|---|
| A | SQLite, extra gravável, caminho alternativo, ligação física, descritores e opção sem isolamento | Escrita recusada; banco preservado; descritor adicional EBADF | confianca-p0.log; ataques-bubblewrap.jsonl | PASSOU |
| B | JSON falso, acesso por API sem variável, executor agy/revisores Claude/agy simulados | Sem aprovação válida ou escrita; falha protegida; controlador recolhe saída | Mesmos logs, processos Bubblewrap reais | PASSOU |
| C | Alterar objeto ou copiar recibo entre tarefas | Recibo não corresponde; REVIEW_REQUIRED | test_C_* | PASSOU |
| D | Política independente sem revisão; rejeição humana | Aprovação recusada; rejeição identificada e tarefa retomável | test_D_* | PASSOU |
| E | Modelo ausente/igual/inventado e revisão só por rótulo | Zero revisões legítimas; recusas registradas | test_E_*; supervisao.log | PASSOU |
| F | Pareceres de aprovação/rejeição e rodadas intermediárias | Conteúdo integral recuperável após encerramento | test_F*; arquivo-sintetico.json | PASSOU |
| G | Prompt local adulterado/removido | Original recuperável do registro inicial protegido | test_G_*; test_FG_* | PASSOU |
| H | Falha de publicação/fsync, contexto ausente, ligação física | Encerramento recusado, originais mantidos | test_H_* | PASSOU |
| I | Arquivar/encerrar repetidamente | Um arquivo por conteúdo, sem corrupção | test_I_* | PASSOU |
| J | Outro projeto, código do controlador, arquivo histórico, foto indevida | Sem alteração autoritativa; escrita na pasta oculta é efêmera | test_J_*; Bubblewrap real | PASSOU |
| K | Fila, reservas, retomada, supervisão, cadastro e consultas | Protocolos seguros compatíveis; limites documentados | Suites abaixo | PASSOU nos casos seguros executados |
| L | --integrar em sessão com/sem ramo | Bloqueado; sessão/HEAD/artefatos preservados | fim.log; test_L_* | PASSOU |

O fsync é uma falha simulada para testar recuperação. Isso não substitui os testes reais de montagem. Provedores são simulados; o bloqueio de suas escritas usa Bubblewrap real.

## Cada cenário P0

A saída confianca-p0.log identifica individualmente os 32 métodos, condição expressa no nome e resultado observado. O código reproduz as condições iniciais e as asserções, sem testes ignorados neste ambiente.

| Método | Resultado observado |
|---|---|
| test_A_caminho alternativo_simbolico_nao_reabre_banco | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_A_configuracao_nao_desliga_fronteira | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_A_descritor_adicional_nao_e_herdado | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_A_descritor_padrao_para_banco_recusado | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_A_ligacao_fisica_recusada_antes_de_iniciar | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_A_sqlite_real_somente_leitura_mesmo_com_extra | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_dependencia_nao_libera_por_sqlite_forjado | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_estado_sqlite_forjado_nao_e_decisao | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_executor_delegado_realmente_isolado_do_sqlite | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_interface_recusa_executor_mesmo_sem_variavel | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_json_de_supervisao_inventada_nao_aprova | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_revisor_agy_realmente_isolado_do_sqlite | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_B_revisor_claude_realmente_isolado_do_sqlite | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_C_aprovacao_outra_tarefa_nao_pode_ser_reutilizada | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_C_artefato_alterado_invalida_decisao | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_D_reprovacao_manual_nao_finge_independencia | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_D_sem_revisao_independente_nao_aprova | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_E_rotulo_modelo_nao_registra_revisao_inexistente | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_FG_encerramento_preserva_integrais_e_contexto | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_F_reprovacoes_e_rodadas_intermediarias_preservadas | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_G_prompt_inicial_protegido_mesmo_apos_adulteracao_local | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_H_caminho alternativo_de_arquivo_recusado_antes_de_criar_pastas | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_H_contexto_ausente_nao_encerra_com_aprovacao | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_H_falha_fsync_nao_apaga_documentos | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_H_falha_publicacao_preserva_originais | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_H_ligacoes_em_evidencias_bloqueiam_limpeza | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_I_arquivamento_repetido_sem_duplicacao | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_J_codigo_do_controlador_nao_pode_ser_alterado | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_J_evidencia_protegida_nao_persiste_escrita_real | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_J_foto_nao_pode_reexpor_autoridade | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_J_isolamento_nao_altera_outro_projeto | PASSOU, resultado e invariantes conferidos pelas asserções |
| test_L_integracao_permanece_bloqueada | PASSOU, resultado e invariantes conferidos pelas asserções |

## Invariantes

INV-01/02/07: A/B/E. INV-03/06: D/E e supervisao.py. INV-04/05: C e baseline segura. INV-08: F/G, recuperação sintética. INV-09: H. INV-10: I. INV-11: J. INV-12: L/fim. INV-13: estado-repositorios.json e estado separado dos testes. INV-14: suites executor, operacional, supervisao e restaurar. INV-15: B/E e recusas persistentes. Garantias limitadas ao modelo de ameaças documentado.

## Suites diretas

| Suite | Cenários | Resultado |
|---|---|---|
| orquestracao | 30 | PASSOU |
| executor | 42 | PASSOU |
| supervisao | 26 | PASSOU |
| operacional | 36 | PASSOU |
| deterministico | 26 | PASSOU |
| delegacao | 8 | PASSOU |
| acompanhamento | 12 | PASSOU |
| metricas-projeto | 20 | PASSOU |
| painel-orquestracao | 3 | PASSOU |
| tarefas | 67 | FALHOU: 4 casos de socket; 63 passaram |
| confianca-p0 | 32 | PASSOU |
| baseline-segura | 10 | PASSOU |

Total de cenários Python diretos: 312; 308 passaram e quatro produziram falha crua de socket na interface. Esses quatro são BLOQUEADOS por infraestrutura na análise, não aprovados. Encerramento: 92 asserções shell; retomada: 30, todas passaram. Não somar novamente os casos repetidos pelo agregado.

Shellcheck dos seis scripts alterados e git diff --check passaram. Nenhum modelo real, serviço real ou integração remota foi testado. Métricas e tempos estão em metricas.json/resultados.json; manifesto SHA-256 cobre os arquivos de evidência.
