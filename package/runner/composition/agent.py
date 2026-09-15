from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState
from package.agent.observer.observer import RedisExecutionObserver
from package.agent.runtime.contracts import AgentProgram
from package.agent.runtime.execution import AgentRuntime
from package.agent.trace.recorder import TraceRecorder


@dataclass(slots=True)
class AgentRuntimeFactory:
    program: AgentProgram
    hot_state: ExecutionHotState
    event_stream: ExecutionEventStream
    session_factory: async_sessionmaker[AsyncSession]

    def create(self) -> AgentRuntime:
        observer = RedisExecutionObserver(
            hot_state=self.hot_state,
            event_stream=self.event_stream,
            trace_recorder=TraceRecorder(self.session_factory),
        )
        return AgentRuntime(program=self.program, observer=observer)
