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

O Agent depende somente do contrato `LLMClient`. As implementações concretas de provider ficam na camada de integração com modelos e utilizam LangChain:

- `openai`: `OpenAILLM`, baseado em `ChatOpenAI`.
- `deepseek`: `DeepSeekLLM`, baseado em `ChatDeepSeek`.

Os adapters traduzem as mensagens internas, configuram o provider e expõem `invoke`/`stream` pelo contrato `LLMClient`. Tool calling também atravessa esse contrato; o runtime não depende diretamente de classes do LangChain.

O provider ativo é selecionado por `LLM_PROVIDER=openai` ou `LLM_PROVIDER=deepseek`. Apenas a configuração específica do provider selecionado é carregada pelo Runner.

## Runtime do Agent

A implementação concreta de `AgentProgram` utiliza LangGraph para controlar o ciclo de execução. O grafo é genérico: ele não conhece OpenAI, DeepSeek ou SQLite diretamente; depende apenas de `LLMClient` e `ToolRegistry`.

```text
START
  |
  v
Agent
  |
  | valida limite e inicia uma iteração
  v
Reasoning / LLM
  |
  +------------------------------+
  |                              |
  | tool call                    | resposta final
  v                              v
Tool                           Answer
  |                              |
  | resultado/erro               v
  +-----------> Agent           END -> Client
```

Cada passagem pelo node `Agent` inicia uma nova iteração. O `Reasoning` pode produzir uma ou mais chamadas de Tool ou concluir a execução com uma resposta. Após uma Tool, o resultado é convertido em `ToolMessage` e devolvido ao contexto do Agent, iniciando uma nova iteração. Erros de Tool também retornam ao Agent como resultado estruturado, permitindo que ele tente corrigir sua decisão em vez de encerrar imediatamente a execução.

O ciclo termina quando:

- o modelo produz uma resposta sem novas chamadas de Tool; ou
- `AGENT_RUNTIME_MAX_ITERATIONS` é atingido.

O Observer recebe apenas eventos estruturados (`agent.iteration.started`, `agent.decision`, lifecycle da LLM e das Tools, resposta final etc.). Raciocínio interno/chain-of-thought do modelo não é persistido nem exposto.

A direção de dependência é:

```text
Agent Runtime
      |
      v
AgentProgram (LangGraph)
      |
      +---------> ToolRegistry
      |
      v
LLMClient
   |      |
   v      v
OpenAI  DeepSeek
```

O Runner já compõe concretamente LLM, Database Tool, Tool Registry, `LangGraphAgentProgram`, Observer e Worker; portanto a execução deixa de ser apenas uma fundação e passa a possuir um ciclo agentic executável.

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

A fundação arquitetural e de infraestrutura contém boundaries entre packages, modelos de execução durável e outbox, hot state e streams no Redis, contratos do Observer, trace de execução, endpoints da API, consumer do Runner, Database Tool read-only, adapters LLM LangChain para OpenAI e DeepSeek e o ciclo iterativo do Agent implementado com LangGraph.

As próximas etapas específicas do desafio são enriquecer o contexto e os prompts para planejamento analítico, tratamento dirigido de falhas de SQL, análise dos resultados e seleção de visualização.

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
