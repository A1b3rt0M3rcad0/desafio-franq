from package.agent.observer.contracts import ExecutionObserver
from package.agent.observer.events import ExecutionEvent


class CompositeExecutionObserver:
    def __init__(self, *observers: ExecutionObserver) -> None:
        self._observers = observers

    async def emit(self, event: ExecutionEvent) -> None:
        for observer in self._observers:
            await observer.emit(event)
