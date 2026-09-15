from typing import Any

import pytest

from package.ui.client import FranqApiClient, parse_sse_frames


class StubFranqApiClient(FranqApiClient):
    def __init__(self, payload: Any) -> None:
        super().__init__(base_url="http://api.test", timeout_seconds=1.0)
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        assert json_body is None
        self.calls.append((method, path))
        return self.payload


def test_list_sessions_requests_recent_sessions_from_api() -> None:
    payload = [{"id": "session-1"}, {"id": "session-2"}]
    client = StubFranqApiClient(payload)

    result = client.list_sessions(limit=25)

    assert result == payload
    assert client.calls == [("GET", "/sessions?limit=25")]


def test_list_sessions_rejects_invalid_limit_before_http_call() -> None:
    client = StubFranqApiClient([])

    with pytest.raises(ValueError, match="limit"):
        client.list_sessions(limit=0)

    assert client.calls == []


def test_list_sessions_rejects_non_list_api_payload() -> None:
    client = StubFranqApiClient({"id": "session-1"})

    with pytest.raises(ValueError, match="sessions endpoint"):
        client.list_sessions()


def test_sse_parser_preserves_delta_order_until_terminal_completion() -> None:
    lines = [
        "id: 8",
        "event: assistant.delta",
        'data: {"execution_id":"execution-1","type":"assistant.delta","sequence":8,"payload":{"content":"Olá "}}',
        "",
        "id: 9",
        "event: assistant.delta",
        'data: {"execution_id":"execution-1","type":"assistant.delta","sequence":9,"payload":{"content":"mundo"}}',
        "",
        "id: 10",
        "event: execution.completed",
        'data: {"execution_id":"execution-1","type":"execution.completed","sequence":10,"payload":{"answer":"Olá mundo","result":{"iterations":1}}}',
        "",
    ]

    frames = list(parse_sse_frames(lines))

    assert [frame.type for frame in frames] == [
        "assistant.delta",
        "assistant.delta",
        "execution.completed",
    ]
    assert "".join(
        str(frame.payload.get("content") or "")
        for frame in frames
        if frame.type == "assistant.delta"
    ) == "Olá mundo"
    assert frames[-1].payload["answer"] == "Olá mundo"
