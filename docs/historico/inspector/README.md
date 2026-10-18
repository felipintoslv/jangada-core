# Jangada Inspector: proposta e decisões iniciais

Situação: proposta registrada em 10/10/2026. Nada foi implementado.
O trabalho começa depois da modularização 3.0 instalada, da tarefa M3-19 e
de alguns dias de uso sem problemas.

Esta pasta guarda o ponto de partida do projeto:

| Arquivo | Conteúdo |
|---|---|
| `README.md` | Este resumo: o que é, o que foi decidido e o que falta decidir |
| `00-especificacao-original.md` | O texto da especificação como o usuário escreveu, sem alterações |

## O que é

Um recurso do Jangada acionado em linguagem comum, só quando o usuário pede,
com dois usos:

1. **Manutenção.** Perguntas como "como está meu sistema?", "por que está
   lento?" ou "o Jangada está saudável?". O Inspector coleta evidências,
   explica e sugere. Não altera nada.
2. **Personalização.** Pedidos como "quero um medidor de conexão de internet
   na barra". O Inspector constrói a peça nos ajustes pessoais do usuário,
   mostra numa janela de ensaio e só instala depois da aprovação, com como
   desfazer.

O uso 2 não está na especificação original. Ele saiu da conversa de
10/10/2026 e precisa entrar no planejamento.

## Decisões do usuário

| # | Decisão |
|---|---|
| I1 | O Inspector não mexe no sistema operacional: não instala nem remove pacotes, não troca drivers, não reinicia serviços e não pede senha de administrador |
| I2 | Roda só quando o usuário pede. Sem coleta periódica |
| I3 | O foco é acompanhar a manutenção do sistema e criar aditivos para a waybar e para o Jangada Shell, por linguagem natural |
| I4 | Haverá um agente exclusivo do `agy` para o Inspector |
| I5 | O controle pelo celular (`jangada-remoto`) foi descartado |
| I6 | Ordem: fechar a 3.0, atualizar a instalação, M3-19, período de uso, e só então o Inspector, começando pelo planejamento |

## Desenho proposto pelo coordenador (ainda sem aprovação do usuário)

- **Leitura e escrita são permissões separadas.** A manutenção só lê. A
  personalização escreve, e só em `~/.config/jangada`.
- **Toda peça nasce pessoal.** Um aditivo criado pela oficina fica nos
  ajustes do usuário. Se for usado e aprovado, pode virar padrão do
  repositório pelo ciclo normal, com autor e revisor de modelos diferentes.
- **Ensaio antes de instalar.** A peça é mostrada num Hyprland aninhado, e
  não na sessão em uso. Hoje o Jangada só abre o aninhado no teste
  `testes/aninhado.sh`, que confere a configuração e os atalhos e não inicia
  a waybar; mostrar a barra nele é trabalho a fazer.
- **Lista do que foi criado.** Cada peça entra num registro com data e o
  comando para desfazer.
- **Coletores com lista fechada.** O modelo analisa evidências já coletadas e
  não recebe terminal, como a especificação original pede.
- **Primeira versão reduzida.** Das áreas de coleta da especificação, começar
  por serviços com falha, recursos (memória, disco, processador), sessão
  gráfica e barra, e o próprio Jangada. GPU e áudio ficam para depois.
- **Primeiro caso da oficina:** o medidor de conexão de internet na waybar.
  A oficina começa só com módulos da waybar; atalhos e menus vêm depois.
- **Onde mora no código:** a coordenação em `core/`, o acionamento (menu e
  atalho) em `shell/` e a consulta de relatórios em `monitor/`.

## Riscos principais

| Risco | Tratamento proposto |
|---|---|
| Registros do sistema contêm dados pessoais e podem ir para um modelo externo | Filtrar antes de enviar, limitar tamanho e quantidade, coletar só o necessário ao pedido |
| Texto dentro de um registro pode trazer instrução para o modelo | Tratar registro como dado; o modelo não controla a coleta nem tem terminal |
| Alarme falso | O relatório separa fato, hipótese e conclusão; testar com casos reais |
| Tamanho do projeto (9 fases na especificação) | Primeira versão reduzida, fases pequenas e reversíveis |
| Peça da oficina que quebra a barra | Ensaio antes, instalação só nos ajustes pessoais, comando de desfazer |

## Perguntas em aberto

1. Qual é o papel do `agy`? Hoje o Jangada só o aceita em delegações e como
   revisor; `jangada-agente` recusa abrir sessão principal com ele. Duas
   formas possíveis: (a) o Inspector delega a análise ao `agy`, sem mudar
   regra nenhuma, que é a recomendação do coordenador; (b) o `agy` escreve o
   código do Inspector, o que exige mudar essa regra do Core em tarefa
   própria e ter revisor de outro modelo.
2. Teste de delegação ao `agy` feito em 10/10/2026 num projeto de teste, com
   o perfil `claude-agy`: duas delegações de leitura concluíram sem erro
   (35 s e 84 s, modelo `gemini-3.8-flash-high`), com 43 mil e 66 mil tokens
   para respostas de 173 e 94 palavras. O custo por resposta curta é alto;
   falta avaliar a qualidade das respostas e decidir quando a delegação
   compensa. O `agy` só atende em pasta que o usuário marcou como confiável.
3. Onde ficam os relatórios e por quanto tempo são guardados.
4. Quais das áreas de coleta adiadas (GPU, áudio) entram na segunda versão.

## Próximo passo

A primeira execução é só auditoria, arquitetura e planejamento, como a
seção 15 da especificação original determina. O resultado será um conjunto
de documentos nesta pasta, no mesmo formato de `docs/modularizacao-3.0/`,
para aprovação do usuário antes de qualquer código.
