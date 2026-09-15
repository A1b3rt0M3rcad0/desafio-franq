from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from package.agent.llm.config import OpenAIConfig
from package.agent.llm.providers._langchain import LangChainLLMClient


class OpenAILLM(LangChainLLMClient):
    """OpenAI implementation backed by LangChain's ChatOpenAI adapter."""

    def __init__(
        self,
        config: OpenAIConfig,
        *,
        model: BaseChatModel | None = None,
    ) -> None:
        chat_model = model or ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
            max_tokens=config.max_output_tokens,
            reasoning_effort=config.reasoning_effort.value,
            use_responses_api=True,
            store=config.store,
            streaming=True,
        )
        super().__init__(chat_model)
