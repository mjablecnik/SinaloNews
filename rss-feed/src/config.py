from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    REQUEST_DELAY_SECONDS: float = 1.0
    REQUEST_TIMEOUT_SECONDS: int = 30
    USER_AGENT: str = "RSSFeedPipeline/1.0 (+https://github.com/example/rss-feed-pipeline)"


settings = Settings()
