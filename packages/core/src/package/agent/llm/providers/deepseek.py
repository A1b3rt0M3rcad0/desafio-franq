import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from deepseek_tokenizer import ds_token
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek

from package.agent.llm.config import DeepSeekConfig, LLMProvider
from package.agent.llm.models import (
    LLMMessage,
    LLMModelProfile,
    LLMToolDefinition,
)
from package.agent.llm.providers._langchain import LangChainLLMClient


# Provider-owned fallback for models whose installed LangChain adapter does not
# yet expose profile metadata. Values are based on the DeepSeek API model
# contract, not on runtime environment configuration.
_DEEPSEEK_CONTEXT_WINDOWS: Mapping[str, int] = {
    "deepseek-flash": 1_000_000,
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4-pro": 1_000_000,
}


class _DeepSeekTokenizer(Protocol):
    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool = True,
    ) -> list[int]: ...


class DeepSeekLLM(LangChainLLMClient):
    """DeepSeek implementation backed by LangChain's ChatDeepSeek adapter.

    LangChain's OpenAI-compatible base currently cannot count chat-message tokens
    for every DeepSeek model name. Runtime context accounting therefore uses the
    DeepSeek V4 tokenizer directly instead of relying on
    ``get_num_tokens_from_messages``.
    """

    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        model: BaseChatModel | None = None,
        tokenizer: _DeepSeekTokenizer | None = None,
    ) -> None:
        self._configured_model = config.model
        self._tokenizer = tokenizer or ds_token
        chat_model = model or ChatDeepSeek(
            model=config.model,
            api_key=config.api_key,
            api_base=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
            max_tokens=config.max_output_tokens,
            reasoning_effort=config.reasoning_effort.value,
            streaming=True,
        )
        super().__init__(
            chat_model,
            provider=LLMProvider.DEEPSEEK,
            model_name=config.model,
        )

    @property
    def profile(self) -> LLMModelProfile:
        """Prefer LangChain metadata and fall back to DeepSeek's model contract."""
        try:
            return super().profile
        except RuntimeError:
            context_window = _DEEPSEEK_CONTEXT_WINDOWS.get(self._configured_model)
            if context_window is None:
                raise
            return LLMModelProfile(
                provider=LLMProvider.DEEPSEEK.value,
                model=self._configured_model,
                context_window_tokens=context_window,
            )

    def count_text_tokens(self, text: str) -> int:
        if not text:
            return 0
        try:
            return len(self._tokenizer.encode(text, add_special_tokens=False))
        except Exception as exc:
            raise RuntimeError(
                f"DeepSeek tokenizer failed for model {self._configured_model!r}: "
                f"{str(exc) or exc.__class__.__name__}"
            ) from exc

    def count_tokens(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> int:
        """Count the complete request payload with the DeepSeek tokenizer.

        The serialized payload intentionally includes role metadata, native tool
        calls, tool call ids and tool schemas. It is conservative compared with
        counting only message content and, importantly, does not depend on the
        OpenAI-specific LangChain chat-token counter that rejects DeepSeek model
        names.
        """
        if not messages and not tools:
            return 0

        payload = {
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                    "tool_call_id": message.tool_call_id,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                        for call in message.tool_calls
                    ],
                }
                for message in messages
            ],
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ],
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return self.count_text_tokens(serialized)
