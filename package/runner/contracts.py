from typing import Protocol

from package.agent.observer.contracts import ExecutionEventSink
from package.agent.runtime.execution import AgentRuntime


class RuntimeFactory(Protocol):
    def create_event_sink(self) -> ExecutionEventSink: ...

    def create(self) -> AgentRuntime: ...
