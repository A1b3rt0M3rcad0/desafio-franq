import pytest

from package.agent.context.memory import InMemoryContextSnapshotStore, InMemoryGlobalContextStore
from package.agent.context.models import ContextSummary, GlobalContextKind, SnapshotReason


@pytest.mark.asyncio
async def test_snapshot_store_keeps_versions_and_returns_latest() -> None:
    store = InMemoryContextSnapshotStore()
    first = await store.create(session_id="session-1", execution_id="execution-1", reason=SnapshotReason.EXECUTION_COMPLETED, summary=ContextSummary(current_request="primeira"), estimated_tokens=20)
    second = await store.create(session_id="session-1", execution_id="execution-2", reason=SnapshotReason.EXECUTION_COMPLETED, summary=ContextSummary(current_request="segunda"), estimated_tokens=25)
    latest = await store.latest("session-1")
    assert first.sequence == 1
    assert second.sequence == 2
    assert latest == second


@pytest.mark.asyncio
async def test_global_context_lexical_search_recovers_old_information() -> None:
    store = InMemoryGlobalContextStore()
    await store.append(session_id="session-1", execution_id="execution-1", kind=GlobalContextKind.USER_MESSAGE, content="A campanha de WhatsApp de maio exclui clientes inativos.")
    await store.append(session_id="session-1", execution_id="execution-2", kind=GlobalContextKind.ASSISTANT_MESSAGE, content="A análise de compras por estado foi concluída.")
    await store.append(session_id="other-session", execution_id="execution-x", kind=GlobalContextKind.USER_MESSAGE, content="WhatsApp maio informação de outra sessão.")
    matches = await store.search(session_id="session-1", query="WhatsApp maio", limit=5)
    assert len(matches) == 1
    assert "exclui clientes inativos" in matches[0].entry.content
    assert matches[0].score > 0
