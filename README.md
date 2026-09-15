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

## LLMs

O Agent depende somente do contrato `LLMClient`. As implementações concretas utilizam integrações oficiais do ecossistema LangChain e são executadas por um grafo LangGraph, preservando streaming de mensagens sem acoplar o restante do runtime ao provider.

Os providers disponíveis são:

- `openai`: `ChatOpenAI`, configurado para utilizar a Responses API e executado através do LangGraph.
- `deepseek`: `ChatDeepSeek`, executado através do mesmo contrato e do mesmo adapter LangGraph.

O provider ativo é selecionado por `LLM_PROVIDER=openai` ou `LLM_PROVIDER=deepseek`. Apenas a configuração específica do provider selecionado é carregada pelo Runner.

## Configuração

Os valores operacionais do backend não ficam definidos diretamente no código. A configuração é carregada do ambiente por meio de `pydantic-settings`. O arquivo `.env.example` contém valores recomendados para desenvolvimento local e deve ser copiado para `.env` antes da execução.

As principais categorias configuráveis são:

- API: título e criação automática do schema local.
- PostgreSQL: imagem, credenciais, portas e healthcheck.
- Redis: conexão, namespace das chaves, TTL do hot state, tamanho e leitura dos Streams.
- Database Tool: caminho do SQLite, timeout de conexão, timeout de query, limite de linhas e frequência do progress handler.
- LLM: provider (`openai` ou `deepseek`), modelo, credenciais, timeout, limite de saída, retries e esforço de raciocínio.
- Agent Runtime: quantidade máxima de iterações e tentativas de correção de SQL.
- Runner/Outbox: identificador do worker, intervalo de polling, batch size e política de retry/backoff.

Parâmetros que fazem parte do protocolo ou do domínio, como nomes de eventos, estados da execução e regras de segurança SQL, permanecem definidos em código por não serem configuração de ambiente.

## Escopo atual

A fundação arquitetural e de infraestrutura já contém boundaries entre packages, modelos de execução durável e outbox, hot state e streams no Redis, contratos do Observer, trace de execução, endpoints da API, consumer do Runner, Database Tool read-only e adapters LLM para OpenAI e DeepSeek executados com LangGraph.

O próximo núcleo funcional é a implementação do programa agentic que utilizará essas capacidades para planejamento, geração de consultas, execução, recuperação de erros, análise dos resultados e seleção de visualização.

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
