# Relatório final da correção P0

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

**CORREÇÃO P0 VALIDADA**, para os dois ataques reproduzidos e a fronteira de confiança definida. Não é declaração de prontidão da baseline ou de qualidade científica das entregas.

## Resultado

P0-A: o executor não escreve no SQLite autoritativo, políticas, decisões ou objetos; montagens opcionais não reabrem esse acesso. Aliases e descritores herdados foram testados. Campos COMPLETED/independência fornecidos pelo executor não bastam: o controlador verifica política, versão do artefato e recibo protegido. Rótulos de modelo sem execução são recusados. Identidade ausente/igual impede supervisão independente.

P0-B: encerramento arquiva bytes integrais de pareceres, marcas, prompts, metadados e rodadas antes da limpeza. Contexto preserva candidato, árvore/base e identidade com nível de confiança. Falhas de leitura, integridade, contexto ou publicação mantêm os originais. Histórico por conteúdo é repetível e protegido contra o executor. Prompt inicial sobrevive à adulteração local. Objetos Git históricos mantêm referências permanentes.

As duas vulnerabilidades anteriores estão demonstradas pelos registros original/baseline verificados contra o manifesto da auditoria. A correção tem 32 cenários P0 aprovados, sem ignorados, com Bubblewrap real. Foram registradas 14 tentativas de isolamento, das quais três recusadas na conferência anterior ao lançamento; as demais executaram processos isolados. Três usam provedores simulados nos comandos reais de lançamento, sem rede externa.

## Validação e compatibilidade

312 cenários Python diretos: 308 passaram; quatro falhas de interface decorrem de sockets negados. Suites essenciais de fila, reservas, artefatos, supervisão, retomada, persistência, validação e encerramento passaram nos cenários executados. Também passaram 92 asserções de encerramento e 30 de retomada. Recuperação dos documentos integrais foi executada em diretório novo. Logs e comandos ficam em evidencias, com manifesto.

`testes/verificar.sh` foi executado com limites: alguns grupos contêm operações proibidas e o agregado foi encerrado aos 90 segundos. Monitoramento/conversa/interface sofrem restrições de comunicação local. Nenhum bloqueio foi apresentado como aprovação; a verificação integral continua pendente.

Há incompatibilidades deliberadas: isolamento não pode ser desativado; conclusões legadas sem recibo exigem reconferência; revisão final de tarefa por mero rótulo de modelo é recusada. Aprovação humana segue a política e não representa revisão independente. Supervisão intermediária e revisão Git conservam seus protocolos. Não foi introduzida API nova de revisão final de tarefa.

Principal continua em bf7a5f1, limpa; baseline em 1fa3d9c, com os relatórios não rastreados preexistentes e sem diferenças rastreadas. Toda implementação fica na worktree jangada-confianca-p0. Instalação ativa, projetos reais e configurações globais não receberam comandos de modificação. Integração automática permanece bloqueada, sem merge, push ou tag.

## Riscos residuais e próxima etapa

Não houve chamada de modelos reais. Independência semântica e autenticidade remota não são garantidas por nomes distintos. Controle irrestrito da conta está fora do modelo de ameaça. Parecer autorizado pode estar errado; corroboração e testes externos permanecem necessários. Histórico cresce sem rotação; arquivo incompleto pode exigir intervenção supervisionada. Ver LIMITACOES.md.

Recomenda-se auditoria posterior do ciclo completo com executor e revisor reais autorizados, identidade distinta, rejeição/correção, encerramento e consulta histórica, em ambiente com sockets/D-Bus permitidos. Reavaliar o fluxo de revisão independente final da fila antes do uso real. Não congelar a baseline com base apenas nesta missão.

## Versionamento local

- `54d8edc53f2f`: fix(confianca): proteger a fila e verificar decisões de conclusão
- `f9e92b82a974`: fix(revisao): preservar evidências antes de encerrar sessões
- `390e8c7efc8a`: fix(testes): verificar ataques à autoridade e recuperação do histórico

A documentação e as evidências ficam em um quarto commit local, identificado pelo HEAD final apresentado na resposta. Os hashes integrais da implementação estão em evidencias/commits-implementacao.json. Nenhum commit foi publicado.
