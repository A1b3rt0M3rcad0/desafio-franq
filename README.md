# Desafio Franq

Implementação do Desafio Técnico 1: um Assistente Virtual de Dados capaz de investigar um banco SQLite de forma autônoma, executar múltiplas operações, recuperar-se de falhas e responder perguntas de negócio com rastreabilidade.

O repositório usa uma topologia de packages inspirada em projetos como Woobe e n8n. Cada diretório em `packages/` representa um boundary executável ou distribuível claro:

- `packages/core`: runtime do Agent, contexto, Skills, Tools, Observer, trace, persistência e migrations;
- `packages/api`: composition root HTTP/SSE;
- `packages/runner`: consumer independente responsável pela execução do Agent;
- `packages/ui`: interface Streamlit, que consome somente a API pública.

Os imports Python continuam sob o namespace `package.*`, mas a propriedade física do código agora acompanha os boundaries de runtime.

## Estrutura do repositório

```text
.
├── packages/
│   ├── core/
│   │   ├── alembic.ini
│   │   ├── migrations/
│   │   ├── pyproject.toml
│   │   └── src/package/agent/
│   ├── api/
│   │   ├── pyproject.toml
│   │   └── src/package/api/
│   ├── runner/
│   │   ├── pyproject.toml
│   │   └── src/package/runner/
│   └── ui/
│       ├── pyproject.toml
│       └── src/package/ui/
├── docker/
│   └── images/app/
│       ├── Dockerfile
│       └── entrypoint.sh
├── data/
│   └── challenge-1/anexo_desafio_1.db
├── docs/
│   ├── architecture.md
│   └── challenge.pdf
├── tests/
├── compose.yaml
├── pyproject.toml
└── README.md
```

## Arquitetura

```text
Streamlit
   |
   | HTTP / SSE
   v
FastAPI --------------------------> PostgreSQL
   |                                   ^
   | cria Session + Execution          |
   |                                   |
   +---- Outbox --------------------> Runner
                                        |
                                        v
                                  Agent Runtime
                                        |
                                LangGraph AgentProgram
                                        |
                        +---------------+---------------+
                        |               |               |
                     Context          Skills           Tools
                                                        |
                                                        v
                                               SQLite do usuário

Agent Runtime --> EventSink --> Redis projection/stream --> ExecutionObserver --> SSE
                         \
                          +--> Trace
```

PostgreSQL é a fonte durável de sessões, execuções, outbox, trace, Global Context e snapshots. Redis mantém hot state e o stream realtime. O SQLite em `data/challenge-1/anexo_desafio_1.db` é o banco de negócio acessado exclusivamente pela Database Tool read-only.

## LLM

O Agent depende apenas de `LLMClient`. Os providers concretos usam LangChain:

- `openai`: `OpenAILLM` baseado em `ChatOpenAI`;
- `deepseek`: `DeepSeekLLM` baseado em `ChatDeepSeek`.

O provider ativo é escolhido por `LLM_PROVIDER=openai` ou `LLM_PROVIDER=deepseek`. A janela de contexto e a contagem de tokens vêm do modelo ativo.

A API não bloqueia a criação de uma Execution com base na disponibilidade do Runner ou do provider. A etapa de Acceptance persiste `Execution(PENDING) + Outbox` atomicamente e retorna `202 Accepted`. Disponibilidade e configuração do LLM pertencem ao Runner.

## Runtime do Agent

O `LangGraphAgentProgram` executa o ciclo:

```text
Agent
  |
  v
Reasoning / LLM
  |
  +----------> Tool ----------+
  |                            |
  +----------> Skill ----------+--> Agent
  |                            |
  +----------> Answer ------------> Client
```

Uma Tool pode ser chamada várias vezes durante a mesma execução. Erros voltam para o Agent como observação e podem gerar novas tentativas. Chamadas independentes da mesma Tool podem executar em paralelo até o limite de `AGENT_TOOL_MAX_CONCURRENCY_PER_TOOL`.

A execução termina quando o modelo conclui uma resposta ou quando `AGENT_RUNTIME_MAX_ITERATIONS` é atingido.

## Context Manager

O contexto é dividido em Global Context, Execution Context, Context Snapshot, Context Budget e Global Context Retriever. Snapshots são criados ao final de cada execução e também quando o Context Budget é ultrapassado durante uma execução. O Global Context continua sendo a fonte de verdade.

## Skills

Skills são arquivos `SKILL.md` lazy-loaded. O contexto base conhece apenas `name` e `description`; o corpo completo entra somente no reasoning que solicitou a Skill.

Skills disponíveis:

- `planning`;
- `sql`;
- `analysis`;
- `visualization`.

## Observer e reattach

Runtime e observação são independentes:

```text
Runtime --> ExecutionEventSink --> Redis
                                   |
                                   v
                           ExecutionObserver
                                   |
                                   v
                                  SSE
```

A Execution pertence ao Runtime; a conexão pertence ao Observer. Atualizar a página ou perder a conexão não cancela nem reinicia a execução.

## Banco interno e migrations

O schema do PostgreSQL é versionado exclusivamente com Alembic. As migrations pertencem ao mesmo package que possui os models persistentes:

```text
packages/core/
├── alembic.ini
├── migrations/
│   ├── env.py
│   ├── bootstrap.py
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_add_session_titles.py
└── src/package/agent/database/
```

`packages/core/migrations/bootstrap.py` suporta banco novo e adoção segura do schema legado anterior. Schemas parcialmente compatíveis falham explicitamente em vez de serem adotados silenciosamente.

Migrations são um job separado. API e Runner não executam migrations implicitamente no startup.

## Docker

Existe uma única imagem Python compartilhada por API, Runner, Streamlit e pelo job de migrations:

```text
docker/images/app/Dockerfile
```

Os processos são diferenciados apenas pelo comando definido no `compose.yaml`. O SQLite do desafio não é copiado para a imagem; somente o Runner recebe o arquivo por bind mount read-only.

## Execução local com Docker Compose

Copie as variáveis de ambiente:

```bash
cp .env.example .env
```

Configure o provider, por exemplo:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave
```

Suba o stack:

```bash
docker compose up --build
```

Ordem principal:

```text
PostgreSQL healthy
      |
      v
migrations (one-shot)
      |
      v
FastAPI healthy
   +--+--+
   |     |
Runner Streamlit
```

A interface fica em `http://localhost:8501` e a API em `http://localhost:8000`.

O Runner pode ser escalado:

```bash
docker compose up --build --scale runner=2
```

Para encerrar:

```bash
docker compose down
```

Para remover também o volume PostgreSQL:

```bash
docker compose down -v
```

## Execução sem containers para os processos Python

Instale as dependências do projeto e os packages locais:

```bash
pip install -e ".[dev]"
pip install --no-deps \
  -e packages/core \
  -e packages/api \
  -e packages/runner \
  -e packages/ui
```

Depois:

```bash
cd packages/core && alembic upgrade head && cd ../..
uvicorn package.api.http.app:app --reload
python -m package.runner.main
streamlit run packages/ui/src/package/ui/app.py
```

## Testes

```bash
pytest
```

Os testes concorrentes contra PostgreSQL são habilitados com:

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 pytest tests/test_context_repository_concurrency.py
```

O workflow `.github/workflows/tests.yml` valida o Compose, constrói a imagem compartilhada, executa migrations duas vezes para validar idempotência, roda `alembic check`, habilita os testes PostgreSQL e browser e executa a suíte completa.

## Estado atual

Já estão implementados: execução durável via Outbox, Runner independente, Observer com reattach, Context Manager com snapshots e recuperação lexical, Skills lazy-loaded, providers OpenAI/DeepSeek, Database Tool read-only, loop LangGraph, interface Streamlit, cancelamento de inferência, migrations Alembic e stack completo via Docker Compose.
