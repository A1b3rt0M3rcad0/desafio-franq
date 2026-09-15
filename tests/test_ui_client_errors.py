import httpx
import pytest

from package.ui.client import FranqApiClient, FranqApiError


def test_streamlit_client_surfaces_fastapi_detail_without_httpx_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "http://api:8000/sessions/session-1/executions")
    response = httpx.Response(
        503,
        request=request,
        json={"detail": "Provider indisponível"},
    )

    class FakeHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def request(self, method: str, path: str, json=None) -> httpx.Response:
            del method, path, json
            return response

    monkeypatch.setattr(httpx, "Client", FakeHttpClient)
    client = FranqApiClient(base_url="http://api:8000", timeout_seconds=30.0)

    with pytest.raises(FranqApiError) as captured:
        client.create_execution(session_id="session-1", question="Olá")

    assert captured.value.status_code == 503
    assert str(captured.value) == "Provider indisponível"
    assert "developer.mozilla.org" not in str(captured.value)
