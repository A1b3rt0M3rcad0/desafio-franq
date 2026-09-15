from package.agent.observer.events import ExecutionEvent, TRACEABLE_EVENT_TYPES


class TracePolicy:
    def should_record(self, event: ExecutionEvent) -> bool:
        return event.type in TRACEABLE_EVENT_TYPES
