import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from package.agent.llm.config import LLMProvider
from package.agent.llm.contracts import LLMClient
from package.agent.llm.errors import LLMProviderError, classify_provider_exception
from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMModelProfile,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
)
from package.agent.llm.providers._messages import to_langchain_messages


class LangChainLLMClient(LLMClient):
    """Base adapter for LangChain chat models.

    Reasoning/tool-selection calls use ``invoke`` and are never exposed as text
    deltas. ``stream`` is reserved for the explicit final-answer phase, so every
    public assistant delta is guaranteed to belong to the user-visible answer.
    """

    def __init__(
        self,
        model: BaseChatModel,
        *,
        provider: LLMProvider,
        model_name: str,
    ) -> None:
        self._model = model
        self._provider = provider
        self._model_name = model_name

    @property
    def profile(self) -> LLMModelProfile:
        raw_profile = getattr(self._model, "profile", None)
        context_window = (
            raw_profile.get("max_input_tokens")
            if isinstance(raw_profile, Mapping)
            else None
        )
        if not isinstance(context_window, int) or isinstance(context_window, bool):
            raise RuntimeError(
                f"Model {self._model_name!r} from provider {self._provider.value!r} "
                "does not expose a valid max_input_tokens model profile"
            )
        if context_window <= 0:
            raise RuntimeError(
                f"Model {self._model_name!r} exposes an invalid context window: "
                f"{context_window}"
            )
        return LLMModelProfile(
            provider=self._provider.value,
            model=self._model_name,
            context_window_tokens=context_window,
        )

    def count_text_tokens(self, text: str) -> int:
        if not text:
            return 0
        return int(self._model.get_num_tokens(text))

    def count_tokens(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> int:
        total = 0
        normalized_messages = list(messages)
        if normalized_messages:
            langchain_messages = to_langchain_messages(normalized_messages)
            try:
                total += int(self._model.get_num_tokens_from_messages(langchain_messages))
            except (NotImplementedError, ValueError) as exc:
                if not _is_unsupported_message_counter(exc):
                    raise
                total += self.count_text_tokens(_serialize_messages(normalized_messages))
        if tools:
            tool_payload = json.dumps(
                [_to_langchain_tool(tool) for tool in tools],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            total += self.count_text_tokens(tool_payload)
        return total

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

        try:
            response = await model.ainvoke(to_langchain_messages(normalized_messages))
        except LLMProviderError:
            raise
        except Exception as exc:
            raise self._provider_error(exc) from exc

        tool_calls = tuple(
            _to_llm_tool_call(call)
            for call in (getattr(response, "tool_calls", None) or [])
        )
        return LLMResponse(
            content=_extract_text(getattr(response, "content", "")),
            tool_calls=tool_calls,
        )

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        normalized_messages = self._normalize_messages(messages)
        langchain_messages = to_langchain_messages(normalized_messages)
        try:
            async for message_chunk in self._model.astream(langchain_messages):
                text = _extract_text(getattr(message_chunk, "content", ""))
                if text:
                    yield LLMChunk(content=text)
        except LLMProviderError:
            raise
        except Exception as exc:
            raise self._provider_error(exc) from exc

    def _provider_error(self, exc: Exception) -> LLMProviderError:
        failure = classify_provider_exception(exc)
        return LLMProviderError(
            provider=self._provider.value,
            model=self._model_name,
            message=str(exc) or exc.__class__.__name__,
            retryable=failure.retryable,
            status_code=failure.status_code,
        )

    @staticmethod
    def _normalize_messages(messages: Sequence[LLMMessage]) -> list[LLMMessage]:
        normalized_messages = list(messages)
        if not normalized_messages:
            raise ValueError("At least one LLM message is required")
        return normalized_messages


def _serialize_messages(messages: Sequence[LLMMessage]) -> str:
    return json.dumps(
        [
            {
                "role": message.role.value,
                "content": message.content,
                "tool_call_id": message.tool_call_id,
                "tool_calls": [call.model_dump(mode="json") for call in message.tool_calls],
            }
            for message in messages
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _is_unsupported_message_counter(exc: Exception) -> bool:
    if isinstance(exc, NotImplementedError):
        return True
    message = str(exc).lower()
    return (
        "get_num_tokens_from_messages" in message
        and ("not presently implemented" in message or "not implemented" in message)
    )


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
