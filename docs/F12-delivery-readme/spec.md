# Especificação técnica: Delivery README

## 1. Visão técnica

**O quê:** o `README.md` da raiz passa a ser o README de entrega, em português, no lugar do enunciado do desafio. Ele tem um título e exatamente três seções: Arquitetura, Garantias e Como rodar. Arquitetura descreve os quatro agentes (`assistente`, `reservas`, `visitantes` e `regulamento`), a responsabilidade de cada um, como cada um é acionado e por quê. Garantias mostra, para cada uma das cinco garantias, o arquivo e o trecho de código que a implementam e por que ela não depende do que o modelo decide. Como rodar leva de um clone limpo até a API respondendo com os dados iniciais e termina com o comando opcional do self-check. A feature também acrescenta `tests/test_readme.py`, que confere a estrutura do README e a correspondência dele com o código, e uma cópia do enunciado original em `tests/fixtures/challenge_statement/README.md`, usada para garantir que nenhum trecho dele sobrou.

**Por quê:** o README é um entregável avaliado no passo 15 do fluxo do avaliador, e a seção Garantias é onde a síndica e o avaliador encontram cada garantia no código. Um README escrito à mão envelhece em silêncio: basta renomear uma função para que um trecho citado deixe de existir. Com os trechos copiados literalmente e conferidos por um teste, qualquer divergência entre o README e o código quebra o gate de testes.

**Escopo**

Incluído:
- `README.md` reescrito: título, Arquitetura, Garantias e Como rodar, nessa ordem, em português
- Arquitetura: uma subseção por agente, com responsabilidade, forma de acionamento e motivo
- Garantias: uma subseção por garantia, com um ou mais pares de caminho e trecho literal e a explicação de por que a garantia não depende do modelo
- Como rodar: pré-requisitos, variáveis do `.env`, comandos de banco, sincronização, restauração e subida, conferência dos dados iniciais e o self-check opcional
- `tests/test_readme.py`: estrutura, ausência do enunciado, nomes e acionamento dos agentes conferidos contra o código, caminhos e trechos das garantias, variáveis do `.env`, comandos conferidos contra o `pyproject.toml`
- `tests/fixtures/challenge_statement/README.md`: cópia literal do enunciado do repositório base

Contratos de entrada (PRD, bloco Consumes):
- Do F04: as rotas `GET /apartamentos/{numero}/reservas` e `GET /apartamentos/{numero}/visitantes`, usadas em Como rodar para conferir os dados iniciais
- Do F05: o comando `uv run aurora-restore`
- Do F09: o especialista `regulamento`, acionado como agent-tool, e a tool `ler_capitulo`
- Do F10: a rota `POST /sessoes/{id}/confirmacoes` e a retomada pelos Runners de cada especialista
- Do F01 ao F03, por meio dos anteriores: `uv run aurora-api`, `docker-compose.yml`, `.env.example` e o serviço de sessão persistido

Contratos de saída:
- O PRD não declara bloco Provides. O README é o entregável final

Fora do escopo desta feature:
- Qualquer mudança no código da aplicação, nos agentes, nas rotas ou nos comandos
- Documentação das rotas da API além das duas usadas para conferir os dados iniciais
- Executar o self-check como parte da verificação desta feature (o F11 não é dependência do F12)
- Tradução do README para outro idioma
- Diagramas em imagem; um diagrama Mermaid é opcional
- Qualquer alteração em `README-ORIGINAL.md`, a cópia do enunciado guardada pelo autor na raiz: o arquivo não é editado, movido, renomeado nem apagado

## 2. Impacto na arquitetura

Componentes afetados:
- `README.md` (reescrito): o README de entrega
- `tests/fixtures/challenge_statement/README.md` (novo): cópia do enunciado, só para o teste
- `tests/test_readme.py` (novo): conferência do README contra o código e o manifesto

```mermaid
graph TD
    R["README.md"] --> A["## Arquitetura"]
    R --> G["## Garantias"]
    R --> C["## Como rodar"]
    A --> AG["src/aurora/agents/*.py (nomes e acionamento)"]
    G --> SRC["arquivos citados em src/ e docker/"]
    C --> ENV[".env.example"]
    C --> PY["pyproject.toml [project.scripts]"]
    C --> DC["docker-compose.yml"]
    T["tests/test_readme.py"] --> R
    T --> AG
    T --> SRC
    T --> ENV
    T --> PY
    T --> F["tests/fixtures/challenge_statement/README.md"]
```

O teste é a única peça executável. Ele lê o README como texto, separa as seções pelos títulos e confere cada uma contra a fonte de verdade correspondente: o código dos agentes, os arquivos citados, o `.env.example` e o `pyproject.toml`. Para os agentes, ele constrói o agente principal com uma engine que nunca conecta e lê os nomes dos subagentes e das tools, sem chamar o Gemini.

## 3. Decisões técnicas

| Decisão | Abordagem escolhida | Alternativa considerada | Trade-off |
|---|---|---|---|
| Formato das referências | Caminho relativo à raiz em `**Arquivo:** \`<caminho>\``, seguido de um bloco de código copiado literalmente, sem número de linha | Caminho com intervalo de linhas | Sem link direto para a linha; em troca, uma edição acima do trecho não invalida a referência |
| Conferência das referências | `tests/test_readme.py`, dentro do gate `uv run pytest` | Só revisão manual | Um teste a mais para manter; em troca, qualquer renomeação que quebre o README quebra o gate |
| Comparação dos trechos | As linhas não vazias do bloco, sem os espaços das pontas, aparecem como linhas consecutivas do arquivo, também sem os espaços das pontas | Comparação byte a byte | Aceita reindentação do trecho no README; em troca, linhas omitidas no meio do trecho não são aceitas |
| Ausência do enunciado | Nenhuma linha do enunciado com 40 ou mais caracteres, sem os espaços das pontas, aparece no README | Lista de frases marcadoras | Precisa da cópia do enunciado em fixture; em troca, a conferência cobre o texto inteiro, como no F09 |
| Origem da cópia do enunciado | `README.md` do commit `be87e1d` (o do repositório base), copiado para `tests/fixtures/challenge_statement/README.md` | Ler do histórico do git no teste | Um arquivo a mais; em troca, o teste funciona em clones rasos |
| Agentes conferidos contra o código | O teste importa `ASSISTANT_NAME`, `RESERVATIONS_NAME`, `VISITORS_NAME` e `BYLAWS_NAME` e inspeciona `sub_agents` e `tools` do agente construído por `build_assistant` | Lista fixa de nomes no teste | O teste importa a camada de agentes; em troca, renomear um agente sem atualizar o README quebra o gate |
| Self-check | Documentado como último passo, opcional, com o aviso de cota e a exigência da porta 8000 livre; a verificação só confere o texto e o registro no `pyproject.toml` | Executá-lo na verificação | Não prova que o self-check passa; em troca, o contrato do F12 não depende do F11 nem gasta cota |
| Banco no Como rodar | `docker compose up -d --wait` | `docker compose up -d` | Exige Compose v2.17 ou mais novo; em troca, a restauração só roda depois de o banco estar saudável |
| Títulos | `# <título>` e exatamente três `##`; subseções com `###` | Seções extras (Sumário, Licença) | Nada fora das três seções; em troca, segue o enunciado e o PRD à risca |

## 4. Visão geral dos componentes (Component Overview)

**Documentação:**

| Caminho | Novo/Modificado | Propósito | Responsabilidades |
|---|---|---|---|
| `README.md` | Modificado (reescrito) | README de entrega | Estrutura da seção 5 |

**Testes e verificação:**

| Caminho | Novo/Modificado | Propósito | Responsabilidades |
|---|---|---|---|
| `tests/fixtures/challenge_statement/README.md` | Novo | Cópia do enunciado | Conteúdo idêntico ao `README.md` do commit `be87e1d` |
| `tests/test_readme.py` | Novo | Conferência do README | Ver seção 7 |

**Banco de dados:** nenhuma mudança.

### Detalhe: `tests/test_readme.py`

| Nome | Tipo | Valor ou assinatura | Observações |
|---|---|---|---|
| `README` | `Path` | `PROJECT_ROOT / "README.md"` | |
| `sections` | função | `(text: str, level: int) -> dict[str, str]` | Título → corpo, para `##` ou `###`; ignora títulos dentro de blocos de código |
| `references` | função | `(body: str) -> list[tuple[str, str]]` | Pares (caminho, bloco) para cada `**Arquivo:** \`<caminho>\`` seguido do próximo bloco cercado por crases |
| `block_in_file` | função | `(block: str, path: Path) -> bool` | Regra de comparação da seção 3 |
| `env_names` | função | `(path: Path) -> set[str]` | Nomes antes de `=` em `.env.example` |

## 5. Estrutura do documento

O README é escrito em português. A estrutura abaixo é a forma conferida pelo teste e pelo contrato; o texto de cada parágrafo é livre.

````markdown
# Residencial Aurora — assistente virtual

<um parágrafo de apresentação, sem título próprio>

## Arquitetura

<parágrafo sobre o agente principal, os especialistas e o Runner; diagrama Mermaid opcional>

### assistente
**Responsabilidade:** ...
**Como é acionado:** ...
**Por quê:** ...

### reservas
### visitantes
### regulamento
(mesmos três rótulos)

## Garantias

### Garantia 1: cobrança ou acesso só com confirmação
**Arquivo:** `src/aurora/agents/reservation_tools.py`
```python
<trecho literal>
```
(um ou mais pares Arquivo + bloco)
**Por que não depende do modelo:** ...

### Garantia 2: cada sessão pertence a um apartamento
### Garantia 3: nada se perde no reinício
### Garantia 4: o regulamento é consultado, não carregado
### Garantia 5: dois moradores, uma reserva

## Como rodar

### Pré-requisitos
### Variáveis do `.env`
### Comandos
### Conferência
### Self-check (opcional)
````

**Arquitetura — conteúdo esperado por agente:**

| Agente | Como é acionado | Origem no código |
|---|---|---|
| `assistente` | Agente raiz do `App`; recebe cada mensagem pelo `Runner` da rota de mensagens | `src/aurora/agents/assistant.py`, `src/aurora/agents/runtime.py` |
| `reservas` | Subagente do `assistente` (`sub_agents`), por transferência; na resposta a uma confirmação, retomado por um `Runner` próprio | `src/aurora/agents/reservations.py`, `runtime.build_resume_runners` |
| `visitantes` | Idem a `reservas` | `src/aurora/agents/visitors.py`, `runtime.build_resume_runners` |
| `regulamento` | Agent-tool (`AgentTool`) do `assistente`; roda isolado e lê um capítulo por vez com `ler_capitulo` | `src/aurora/agents/bylaws.py`, `src/aurora/agents/bylaws_tools.py` |

O "Por quê" de cada agente explica a escolha. Pontos esperados: subagentes por transferência para que o especialista que pediu a confirmação seja o mesmo que a recebe; agent-tool para o regulamento porque o texto dos capítulos fica na sessão isolada da tool e só a resposta curta volta à conversa.

**Garantias — trechos sugeridos:**

| Garantia | Trechos sugeridos | Âncora obrigatória em algum trecho |
|---|---|---|
| 1 | `_reserve` em `reservation_tools.py` (pedido de confirmação quando a taxa é maior que zero); `answer_confirmation` em `conversation/confirmations.py` (só aceita id pendente na sessão) | `request_confirmation` |
| 2 | `open_session` e `AuroraSessionService.append_event` em `sessions/service.py`; `apartment_of` em `agents/tool_support.py` | `APARTMENT_KEY` |
| 3 | `AuroraSessionService(DatabaseSessionService)` e `create_session_service` em `sessions/service.py` | `DatabaseSessionService` |
| 4 | `build_bylaws_tool` em `agents/bylaws.py`; `tools=[build_bylaws_tool(...)]` em `agents/assistant.py` | `AgentTool` |
| 5 | Índice `uq_reservations_active_area_day` em `store/schema.py`; `create_reservation` com `on_conflict_do_nothing` em `store/reservations.py` | `status = 'active'` |

**Como rodar — conteúdo esperado:**

- Pré-requisitos: Python 3.12 ou mais novo, uv e Docker com Docker Compose v2
- Variáveis: copiar `.env.example` para `.env`; uma tabela com `GOOGLE_API_KEY` (obrigatória), `GEMINI_MODEL_MAIN` e `GEMINI_MODEL_SPECIALISTS` (padrão `gemini-3.8-flash`) e `DATABASE_URL` (padrão `postgresql+asyncpg://aurora:aurora@localhost:5432/aurora`)
- Comandos, em blocos `bash`, nesta ordem: `cp .env.example .env`, `uv sync`, `docker compose up -d --wait`, `uv run aurora-restore`, `uv run aurora-api`
- Conferência: `curl http://localhost:8000/apartamentos/101/reservas` com a saída `[{"codigo":"RSV-1377","area":"quadra","data":"2030-03-09"}]`
- Self-check (opcional): `uv run aurora-selfcheck`, rodado com a API parada e a porta 8000 livre, porque ele sobe e reinicia a API; consome cota do Gemini

## 6. Modelo de dados

Não se aplica: nenhuma tabela, índice ou migração.

## 7. Estratégia de testes

Segue as convenções do F01 ao F11: pytest com `pytest-asyncio` em modo automático, variáveis em `tests/conftest.py`, nenhum teste chama o Gemini. O teste do README não precisa do banco: a engine passada a `build_assistant` é criada sem conectar.

**Estrutura dos arquivos de teste:**

| Arquivo | Tipo | Alvo | Meta de cobertura |
|---|---|---|---|
| `tests/test_readme.py` | Documentação | `README.md` contra o código, o `.env.example` e o `pyproject.toml` | Toda a estrutura da seção 5 |

**`tests/test_readme.py`:**

| Função | Descrição | Asserções |
|---|---|---|
| `test_title_and_three_sections` | Títulos fora de blocos de código | Um `#`; os `##` são exatamente Arquitetura, Garantias e Como rodar, nessa ordem |
| `test_no_challenge_statement_text` | Linhas da fixture com 40 ou mais caracteres | Nenhuma aparece no README |
| `test_fixture_is_original_statement` | Fixture contra o conteúdo esperado | Começa com `# Regra é regra` e contém `## Fluxo do avaliador` |
| `test_architecture_lists_the_four_agents` | `###` de Arquitetura | Exatamente os quatro nomes das constantes do código |
| `test_each_agent_has_three_labels` | Corpo de cada agente | Os três rótulos, cada um com texto não vazio |
| `test_agent_invocation_matches_code` | Agente construído por `build_assistant` | `sub_agents` são `reservas` e `visitantes` e o texto deles cita subagente; há um `AgentTool` de `regulamento` e o texto dele cita agent-tool |
| `test_specialists_mention_resume` | Corpos de `reservas` e `visitantes` | Citam a retomada da confirmação |
| `test_five_guarantees_in_order` | `###` de Garantias | Cinco títulos de `Garantia 1` a `Garantia 5` |
| `test_each_guarantee_has_reference_and_reason` | Corpo de cada garantia | Pelo menos um par Arquivo + bloco; rótulo `**Por que não depende do modelo:**` com texto |
| `test_referenced_files_exist` | Todos os caminhos | Existem e são rastreados pelo git |
| `test_excerpts_are_verbatim` | Todos os blocos | `block_in_file` verdadeiro |
| `test_guarantee_anchors` | Âncoras da seção 5 | Cada garantia tem a sua âncora em algum trecho |
| `test_env_variables_match_example` | Variáveis citadas em Como rodar | Mesmo conjunto que `.env.example` |
| `test_commands_in_order` | Blocos de código de Como rodar | `uv sync`, `docker compose up`, `uv run aurora-restore` e `uv run aurora-api` em ordem |
| `test_uv_run_commands_are_registered` | Todo `uv run <nome>` | `<nome>` está em `[project.scripts]` |
| `test_selfcheck_documented_after_api` | Subseção do self-check | Cita `uv run aurora-selfcheck` depois de `uv run aurora-api`; cita cota; cita a porta 8000 |
| `test_initial_data_check_documented` | Subseção de conferência | Cita `/apartamentos/101/reservas` e `RSV-1377` |

## Tratamento de erros

O PRD não tem bloco Error Handling para o F12. Os casos relevantes são de divergência entre o README e o repositório:

| Cenário | Comportamento | Resultado |
|---|---|---|
| Função citada é renomeada ou alterada | `test_excerpts_are_verbatim` falha com o caminho e a primeira linha do trecho | Gate de testes vermelho |
| Arquivo citado é movido | `test_referenced_files_exist` falha com o caminho | Gate de testes vermelho |
| Variável nova no `.env.example` | `test_env_variables_match_example` falha com a diferença | Gate de testes vermelho |
| Comando renomeado no `pyproject.toml` | `test_uv_run_commands_are_registered` falha com o nome | Gate de testes vermelho |
| Agente renomeado ou acionado de outra forma | `test_architecture_lists_the_four_agents` ou `test_agent_invocation_matches_code` falha | Gate de testes vermelho |
| Docker Compose antigo, sem `--wait` | O comando falha no terminal do leitor | Como rodar cita a versão mínima nos pré-requisitos |

## Premissas e decisões

Decididas na entrevista:
- `README-ORIGINAL.md` (commit `d52c3d8`) é mantido como está: a implementação não o modifica, e o contrato confere que ele continua idêntico ao enunciado do commit `be87e1d`
- Quality gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`
- O self-check entra em Como rodar como passo opcional; a verificação só confere o texto e o registro do comando, sem executá-lo
- Cada garantia aponta caminho mais bloco literal, sem número de linha, conferidos por `tests/test_readme.py`
- A verificação do Como rodar usa um clone limpo numa pasta temporária com o mesmo nome da pasta do repositório, para reaproveitar o projeto e o volume do compose, com o `.env` copiado do checkout original

Assumidas por mim (revise se discordar):
- Escopo completo: o PRD não separa Core Scope de Full Scope
- "Exatamente três seções" significa três títulos `##`; o título `#` e o parágrafo de abertura não contam como seção, e subseções `###` são permitidas
- Nomes das subseções da Arquitetura: os nomes dos agentes no código (`assistente`, `reservas`, `visitantes`, `regulamento`)
- Títulos das garantias: `Garantia N: <nome>`, com os nomes usados no enunciado
- Uma âncora por garantia (tabela da seção 5) garante que o trecho citado é o que implementa a garantia, e não um trecho qualquer que exista
- "Nenhum texto do enunciado" é verificado por linhas de 40 ou mais caracteres, a mesma técnica do F09; frases curtas e títulos comuns podem coincidir
- A cópia do enunciado vem do commit `be87e1d`, o único que alterou o `README.md` antes desta feature
- `docker compose up -d --wait` no lugar de `docker compose up -d`, para que a restauração não comece antes de o banco ficar saudável
- A conferência de dados iniciais usa `curl`; o README cita também `http://localhost:8000/docs` como alternativa
- O README não documenta todas as rotas da API: o enunciado pede só as três seções, e as rotas estão no contrato do desafio
- Nenhuma dependência nova
- Nenhuma issue do GitHub (issues estão desativadas no repositório)

## Rastreabilidade com o PRD

| Bloco do PRD (F12) | Onde está nesta especificação |
|---|---|
| Consumes | Seção 1 (contratos de entrada); seção 5 (Arquitetura, Conferência) |
| Capabilities | Seções 3 e 5 |
| Experience | Seção 5 (Como rodar, do clone à API) |
| Error Handling | Não há bloco no PRD; a seção "Tratamento de erros" cobre a divergência entre README e código |
