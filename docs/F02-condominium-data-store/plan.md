# Plano de implementação: Condominium Data Store

**Pré-requisitos:**
- F01 implementado: projeto uv sincronizado, configuração de runtime e engine assíncrona disponíveis
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- Arquivos de `dados/` no estado do repositório base
- Nenhuma dependência nova: SQLAlchemy, asyncpg e pydantic já estão no projeto

### Fase 1: Esquema e tipos da camada

**1. Tipos e erros da camada** - Criar o pacote da camada de dados com os tipos devolvidos pelas operações, os marcadores dos desfechos esperados e os dois erros próprios, incluindo a tradução de falhas do banco para o erro genérico de serviço. A especificação lista cada tipo e o que ele pode carregar.

**2. Esquema do banco** - Definir as quatro tabelas, a sequência de códigos e os índices, com destaque para o índice que garante a exclusividade das reservas ativas. Implementar a criação idempotente do esquema, que também posiciona a sequência acima do maior código inicial sem nunca rebobiná-la.

### Fase 2: Dados iniciais e preparação do banco

**3. Leitura e validação de `dados/`** - Implementar a leitura dos quatro arquivos com todas as validações descritas na especificação, sem tocar no banco, e produzir os diretórios de dados de apoio com defeito listados no contrato.

**4. Catálogo** - Implementar a sincronização de apartamentos e áreas a partir dos dados lidos e as consultas de catálogo usadas pelas features seguintes.

**5. Preparação e carga** - Implementar a preparação do banco (esquema e catálogo, sem tocar em reservas e visitantes) e a carga que restaura reservas, visitantes e a sequência dentro da transação de quem chama.

**6. Preparação na subida da API** - Acrescentar a preparação do banco ao comando de subida, depois da espera pelo banco e antes de abrir a porta, convertendo as falhas previstas em mensagem e código de saída.

### Fase 3: Operações de reserva

**7. Criar reserva e consultar disponibilidade** - Implementar a criação de reserva, em que o próprio banco decide a disputa pela data, e a consulta que responde apenas livre ou ocupada. A especificação descreve os resultados possíveis de cada uma.

**8. Cancelar e listar reservas** - Implementar o cancelamento como mudança de status restrita ao apartamento informado e a listagem das reservas ativas do apartamento, na ordem definida na especificação.

### Fase 4: Operações de visitante

**9. Autorizar e listar visitantes** - Implementar a autorização de visitante com a normalização do nome e a proteção contra duplicidade no banco, e a listagem restrita ao apartamento informado.
