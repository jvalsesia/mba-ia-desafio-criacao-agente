# Plano de implementação: Conversation Orchestration

**Pré-requisitos:**
- F03 implementado: serviço de sessão persistido, resolução de sessão com `404` e apartamento no state da sessão disponíveis
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- `google-adk==2.2.0` já instalado; `httpx` passa a ser dependência de runtime, seguido de `uv sync`
- Nenhuma variável de ambiente nova: os modelos do agente principal e dos especialistas já estão na configuração

### Fase 1: Árvore de agentes

**1. Especialistas** - Criar o pacote de agentes com os três especialistas (reservas, visitantes e regulamento) como cascas: nome, descrição usada no roteamento e uma instrução curta, sem nenhuma tool. A especificação descreve o conteúdo das cascas e os bloqueios de transferência.

**2. Agente principal** - Criar o agente principal com os dois subagentes e o especialista do regulamento acionado como agent-tool, e escrever a instrução de roteamento em português. O conteúdo obrigatório e o conteúdo proibido da instrução estão na especificação.

**3. App e Runner** - Criar as fábricas que montam a aplicação do ADK com a árvore completa e o Runner sobre o serviço de sessão recebido, aceitando os modelos como parâmetro.

### Fase 2: Conversa

**4. Confirmações pendentes** - Implementar a listagem das confirmações pendentes de uma sessão a partir dos eventos, com a regra que define um pedido como respondido. A especificação traz o formato do pedido e a origem de cada campo do item.

**5. Execução de um turno** - Implementar a operação que entrega uma mensagem ao Runner, reúne o texto da resposta, relê a sessão e devolve o texto com a lista de pendências. As regras de composição do texto e os casos de resposta vazia estão na especificação.

**6. Falhas do turno** - Separar a indisponibilidade do modelo, a indisponibilidade do armazenamento e as demais falhas da execução, cada uma com o resultado definido na especificação, registrando as falhas de execução no log.

### Fase 3: Rota e aplicação

**7. Rota de mensagens** - Implementar a rota de envio de mensagem com a validação do texto, a resolução de sessão do F03 e o corpo de resposta compartilhável com a rota de confirmações. O contrato de requisição e resposta está na especificação.

**8. Erro de assistente indisponível** - Acrescentar ao formato de erro das rotas a resposta para a indisponibilidade do modelo, com a mensagem fixa em português.

**9. Aplicação** - Criar o Runner no ciclo de vida da aplicação, depois do serviço de sessão, encerrá-lo na ordem descrita na especificação e incluir a rota de mensagens.

### Fase 4: Insumos de verificação

**10. Modelo roteirizado e tool de teste** - Criar o modelo que responde com um roteiro no lugar do Gemini, os construtores de resposta e de erro, e a tool de teste que exige confirmação. O contrato descreve o que cada um precisa fazer.

**11. Estados de sessão para verificação** - Produzir a sessão vazia, a sessão com duas confirmações pendentes e a sessão com confirmação respondida declaradas no contrato, pelo mecanismo de preparação de estado do projeto, gravando os eventos pelo próprio serviço de sessão.
