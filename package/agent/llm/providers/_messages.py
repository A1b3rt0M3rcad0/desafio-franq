from typing import Any

from package.agent.llm.models import LLMMessage, MessageRole


def _require_tool_call_id(message: LLMMessage) -> str:
    if not message.tool_call_id:
        raise ValueError("Tool messages require tool_call_id")
    return message.tool_call_id


def to_responses_input(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == MessageRole.TOOL:
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": _require_tool_call_id(message),
                    "output": message.content,
                }
            )
            continue

        items.append(
            {
                "role": message.role.value,
                "content": message.content,
            }
        )
    return items


def to_chat_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {
            "role": message.role.value,
            "content": message.content,
        }
        if message.role == MessageRole.TOOL:
            item["tool_call_id"] = _require_tool_call_id(message)
        result.append(item)
    return result
