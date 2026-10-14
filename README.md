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
