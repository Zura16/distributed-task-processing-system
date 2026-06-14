import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD", None)

    # Queue Names
    DEFAULT_QUEUE: str = "queue:default"
    DELAYED_QUEUE: str = "scheduler:delayed"
    
    # Prefix for task hashes
    TASK_METADATA_PREFIX: str = "tasks:metadata"
    # Prefix for logs
    TASK_LOG_PREFIX: str = "tasks:logs"
    # Worker Heartbeats key
    WORKERS_HEARTBEATS_KEY: str = "workers:active"

    class Config:
        env_file = ".env"

settings = Settings()
