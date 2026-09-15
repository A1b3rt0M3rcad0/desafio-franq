from package.agent.context.manager import ContextManager
from package.agent.llm.contracts import LLMClient
from package.agent.observer.contracts import ExecutionEventSink
from package.agent.runtime.execution import AgentRuntime
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.program import LangGraphAgentProgram
from package.agent.tools.registry import ToolRegistry


def compose_agent_program(
    *,
    llm: LLMClient,
    tools: ToolRegistry,
    context_manager: ContextManager,
) -> LangGraphAgentProgram:
    return LangGraphAgentProgram(
        llm=llm,
        tools=tools,
        context_manager=context_manager,
    )


def compose_runtime(
    *,
    program: LangGraphAgentProgram,
    event_sink: ExecutionEventSink,
    policy: RuntimePolicy,
) -> AgentRuntime:
    return AgentRuntime(program=program, event_sink=event_sink, policy=policy)
