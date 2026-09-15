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

As sequências de `Global Context` e `Context Snapshot` são ordenadas por sessão. A alocação da sequência é protegida por lock transacional da própria `agent_sessions`, permitindo que Tools continuem executando em paralelo sem colisões de `(session_id, sequence)` durante a persistência.

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
- seleção e recuperação do histórico de Sessions através da API;
- reattach de Execution ativa após refresh usando o Observer/SSE;
- resposta textual com streaming;
- um único composer cujo botão muda de `Enviar` para `Stop` enquanto existe uma execução ativa;
- cancelamento real da inferência pelo Runner;
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

## Banco interno e migrations

O schema do PostgreSQL é versionado exclusivamente com Alembic. A API não executa `Base.metadata.create_all()` e não é autoridade sobre criação de tabelas.

A estrutura de migrations fica em:

```text
alembic.ini
migrations/
  env.py
  bootstrap.py
  versions/
    0001_initial_schema.py
Dockerfile.migrations
```

`migrations/bootstrap.py` suporta dois caminhos:

- banco novo: executa `alembic upgrade head` normalmente;
- banco legado criado pela versão anterior via `create_all`: valida a presença das tabelas/colunas esperadas, executa `alembic stamp 0001_initial_schema` sem destruir dados e depois aplica migrations futuras.

Schemas legados parciais não são adotados silenciosamente: o container de migrations falha e impede a aplicação de iniciar.

## Execução local com Docker Compose

O `compose.yaml` sobe a aplicação completa: PostgreSQL, migration one-shot, Redis, FastAPI, Runner e Streamlit. API, Runner e interface continuam processos separados.

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

A ordem relevante de startup é:

```text
PostgreSQL healthy
      |
      v
migrations (one-shot)
      |
      | service_completed_successfully
      v
FastAPI healthy
   +--+--+
   |     |
Runner Streamlit
```

Redis inicia em paralelo e também precisa estar saudável antes da API.

Se uma migration falhar, API, Runner e Streamlit não iniciam. Isso evita descobrir um schema incompatível no meio de uma Execution.

Quando os serviços estiverem saudáveis, a conversa pode ser iniciada diretamente em:

```text
http://localhost:8501
```

A API fica disponível em:

```text
http://localhost:8000
```

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

Também é possível subir PostgreSQL/Redis, aplicar migrations e executar API, Runner e Streamlit localmente. Nesse caso mantenha os valores `localhost` definidos em `.env` e execute:

```bash
pip install -e .
alembic upgrade head
uvicorn package.api.http.app:app --reload
python -m package.runner.main
streamlit run package/ui/app.py
```

## Testes

```bash
pytest
```

Os testes de concorrência reais do repositório PostgreSQL são habilitados com:

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 pytest tests/test_context_repository_concurrency.py
```

O workflow `.github/workflows/tests.yml` valida Docker Compose, executa o container one-shot de migrations duas vezes para validar idempotência, roda `alembic check`, habilita os testes concorrentes contra PostgreSQL real e depois executa toda a suíte.

## Estado atual

Já estão implementados: execução durável via Outbox, Runner independente, Observer com reattach, Context Manager com snapshots e recuperação lexical, Skills lazy-loaded, providers OpenAI/DeepSeek, Database Tool read-only, loop LangGraph, interface Streamlit, cancelamento de inferência, migrations Alembic e stack completo via Docker Compose.

As próximas capacidades específicas do desafio são consolidar o tratamento dirigido de erros SQL, estruturar o resultado analítico final e fazer o Agent produzir a especificação de visualização consumida pela interface.
