# Plano de implementação: Verification Routes

**Pré-requisitos:**
- F01 e F02 implementados: aplicação FastAPI, engine no ciclo de vida, catálogo de apartamentos e listagens por apartamento disponíveis
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- Nenhuma dependência nova e nenhuma variável de ambiente nova

### Fase 1: Rotas de verificação

**1. Pacote e verificação do apartamento** - Criar o pacote de verificação com o router e a verificação reutilizável que confere o apartamento no catálogo e responde apartamento desconhecido. A especificação traz as mensagens e a regra de comparação do número.

**2. Listagem de reservas** - Implementar a rota que devolve as reservas ativas do apartamento no formato documentado, usando a listagem da camada de dados. Os campos e a ordenação estão na especificação.

**3. Listagem de visitantes** - Implementar a rota que devolve os visitantes do apartamento no formato documentado, usando a listagem da camada de dados.

**4. Indisponibilidade do banco** - Fazer as duas rotas responderem serviço indisponível, com a mensagem genérica da especificação, quando a camada de dados falha, sem expor detalhes da falha.

### Fase 2: Aplicação

**5. Inclusão na aplicação** - Ligar o router de verificação à aplicação, sem alterar o ciclo de vida. A especificação registra a convivência com as mudanças do F03 no mesmo arquivo.

**6. Estado para verificação** - Produzir os estados citados no contrato além dos dados iniciais (reserva cancelada, reservas e visitantes adicionais) pelas operações da camada de dados, seguindo o mecanismo de preparação de estado do projeto.
