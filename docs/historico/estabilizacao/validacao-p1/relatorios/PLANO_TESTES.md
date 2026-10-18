# Plano de testes P1

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Versão 17178ded546642e3246bfe3bd5c33df8da821874, cópia exportada e sem mudanças de produção. Worktrees principal, baseline e P0 preservadas. Todos os artefatos em raiz sintética ou neste diretório novo.

1. Guardas de caminhos e separação de estado, leitura de arquitetura e dependências. Executado na preparação.
2. Oráculo independente Python/R, duas sementes privadas e critérios fixados antes dos modelos. Somente dados artificiais.
3. Isolar e sondar canais privados, links e interfaces do executor; gabarito não pode aparecer na montagem.
4. Cadastrar projeto e atividade com critérios reais pelo backend. Sem declarar execução de IA.
5. Reexecutar ataques P0 e recuperação histórica sintética; inspecionar estado posterior, não só stderr.
6. Preparar oito defeitos A1 a A8 e comparar com testes públicos/privados. Não atribuir detecção a revisor inexistente.
7. Execução, dois revisores cegos e correção por modelos reais somente se acesso previamente autorizado e infraestrutura compatível. Ausência dessas condições é BLOQUEADO, não substituída por mocks.
8. Componentes backend e interface; comunicação bloqueada por sockets será registrada como tal.
9. Nova rodada determinística, mesmas regras e novos dados; ensaio cego com IA depende de concluir a primeira rodada real.
10. Manifestos, métricas separadas, reconstrução somente por histórico arquivado e classificação A/B/C.

Segurança: sem instalar, atualizar, publicar, merge/rebase/reset/clean/tag, alterar globals ou usar projetos reais. Nenhuma credencial será lida/copieda e nenhuma chamada externa realizada nesta execução sem autorização prévia específica. Integração permanece bloqueada. Custos de modelos reais: zero nesta execução.

Modelos reais e comunicação integrada são essenciais para P1 VALIDADA. Se bloqueados, P1 INCONCLUSIVA, salvo falha crítica confirmada que imponha P1 REPROVADA.
