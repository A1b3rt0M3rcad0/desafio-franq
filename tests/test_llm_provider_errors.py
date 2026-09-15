import pytest

from package.agent.llm.errors import classify_provider_exception


class StatusError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status={status_code}")
        self.status_code = status_code


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class ResponseError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"response status={status_code}")
        self.response = Response(status_code)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_non_retryable_provider_http_errors(status_code: int) -> None:
    failure = classify_provider_exception(StatusError(status_code))

    assert failure.status_code == status_code
    assert failure.retryable is False


@pytest.mark.parametrize("status_code", [408, 409, 425, 429, 500, 502, 503, 599])
def test_retryable_provider_http_errors(status_code: int) -> None:
    failure = classify_provider_exception(ResponseError(status_code))

    assert failure.status_code == status_code
    assert failure.retryable is True


@pytest.mark.parametrize("status_code", [405, 410, 418, 451])
def test_other_client_http_errors_are_terminal(status_code: int) -> None:
    failure = classify_provider_exception(StatusError(status_code))

    assert failure.status_code == status_code
    assert failure.retryable is False


def test_unknown_provider_errors_remain_retryable_at_provider_boundary() -> None:
    failure = classify_provider_exception(RuntimeError("connection reset"))

    assert failure.status_code is None
    assert failure.retryable is True


def test_status_code_is_discovered_through_exception_cause() -> None:
    try:
        try:
            raise StatusError(429)
        except StatusError as inner:
            raise RuntimeError("provider wrapper") from inner
    except RuntimeError as outer:
        failure = classify_provider_exception(outer)

    assert failure.status_code == 429
    assert failure.retryable is True


def test_boolean_status_code_is_not_treated_as_http_status() -> None:
    exc = RuntimeError("bad status")
    exc.status_code = True  # type: ignore[attr-defined]

    failure = classify_provider_exception(exc)

    assert failure.status_code is None
    assert failure.retryable is True
