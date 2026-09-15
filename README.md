# Desafio Franq

Foundation for challenge 1: a durable agent execution architecture for a data assistant.

The project deliberately separates three processes/packages:

- `package.agent`: agent runtime, session persistence, hot state, trace, tools and contracts.
- `package.api`: HTTP/SSE inbound interface. It may import `agent`, but never `runner`.
- `package.runner`: independent consumer process that imports `agent`, consumes durable work and executes it. It never imports `api`.

## Runtime architecture

```text
Client
  |
  v
API --------------------> Agent package
  |                            ^
  | create session/run         |
  v                            |
PostgreSQL <---- Runner -------+
  ^                |
  |                v
  |           Agent Runtime -----> Observer -----> Redis hot state/stream
  |                                      |
  +---------------- Trace ---------------+

Agent Database Tool -----------------------------> user SQLite database
                                                   data/anexo_desafio_1.db
```

There are three distinct data responsibilities:

1. **PostgreSQL** is the internal durable database for agent sessions, executions, outbox and trace.
2. **Redis** is the execution hot state and resumable live event stream used by the interface.
3. **SQLite (`anexo_desafio_1.db`)** is user/business data and is only accessed through `agent.tools.database`; it is not the agent's internal database.

The HTTP connection does not own an execution. Refreshing or losing the browser connection only interrupts observation. The runner continues executing, the observer continues writing events, and the client can reconnect to the Redis Stream using `Last-Event-ID`.

## Current scope

This commit establishes the architecture and infrastructure foundation: package boundaries, durable execution/outbox models, Redis hot state and streams, observer contracts, execution trace, API endpoints, runner consumer, and a read-only SQLite database tool. The LLM-driven planning/query-analysis strategy is intentionally left for the next implementation stage.

## Local infrastructure

```bash
cp .env.example .env
docker compose up -d
```

Install development dependencies with your Python package manager and run:

```bash
pytest
```
