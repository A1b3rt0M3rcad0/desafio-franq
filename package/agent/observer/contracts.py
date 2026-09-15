from typing import Protocol

from package.agent.observer.events import ExecutionEvent


class ExecutionObserver(Protocol):
    async def emit(self, event: ExecutionEvent) -> None: ...
