# Especificação técnica: Project Foundation and Runtime

## 1. Visão técnica

**O quê:** a base executável do projeto. Um pacote Python `aurora` gerenciado por uv, com `google-adk==2.2.0` fixado, um esqueleto FastAPI que sobe em `http://localhost:8000` por um único comando (`uv run aurora-api`), um `docker-compose.yml` com um serviço PostgreSQL e um módulo de configuração que lê o `.env`, aplica padrões e falha rápido quando falta a chave do Gemini ou o banco não responde.

**Por quê:** todas as features seguintes dependem de três coisas que precisam existir antes: configuração de runtime tipada (chave, modelos, URL do banco), um processo de API com ciclo de vida definido e um Postgres local reproduzível. O `DatabaseSessionService` do ADK 2.2.0 usa engine assíncrona do SQLAlchemy e o SQLAlchemy não vem na instalação padrão do ADK, então a pilha de banco precisa ser declarada aqui.

**Escopo**

Incluído:
- Projeto uv com `pyproject.toml`, `uv.lock` e `.python-version` versionados
- Dependências de runtime e de desenvolvimento, com o ADK em versão exata
- `.env.example` só com nomes de variáveis; `.env` fora do Git
- `docker-compose.yml` com um Postgres e as databases `aurora` e `aurora_test`
- Módulo de configuração com padrões e validação
- Checagem de conexão com o banco na subida, com novas tentativas por 10 segundos
- Aplicação FastAPI com ciclo de vida (engine do banco) e a rota `GET /health`
- Comando de subida `uv run aurora-api`
- Convenções de teste do projeto (pytest, pasta `tests/`, `tests/fixtures/`)

Contratos de saída (PRD, bloco Provides): configuração de runtime (chave do Gemini, nomes dos modelos, URL do banco), layout do projeto e ponto de entrada da aplicação, consumidos por F02 e F03.

Fora do escopo desta feature:
- Tabelas do condomínio e carga de `dados/` (F02)
- Sessões, agentes, rotas do contrato do enunciado (F03 em diante)
- Comando de restauração (F05) e README de entrega (F12)

## 2. Impacto na arquitetura

Componentes afetados:
- Raiz do repositório: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `.gitignore`, `docker-compose.yml`
- `docker/postgres/init/`: script de criação da database de testes
- `src/aurora/`: `config.py`, `db.py`, `main.py`, `cli.py`
- `tests/`: convenções e testes da base

```mermaid
graph TD
    A["uv run aurora-api"] --> B["aurora.cli: run_api"]
    B --> C["aurora.config: load_settings"]
    C --> D[".env + variaveis de ambiente"]
    B --> E["aurora.db: wait_for_database"]
    E --> F["PostgreSQL (docker compose)"]
    B --> G["uvicorn em 127.0.0.1:8000"]
    G --> H["aurora.main: create_app"]
    H --> I["lifespan: engine async"]
    I --> F
    H --> J["GET /health"]
```

Fluxo de subida: o comando valida a configuração, espera o banco responder e só então entrega o controle ao uvicorn. Qualquer falha nas duas primeiras etapas encerra o processo com código 1 e uma mensagem em stderr, antes de abrir a porta 8000.

## 3. Decisões técnicas

| Decisão | Abordagem escolhida | Alternativa considerada | Trade-off |
|---|---|---|---|
| Layout e pacote | Layout src com pacote `aurora`, instalado pelo `uv sync` (backend de build hatchling) | Manter `mba_ia_desafio_criacao_agente`; pacote `app/` na raiz | Exige `[build-system]`, em troca de imports curtos e testes independentes do diretório de execução |
| Comando de subida | Script `aurora-api` em `[project.scripts]`, host e porta fixos no código | `uv run uvicorn aurora.main:app --port 8000` | Menos transparente sobre o que roda, mas sem flags para errar e com espaço para validar antes de abrir a porta |
| Onde validar | Em `aurora.cli`, antes de chamar o uvicorn | No lifespan do FastAPI | Quem subir a aplicação por outro caminho não recebe a mensagem amigável; em troca, a falha sai com código 1 e sem traceback do uvicorn |
| Configuração | `pydantic-settings` com `env_ignore_empty` | `python-dotenv` com leitura manual de `os.environ` | Uma dependência a mais, em troca de tipos, padrões e tratamento de valor vazio como ausente |
| Acesso ao banco | SQLAlchemy 2 async + asyncpg, URL `postgresql+asyncpg://` | asyncpg com SQL puro; Alembic para migrações | Sem histórico de migrações; o esquema é criado de forma idempotente pelas features que o possuem |
| Porta do Postgres | 5432 no host | 5433 para evitar colisão | `docker compose up -d` falha se já houver um Postgres local na 5432 |
| Rota de disponibilidade | `GET /health` sem tocar no banco nem no modelo | Health com consulta ao banco; nenhuma rota extra | Não detecta queda do banco depois da subida |
| Banco de testes | Database `aurora_test` no mesmo container, criada por script de inicialização | SQLite em memória; Testcontainers | `uv run pytest` exige o compose de pé |
| Modelo padrão | `gemini-3.8-flash` para agente principal e especialistas | Flash no principal e flash-lite nos especialistas | Mais cota consumida, em troca de chamadas de tool mais confiáveis |

## 4. Visão geral dos componentes (Component Overview)

**Projeto e infraestrutura:**

| Caminho | Novo/Modificado | Propósito | Responsabilidades |
|---|---|---|---|
| `pyproject.toml` | Novo | Manifesto do projeto | `requires-python = ">=3.12"`; dependências com `google-adk==2.2.0` exato; grupo `dev`; script `aurora-api`; configuração de ruff e pytest |
| `uv.lock` | Novo | Lock de dependências | Gerado por `uv lock`, versionado, coerente com o `pyproject.toml` |
| `.python-version` | Novo | Versão do interpretador | Contém `3.12`, para o uv escolher (ou baixar) a mesma versão em qualquer máquina |
| `.env.example` | Novo | Modelo do `.env` | Lista `GOOGLE_API_KEY`, `GEMINI_MODEL_MAIN`, `GEMINI_MODEL_SPECIALISTS`, `DATABASE_URL`, cada uma no formato `NOME=` sem valor |
| `.gitignore` | Modificado | Higiene do repositório | Mantém `.env`, `.venv/`, `__pycache__/` e `/graft/`; acrescenta `.pytest_cache/` e `.ruff_cache/` |
| `docker-compose.yml` | Novo | Banco local | Um serviço `postgres` (imagem `postgres:17`), porta `5432:5432`, usuário, senha e database `aurora`, volume nomeado, healthcheck com `pg_isready` |
| `docker/postgres/init/01-create-test-db.sql` | Novo | Database de testes | Cria `aurora_test` com dono `aurora` na primeira inicialização do volume |

**Backend:**

| Caminho | Novo/Modificado | Propósito | Responsabilidades |
|---|---|---|---|
| `src/aurora/__init__.py` | Novo | Pacote | Marca o pacote; sem lógica |
| `src/aurora/config.py` | Novo | Configuração de runtime | Classe `Settings`; `load_settings()` e `get_settings()` (com cache); `ConfigError`; constantes `PROJECT_ROOT`, `DATA_DIR`, `API_HOST`, `API_PORT`; exporta a chave para `os.environ` |
| `src/aurora/db.py` | Novo | Conexão com o banco | `create_engine(settings)`; `wait_for_database(url, timeout, interval)`; `describe_target(url)` sem credenciais; `DatabaseUnavailableError` |
| `src/aurora/main.py` | Novo | Aplicação FastAPI | `create_app(settings)`; lifespan que cria e descarta a engine em `app.state`; rota `GET /health`; objeto `app` |
| `src/aurora/cli.py` | Novo | Ponto de entrada | `run_api()`: carrega configuração, espera o banco, chama o uvicorn; converte falhas em mensagem em stderr e código 1 |

**Testes:**

| Caminho | Novo/Modificado | Propósito | Responsabilidades |
|---|---|---|---|
| `tests/conftest.py` | Novo | Configuração de teste | Define as variáveis de ambiente de teste, isola do `.env` real, limpa o cache de configuração |
| `tests/fixtures/.gitkeep` | Novo | Convenção de arquivos de apoio | Reserva a pasta usada pelas próximas features |
| `tests/test_config.py` | Novo | Testes de configuração | Ver seção 7 |
| `tests/test_db.py` | Novo | Testes de conexão | Ver seção 7 |
| `tests/test_health.py` | Novo | Testes da rota | Ver seção 7 |
| `tests/test_cli.py` | Novo | Testes do comando | Ver seção 7 |

**Limpeza:** a pasta vazia e não versionada `src/mba_ia_desafio_criacao_agente/` é removida. O `.venv` existente (Python 3.11) é recriado pelo `uv sync`.

### Detalhe: `src/aurora/config.py`

| Campo de `Settings` | Variável | Obrigatória | Padrão |
|---|---|---|---|
| `google_api_key` | `GOOGLE_API_KEY` | Sim, não vazia | — |
| `gemini_model_main` | `GEMINI_MODEL_MAIN` | Não | `gemini-3.8-flash` |
| `gemini_model_specialists` | `GEMINI_MODEL_SPECIALISTS` | Não | `gemini-3.8-flash` |
| `database_url` | `DATABASE_URL` | Não | `postgresql+asyncpg://aurora:aurora@localhost:5432/aurora` |

Regras:
- O `.env` é lido de `PROJECT_ROOT/.env`, independente do diretório de execução. Variáveis do ambiente do processo têm precedência sobre o arquivo.
- Valor vazio (`NOME=`) conta como ausente e recebe o padrão. É o que permite copiar o `.env.example` e preencher só a chave.
- `load_settings(env_file=...)` aceita um caminho alternativo ou `None`, para os testes não lerem o `.env` real.
- Chave ausente ou vazia gera `ConfigError` com mensagem que cita `GOOGLE_API_KEY`.
- `DATABASE_URL` que não seja uma URL válida com driver `postgresql+asyncpg` gera `ConfigError` que cita `DATABASE_URL` sem reproduzir o valor (pode conter senha).
- Depois de validar, a chave é exportada para `os.environ["GOOGLE_API_KEY"]`, porque o cliente do Gemini usado pelo ADK lê do ambiente, e o `pydantic-settings` não exporta o conteúdo do `.env`.
- `DATA_DIR` aponta para `PROJECT_ROOT/dados`. Nenhum código desta feature escreve nessa pasta.
- `API_HOST = "127.0.0.1"` e `API_PORT = 8000` são constantes, não variáveis de ambiente.

### Detalhe: `src/aurora/db.py`

- `create_engine(settings)` devolve uma `AsyncEngine` com `pool_pre_ping` ligado.
- `wait_for_database(url, timeout_seconds=10, interval_seconds=1)` abre uma engine temporária, executa uma consulta trivial e repete a cada intervalo até responder ou o tempo acabar. Descarta a engine ao terminar, porque roda em um laço de eventos diferente do uvicorn.
- `describe_target(url)` devolve `host:porta` e o nome da database, sem usuário nem senha.

### Detalhe: `src/aurora/cli.py`

Ordem de `run_api()`: carregar configuração → esperar o banco → `uvicorn.run(create_app(settings), host=API_HOST, port=API_PORT)`. `ConfigError` e `DatabaseUnavailableError` viram uma linha em stderr e `SystemExit(1)`, sem traceback.

## 5. Contratos de API

**Endpoint: verificação de disponibilidade**
- **Método:** GET
- **Caminho:** `/health`
- **Autenticação:** nenhuma

**Requisição:** sem corpo e sem parâmetros.

**Resposta (sucesso - 200):**

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | `string` | Sempre `"ok"` |

**Exemplo de resposta:**
```json
{
  "status": "ok"
}
```

A rota não consulta o banco nem o modelo. Ela é adicional às rotas do enunciado e não conflita com nenhuma delas. Não há códigos de erro próprios.

## 6. Modelo de dados

Esta feature não cria tabelas. Ela entrega apenas a instância e as databases:

| Database | Dono | Criada por | Uso |
|---|---|---|---|
| `aurora` | `aurora` | Variáveis `POSTGRES_*` do compose | Dados do condomínio e sessões, a partir do F02 e F03 |
| `aurora_test` | `aurora` | `docker/postgres/init/01-create-test-db.sql` | Testes de integração |

O script de inicialização roda apenas quando o volume é criado pela primeira vez.

## 7. Estratégia de testes

**Convenções do projeto (valem para as próximas features):**
- pytest com `pytest-asyncio` em modo automático e `httpx` para chamar a aplicação em processo
- Testes em `tests/`, arquivos de apoio em `tests/fixtures/`
- Variáveis de ambiente definidas em `tests/conftest.py`; não há arquivo `.env.test`
- Chave do Gemini nos testes é o literal `test-key`; nenhum teste chama o Gemini
- Testes de integração usam `postgresql+asyncpg://aurora:aurora@localhost:5432/aurora_test` e exigem o compose de pé
- Estado persistente de teste é preparado por fixtures do pytest, usando as próprias funções do projeto

**Estrutura dos arquivos de teste:**

| Arquivo | Tipo | Alvo | Meta de cobertura |
|---|---|---|---|
| `tests/test_config.py` | Unitário | `aurora.config` | 90% |
| `tests/test_db.py` | Unitário e integração | `aurora.db` | 85% |
| `tests/test_health.py` | Integração | `aurora.main` | 90% |
| `tests/test_cli.py` | Unitário | `aurora.cli` | 85% |

**`tests/test_config.py`:**

| Função | Descrição | Asserções |
|---|---|---|
| `test_defaults_when_only_key_is_set` | Só a chave definida | Modelos iguais a `gemini-3.8-flash`; URL igual ao padrão |
| `test_empty_values_fall_back_to_defaults` | Variáveis presentes e vazias | Mesmos padrões do teste anterior |
| `test_env_overrides_defaults` | Modelos e URL definidos | Valores refletem o ambiente |
| `test_missing_key_raises_config_error` | Chave ausente | `ConfigError`; mensagem contém `GOOGLE_API_KEY` |
| `test_empty_key_raises_config_error` | Chave vazia | `ConfigError`; mensagem contém `GOOGLE_API_KEY` |
| `test_invalid_database_url_does_not_leak_value` | URL malformada com senha | `ConfigError`; mensagem contém `DATABASE_URL` e não contém a senha |
| `test_key_is_exported_to_environment` | Carga bem-sucedida | `os.environ["GOOGLE_API_KEY"]` igual ao valor carregado |

**`tests/test_db.py`:**

| Função | Descrição | Asserções |
|---|---|---|
| `test_describe_target_hides_credentials` | URL com usuário e senha | Saída contém host, porta e database; não contém usuário nem senha |
| `test_wait_for_database_succeeds` | Database de teste no ar | Retorna sem erro |
| `test_wait_for_database_times_out_on_closed_port` | Porta sem serviço, tempo limite curto | `DatabaseUnavailableError`; mensagem contém `host:porta` |

**`tests/test_health.py`:**

| Função | Descrição | Asserções |
|---|---|---|
| `test_health_returns_ok` | `GET /health` | Status 200; corpo `{"status": "ok"}` |
| `test_health_is_json` | Cabeçalho da resposta | `Content-Type` começa com `application/json` |
| `test_lifespan_creates_and_disposes_engine` | Ciclo de vida | Engine disponível em `app.state` durante a execução |

**`tests/test_cli.py`:**

| Função | Descrição | Asserções |
|---|---|---|
| `test_run_api_exits_1_without_key` | Sem chave | Código 1; stderr contém `GOOGLE_API_KEY`; uvicorn não é chamado |
| `test_run_api_exits_1_when_database_unreachable` | Banco fora do ar | Código 1; stderr contém `host:porta` e não contém a senha; uvicorn não é chamado |
| `test_run_api_starts_uvicorn_on_fixed_address` | Configuração válida | uvicorn chamado com `127.0.0.1` e `8000` |

## Tratamento de erros

| Cenário | Comportamento | Mensagem (stderr) |
|---|---|---|
| `GOOGLE_API_KEY` ausente ou vazia | Processo encerra com código 1 antes de abrir a porta | `Configuração inválida: defina GOOGLE_API_KEY no arquivo .env (copie .env.example para .env e preencha a chave do Google AI Studio).` |
| `DATABASE_URL` malformada | Processo encerra com código 1 | `Configuração inválida: DATABASE_URL não é uma URL postgresql+asyncpg válida.` |
| Banco inacessível | Novas tentativas a cada 1 s por 10 s; depois encerra com código 1 | `Banco de dados inacessível em <host>:<porta> (database <nome>) após 10 s. Suba o Postgres com "docker compose up -d".` |
| Python abaixo de 3.12 | `uv sync` recusa pela restrição `requires-python` | Mensagem do próprio uv |
| `.env` adicionado ao Git por engano | Bloqueado pelo `.gitignore` | — |

Nenhuma mensagem reproduz a chave do Gemini nem a senha do banco.

## Premissas e decisões

Decididas na entrevista:
- Quality gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`
- Pacote `aurora` em layout src; comando `uv run aurora-api`
- `GET /health` simples; modelo padrão `gemini-3.8-flash` para todos os agentes
- SQLAlchemy async + asyncpg, sem Alembic; Postgres na porta 5432 do host
- Código em inglês; rotas, campos JSON, mensagens e textos lidos pelo modelo em português
- Testes contra a database `aurora_test` do mesmo container

Assumidas por mim (revise se discordar):
- `pydantic-settings` para a configuração, com valor vazio tratado como ausente
- Nomes das variáveis: `GOOGLE_API_KEY`, `GEMINI_MODEL_MAIN`, `GEMINI_MODEL_SPECIALISTS`, `DATABASE_URL`
- Imagem `postgres:17`; usuário, senha e database `aurora`. A senha do banco local fica versionada no compose e no padrão do código; ela não é uma chave de API e só vale para o container local
- API ligada em `127.0.0.1`, não em todas as interfaces, porque as rotas de verificação não têm autenticação
- Backend de build hatchling; `.python-version` com `3.12`
- As mensagens de erro de subida ficam em português, seguindo a decisão de idioma. O PRD traz o texto em inglês como ilustração; o que se preserva é citar a variável `GOOGLE_API_KEY`
- O comando de subida fica documentado nesta especificação e no contrato; o README de entrega é do F12 e o enunciado permanece como README até lá
- `gemini-3.8-flash` aparece hoje na página oficial de modelos; a cota do projeto no AI Studio não foi verificada

Verificado antes de escrever:
- `google-adk` 2.2.0 existe no PyPI e aceita Python >=3.10
- O `DatabaseSessionService` da 2.2.0 chama `create_async_engine` e o SQLAlchemy só entra pelo extra `db`, que também traz o conector do Spanner; por isso o projeto declara `sqlalchemy[asyncio]` e `asyncpg` diretamente, sem o extra

## Rastreabilidade com o PRD

| Bloco do PRD (F01) | Onde está nesta especificação |
|---|---|
| Provides | Seção 1 (contratos de saída); seção 4 (`config.py`, `main.py`) |
| Capabilities | Seções 3 e 4 |
| Experience | Seção 2 (fluxo de subida); seção 4 (`cli.py`) |
| Error Handling | Seção "Tratamento de erros" |
