# Plano de implementação: Evaluator Flow Self-Check

**Pré-requisitos:**
- F04, F05, F09 e F10 implementados: rotas de verificação, comando de restauração, especialista do regulamento e rota de confirmações
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- Nenhuma dependência nova: `httpx`, `fastapi` e `uvicorn` já estão no projeto
- Nenhuma variável de ambiente nova; para a execução real, `.env` com uma `GOOGLE_API_KEY` válida
- `uv sync` depois de registrar o comando, para que o novo ponto de entrada seja instalado no ambiente

### Fase 1: Comando e processo da API

**1. Opções e textos fixos** - Criar o pacote do self-check com as opções de linha de comando, os valores padrão, o aviso de cota, o texto de seguimento e os prazos. Os valores estão na especificação.

**2. Controle do processo** - Implementar a conferência de porta livre, a execução da restauração e o processo da API: subida em sessão própria com log em arquivo, espera por `/health`, detecção de saída precoce e parada com SIGINT e escalonamento. O comportamento de cada caso está na especificação.

**3. Ponto de entrada e registro** - Acrescentar o ponto de entrada do comando ao lado dos comandos de subida e restauração, com a interrupção convertida no código de saída da especificação, registrar o comando no manifesto do projeto e sincronizar o ambiente.

### Fase 2: Cliente e verificações

**4. Cliente HTTP** - Criar o cliente das rotas usadas no fluxo (sessões, mensagens, confirmações, eventos, verificação e saúde), com o prazo por requisição da especificação.

**5. Verificações** - Implementar as verificações sobre respostas e eventos: busca de textos proibidos, `302` isolado, linhas de outros capítulos do regulamento, correspondência dos detalhes de uma pendência, horário de fechamento, chamadas de função e códigos de `dados/`. As definições exatas estão na especificação.

**6. Conversa com seguimentos** - Implementar o envio de uma mensagem com as mensagens de seguimento opcionais, limitadas por passo e encerradas assim que o efeito esperado aparece.

### Fase 3: Fluxo e relatório

**7. Os 14 passos** - Implementar cada passo da tabela da especificação, com as mensagens do enunciado, o estado que um passo deixa para os seguintes e o motivo de cada falha. O passo 13 usa o controle de processo para o reinício, e o passo 14 dispara as duas aprovações ao mesmo tempo.

**8. Execução e relatório** - Implementar a execução dos passos em ordem, com o aviso antes de tudo, a marcação de dependências, a conversão de erros inesperados em falha, a linha de cada passo, o resumo, a linha do log e a parada final da API em qualquer caminho.

### Fase 4: Insumos de verificação

**9. API simulada** - Criar a API simulada em `tests/`, com os subcomandos de restauração e de subida, as rotas do fluxo, o estado persistido em arquivo e as respostas de um build correto. O formato do estado está na especificação.

**10. Falhas injetáveis e estatísticas** - Acrescentar à API simulada as falhas da tabela da especificação e as estatísticas de subidas, encerramentos, aprovações simultâneas e seguimentos.
