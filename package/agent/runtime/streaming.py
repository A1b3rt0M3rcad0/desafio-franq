from package.agent.observer.contracts import ExecutionEventSink
from package.agent.observer.events import ExecutionEvent, ExecutionEventType


class RuntimeStreamingEventSink:
    """Adds model-native text deltas without duplicating the final answer event.

    The wrapped runtime program still owns semantic decisions. This adapter only
    bridges text chunks produced by the active model into the execution event
    stream and suppresses the legacy full-answer delta when it matches the text
    that was already streamed for the final reasoning step.
    """

    def __init__(self, *, delegate: ExecutionEventSink, execution_id: str) -> None:
        self._delegate = delegate
        self._execution_id = execution_id
        self._streamed_text = ""

    async def emit_model_delta(self, content: str) -> None:
        if not content:
            return
        self._streamed_text += content
        await self._delegate.emit(
            ExecutionEvent(
                execution_id=self._execution_id,
                type=ExecutionEventType.ASSISTANT_DELTA,
                payload={"content": content},
            )
        )

    async def emit(self, event: ExecutionEvent) -> None:
        if event.type == ExecutionEventType.AGENT_DECISION:
            if str(event.payload.get("decision") or "") == "action":
                self._streamed_text = ""

        if event.type == ExecutionEventType.ASSISTANT_DELTA and self._streamed_text:
            content = str(event.payload.get("content") or "")
            if content == self._streamed_text:
                return

        await self._delegate.emit(event)
