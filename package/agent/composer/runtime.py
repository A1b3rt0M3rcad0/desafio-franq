from package.agent.llm.contracts import LLMClient
from package.agent.observer.contracts import ExecutionObserver
from package.agent.runtime.execution import AgentRuntime
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.program import LangGraphAgentProgram
from package.agent.tools.registry import ToolRegistry


def compose_agent_program(*, llm: LLMClient, tools: ToolRegistry) -> LangGraphAgentProgram:
    return LangGraphAgentProgram(llm=llm, tools=tools)


def compose_runtime(
    *,
    program: LangGraphAgentProgram,
    observer: ExecutionObserver,
    policy: RuntimePolicy,
) -> AgentRuntime:
    return AgentRuntime(program=program, observer=observer, policy=policy)
