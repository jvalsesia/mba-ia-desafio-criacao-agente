# Residencial Aurora — assistente virtual

Assistente do aplicativo dos moradores do Residencial Aurora, construído com Google ADK e exposto por uma API FastAPI em `http://localhost:8000`. Pelo chat, o morador reserva e cancela áreas comuns, autoriza visitantes e tira dúvidas sobre o regulamento interno. O modelo conduz a conversa; as regras que não podem ser quebradas ficam no código, e este README mostra onde.

## Arquitetura

O morador conversa com um único agente principal, o `assistente`, que não executa nenhuma ação: ele responde saudações e encaminha cada pedido a um especialista. Reservas e visitantes são especialistas ligados ao `assistente` como subagentes; o regulamento é um especialista usado como agent-tool. Todos os agentes leem e gravam os dados do condomínio só por tools, que acessam o PostgreSQL. A API monta um `App` do ADK com o `assistente` como raiz e o executa por um `Runner` cujas sessões ficam no mesmo banco.

```mermaid
graph TD
    API["POST /sessoes/{id}/mensagens"] --> R["Runner (App aurora)"]
    R --> A["assistente"]
    A -- "transferência (subagente)" --> RS["reservas"]
    A -- "transferência (subagente)" --> V["visitantes"]
    A -- "agent-tool" --> RG["regulamento"]
    RG --> L["ler_capitulo"]
    C["POST /sessoes/{id}/confirmacoes"] --> RR["Runners de retomada"]
    RR --> RS
    RR --> V
```

### assistente
**Responsabilidade:** recebe cada mensagem do morador, responde saudações e perguntas sobre o que sabe fazer, e distribui o resto: reservas para `reservas`, visitantes para `visitantes` e dúvidas sobre regras para `regulamento`. Não tem tools de dados e nunca responde de memória sobre reservas, visitantes ou regras.
**Como é acionado:** é o agente raiz do `App` montado em `src/aurora/agents/runtime.py`; a rota de mensagens entrega cada texto do morador ao `Runner` desse `App`, que começa todo turno pelo `assistente`.
**Por quê:** um único ponto de entrada mantém a conversa coerente e deixa cada especialista com poucas tools e uma instrução curta. Como os especialistas não podem devolver a conversa sozinhos, cada nova mensagem volta a passar pelo `assistente`, que escolhe de novo quem atende.

### reservas
**Responsabilidade:** reservar, cancelar e listar as reservas do morador, consultar a disponibilidade de uma área numa data e listar as áreas com as taxas, sempre pelas tools de `src/aurora/agents/reservation_tools.py`.
**Como é acionado:** é um subagente do `assistente` (`sub_agents`), acionado por transferência quando o pedido é sobre reservas. Quando o morador responde a uma confirmação, ele é retomado por um `Runner` próprio, criado por `build_resume_runners`, que reexecuta a tool pendente com a resposta.
**Por quê:** como subagente, ele conduz a conversa direto com o morador, pedindo área e data quando faltam. A transferência, somada ao `Runner` de retomada, garante que o especialista que pediu a confirmação de uma reserva com taxa é o mesmo que recebe a resposta e conclui a ação.

### visitantes
**Responsabilidade:** autorizar a entrada de um visitante numa data e listar os visitantes autorizados do morador, pelas tools de `src/aurora/agents/visitor_tools.py`.
**Como é acionado:** é um subagente do `assistente` (`sub_agents`), acionado por transferência quando o pedido é sobre visitantes. Quando o morador responde a uma confirmação, ele é retomado por um `Runner` próprio, criado por `build_resume_runners`.
**Por quê:** pelo mesmo motivo de `reservas`: toda autorização libera acesso ao prédio e passa por confirmação, e a retomada precisa cair no especialista que fez o pedido, com as mesmas tools.

### regulamento
**Responsabilidade:** responder dúvidas sobre as regras do condomínio com base no texto do regulamento interno, citando o artigo, ou dizer que a resposta não está no regulamento.
**Como é acionado:** é um agent-tool (`AgentTool`) do `assistente`, construído por `build_bylaws_tool` em `src/aurora/agents/bylaws.py`. Roda isolado, com o índice do regulamento na instrução, e lê um capítulo por vez com a tool `ler_capitulo`, no máximo dois por pergunta.
**Por quê:** como agent-tool, o texto dos capítulos lidos fica na execução isolada da tool e só a resposta curta volta à conversa principal. O regulamento é consultado sob demanda em vez de carregado no prompt, e a conversa não cresce a cada dúvida.

## Garantias

Cada garantia aponta o arquivo e o trecho de código que a implementam, copiados literalmente do repositório. `tests/test_readme.py` confere que cada arquivo existe e que cada trecho continua igual ao código, então este README não fica para trás quando o código muda.

### Garantia 1: cobrança ou acesso só depois da confirmação

A tool de reserva só grava uma reserva com taxa depois de receber a resposta de uma confirmação. Sem ela, registra o pedido de confirmação e devolve que nada foi gravado:

**Arquivo:** `src/aurora/agents/reservation_tools.py`
```python
fee = float(found.fee)
answer = tool_context.tool_confirmation
if fee > 0 and answer is None:
    availability = await reservations.check_availability(engine, area_id=area_id, day=day)
    if availability is Availability.TAKEN:
        return refusal(DATE_TAKEN, MSG_TAKEN_ON_REQUEST)
    payload = {"area": area_id, "data": day.isoformat(), "taxa": fee}
    tool_context.request_confirmation(hint=CONFIRMATION_HINT, payload=payload)
    tool_context.actions.skip_summarization = True
    return {"status": AWAITING_CONFIRMATION, **payload, "mensagem": MSG_AWAITING}
if fee > 0 and not answer.confirmed:
    return refusal(NOT_CONFIRMED, MSG_DENIED)
```

A autorização de visitante faz o mesmo, sem exceção, porque toda autorização libera acesso:

**Arquivo:** `src/aurora/agents/visitor_tools.py`
```python
answer = tool_context.tool_confirmation
if answer is None:
    current = await visitors.list_visitors(engine, apartment=apartment)
    if any(v.day == day and v.name.lower() == name.lower() for v in current):
        return refusal(ALREADY_AUTHORIZED, MSG_ALREADY_AUTHORIZED)
    payload = {"nome": name, "data": day.isoformat()}
    tool_context.request_confirmation(hint=CONFIRMATION_HINT, payload=payload)
    tool_context.actions.skip_summarization = True
    return {"status": AWAITING_CONFIRMATION, **payload, "mensagem": MSG_AWAITING}
if not answer.confirmed:
    return refusal(NOT_CONFIRMED, MSG_DENIED)
```

A rota de confirmações só retoma a execução para um `id` pendente na própria sessão; qualquer outro `id` vira `409` sem executar nada:

**Arquivo:** `src/aurora/conversation/confirmations.py`
```python
item = next((p for p in pending_confirmations(session) if p.id == confirmation_id), None)
if item is None:
    return None
```

**Por que não depende do modelo:** o modelo só consegue chamar a tool; quem decide se a ação é gravada é o código, pela presença de `tool_context.tool_confirmation`. Essa resposta só existe quando a rota de confirmações entrega um `FunctionResponse` com o `id` pendente, e a conversa não tem como produzi-la: um "já confirmei" escrito pelo morador é só texto. Uma confirmação já respondida deixa de estar pendente, então a ação aprovada roda uma única vez.

### Garantia 2: uma sessão, um apartamento

O apartamento é validado contra o cadastro e gravado no state da sessão uma única vez, na criação:

**Arquivo:** `src/aurora/sessions/service.py`
```python
async def open_session(
    service: AuroraSessionService, engine: AsyncEngine, *, apartment: str
) -> Session | None:
    if await get_apartment(engine, number=apartment) is None:
        return None
    return await service.create_session(
        app_name=APP_NAME, user_id=USER_ID, state={APARTMENT_KEY: apartment}
    )
```

O `AuroraSessionService.append_event` descarta qualquer tentativa posterior de alterar essa chave:

**Arquivo:** `src/aurora/sessions/service.py`
```python
async def append_event(self, session: Session, event: Event) -> Event:
    if event.actions is not None and event.actions.state_delta:
        event.actions.state_delta.pop(APARTMENT_KEY, None)
    return await super().append_event(session, event)
```

E todas as tools leem o apartamento desse state, nunca de um argumento:

**Arquivo:** `src/aurora/agents/tool_support.py`
```python
def apartment_of(tool_context: ToolContext) -> str | None:
    return tool_context.state.get(APARTMENT_KEY)
```

**Por que não depende do modelo:** nenhuma tool de reservas ou visitantes recebe o número do apartamento como parâmetro, então o modelo não tem onde escrever "302" mesmo que o morador peça. O valor vem do state gravado na criação da sessão, e o `append_event` remove do `state_delta` qualquer mudança nessa chave antes de persistir o evento. A consulta de disponibilidade devolve só `livre` ou `ocupada`, sem dizer de quem é a reserva.

### Garantia 3: nada se perde no reinício

As sessões ficam no PostgreSQL, pelo serviço de sessão em banco do próprio ADK:

**Arquivo:** `src/aurora/sessions/service.py`
```python
class AuroraSessionService(DatabaseSessionService):
```

**Arquivo:** `src/aurora/sessions/service.py`
```python
def create_session_service(settings: Settings) -> AuroraSessionService:
    return AuroraSessionService(settings.database_url)
```

Reservas e visitantes ficam em tabelas do mesmo banco, que guarda os dados no volume `aurora_pgdata`:

**Arquivo:** `docker-compose.yml`
```yaml
volumes:
  - aurora_pgdata:/var/lib/postgresql/data
```

**Por que não depende do modelo:** nada da conversa nem dos dados vive na memória do processo. Cada evento é gravado pelo `DatabaseSessionService` no banco antes de a resposta sair, e as tools gravam reservas e visitantes direto nas tabelas. Ao subir de novo, a API só cria o que falta e lê a sessão pelo `session_id`, com os eventos anteriores e o mesmo state.

### Garantia 4: regulamento consultado, nunca carregado

O regulamento é um especialista embrulhado como agent-tool:

**Arquivo:** `src/aurora/agents/bylaws.py`
```python
class BylawsAgentTool(AgentTool):
```

**Arquivo:** `src/aurora/agents/bylaws.py`
```python
def build_bylaws_tool(model: str | BaseLlm, bylaws: Bylaws | None) -> BylawsAgentTool:
    return BylawsAgentTool(agent=build_bylaws_agent(model, bylaws))
```

O `assistente` recebe essa tool, e não o texto do regulamento:

**Arquivo:** `src/aurora/agents/assistant.py`
```python
return LlmAgent(
    name=ASSISTANT_NAME,
    model=model,
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    sub_agents=[
        build_reservations_agent(specialists_model, engine),
        build_visitors_agent(specialists_model, engine),
    ],
    tools=[build_bylaws_tool(specialists_model, bylaws)],
)
```

Dentro do especialista, cada capítulo é lido pela tool `ler_capitulo`, com um limite por pergunta contado no código:

**Arquivo:** `src/aurora/agents/bylaws_tools.py`
```python
delivered = state.get(READ_COUNT_KEY, 0)
if delivered >= MAX_CHAPTERS:
    return refusal(LIMIT_REACHED, MSG_LIMIT_REACHED)
state[READ_COUNT_KEY] = delivered + 1
```

**Por que não depende do modelo:** o texto dos capítulos só chega ao especialista quando ele chama `ler_capitulo`, e o prompt dele tem apenas o índice. O `AgentTool` executa o especialista numa sessão isolada, então os capítulos lidos não entram no histórico da conversa principal; só a resposta curta volta. O limite de capítulos é um contador no state temporário da tool, não um pedido no prompt.

### Garantia 5: dois moradores, uma reserva

O banco tem um índice único parcial: uma reserva ativa por área e data:

**Arquivo:** `src/aurora/store/schema.py`
```python
Index(
    "uq_reservations_active_area_day",
    reservations.c.area_id,
    reservations.c.day,
    unique=True,
    postgresql_where=text("status = 'active'"),
)
```

A gravação usa esse índice como árbitro, em uma única instrução:

**Arquivo:** `src/aurora/store/reservations.py`
```python
stmt = (
    insert(reservations)
    .values(apartment=apartment, area_id=area_id, day=day)
    .on_conflict_do_nothing(
        index_elements=[reservations.c.area_id, reservations.c.day],
        index_where=text("status = 'active'"),
    )
    .returning(*_COLUMNS)
)
row = (await conn.execute(stmt)).first()
```

**Por que não depende do modelo:** a disponibilidade consultada antes serve só para responder ao morador; quem decide é o PostgreSQL. Quando dois pedidos para a mesma área e data chegam juntos, o índice único deixa só um `INSERT` gravar. O outro não devolve linha e vira `DateTaken`, que a tool transforma em "essa data não está disponível". Uma reserva cancelada sai do índice, e a data volta a ficar livre.

## Como rodar

### Pré-requisitos

- Python 3.12 ou mais novo
- [uv](https://docs.astral.sh/uv/)
- Docker com Docker Compose v2.17 ou mais novo (o comando do banco usa `--wait`)
- Uma chave do Google AI Studio para os modelos Gemini

### Variáveis do `.env`

O `.env` fica fora do Git. Crie o seu a partir do `.env.example` com `cp .env.example .env` e preencha:

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `GOOGLE_API_KEY` | sim | — | Chave do Google AI Studio |
| `GEMINI_MODEL_MAIN` | não | `gemini-3.8-flash` | Modelo do `assistente` |
| `GEMINI_MODEL_SPECIALISTS` | não | `gemini-3.8-flash` | Modelo dos especialistas |
| `DATABASE_URL` | não | `postgresql+asyncpg://aurora:aurora@localhost:5432/aurora` | Banco da API, das sessões e da restauração |

Variáveis vazias usam o padrão.

### Comandos

Na raiz do repositório, nesta ordem:

```bash
# cria o .env; depois, preencha GOOGLE_API_KEY
cp .env.example .env
```

```bash
# instala as dependências
uv sync
```

```bash
# sobe o PostgreSQL e espera ficar saudável
docker compose up -d --wait
```

```bash
# carrega reservas e visitantes de dados/ e apaga as sessões
uv run aurora-restore
```

```bash
# sobe a API em http://localhost:8000
uv run aurora-api
```

A restauração pode ser repetida a qualquer momento para voltar ao estado inicial. A API cria as tabelas que faltarem ao subir e para com `Ctrl+C`; as conversas e os dados continuam no volume do banco.

### Conferência

Com a API no ar, em outro terminal:

```bash
curl http://localhost:8000/apartamentos/101/reservas
```

A resposta com os dados iniciais é:

```json
[{"codigo":"RSV-1377","area":"quadra","data":"2030-03-09"}]
```

A documentação interativa das rotas fica em `http://localhost:8000/docs`.

### Self-check (opcional)

```bash
uv run aurora-selfcheck
```

O self-check percorre o fluxo do avaliador contra a API e imprime um relatório. Ele sobe e reinicia a própria API, então rode com a API parada e a porta 8000 livre. Ele consome cota do Gemini: são algumas dezenas de chamadas ao modelo.
