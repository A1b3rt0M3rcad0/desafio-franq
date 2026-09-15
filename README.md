# Desafio Franq

Implementação do Desafio Técnico 1: um Assistente Virtual de Dados capaz de investigar um banco SQLite de forma autônoma, executar múltiplas operações, recuperar-se de falhas e responder perguntas de negócio com rastreabilidade.

O projeto separa três processos/packages principais:

- `package.agent`: runtime, contexto, Skills, Tools, Observer, trace e persistência do agente.
- `package.api`: API HTTP/SSE. Pode importar `agent`, mas nunca `runner`.
- `package.runner`: consumer independente que executa o agente. Pode importar `agent`, mas nunca `api`.

A interface fica em `package.ui` e consome somente a API pública.

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

PostgreSQL é a fonte durável de sessões, execuções, outbox, trace, Global Context e snapshots. Redis mantém hot state e o stream realtime. O SQLite em `data/anexo_desafio_1.db` é o banco de negócio acessado exclusivamente pela Database Tool read-only.

## LLM

O Agent depende apenas de `LLMClient`. Os providers concretos usam LangChain:

- `openai`: `OpenAILLM` baseado em `ChatOpenAI`;
- `deepseek`: `DeepSeekLLM` baseado em `ChatDeepSeek`.

O provider ativo é escolhido por `LLM_PROVIDER=openai` ou `LLM_PROVIDER=deepseek`. A janela de contexto e a contagem de tokens vêm do modelo ativo; não são valores mockados no runtime.

A API não bloqueia a criação de uma Execution com base na disponibilidade do Runner ou do provider. A etapa de Acceptance é responsável apenas por persistir `Execution(PENDING) + Outbox` atomicamente e retornar `202 Accepted`.

Disponibilidade/configuração do LLM pertence ao Runner. O Runner publica seu estado de readiness no Redis apenas para observabilidade operacional; essa readiness não participa da admissão da requisição. Se o Runner estiver degradado por configuração inválida, ele continua consumindo o Outbox com um runtime indisponível e transforma a Execution em `failed`. Se o provider rejeitar uma chamada depois que o runtime foi composto, a falha também é terminal para aquela Execution. Em ambos os casos o erro chega ao cliente pelo fluxo normal `Execution -> Observer -> SSE`, sem deixar a conversa presa em `pending` e sem reexecutar indefinidamente a mesma tarefa.

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

O contexto é dividido em:

```text
Global Context
  = memória durável completa da sessão

Execution Context
  = working context da execução atual

Context Snapshot
  = checkpoint semântico compacto para continuidade

Context Budget
  = percentual máximo do contexto dinâmico antes de compactação

Global Context Retriever
  = busca lexical sob demanda sobre informações antigas
```

O percentual é definido por `AGENT_CONTEXT_BUDGET_PERCENT`. A janela real e a contagem de tokens são obtidas pelo adapter do modelo selecionado.

Snapshots são criados ao final de cada execução e também quando o Context Budget é ultrapassado durante uma execução. O Global Context continua sendo a fonte de verdade, permitindo recuperar detalhes eventualmente omitidos pelos summaries.

## Skills

Skills são arquivos `SKILL.md` lazy-loaded. O contexto base conhece apenas `name` e `description`. O corpo completo entra somente no reasoning que solicitou a Skill e é descartado depois.

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

O reattach usa `projection + high-watermark + live tail`. O protocolo público utiliza sequência lógica; o cursor interno do Redis não é exposto ao cliente. Quando Redis não está disponível, PostgreSQL continua sendo a fonte autoritativa do estado durável.

## Interface Streamlit

A interface é deliberadamente simples: um chat com acompanhamento da execução e renderização do resultado dentro da própria resposta.

Ela suporta:

- criação automática de Session;
- recuperação do histórico da Session através da API;
- reattach de Execution ativa após refresh usando o Observer/SSE;
- resposta textual no chat;
- tabelas;
- gráficos `bar`, `line` e `scatter`.

Quando houver visualização, o frontend espera um resultado no formato:

```json
{
  "data": {
    "columns": ["estado", "clientes"],
    "rows": [["SP", 18], ["SC", 13]]
  },
  "visualization": {
    "type": "bar",
    "title": "Clientes por estado",
    "x": "estado",
    "y": ["clientes"]
  }
}
```

Se houver dados tabulares mas nenhuma especificação de visualização, a interface degrada automaticamente para tabela. Uma especificação inválida também degrada para tabela em vez de quebrar a conversa.

## Execução local com Docker Compose

O `compose.yaml` sobe a aplicação completa: PostgreSQL, Redis, FastAPI, Runner e Streamlit. O mesmo `Dockerfile` é reutilizado pelos três processos Python, mantendo API, Runner e interface como processos separados apesar de compartilharem a mesma imagem.

Primeiro copie as variáveis de ambiente e preencha a chave do provider selecionado:

```bash
cp .env.example .env
```

Exemplo para OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave
```

Depois suba todo o stack:

```bash
docker compose up --build
```

Quando os serviços estiverem saudáveis, a conversa pode ser iniciada diretamente em:

```text
http://localhost:8501
```

A API fica disponível em:

```text
http://localhost:8000
```

O startup é ordenado por healthchecks: PostgreSQL e Redis ficam saudáveis, a API sobe e cria o schema interno quando necessário, depois Runner e Streamlit são iniciados. Dentro da rede Docker, a API e o Runner recebem automaticamente URLs internas para PostgreSQL/Redis, enquanto o Streamlit utiliza `http://api:8000`.

O serviço `runner` é escalável. Cada container recebe o próprio hostname como `RUNNER_ID`, então é possível iniciar múltiplos consumers sem colisão de identidade:

```bash
docker compose up --build --scale runner=2
```

A readiness dos Runners é publicada no Redis para diagnóstico e observabilidade operacional, não para impedir a etapa de Acceptance da API.

O PostgreSQL utiliza volume nomeado para preservar Sessions, Executions, Outbox, traces e contexto entre reinicializações do stack. O Redis permanece responsável apenas pelo estado realtime/hot.

Para encerrar:

```bash
docker compose down
```

Para também remover o volume durável de desenvolvimento:

```bash
docker compose down -v
```

### Execução sem containers para os processos Python

Também é possível subir apenas PostgreSQL/Redis e executar API, Runner e Streamlit localmente. Nesse caso mantenha os valores `localhost` definidos em `.env` e execute:

```bash
pip install -e .
uvicorn package.api.http.app:app --reload
python -m package.runner.main
streamlit run package/ui/app.py
```

## Testes

```bash
pytest
```

O workflow `.github/workflows/tests.yml` valida também a configuração do Docker Compose e executa a suíte automaticamente em todo pull request direcionado à `master`.

## Estado atual

Já estão implementados: execução durável via Outbox, Runner independente, Observer com reattach, Context Manager com snapshots e recuperação lexical, Skills lazy-loaded, providers OpenAI/DeepSeek, Database Tool read-only, loop LangGraph, interface Streamlit e stack completo via Docker Compose.

As próximas capacidades específicas do desafio são consolidar o tratamento dirigido de erros SQL, estruturar o resultado analítico final e fazer o Agent produzir a especificação de visualização consumida pela interface.
