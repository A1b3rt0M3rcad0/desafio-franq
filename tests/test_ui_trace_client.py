from typing import Any

from package.ui.client import FranqApiClient


def test_ui_client_fetches_execution_trace(monkeypatch) -> None:
    client = FranqApiClient(base_url="http://api:8000", timeout_seconds=30.0)
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, *, json_body=None) -> Any:
        del json_body
        calls.append((method, path))
        return [
            {
                "sequence": 1,
                "event_type": "context.loaded",
                "payload": {"history_turns": 2},
                "created_at": "2026-09-15T20:00:00Z",
            }
        ]

    monkeypatch.setattr(client, "_request_json", fake_request)

    trace = client.get_execution_trace("execution-1")

    assert calls == [("GET", "/executions/execution-1/trace")]
    assert trace[0]["event_type"] == "context.loaded"
