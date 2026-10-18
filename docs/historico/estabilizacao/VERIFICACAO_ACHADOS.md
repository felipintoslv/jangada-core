# Verificação do registro documental

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

Executado `bash testes/verificar.sh` em cópia temporária do código de main (`bf7a5f1`) com os novos documentos. HOME, XDG, temporários e runtime próprios; sem credenciais ou configuração ativa. Estado sintético preservado em `/tmp/jmain-brza9qwl`.

Resultado bruto: código 1, duração 172,957 segundos, seis grupos com falha: monitoramento, validar, isolar, tarefas, conversa e delegar. O log demonstra restrições de sockets (`PermissionError: Operation not permitted`) e Bubblewrap (`Failed to create NETLINK_ROUTE socket`). Há falhas derivadas dessas restrições. Não foi feita classificação individual de todos os casos restantes; os grupos não são considerados aprovados. A suíte não valida produção neste ambiente. Não se trata de reexecução da versão P0.

Resultado estruturado: `arquivo/evidencias:docs/estabilizacao/verificacao-main/resultado.json`.
Log integral: `arquivo/evidencias:docs/estabilizacao/verificacao-main/verificar.log`
(commit `7a9d1e5`).

O manifesto conferiu SHA-256 dos 262 arquivos importados. O índice contém somente README e docs/estabilizacao, sem alterações em bin, default, install ou migrations. A formatação dos novos documentos consolidados passou em `git diff --cached --check` para esses arquivos. A verificação global de espaços apontou espaços finais nos logs brutos importados; os logs foram preservados byte a byte para manter as evidências e seus hashes. Não foram normalizados para ocultar o aviso.

A instalação foi conferida somente para leitura: os cinco componentes registrados em INSTALACAO_CONFERIDA.json continuam diferentes da P0, ou ausentes. Nenhuma atualização da instalação, configuração, serviço, push, merge ou tag foi realizada. Entrada em produção validada permanece pendente da incorporação das proteções P0 e da verificação da versão instalada.
