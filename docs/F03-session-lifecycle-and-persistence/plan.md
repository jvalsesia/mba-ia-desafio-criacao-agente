# Plano de implementação: Session Lifecycle and Persistence

**Pré-requisitos:**
- F01 e F02 implementados: configuração de runtime, aplicação FastAPI, comando de subida e catálogo de apartamentos disponíveis
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- Nenhuma dependência nova: `google-adk==2.2.0`, SQLAlchemy e asyncpg já estão no projeto
- Nenhuma variável de ambiente nova: as sessões usam a mesma `DATABASE_URL`

### Fase 1: Serviço e armazenamento de sessões

**1. Serviço de sessão com guarda** - Criar o pacote de sessões com as constantes de identidade e o serviço de sessão persistido que protege a chave do apartamento contra qualquer escrita posterior. A especificação descreve a regra da guarda e o limite conhecido dela.

**2. Abertura e resolução de sessão** - Implementar a abertura de sessão vinculada a um apartamento do catálogo e a busca de sessão pelo identificador, com a tradução das falhas de banco para o erro próprio da camada. A especificação lista os resultados possíveis de cada operação.

**3. Preparação e limpeza do armazenamento** - Implementar a criação das tabelas de sessão fora do laço de eventos da aplicação e a limpeza que roda na transação de quem chama, tolerando tabelas ainda inexistentes.

### Fase 2: Rotas e formato de erro

**4. Formato de erro das rotas** - Criar os handlers que dão a todos os erros o mesmo corpo com texto em português, cobrindo validação de requisição e indisponibilidade de serviço. As mensagens estão na especificação.

**5. Rotas de sessão** - Implementar a criação de sessão e a listagem de eventos, junto com a resolução de sessão reutilizável que responde sessão desconhecida. Os contratos de requisição e resposta estão na especificação.

**6. Aplicação** - Ligar o serviço de sessão ao ciclo de vida da aplicação, incluir as rotas e instalar os handlers de erro.

### Fase 3: Subida da API

**7. Preparação das sessões na subida** - Acrescentar a criação das tabelas de sessão ao comando de subida, depois da preparação do banco e antes de abrir a porta, convertendo a falha prevista em mensagem e código de saída.

**8. Estado de sessão para verificação** - Produzir a sessão com histórico e os demais estados declarados no contrato pelo mecanismo de preparação de estado do projeto, gravando os eventos pelo próprio serviço de sessão.
