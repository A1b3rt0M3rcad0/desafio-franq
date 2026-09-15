from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from package.agent.llm.models import LLMMessage, MessageRole


def _require_tool_call_id(message: LLMMessage) -> str:
    if not message.tool_call_id:
        raise ValueError("Tool messages require tool_call_id")
    return message.tool_call_id


def to_langchain_messages(messages: list[LLMMessage]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for message in messages:
        if message.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER}:
            result.append(SystemMessage(content=message.content))
            continue
        if message.role == MessageRole.USER:
            result.append(HumanMessage(content=message.content))
            continue
        if message.role == MessageRole.ASSISTANT:
            result.append(
                AIMessage(
                    content=message.content,
                    tool_calls=[
                        {
                            "id": call.id,
                            "name": call.name,
                            "args": call.arguments,
                            "type": "tool_call",
                        }
                        for call in message.tool_calls
                    ],
                )
            )
            continue
        if message.role == MessageRole.TOOL:
            result.append(
                ToolMessage(
                    content=message.content,
                    tool_call_id=_require_tool_call_id(message),
                )
            )
            continue
        raise ValueError(f"Unsupported message role: {message.role}")
    return result
