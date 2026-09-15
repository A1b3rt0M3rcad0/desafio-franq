# Architecture

## Repository topology

The repository is organized around executable and ownership boundaries instead of a single application package.

```text
packages/
├── core/     # agent runtime, persistence, migrations and shared execution contracts
├── api/      # FastAPI composition root
├── runner/   # independent execution consumer
└── ui/       # Streamlit presentation process
```

`packages/core` owns the PostgreSQL schema and therefore owns Alembic configuration and migration history. `api` and `runner` depend on Core behavior, while `ui` talks to the system through the public HTTP/SSE boundary.

Python imports intentionally remain under the `package.*` namespace. The physical package split is implemented with a shared namespace package so the topology can change without rewriting domain imports as part of the repository-organization refactor.

## Runtime topology

```text
Streamlit -> FastAPI -> PostgreSQL
                |
                +-> Outbox -> Runner -> Agent Runtime -> SQLite
                                  |
                                  +-> Redis events -> Observer -> SSE
```

PostgreSQL is durable application state. Redis is realtime/hot state. The challenge SQLite database is external business data and is mounted read-only only into the Runner process.

## Containers

All Python processes use the same application image from `docker/images/app/Dockerfile`. Compose provides different commands for migrations, API, Runner and Streamlit. Migrations are an explicit one-shot job and are not executed implicitly by application entrypoints.
