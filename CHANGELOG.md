# Registro de mudanças

Gerado das mensagens de commit por `jangada-versao --lancar`; não edite
à mão. A versão instalada aparece em `jangada-versao`.

## Não lançado

- core: a raiz do Core passa a se chamar `JANGADA_CORE_PATH` (antes `JANGADA_PATH`) e o local de instalação padrão, `~/.local/share/jangada-core`. O Core ignora o `JANGADA_PATH` que o Shell exporta na sessão. A nova etapa `install/20-comandos.sh` grava em `~/.local/bin` um invólucro para cada comando de `bin/`.

## Planejado para v0.4.0

- Remover os links de compatibilidade de `bin/` e `default/`.
  Quem usa `bin/jangada-*` deverá chamar o comando pelo PATH instalado ou
  pelo caminho do módulo (`core/bin/`, `shell/bin/` ou `monitor/bin/`).
  Referências a `default/` deverão usar o arquivo em `core/`, `shell/`
  ou `monitor/`, conforme o [mapa de caminhos](docs/modularizacao-3.0/01-inventario.md).
  Os links permanecem nesta versão; a retirada exige adaptar a resolução
  de `jangada-config` antes de permitir chamadas diretas aos módulos.

## 0.2.0 (2026-10-01)

### Novidades

- agentes: oferecer Codex com revisão e delegação ao agy Flash
- painel: reunir consumo de Claude, Codex e Ollama com cobertura
- pescador: adicionar janela de conversa e auditoria com isolamento
- agentes: integrar Codex com isolamento e revisão
- delegar: suporte a destino local com ollama e fatiamento
- delegar: parametros e isolamento para delegacao local
- pescador: adicionar suporte a colagem de textos e listas multilinhas
- painel: reestruturar painel com data storytelling e diagnosticos dinamicos
- painel: adicionar nuvem de palavras e grafico de termos na aba pesquisas
- pescador: adicionar decomposicao atomica de busca e documentacao arquitetural
- pescador: adicionar bancada de auditores, pares cruzados e rodadas de purificacao
- pescador: adicionar conversas encadeadas, atalhos e integracao ao painel
- pescador: adiciona aplicacao conversa-de-pescador com auditoria e voz
- update: com allowed_signers, só entram commits assinados
- painel: o cache guarda só os últimos JANGADA_PAINEL_RETENCAO dias
- docs: registra o modelo de ameaça e as respostas às perguntas da auditoria
- docs: documenta cada processo com fluxogramas e reúne as boas práticas
- agentes: adiciona subagentes auditor, arquiteto, otimizador e redator
- agentes: indicadores de subagentes no terminal e no painel
- agentes: registro de delegações e dos subagentes por entrega
- agentes: jangada-delegar manda leitura, pesquisa e verificação ao agy Flash
- agentes: papéis de subagente no Claude e no agy e item de delegação no protocolo
- painel: redes de retrabalho, pontos quentes e espaço de ferramentas; módulo na waybar
- painel: coletor em Parquet e app Shiny com revisão, consumo e tempo
- agentes: histórico de estados em eventos-agentes.jsonl
- validar: lintr aponta a variável sem uso em R
- agentes: skills do jangada também no agy

### Correções

- codex: preservar confiança dos hooks e atualizar estado na barra
- delegacao: usar medição do host quando nvidia-smi devolve erro
- codex: passar confiança como tabela no argumento de configuração
- codex: confirmar confiança da pasta ao iniciar a sessão
- interface: corrigir microfone e limitar sinais à sessão
- agentes: exigir isolamento em todas as sessões Codex
- isolar: entrega unica de SIGINT no grupo e filtragem de tags think
- isolar: colheita de codigo definitivo apos sinais e isolamento de sleep
- isolar: restauracao de sinais padrao para bwrap, mock de pgrep e documentacao de intervalo
- isolar: encerramento atomico de filhos do monitor e intervalo configuravel
- isolar: pasta de marcas com montagem de diretorio e renovacao dinamica
- isolar: repasse de sinais com stdin interativo e fatiamento seguro
- isolar: bwrap em primeiro plano, teste de stdin e refinamento de sinais
- delegar: correcoes no repasse de sinais, isolamento e fatiamento
- delegar: ajustes no isolamento, sinais e tratamento de marcas temporais
- delegar: renovacao de marcas, validacao previa de contexto e modelo de ameacas
- delegar: ajustes no isolamento, protecoes e argumentos posicionais
- delegar: correcoes na delegacao local apos revisao tecnica
- pescador: remover atalhos padrao para evitar conflito com o menu jangada
- pescador: tipar retorno do autor como tupla eliminando falso positivo de conexao
- pescador: resolver executaveis agy e claude no PATH e tratar falha de conexao
- instalador: remove install-macos e ajusta isolamento e testes
- hooks: configuração vazia não passa mais por hooks instalados
- revisao: a aprovação que o --integrar aceita é a feita fora do isolamento
- update: checkupdates sem atualização não é dado como falha
- isolamento: o agy regrava o agentapi numa camada temporária
- painel: os indicadores de subagentes só releem o que mudou
- agentes: o Bash do leitor só roda comandos de leitura
- painel: o app cobra um token que o isolamento oculta
- validar: o .jangada/validar.sh roda pelo jangada-isolar
- verificar: o diagnóstico trata o log como dado
- snapshot: os snapshots do agente têm limpeza própria
- bluetooth: parear não implica confiar
- agy: o worktree só herda a confiança do repositório principal
- instalacao: o install.sh recusa a cópia de trabalho e os worktrees
- hypr: o bootstrap tira a pasta atual do caminho de módulos
- barra: todo clique que abre janela roda com setsid -f
- validar: o R não lê o .Rprofile, o .Renviron nem o .lintr do worktree
- validar: registra por que o resumo de subagentes ficou de fora
- agentes: documenta os indicadores do jangada-subagentes e lista os papéis novos no teste
- filtrar: avisa que a saída condensada esconde o código de saída
- consumo: ignora mensagens com data inválida
- validar: confere a pasta dentro do TMPDIR pelo caminho inteiro
- shell: descobre o JANGADA_PATH pelo caminho do jangada-shell.sh
- importar: decodifica os textos do niri sem unicode_escape
- barra: atualiza o indicador de agentes por sinal e protege os caminhos
- hypr: põe aspas nos caminhos e lê o jangada.conf como o bash
- painel: confere a subida do app sem perder a página no cano
- rede: alinha o teste ao formato do nmcli e cobre SSID com dois pontos
- agentes: liga os subagentes auditor, arquiteto, otimizador e redator
- painel: confere o htmltools junto dos outros pacotes R
- shell: adiciona diretiva shellcheck e valida destino no mapear
- painel: otimiza leitura incremental, healthcheck do app e limpeza de testes
- agentes: sincroniza leitura de estado sob trava, evita recriacao e trata zsh
- interface: corrige escape de argumentos, parsing de config, rede e seguranca
- instalacao: corrige idempotencia, travas, pacote fakeroot e update
- agy: fecha os itens médios da auditoria sobre o agy e a delegação
- painel: fecha os itens médios da auditoria sobre o painel
- validar: fecha os itens médios da auditoria sobre o jangada-validar
- seguranca: corrige os itens altos da auditoria de 27/09
- docs: alinha a documentação ao isolamento e à atualização novos
- isolamento: fecha as fugas do jangada-isolar apontadas pela auditoria
- painel: CI sem cmp e instalação simulada sem escrita no HOME
- versao: --ajuda responde sem repositório git válido

### Outras mudanças

- docs(revisao): adicionar benchmark de agente local com verificacao
- docs(regras): lista as exceções à regra 1 e testa que estão completas
- docs(auditoria): registra as perguntas 6, 10 e 13 como resolvidas

## 0.1.0 (2026-09-26)

### Novidades

- versao: versões com tag e CHANGELOG gerado dos commits
- agentes: isola o agente no bubblewrap com o jangada-isolar
- validar: registra cada rodada em validar.jsonl e resume com --metricas
- validar: procura segredos com o gitleaks nas linhas acrescentadas
- escrita: fecha lacunas em relação ao benchmark
- validar: revisor confere regras objetivas de escrita
- skills: acrescenta skills de relatório técnico e acadêmico
- agente: acrescenta regras de código R ao protocolo em projetos R
- validar: roda o lintr nas linhas R alteradas antes do revisor
- protocolo: acrescenta regras de escrita para os agentes
- suporte macos, console de agentes focado e atalhos na waybar
- agente-fim: atualiza cópia instalada após integração e repassa raiz e integrado a pos-agente-fim
- agente: suporta opção --revisor e seletor com auto-revisão
- validar: suporta auto-revisão pelo mesmo modelo e opção --revisor mesmo
- agentes: adiciona perfis agy-agy e claude-claude para auto-revisão
- waybar: adiciona módulos nativos systemd-failed-units, privacy e disk

### Correções

- agente: --janela repassa o --sem-isolar ao terminal novo
- validar: nomes, renomeações e métricas apontados pela revisão
- validar: conflito e sintaxe conferem também arquivos novos
- validar: cada entrega aprovada reinicia base e rodadas
- resolve apontamentos de auditoria tecnica com claude e portabilidade macos
- agente-fim: permite encerrar sessoes diretas com --integrar sem erro fatal
- resolve inconsistencias gerais e cobertura de testes
- validar,agente: ajusta precedência de revisor e coerência de auto-revisão
- waybar: preserva hide-on-ok na barra em pé e remove format-ok inalcançável
- ajustes da revisão do tema e do papel por tela
- detecta systemd-boot sem precisar de root
- caminho na shell, corrida no estado do agente e Lua 5.5

### Outras mudanças

- ci: roda os testes e simula a instalação num contêiner Arch
- style: aplica tom do papel de parede ao icone da jangada no waybar
- docs(revisao): registra parecer e avaliação da atualização automática pós-integração
- docs(agentes): documenta auto-revisão, novos perfis e opção --revisor
- benchmarking: revisão de escopo, adjetivação e lições de segurança
- benchmarking: revisão do Claude sobre o README do agy
- docs(waybar): corrige fontes do cliphist e screenrecorder no benchmark
- docs(waybar): benchmarking de repositórios e módulos do waybar
- agentes: revisão cruzada no jangada-validar e fim do jangada-par
- agy: correções da revisão (modo direto no jangada-validar, status com Markdown, limpeza do prompt, JSON no verificar)
- agentes: agy como agente da sessão, com hook próprio, seletor de agente e jangada-validar (Claude só revisa o diff)
- skill: compartilhamento de tela, tamanho lógico no seletor e custo do monitor 4K
- agentes: lista em janela espera Enter depois do Alt+I e do Ctrl+X
- auditoria do fechamento: parecer do agy (15 itens) e avaliação; 13 aplicados no todo ou em parte
- README: ciclo dos agentes, várias máquinas, canal e testes; revisao/README.md com índice e cabeçalho fixo; situação dos itens do benchmark
- portabilidade: regra do DP-3 sai de base.css e a skill deixa de citar esta máquina; skill de agentes cobre avaliação, hooks, restauração, perfis e ganchos
- importar: niri para usuario.lua, monitores.lua e jangada.conf com extensão .importado; lista e shell focam a janela aberta
- testes/aninhado.sh: carrega a configuração num Hyprland aninhado
- update: canal, conferência do boot e da NVIDIA; ganchos do usuário
- verificar: --diagnostico e --agente; chaves JANGADA_REPO e JANGADA_CANAL
- jangada-consumo: tokens do Claude no bloco de 5 horas
- agente: perfis em ~/.config/jangada/agentes/NOME.conf
- agentes: --integrar, --restaurar e --anterior
- agente: --prompt e --prompt-arquivo; nome de ramo sem acento
- hooks: id da conversa, SessionStart/SessionEnd e tipo da notificação
- par: Claude avalia cada apontamento do agy antes de implementar
- agentes: jangada-agente-fim recusa opção e sessão inexistente
- agentes: corrige nomes com acento no preparo, reflink entre subvolumes e campos vazios no painel
- revisao: parecer do agy sobre os itens 1 a 3 e avaliação
- agentes: SUPER+N foca o próximo agente que espera
- agentes: skill do jangada para o Claude Code
- agentes: prepara o worktree novo com o que o git não leva
- par: limita o prompt do agy em bytes, não o diff em caracteres
- revisao: compara o jangada com gerenciadores de agentes e camadas de Hyprland
- waybar: solta os terminais abertos por clique na barra
- tema: cores fieis ao papel de parede, modelo do sddm e papel sem corte por tela
- sddm: tema de login no estilo do menu e sessao exclusiva sem mover arquivos de pacotes
- sessao: acoes rapidas de energia, tema cordel no hyprlock e exclusividade sddm
- waybar: compensa tamanho de fonte no monitor 4K (DP-3)
- waybar: correcoes da revisao tecnica de ilhas e agentes
- waybar: layout em ilhas flutuantes e enriquecimento do modulo de agentes
- migrar: a simulação não grava mais a marca da migração
- revisao: corrige a nota do Noctalia, que saiu do AUR
- revisao: fecha o benchmarking da barra e registra o Noctalia parado
- barra: posição escolhível nas quatro bordas, com formatos só de ícone em pé
- barra: escala de medidas no lugar dos números soltos
- fuzzel: jangada-energia usa a função compartilhada
- instalador: declara o less, que o mudancas precisa
- shell: revisar diz ao agy para não executar comandos
- jangada-par: captura a resposta do agy por cano, não por arquivo
- barra: temperatura resolve o sensor por dispositivo, não por número
- energia: menu de perfil, bateria e sessão no clique da bateria
- revisão: compara a barra do jangada com a do Omarchy
- barra: mostra a janela em foco entre os agentes e o relógio
- barra: clique direito da rede abre o nmtui
- agentes: escolhe o parecer sem ls e cobre o subshell no verificar
- shell: conserta o diff, o concluir e o caminho do subshell
- calendario: comandos add, listar e importar na linha de comando
- agentes: prévia do seletor imune à expansão de igual do zsh
- barra: aplica o que o benchmarking com o Omarchy apontou
- jangada-par: repete a chamada do agy quando ela volta vazia
- comandos de áudio, bluetooth, rede e calendário na barra e no menu
- jangada-par: evita estourar o limite de tokens na revisão
- painel respeita ciclos encerrados em concluido ou aguardando
- jangada-par: aplica a revisão do Antigravity e conserta o prompt dele
- jangada-par: cor e negrito na saída, e limpeza do que o ciclo cria
- jangada-par: preserva o estado final, confere o agy e mostra o worktree
- monitor: btop em janela flutuante e indicadores de carga na waybar
- shell: subshell com comandos diretos de agentes e projetos
- par: protocolo de trabalho em par entre o Claude e o Antigravity
- agentes: painel enxerga sessões sem tmux e o fzf cancelado não derruba o script
- atalhos: comando jangada-atalhos, no espírito do Omarchy
- tema: o terminal passa a receber as cores do matugen
- hypridle: sobe o daemon pelo XDG_CONFIG_HOME
- sessão: resolve a GPU para /dev/dri/cardN antes do aquamarine
- revisao: registra os testes feitos no desktop e fecha quatro pendências
- verificar: não trata glob vazio como arquivo Lua
- mapear: reconhece systemd-boot sem precisar de root
- escolha da GPU antes de o compositor subir e dois pacotes que faltavam
- revisão: script rodar-revisao.sh para o Antigravity CLI (agy -p)
- revisão cruzada: aplica 7 apontamentos do Gemini, rejeita 1 e corrige alvo do tmux
- jangada: estrutura inicial, instalador, Hyprland em Lua, camada de agentes, mapeamento e revisão
