from package.agent.observer.contracts import ExecutionEventSink
from package.agent.observer.events import ExecutionEvent


class CompositeExecutionEventSink:
    def __init__(self, *sinks: ExecutionEventSink) -> None:
        self._sinks = sinks

    async def emit(self, event: ExecutionEvent) -> None:
        for sink in self._sinks:
            await sink.emit(event)
