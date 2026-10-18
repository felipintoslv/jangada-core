# Ambiente isolado

Registro histórico do ensaio; referências a `main` e à instalação retratam
a data desse registro. Veja o [estado atual](../../README.md).
Evidências, manifestos e scripts citados estão no ramo `arquivo/evidencias`,
commit `7a9d1e5`, nos caminhos originais.

PASSOU: cópia via `git archive`, estado sintético separado em `/tmp/jangada-p1-342gtope`, com HOME, quatro XDG, TMPDIR, TMUX_TMPDIR, banco, sockets, sessões, logs, projetos e worktrees próprios. Configuração desativa acesso remoto e exige isolamento. Guardas recusam operações Git proibidas e comandos administrativos; não substituem Bubblewrap.

`evidencias/configuracao-efetiva.json`, `isolamento-preventivo.json`, `oraculo-inacessivel.stdout.log` demonstram ocultação de `$HOME`, recusa de escrita autoritativa e impossibilidade de ler o gabarito por caminho direto, symlink ou `/proc/self/root`. Nenhum socket de consulta ao oráculo foi exposto. Testes P0 verificam descritores adicionais e padrão, links e interfaces. A semente e referências ficam em `privado/`, fora da montagem dos processos de ensaio.

Modelos não foram iniciados. Credenciais não foram copiadas nem configurações globais alteradas. Pacotes R foram apenas consultados por metadados, sem instalação. R base executou o oráculo; Shiny instalado não comprova aplicação funcional. Bloqueios: socket INET EPERM, bind UNIX EPERM e perfil sem rede Bubblewrap com NETLINK_ROUTE EPERM. Evidências nos logs correspondentes.

Reprodução deve usar uma nova raiz sintética e atualizar `origem-ensaio.json`/ambiente; nunca apontar esses scripts ao estado ativo. Os relatórios conservam comandos e caminhos do ensaio efetivamente executado. `integridade-final.json` comprova bytes da cópia e estados Git finais.

Versão avaliada: `17178ded546642e3246bfe3bd5c33df8da821874`. Resultados externos às três worktrees. Não houve execução de modelos reais, chamadas externas, mudanças de produção, merge, push ou tags.
