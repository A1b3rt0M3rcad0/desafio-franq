from package.agent.llm.config import LLMProvider, OpenAIConfig
from package.agent.llm.contracts import LLMClient
from package.agent.llm.providers import GPTLLM, OpenAILLM
from package.runner.settings import RunnerSettings


def compose_llm(settings: RunnerSettings) -> LLMClient:
    config = OpenAIConfig(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_output_tokens=settings.openai_max_output_tokens,
        reasoning_effort=settings.openai_reasoning_effort,
        store=settings.openai_store,
    )

    if settings.llm_provider == LLMProvider.OPENAI_RESPONSES:
        return OpenAILLM(config)
    if settings.llm_provider == LLMProvider.GPT_CHAT:
        return GPTLLM(config)

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
