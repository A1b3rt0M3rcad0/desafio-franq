# Desafio Franq

Fundação do Desafio Técnico 1: uma arquitetura de execução durável para um assistente de dados baseado em agentes.

O projeto separa deliberadamente três processos/packages principais:

- `package.agent`: runtime do agente, persistência de sessões, hot state, trace, tools e contratos.
- `package.api`: interface de entrada HTTP/SSE. Pode importar `agent`, mas nunca `runner`.
- `package.runner`: processo consumidor independente que importa `agent`, consome trabalhos duráveis e executa o agente. Nunca importa `api`.

## Arquitetura de execução

```text
Cliente
  |
  v
API --------------------> Agent package
  |                            ^
  | cria sessão/execução       |
  v                            |
PostgreSQL <---- Runner -------+
  ^                |
  |                v
  |           Agent Runtime -----> Observer -----> Redis hot state/stream
  |                                      |
  +---------------- Trace ---------------+

Agent Database Tool -----------------------------> SQLite do usuário
                                                   data/anexo_desafio_1.db
```

Existem três responsabilidades de dados distintas:

1. **PostgreSQL** é o banco interno e durável do agente, responsável por sessões, execuções, outbox e trace.
2. **Redis** é utilizado como hot state da execução e como stream de eventos em tempo real, permitindo que a interface retome o acompanhamento de uma execução após uma reconexão.
3. **SQLite (`anexo_desafio_1.db`)** contém os dados de negócio consultados pelo agente e é acessado exclusivamente por meio de `agent.tools.database`; ele não faz parte do banco interno do agente.

A conexão HTTP não é proprietária da execução. Atualizar a página ou perder a conexão do navegador interrompe apenas a observação da execução. O Runner continua processando, o Observer continua publicando os eventos e o cliente pode se reconectar ao Redis Stream utilizando `Last-Event-ID` para continuar a partir do último evento recebido.

## Escopo atual

Esta etapa estabelece a fundação arquitetural e de infraestrutura do projeto: boundaries entre packages, modelos de execução durável e outbox, hot state e streams no Redis, contratos do Observer, trace de execução, endpoints da API, consumer do Runner e uma ferramenta de acesso read-only ao banco SQLite fornecido no desafio.

A estratégia orientada por LLM para planejamento, geração de consultas, execução, recuperação de erros e análise dos resultados será implementada na próxima etapa.

## Infraestrutura local

Crie o arquivo de configuração local e suba PostgreSQL e Redis:

```bash
cp .env.example .env
docker compose up -d
```

Instale as dependências de desenvolvimento utilizando o gerenciador de pacotes Python de sua preferência e execute os testes:

```bash
pytest
```
