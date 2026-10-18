# Estado da estabilização

Em 16/10/2026, o código P0 já está incorporado em `main`, desde `19f5569`
(09/10/2026). A validação P1 continua **INCONCLUSIVA**.
Esse estado do código não certifica a instalação ativa de cada máquina.

## Prova da incorporação P0

A comparação de `bf7a5f1` com `17178de` identifica 26 arquivos fora de
`docs/`. Desses, 25 têm os mesmos bytes em `19f5569`; somente `README.md`
difere. Isso inclui os comandos, as proteções e os testes da correção P0.
A conferência pode ser repetida sem executar código dessas versões:

```sh
git diff --name-only bf7a5f1 17178de -- . ':!docs/'
git diff --name-only 17178de 19f5569 -- \
  $(git diff --name-only bf7a5f1 17178de -- . ':!docs/')
```

O segundo comando lista somente `README.md`. O antigo `ACHADOS_ATUAIS.md`
foi escrito antes dessa incorporação e não representava o estado posterior.
Os relatórios abaixo conservam as conclusões da data do ensaio.

## O que P1 não demonstrou

Os ensaios registraram 32/32 cenários P0, 67/67 testes de interface no
terminal compatível e 294 conferências de indicadores em sete cenários.
Isso não demonstra o ciclo econômico completo com modelos reais de famílias
distintas, reprovação, correção, nova revisão, aprovação protegida e
recuperação integral do histórico dessa atividade.

A autenticação do agy falhou no ambiente sintético; a última sonda retornou
NoReply. O ensaio nativo usou executáveis instalados diferentes da P0.
A investigação foi interrompida; não há aprovação dos 30 dias experimentais.
Detalhes e limites estão no [relatório P1](validacao-p1/relatorios/RELATORIO_FINAL.md).

## Relatórios mantidos

- [Correção P0](correcao-p0/RELATORIO_FINAL.md), [causa raiz](correcao-p0/CAUSA_RAIZ.md)
  e [limitações](correcao-p0/LIMITACOES.md).
- [Índice P1](validacao-p1/README.md) e [execução dos modelos](validacao-p1/relatorios/EXECUCAO_MODELOS.md).
- [Segurança operacional](SEGURANCA_OPERACIONAL.md) e [backup e recuperação](BACKUP_RECUPERACAO.md).
- [Prontidão da baseline](RELATORIO_PRONTIDAO.md) e [testes da baseline](TESTES_BASELINE.md).
- [Preparação da atualização em 09/10](ATUALIZACAO_LOCAL_20261009.md), registro histórico da instalação então observada.

## Evidências arquivadas

Logs, JSON, dados, manifestos e scripts foram retirados do ramo principal.
O conteúdo original permanece no ramo `arquivo/evidencias`, commit
`7a9d1e5` (a publicação desse ramo cabe ao dono).
Para consultar um arquivo sem mudar de ramo:

```sh
git show arquivo/evidencias:docs/estabilizacao/validacao-p1/SHA256SUMS
git show 7a9d1e5:docs/estabilizacao/correcao-p0/evidencias/resultados.json
```

Os diretórios originais são `docs/estabilizacao/correcao-p0/evidencias/`,
`docs/estabilizacao/validacao-p1/evidencias/`,
`docs/estabilizacao/validacao-p1/scripts/` e
`docs/estabilizacao/verificacao-main/`. Manifestos P1 também citam dados
privados externos que nunca foram incorporados ao Git.
