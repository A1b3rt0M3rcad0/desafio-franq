from typing import Protocol

from package.agent.runtime.execution import AgentRuntime


class RuntimeFactory(Protocol):
    def create(self) -> AgentRuntime: ...
