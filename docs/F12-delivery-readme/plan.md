# Plano de implementação: Delivery README

**Pré-requisitos:**
- F04, F05, F09 e F10 implementados: rotas de verificação, comando de restauração, especialista do regulamento e fluxo de confirmação
- F11 integrado à branch, para que o comando do self-check citado em Como rodar esteja registrado
- PostgreSQL do compose no ar e saudável, para o gate de testes
- Nenhuma dependência nova e nenhuma variável de ambiente nova
- `README-ORIGINAL.md` na raiz não é alterado em nenhuma fase

### Fase 1: Arquitetura e Como rodar

**1. Cópia do enunciado** - Guardar uma cópia literal do enunciado do repositório base no diretório de fixtures, antes de reescrever o README. A origem da cópia está na especificação.

**2. Esqueleto e Arquitetura** - Substituir o conteúdo do README pelo título, pela apresentação e pelas três seções da especificação, e escrever a Arquitetura com uma subseção por agente, com responsabilidade, acionamento e motivo, fiéis ao código dos agentes e do runtime.

**3. Como rodar** - Escrever os pré-requisitos, a tabela de variáveis do `.env`, os comandos em ordem, a conferência dos dados iniciais e o self-check opcional, com os valores da especificação.

### Fase 2: Garantias

**4. As cinco garantias** - Escrever uma subseção por garantia, com o arquivo e o trecho copiado literalmente do código que a implementa e a explicação de por que ela não depende do modelo. Os trechos sugeridos e a âncora de cada garantia estão na especificação.

### Fase 3: Insumos de verificação

**5. Conferência do README** - Criar o teste que confere a estrutura do README, a ausência do enunciado, os agentes contra o código, os caminhos e trechos das garantias, as variáveis contra o `.env.example` e os comandos contra o manifesto do projeto.
