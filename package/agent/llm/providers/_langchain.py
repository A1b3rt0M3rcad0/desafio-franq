from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMChunk, LLMMessage
from package.agent.llm.providers._messages import to_langchain_messages


class LangChainLLMClient(LLMClient):
    """Base adapter for LangChain chat models.

    This layer is responsible only for provider/model integration. Agent orchestration
    belongs to the AgentProgram and will be implemented with LangGraph above this
    contract.
    """

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        normalized_messages = list(messages)
        if not normalized_messages:
            raise ValueError("At least one LLM message is required")

        langchain_messages = to_langchain_messages(normalized_messages)
        async for message_chunk in self._model.astream(langchain_messages):
            text = _extract_text(message_chunk.content)
            if text:
                yield LLMChunk(content=text)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for item in content:
        if isinstance(item, str):
            chunks.append(item)
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"text", "output_text"}:
            continue
        text = item.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "".join(chunks)
