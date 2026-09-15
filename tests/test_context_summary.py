from collections.abc import AsyncIterator, Sequence

import pytest

from package.agent.context.models import ContextSummary
from package.agent.context.summary import FallbackContextSummarizer, LLMContextSummarizer
from package.agent.llm.models import LLMChunk, LLMMessage, LLMResponse, LLMToolDefinition, MessageRole


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def invoke(self, messages: Sequence[LLMMessage], *, tools: Sequence[LLMToolDefinition] = ()) -> LLMResponse:
        return LLMResponse(content=self.content)

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        if False:
            yield LLMChunk(content="")


def _fallback() -> FallbackContextSummarizer:
    return FallbackContextSummarizer(max_messages=2, max_chars_per_message=20)


@pytest.mark.asyncio
async def test_llm_summarizer_returns_structured_snapshot_summary() -> None:
    llm = FakeLLM('{"current_request":"analise", "objective":"comparar estados", "established_facts":["SP lidera"], "constraints":[], "decisions":[], "open_questions":[], "relevant_references":["execution-1"], "continuity_notes":["continuar comparação"]}')
    summarizer = LLMContextSummarizer(llm=llm, fallback=_fallback())
    summary = await summarizer.summarize(previous_snapshot=None, messages=[LLMMessage(role=MessageRole.USER, content="analise")], question="analise")
    assert isinstance(summary, ContextSummary)
    assert summary.objective == "comparar estados"
    assert summary.established_facts == ["SP lidera"]


@pytest.mark.asyncio
async def test_invalid_summary_json_uses_bounded_fallback() -> None:
    summarizer = LLMContextSummarizer(llm=FakeLLM("not-json"), fallback=_fallback())
    summary = await summarizer.summarize(previous_snapshot=None, messages=[LLMMessage(role=MessageRole.USER, content="A" * 100), LLMMessage(role=MessageRole.ASSISTANT, content="B" * 100), LLMMessage(role=MessageRole.USER, content="C" * 100)], question="pedido atual")
    assert summary.current_request == "pedido atual"
    assert len(summary.continuity_notes) == 2
    assert all(len(note) < 40 for note in summary.continuity_notes)
