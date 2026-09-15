from collections.abc import AsyncIterator
from typing import Any, Protocol

from package.agent.observer.events import ExecutionEvent
from package.agent.observer.frames import ExecutionFrame


class ExecutionEventSink(Protocol):
    """Receives observable runtime facts produced by an execution."""

    async def emit(self, event: ExecutionEvent) -> None: ...


class DurableExecutionStateReader(Protocol):
    """Reads the canonical durable execution state used when realtime state is unavailable."""

    async def get(self, execution_id: str) -> dict[str, Any] | None: ...


class ExecutionObserver(Protocol):
    """Transport-neutral boundary for attaching and reattaching to an execution."""

    async def current_state(
        self,
        execution_id: str,
        *,
        last_sequence: int | None = None,
    ) -> ExecutionFrame: ...

    def observe(
        self,
        execution_id: str,
        *,
        last_sequence: int | None = None,
    ) -> AsyncIterator[ExecutionFrame]: ...
