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

A implementação concreta de `AgentProgram` utiliza LangGraph para controlar o ciclo de execução. O grafo é genérico: ele não conhece OpenAI, DeepSeek ou SQLite diretamente; depende de `LLMClient`, `ToolRegistry` e `ContextManager`.

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
  | action                       | resposta final
  v                              v
Tool / Skill                  Answer
  |                              |
  | resultado/contexto           v
  +-----------> Agent           END -> Client
```

Cada passagem pelo node `Agent` inicia uma nova iteração. O `Reasoning` pode produzir uma ou mais chamadas de Tool, solicitar uma Skill ou concluir a execução com uma resposta. Resultados e erros de Tools retornam ao Agent como `ToolMessage`, permitindo novas tentativas sem encerrar imediatamente a execução.

O ciclo termina quando:

- o modelo produz uma resposta sem novas ações; ou
- `AGENT_RUNTIME_MAX_ITERATIONS` é atingido.

O Observer recebe apenas eventos estruturados (`agent.iteration.started`, `agent.decision`, lifecycle da LLM, Skills e Tools, resposta final etc.). Raciocínio interno/chain-of-thought do modelo não é persistido nem exposto.

## Context Manager

O `ContextManager` controla o working context entregue à LLM e diferencia explicitamente Skills de Tools.

### Skills

Skills representam conhecimento ou instruções especializadas e utilizam lazy loading:

```text
Contexto base
  |
  +-- skill: nome + descrição
  |
  v
Agent decide usar a skill
  |
  v
use_skill([nome])
  |
  v
conteúdo completo carregado
  |
  v
próximo Reasoning
  |
  v
conteúdo descartado
```

O conteúdo completo de uma Skill nunca é anexado às mensagens persistentes do grafo. O Agent mantém permanentemente apenas o catálogo com `name` e `description`. Quando chama `use_skill`, o conteúdo é carregado pelo `SkillRegistry`, inserido em uma cópia das mensagens somente para a próxima chamada da LLM e removido logo depois. Se a mesma Skill for necessária novamente, ela precisa ser solicitada novamente.

Mais de uma Skill pode ser solicitada para a mesma etapa de reasoning. O trace registra somente os nomes e o lifecycle (`skill.requested`, `skill.context.loaded`, `skill.context.released`), nunca o conteúdo privado da Skill.

### Tools

Tools representam efeitos/capacidades executáveis. Nome, descrição e JSON Schema são enviados à LLM através de tool calling. Uma Tool pode ser chamada repetidamente na mesma Execution; sucesso ou erro volta ao contexto e o Agent decide se conclui, tenta novamente ou realiza outra operação.

Chamadas independentes produzidas na mesma decisão são executadas concorrentemente. O limite por **mesma Tool** é configurado por `AGENT_TOOL_MAX_CONCURRENCY_PER_TOOL` e o valor recomendado para desenvolvimento é `3`. Isso limita concorrência, não o número total de usos da Tool durante uma Execution.

A direção de dependência é:

```text
Agent Runtime
      |
      v
AgentProgram (LangGraph)
      |
      +---------> ContextManager -----> SkillRegistry
      |
      +---------> ToolRegistry
      |
      v
LLMClient
   |      |
   v      v
OpenAI  DeepSeek
```

O Runner compõe concretamente LLM, Database Tool, registries, Context Manager, `LangGraphAgentProgram`, Observer e Worker.

## Configuração

Os valores operacionais do backend não ficam definidos diretamente no código. A configuração é carregada do ambiente por meio de `pydantic-settings`. O arquivo `.env.example` contém valores recomendados para desenvolvimento local e deve ser copiado para `.env` antes da execução.

As principais categorias configuráveis são:

- API: título e criação automática do schema local.
- PostgreSQL: imagem, credenciais, portas e healthcheck.
- Redis: conexão, namespace das chaves, TTL do hot state, tamanho e leitura dos Streams.
- Database Tool: caminho do SQLite, timeout de conexão, timeout de query, limite de linhas e frequência do progress handler.
- LLM: provider (`openai` ou `deepseek`), modelo, credenciais, timeout, limite de saída, retries e esforço de raciocínio.
- Agent Runtime: quantidade máxima de iterações, tentativas de correção de SQL e concorrência máxima por Tool.
- Runner/Outbox: identificador do worker, intervalo de polling, batch size e política de retry/backoff.

Parâmetros que fazem parte do protocolo ou do domínio, como nomes de eventos, estados da execução e regras de segurança SQL, permanecem definidos em código por não serem configuração de ambiente.

## Escopo atual

A fundação arquitetural e de infraestrutura contém boundaries entre packages, modelos de execução durável e outbox, hot state e streams no Redis, contratos do Observer, trace de execução, endpoints da API, consumer do Runner, Database Tool read-only, adapters LLM LangChain para OpenAI e DeepSeek, ciclo iterativo implementado com LangGraph e Context Manager com Skills efêmeras e Tools reutilizáveis.

As próximas etapas específicas do desafio são registrar Skills concretas para planejamento/SQL/análise, carregar histórico de sessão relevante, implementar tratamento dirigido de falhas de SQL, análise final dos resultados e seleção de visualização.

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
