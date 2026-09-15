from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, MessagesState, StateGraph

from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMChunk, LLMMessage
from package.agent.llm.providers._messages import to_langchain_messages


class LangGraphLLMClient(LLMClient):
    """Base LLM adapter executed through a LangGraph graph."""

    _MODEL_NODE = "model"

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model
        graph = StateGraph(MessagesState)
        graph.add_node(self._MODEL_NODE, self._call_model)
        graph.add_edge(START, self._MODEL_NODE)
        graph.add_edge(self._MODEL_NODE, END)
        self._graph = graph.compile()

    async def _call_model(self, state: MessagesState) -> dict[str, Any]:
        response = await self._model.ainvoke(state["messages"])
        return {"messages": [response]}

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        normalized_messages = list(messages)
        if not normalized_messages:
            raise ValueError("At least one LLM message is required")

        async for part in self._graph.astream(
            {"messages": to_langchain_messages(normalized_messages)},
            stream_mode="messages",
            version="v2",
        ):
            if part["type"] != "messages":
                continue

            message_chunk, metadata = part["data"]
            if metadata.get("langgraph_node") != self._MODEL_NODE:
                continue

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
