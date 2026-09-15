from pydantic_settings import BaseSettings, SettingsConfigDict


class StreamlitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    streamlit_api_base_url: str
    streamlit_api_timeout_seconds: float
