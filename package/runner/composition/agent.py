from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState
from package.agent.observer.publisher import RedisExecutionEventSink
from package.agent.runtime.contracts import AgentProgram
from package.agent.runtime.execution import AgentRuntime
from package.agent.runtime.policies import create_runtime_policy
from package.agent.trace.recorder import TraceRecorder


@dataclass(slots=True)
class AgentRuntimeFactory:
    program: AgentProgram
    hot_state: ExecutionHotState
    event_stream: ExecutionEventStream
    session_factory: async_sessionmaker[AsyncSession]
    max_iterations: int
    max_sql_retries: int
    max_parallel_tool_calls_per_tool: int
    projection_max_activities: int

    def create(self) -> AgentRuntime:
        event_sink = RedisExecutionEventSink(
            hot_state=self.hot_state,
            event_stream=self.event_stream,
            projection_max_activities=self.projection_max_activities,
            trace_recorder=TraceRecorder(self.session_factory),
        )
        policy = create_runtime_policy(
            max_iterations=self.max_iterations,
            max_sql_retries=self.max_sql_retries,
            max_parallel_tool_calls_per_tool=self.max_parallel_tool_calls_per_tool,
        )
        return AgentRuntime(
            program=self.program,
            observer=event_sink,
            policy=policy,
        )
