from typing import Any

import pytest

from package.ui.client import FranqApiClient, parse_sse_frames


class StubFranqApiClient(FranqApiClient):
    def __init__(self, payload: Any) -> None:
        super().__init__(base_url="http://api.test", timeout_seconds=1.0)
        self.payload = payload
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method, path, json_body))
        return self.payload


def test_list_sessions_requests_recent_sessions_from_api() -> None:
    payload = [{"id": "session-1"}, {"id": "session-2"}]
    client = StubFranqApiClient(payload)

    result = client.list_sessions(limit=25, offset=10)

    assert result == payload
    assert client.calls == [("GET", "/sessions?limit=25&offset=10", None)]


def test_list_sessions_rejects_invalid_pagination_before_http_call() -> None:
    client = StubFranqApiClient([])

    with pytest.raises(ValueError, match="limit"):
        client.list_sessions(limit=0)
    with pytest.raises(ValueError, match="offset"):
        client.list_sessions(offset=-1)

    assert client.calls == []


def test_list_sessions_rejects_non_list_api_payload() -> None:
    client = StubFranqApiClient({"id": "session-1"})

    with pytest.raises(ValueError, match="sessions endpoint"):
        client.list_sessions()


def test_start_session_creates_first_message_atomically() -> None:
    payload = {"session": {"id": "session-1"}, "execution": {"id": "execution-1"}}
    client = StubFranqApiClient(payload)

    assert client.start_session(question="Minha primeira pergunta") == payload
    assert client.calls == [
        (
            "POST",
            "/sessions/start",
            {
                "question": "Minha primeira pergunta",
                "metadata": {"client": "streamlit"},
            },
        )
    ]


def test_session_can_be_renamed_and_deleted() -> None:
    client = StubFranqApiClient({"id": "session-1", "title": "Novo título"})

    client.update_session_title("session-1", "Novo título")
    client.delete_session("session-1")

    assert client.calls == [
        ("PATCH", "/sessions/session-1", {"title": "Novo título"}),
        ("DELETE", "/sessions/session-1", None),
    ]


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
