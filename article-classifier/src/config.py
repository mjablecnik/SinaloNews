from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database (required)
    DATABASE_URL: str

    # OpenRouter / LLM (required)
    OPENROUTER_API_KEY: str

    # Server
    APP_PORT: int = 8002

    # LLM
    LLM_MODEL: str = "openai/gpt-4o-mini"
    BATCH_SIZE: int = 20
    LLM_RETRY_DELAY_SECONDS: int = 5
    LLM_MAX_RETRIES: int = 3

    # LangSmith
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "sinalo-classifier"
    LANGSMITH_TRACING: str = "true"

    # Grouping
    GROUPING_LLM_MODEL: str | None = None
    GROUPING_MIN_ARTICLES: int = 2
    GROUPING_MAX_ARTICLES_PER_CATEGORY: int = 50
    GROUPING_MIN_SCORE: int = 0  # Only group articles with importance_score >= this value


settings = Settings()
