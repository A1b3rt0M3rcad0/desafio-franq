from package.agent.observer.contracts import ExecutionObserver
from package.agent.runtime.contracts import AgentProgram
from package.agent.runtime.execution import AgentRuntime


def compose_runtime(*, program: AgentProgram, observer: ExecutionObserver) -> AgentRuntime:
    return AgentRuntime(program=program, observer=observer)
