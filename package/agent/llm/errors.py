from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMProviderFailure:
    status_code: int | None
    retryable: bool


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.status_code = status_code


def classify_provider_exception(exc: Exception) -> LLMProviderFailure:
    status_code = _extract_status_code(exc)
    if status_code is None:
        return LLMProviderFailure(status_code=None, retryable=True)
    if status_code in {400, 401, 403, 404, 422}:
        return LLMProviderFailure(status_code=status_code, retryable=False)
    if status_code in {408, 409, 425, 429} or status_code >= 500:
        return LLMProviderFailure(status_code=status_code, retryable=True)
    return LLMProviderFailure(status_code=status_code, retryable=False)


def _extract_status_code(exc: Exception) -> int | None:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        direct = getattr(current, "status_code", None)
        if isinstance(direct, int) and not isinstance(direct, bool):
            return direct
        response: Any = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int) and not isinstance(response_status, bool):
            return response_status
        current = current.__cause__ or current.__context__
    return None
