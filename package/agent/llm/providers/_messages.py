from typing import Any

from langchain_core.messages import BaseMessage, convert_to_messages

from package.agent.llm.models import LLMMessage, MessageRole


def _require_tool_call_id(message: LLMMessage) -> str:
    if not message.tool_call_id:
        raise ValueError("Tool messages require tool_call_id")
    return message.tool_call_id


def to_langchain_messages(messages: list[LLMMessage]) -> list[BaseMessage]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": message.content,
        }
        if message.role == MessageRole.TOOL:
            payload["tool_call_id"] = _require_tool_call_id(message)
        payloads.append(payload)

    return list(convert_to_messages(payloads))
