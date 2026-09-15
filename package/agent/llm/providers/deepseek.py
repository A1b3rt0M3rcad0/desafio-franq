from langchain_core.language_models.chat_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek

from package.agent.llm.config import DeepSeekConfig
from package.agent.llm.providers._langchain import LangChainLLMClient


class DeepSeekLLM(LangChainLLMClient):
    """DeepSeek implementation backed by LangChain's ChatDeepSeek adapter."""

    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        model: BaseChatModel | None = None,
    ) -> None:
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
        super().__init__(chat_model)
