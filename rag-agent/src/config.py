from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database (required)
    DATABASE_URL: str

    # Server
    APP_PORT: int = 8001

    # OpenRouter / LLM (required)
    OPENROUTER_API_KEY: str
    LLM_MODEL: str = "openai/gpt-4o-mini"

    # Embedding
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_API_URL: str = "https://openrouter.ai/api/v1"
    EMBEDDING_API_KEY: str | None = None  # defaults to OPENROUTER_API_KEY at runtime

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "article_chunks"

    # RAG
    RAG_TOP_K: int = 10
    RAG_MAX_CHUNKS_PER_ARTICLE: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # LangSmith
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "sinalo-agent"
    LANGSMITH_TRACING: str = "true"

    def effective_embedding_api_key(self) -> str:
        return self.EMBEDDING_API_KEY or self.OPENROUTER_API_KEY


settings = Settings()
