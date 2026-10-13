# Plano de implementação: Bylaws Specialist

**Pré-requisitos:**
- F06 implementado: especialista `regulamento` como casca, agent-tool montado no agente principal, execução de turno e rota de mensagens disponíveis
- `dados/regulamento.md` idêntico ao do repositório base
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- `google-adk==2.2.0` já instalado; nenhuma dependência nova e nenhuma variável de ambiente nova

### Fase 1: Documento do regulamento

**1. Leitura e capítulos** - Criar o módulo que lê o arquivo do regulamento a partir da pasta de dados e o separa em capítulos e artigos, sem depender do ADK. As regras de separação e os campos de cada capítulo estão na especificação.

**2. Arquivo que não serve** - Fazer a leitura devolver nada, sem lançar erro, quando o arquivo está ausente, ilegível ou sem capítulos, registrando a falha no log sem conteúdo do arquivo.

**3. Índice de capítulos** - Montar o índice com número, título, faixa de artigos e as palavras iniciais de cada artigo. O formato das linhas está na especificação.

### Fase 2: Tool de leitura

**4. Módulo da tool e vocabulário** - Criar o módulo da tool do regulamento com a fábrica que recebe o regulamento carregado, o nome da tool, os valores de situação dos resultados e as mensagens fixas em português. A especificação lista cada nome, valor e mensagem.

**5. Entrega de um capítulo** - Implementar a tool que recebe o número de um capítulo e devolve o título e o texto dele, com a validação do número descrita na especificação.

**6. Limites por pergunta** - Fazer a tool contar, na sessão descartável da pergunta, os capítulos entregues e os números inválidos, recusando o terceiro capítulo e o segundo número inválido. Os contadores não podem chegar à sessão do morador.

### Fase 3: Especialista e agent-tool

**7. Instrução do especialista** - Substituir a instrução de casca do especialista pela instrução de domínio em português, com o índice. O conteúdo obrigatório da instrução está na especificação.

**8. Regulamento indisponível** - Montar o especialista, quando o regulamento não foi carregado, sem tool e com a resposta fixa entregue sem chamada ao modelo.

**9. Agent-tool do regulamento** - Fazer o agent-tool do especialista limitar o tamanho da resposta, trocar a resposta vazia pela frase de "não encontrei" e devolver a mensagem fixa quando o modelo do especialista falha. As regras de corte estão na especificação.

### Fase 4: Fiação e insumos de verificação

**10. Carga na subida** - Carregar o regulamento uma vez na montagem da aplicação do ADK, a partir da pasta de dados, e fazer o resultado chegar à fábrica do especialista pelo agente principal.

**11. Instrução do agente principal** - Acrescentar à instrução do agente principal a orientação de enviar a dúvida completa ao chamar o regulamento, sem incluir nenhum texto do regulamento.

**12. Pastas de regulamento para verificação** - Produzir, pelo mecanismo de arquivos de teste do projeto, as três pastas que o contrato declara: sem arquivo, com arquivo ilegível e com arquivo sem capítulos.

**13. Modelo roteirizado e Runner de verificação** - Permitir que o modelo roteirizado devolva várias chamadas de tool em uma única resposta e que o Runner de verificação seja montado sobre outra pasta do regulamento.
