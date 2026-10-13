# Plano de implementação: Reservations Specialist

**Pré-requisitos:**
- F02 implementado: operações de reserva por apartamento, consulta de disponibilidade e catálogo de áreas disponíveis
- F06 implementado: especialista `reservas` como casca, execução de turno, leitura de pendências e rota de mensagens disponíveis
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- `google-adk==2.2.0` já instalado; nenhuma dependência nova e nenhuma variável de ambiente nova

### Fase 1: Tools de leitura

**1. Módulo de tools e vocabulário de resultados** - Criar o módulo das tools de reservas com a fábrica que recebe a engine, os nomes das tools, os valores de situação dos resultados e as mensagens fixas em português. A especificação lista cada nome, valor e mensagem.

**2. Apartamento, data e área** - Implementar o que todas as tools compartilham: a leitura do apartamento no state da sessão, a validação da data, a normalização dos argumentos e a conversão de uma falha do banco em resultado. As regras gerais das tools estão na especificação.

**3. Minhas reservas** - Implementar a tool que lista as reservas ativas do apartamento da sessão, sem nenhum parâmetro.

**4. Disponibilidade** - Implementar a tool que informa se uma área está livre ou ocupada em uma data, sem devolver nada sobre quem ocupa.

**5. Áreas e taxas** - Implementar a tool que lista as áreas do catálogo com as taxas.

### Fase 2: Tools de escrita

**6. Cancelamento** - Implementar a tool que cancela uma reserva do próprio morador, identificada por área e data ou por código, sem confirmação. A especificação define a precedência entre as formas de identificação e o resultado único para reserva não encontrada.

**7. Reserva sem taxa** - Implementar a tool de reserva para o caso em que a área não tem taxa: a reserva é gravada na hora e a data ocupada vira recusa.

**8. Reserva com taxa** - Estender a tool de reserva para as áreas com taxa: recusar a data ocupada antes de qualquer pedido e, com a data livre, registrar o pedido de confirmação com área, data e taxa e encerrar o turno sem gravar. O formato do pedido está na especificação.

**9. Resposta da confirmação** - Tratar na tool de reserva a resposta da confirmação: a aprovação grava, a recusa não grava, e a data ocupada no momento da aprovação vira uma recusa normal.

### Fase 3: Especialista e fiação

**10. Instrução do especialista** - Substituir a instrução de casca do especialista de reservas pela instrução de domínio em português. O conteúdo obrigatório e o conteúdo proibido da instrução estão na especificação.

**11. Engine nas fábricas** - Fazer a engine do banco chegar às tools pelas fábricas do especialista de reservas, do agente principal e da aplicação do ADK, anexando as cinco tools ao especialista.

**12. Aplicação** - Passar a engine da aplicação à construção do Runner no ciclo de vida.

### Fase 4: Insumos de verificação

**13. Runner roteirizado com engine** - Ajustar a construção do Runner com o modelo roteirizado para receber a engine, e atualizar os pontos que já a usam.

**14. Contexto de tool e estados de sessão** - Produzir o que o contrato declara para exercitar as tools em processo: o contexto de tool ligado a uma sessão, com ou sem resposta de confirmação, a sessão de um segundo apartamento e a engine sem banco, pelo mecanismo de preparação de estado do projeto.
