# Plano de implementação: Data Restore Command

**Pré-requisitos:**
- F02 e F03 implementados: carga dos dados iniciais e limpeza das sessões disponíveis, as duas recebendo a conexão de quem chama
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- Nenhuma dependência nova e nenhuma variável de ambiente nova
- `uv sync` depois de registrar o comando, para que o novo ponto de entrada seja instalado no ambiente

### Fase 1: Operação de restauração

**1. Configuração só de banco** - Permitir que a URL do banco seja lida e validada sem exigir a chave do Gemini, reaproveitando a validação que já existe. A especificação descreve a relação entre a configuração completa e a de banco.

**2. Operação de restauração** - Criar o módulo de restauração com a operação que abre uma única transação, limpa as sessões e executa a carga dos dados iniciais, confirmando tudo junto. A ordem dos dois passos e o motivo dela estão na especificação.

**3. Resumo e falhas da operação** - Fazer a operação devolver as três contagens da restauração e traduzir as falhas de conexão para o erro da camada de dados, sem imprimir nada e sem encerrar o processo.

### Fase 2: Comando

**4. Ponto de entrada** - Acrescentar o ponto de entrada que lê a URL, espera o banco, chama a operação e imprime o resumo. Os erros previstos viram uma mensagem e código de saída diferente de zero, no mesmo formato do comando de subida. Os textos estão na especificação.

**5. Registro do comando** - Registrar o comando de restauração no manifesto do projeto, ao lado do comando de subida, e sincronizar o ambiente.

### Fase 3: Insumos de verificação

**6. Dados de origem com falha tardia** - Criar o diretório de dados de origem que passa na validação e falha durante a escrita, usado para provocar a falha no meio da transação. O formato está na especificação e no contrato.

**7. Estado para verificação** - Produzir os estados declarados no contrato (banco alterado, sessões existentes, database vazia e database sem tabelas de sessão) pelo mecanismo de preparação de estado do projeto, usando as operações da camada de dados e o serviço de sessão.
