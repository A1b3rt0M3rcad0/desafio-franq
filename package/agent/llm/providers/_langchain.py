import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
)
from package.agent.llm.providers._messages import to_langchain_messages


class LangChainLLMClient(LLMClient):
    """Base adapter for LangChain chat models.

    This layer owns provider/model integration only. Agent orchestration belongs to
    the LangGraph-backed AgentProgram above this contract.
    """

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse:
        normalized_messages = self._normalize_messages(messages)
        model = self._model
        if tools:
            model = model.bind_tools([_to_langchain_tool(tool) for tool in tools])

        response = await model.ainvoke(to_langchain_messages(normalized_messages))
        tool_calls = tuple(_to_llm_tool_call(call) for call in (response.tool_calls or []))
        return LLMResponse(
            content=_extract_text(response.content),
            tool_calls=tool_calls,
        )

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        normalized_messages = self._normalize_messages(messages)
        langchain_messages = to_langchain_messages(normalized_messages)
        async for message_chunk in self._model.astream(langchain_messages):
            text = _extract_text(message_chunk.content)
            if text:
                yield LLMChunk(content=text)

    @staticmethod
    def _normalize_messages(messages: Sequence[LLMMessage]) -> list[LLMMessage]:
        normalized_messages = list(messages)
        if not normalized_messages:
            raise ValueError("At least one LLM message is required")
        return normalized_messages


def _to_langchain_tool(tool: LLMToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _to_llm_tool_call(call: dict[str, Any]) -> LLMToolCall:
    arguments = call.get("args", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("LLM tool call arguments must be an object")

    call_id = str(call.get("id") or "")
    name = str(call.get("name") or "")
    if not call_id or not name:
        raise ValueError("LLM tool calls require both id and name")

    return LLMToolCall(id=call_id, name=name, arguments=arguments)


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
