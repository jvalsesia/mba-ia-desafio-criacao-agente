# Plano de implementação: Project Foundation and Runtime

**Pré-requisitos:**
- uv instalado, com acesso ao PyPI
- Python 3.12 disponível (o uv baixa se faltar)
- Docker Engine com Docker Compose v2 e acesso ao Docker Hub
- Portas 5432 e 8000 livres na máquina
- Git, com o repositório no estado do commit inicial (enunciado e `dados/`)

### Fase 1: Base do projeto e configuração

**1. Manifesto e dependências** - Criar o projeto uv com o pacote `aurora` em layout src, declarar as dependências de runtime e de desenvolvimento com o ADK em versão exata e gerar o lock. Remover a pasta de pacote vazia antiga. A especificação lista as dependências e as configurações de ferramentas.

**2. Higiene de segredos e versão do interpretador** - Criar o modelo de `.env` apenas com os nomes das variáveis, fixar a versão do Python e completar o `.gitignore`. Os nomes das variáveis estão na especificação.

**3. Configuração de runtime** - Implementar o módulo que lê o `.env`, aplica os padrões, trata valor vazio como ausente e falha com mensagem clara quando falta a chave. Estabelecer junto as convenções de teste do projeto descritas na especificação.

### Fase 2: Banco local e checagem de conexão

**4. Serviço PostgreSQL** - Criar o arquivo do compose com um único serviço de banco, volume persistente e verificação de saúde, incluindo a criação da database de testes na primeira inicialização.

**5. Conexão e espera pelo banco** - Implementar a criação da engine assíncrona e a espera pelo banco com novas tentativas e tempo limite, descrevendo o destino da conexão sem expor credenciais.

### Fase 3: API e comando de subida

**6. Aplicação e rota de disponibilidade** - Criar a aplicação FastAPI com ciclo de vida que mantém a engine do banco e a rota de disponibilidade descrita na especificação.

**7. Comando de subida** - Registrar o script do projeto que valida a configuração, espera o banco e só então sobe o servidor no endereço fixo, convertendo as falhas previstas em mensagem e código de saída.
