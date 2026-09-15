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


def test_authentication_and_invalid_model_errors_are_not_retryable() -> None:
    assert classify_provider_exception(StatusError(401)).retryable is False
    assert classify_provider_exception(StatusError(403)).retryable is False
    assert classify_provider_exception(ResponseError(404)).retryable is False


def test_rate_limit_and_server_errors_are_retryable() -> None:
    assert classify_provider_exception(StatusError(429)).retryable is True
    assert classify_provider_exception(StatusError(500)).retryable is True
    assert classify_provider_exception(ResponseError(503)).retryable is True


def test_unknown_provider_errors_remain_retryable_at_provider_boundary() -> None:
    failure = classify_provider_exception(RuntimeError("connection reset"))

    assert failure.status_code is None
    assert failure.retryable is True
