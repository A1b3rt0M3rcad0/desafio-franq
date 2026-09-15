from package.agent.llm.config import DeepSeekConfig, LLMProvider, OpenAIConfig
from package.agent.llm.contracts import LLMClient
from package.agent.llm.providers import DeepSeekLLM, OpenAILLM
from package.runner.settings import (
    DeepSeekProviderSettings,
    OpenAIProviderSettings,
    RunnerSettings,
)


def compose_llm(settings: RunnerSettings) -> LLMClient:
    if settings.llm_provider == LLMProvider.OPENAI:
        provider = OpenAIProviderSettings()
        api_key = provider.openai_api_key.get_secret_value().strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        return OpenAILLM(
            OpenAIConfig(
                api_key=api_key,
                base_url=provider.openai_base_url,
                model=provider.openai_model,
                timeout_seconds=provider.openai_timeout_seconds,
                max_output_tokens=provider.openai_max_output_tokens,
                max_retries=provider.openai_max_retries,
                reasoning_effort=provider.openai_reasoning_effort,
                store=provider.openai_store,
            )
        )

    if settings.llm_provider == LLMProvider.DEEPSEEK:
        provider = DeepSeekProviderSettings()
        api_key = provider.deepseek_api_key.get_secret_value().strip()
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured")
        return DeepSeekLLM(
            DeepSeekConfig(
                api_key=api_key,
                base_url=provider.deepseek_base_url,
                model=provider.deepseek_model,
                timeout_seconds=provider.deepseek_timeout_seconds,
                max_output_tokens=provider.deepseek_max_output_tokens,
                max_retries=provider.deepseek_max_retries,
                reasoning_effort=provider.deepseek_reasoning_effort,
            )
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
