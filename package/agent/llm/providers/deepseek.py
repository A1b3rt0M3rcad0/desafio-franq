from collections.abc import Mapping

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek

from package.agent.llm.config import DeepSeekConfig, LLMProvider
from package.agent.llm.models import LLMModelProfile
from package.agent.llm.providers._langchain import LangChainLLMClient


# Provider-owned fallback for models whose installed LangChain adapter does not
# yet expose profile metadata. Values are based on the DeepSeek API model
# contract, not on runtime environment configuration.
_DEEPSEEK_CONTEXT_WINDOWS: Mapping[str, int] = {
    "deepseek-flash": 1_000_000,
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4-pro": 1_000_000,
}


class DeepSeekLLM(LangChainLLMClient):
    """DeepSeek implementation backed by LangChain's ChatDeepSeek adapter."""

    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        model: BaseChatModel | None = None,
    ) -> None:
        self._configured_model = config.model
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
