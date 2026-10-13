# Plano de implementação: Visitors Specialist

**Pré-requisitos:**
- F02 implementado: operações de visitante por apartamento disponíveis
- F06 implementado: especialista `visitantes` como casca, execução de turno, leitura de pendências e rota de mensagens disponíveis
- F07 implementado: a engine já chega à fábrica do agente principal, e as tools de reservas trazem os auxiliares que serão compartilhados
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- `google-adk==2.2.0` já instalado; nenhuma dependência nova e nenhuma variável de ambiente nova

### Fase 1: Suporte compartilhado das tools

**1. Módulo de suporte** - Criar o módulo com o que as tools de reservas e de visitantes têm em comum: a leitura do apartamento no state da sessão, a validação da data, a conversão de uma falha do banco em resultado e os valores e mensagens comuns. A especificação lista cada nome e a origem dele.

**2. Tools de reservas sobre o suporte** - Fazer as tools de reservas usarem o módulo de suporte no lugar dos auxiliares próprios, sem mudar o comportamento, os nomes das tools nem os resultados.

### Fase 2: Tools de visitantes

**3. Módulo de tools e vocabulário de resultados** - Criar o módulo das tools de visitantes com a fábrica que recebe a engine, os nomes das tools, os valores de situação dos resultados, as mensagens fixas em português e a dica do pedido de confirmação. A especificação lista cada nome, valor e mensagem.

**4. Meus visitantes** - Implementar a tool que lista os visitantes autorizados do apartamento da sessão, sem nenhum parâmetro.

**5. Validação de nome e data** - Implementar na tool de autorização a normalização e a validação do nome e a validação da data, antes de qualquer leitura, escrita ou pedido de confirmação. As regras estão na especificação.

**6. Pedido de autorização** - Implementar o caminho da tool de autorização sem resposta de confirmação: recusar a autorização que o apartamento da sessão já tem e, nos demais casos, registrar o pedido de confirmação com nome e data e encerrar o turno sem gravar. O formato do pedido está na especificação.

**7. Resposta da confirmação** - Tratar na tool de autorização a resposta da confirmação: a aprovação grava, a recusa não grava, e a autorização que já existe no momento da aprovação vira uma resposta informativa, sem segunda linha.

### Fase 3: Especialista e fiação

**8. Instrução do especialista** - Substituir a instrução de casca do especialista de visitantes pela instrução de domínio em português. O conteúdo obrigatório e o conteúdo proibido da instrução estão na especificação.

**9. Engine na fábrica do especialista** - Fazer a engine do banco chegar às tools pela fábrica do especialista de visitantes, anexar as duas tools ao especialista e repassar a engine a partir da fábrica do agente principal.

### Fase 4: Insumos de verificação

**10. Tools para invocação direta** - Produzir o que o contrato declara para exercitar as tools de visitantes em processo: as tools construídas sobre a database de teste e sobre a engine sem banco, pelo mecanismo de preparação de estado do projeto.
