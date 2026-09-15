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

## Execução local

Copie as variáveis de ambiente e suba PostgreSQL e Redis:

```bash
cp .env.example .env
docker compose up -d
```

Preencha a chave do provider selecionado em `.env` e instale o projeto:

```bash
pip install -e .
```

Em terminais separados, execute:

```bash
uvicorn package.api.http.app:app --reload
```

```bash
python -m package.runner.main
```

```bash
streamlit run package/ui/app.py
```

A interface usa `STREAMLIT_API_BASE_URL`, cujo valor recomendado para desenvolvimento local é `http://localhost:8000`.

## Testes

```bash
pytest
```

O workflow `.github/workflows/tests.yml` executa a suíte automaticamente em todo pull request direcionado à `master`.

## Estado atual

Já estão implementados: execução durável via Outbox, Runner independente, Observer com reattach, Context Manager com snapshots e recuperação lexical, Skills lazy-loaded, providers OpenAI/DeepSeek, Database Tool read-only, loop LangGraph e interface Streamlit.

As próximas capacidades específicas do desafio são consolidar o tratamento dirigido de erros SQL, estruturar o resultado analítico final e fazer o Agent produzir a especificação de visualização consumida pela interface.
