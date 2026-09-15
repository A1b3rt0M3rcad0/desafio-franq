import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class ObservedFrame:
    execution_id: str
    type: str
    sequence: int | None
    payload: dict[str, Any]


class FranqApiError(httpx.HTTPStatusError):
    def __init__(self, *, status_code: int, detail: str, response: httpx.Response) -> None:
        super().__init__(detail, request=response.request, response=response)
        self.status_code = status_code
        self.detail = detail


class FranqApiClient:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        normalized = base_url.rstrip("/")
        if not normalized:
            raise ValueError("base_url cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._base_url = normalized
        self._timeout_seconds = timeout_seconds

    def create_session(self) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/sessions",
            json_body={"metadata": {"client": "streamlit"}},
        )

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        payload = self._request_json("GET", f"/sessions?limit={limit}")
        if not isinstance(payload, list):
            raise ValueError("Expected the sessions endpoint to return a list")
        return payload

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/sessions/{session_id}")

    def list_session_executions(self, session_id: str) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"/sessions/{session_id}/executions")
        if not isinstance(payload, list):
            raise ValueError("Expected the executions endpoint to return a list")
        return payload

    def create_execution(self, *, session_id: str, question: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/sessions/{session_id}/executions",
            json_body={"question": question},
        )

    def stop_execution(self, execution_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"/executions/{execution_id}/cancel")

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/executions/{execution_id}")

    def get_execution_trace(self, execution_id: str) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"/executions/{execution_id}/trace")
        if not isinstance(payload, list):
            raise ValueError("Expected the trace endpoint to return a list")
        return payload

    def observe_execution(
        self,
        execution_id: str,
        *,
        last_sequence: int | None = None,
    ) -> Iterator[ObservedFrame]:
        headers = {"Accept": "text/event-stream"}
        if last_sequence is not None:
            headers["Last-Event-ID"] = str(last_sequence)
        timeout = httpx.Timeout(self._timeout_seconds, read=None)
        with httpx.Client(base_url=self._base_url, timeout=timeout) as client:
            with client.stream(
                "GET",
                f"/executions/{execution_id}/events",
                headers=headers,
            ) as response:
                response.raise_for_status()
                yield from parse_sse_frames(response.iter_lines())

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        with httpx.Client(base_url=self._base_url, timeout=self._timeout_seconds) as client:
            response = client.request(method, path, json=json_body)
            if response.is_error:
                detail = _response_detail(response) or f"HTTP {response.status_code}"
                raise FranqApiError(
                    status_code=response.status_code,
                    detail=detail,
                    response=response,
                )
            return response.json()


def _response_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail")
    return str(detail) if detail else None


def parse_sse_frames(lines: Iterable[str]) -> Iterator[ObservedFrame]:
    event_name: str | None = None
    event_id: str | None = None
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if event_name is not None or data_lines:
                yield _decode_frame(event_name, event_id, data_lines)
            event_name = None
            event_id = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "id":
            event_id = value
        elif field == "data":
            data_lines.append(value)
    if event_name is not None or data_lines:
        yield _decode_frame(event_name, event_id, data_lines)


def _decode_frame(
    event_name: str | None,
    event_id: str | None,
    data_lines: list[str],
) -> ObservedFrame:
    if not data_lines:
        raise ValueError("SSE frame does not contain data")
    raw = json.loads("\n".join(data_lines))
    if not isinstance(raw, dict):
        raise ValueError("SSE frame data must be a JSON object")
    payload = raw.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("SSE frame payload must be an object")
    raw_sequence = raw.get("sequence")
    if isinstance(raw_sequence, int) and not isinstance(raw_sequence, bool):
        sequence: int | None = raw_sequence
    elif event_id is not None and event_id.strip():
        sequence = int(event_id)
    else:
        sequence = None
    frame_type = str(raw.get("type") or event_name or "message")
    execution_id = str(raw.get("execution_id") or payload.get("execution_id") or "")
    return ObservedFrame(
        execution_id=execution_id,
        type=frame_type,
        sequence=sequence,
        payload=payload,
    )
