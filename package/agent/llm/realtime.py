from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar


TextDeltaHandler = Callable[[str], Awaitable[None]]

_text_delta_handler: ContextVar[TextDeltaHandler | None] = ContextVar(
    "llm_text_delta_handler",
    default=None,
)


def current_text_delta_handler() -> TextDeltaHandler | None:
    return _text_delta_handler.get()


@contextmanager
def bind_text_delta_handler(handler: TextDeltaHandler) -> Iterator[None]:
    token = _text_delta_handler.set(handler)
    try:
        yield
    finally:
        _text_delta_handler.reset(token)
