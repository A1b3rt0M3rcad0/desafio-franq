# Packages

| Package | Responsibility |
| --- | --- |
| `core` | Agent runtime, context, tools, skills, persistence contracts and Alembic migrations |
| `api` | FastAPI HTTP/SSE process composition root |
| `runner` | Independent execution/outbox consumer composition root |
| `ui` | Streamlit presentation process |

The packages share the `package.*` Python namespace, while each distribution owns a separate source root under its own `src/` directory.
