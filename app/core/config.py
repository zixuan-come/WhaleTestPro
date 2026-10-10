from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SHADOW_DATABASE_URL: str
    # User-authored SQL must never use the platform or shadow database account.
    TEST_DATABASE_URL: str | None = None
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5672//"
    FEISHU_WEBHOOK: str = ""
    LOCUST_MASTER_URL: str = "http://localhost:8089"
    REQUEST_TIMEOUT_SECONDS: float = 30.0
    PERF_QUEUE_TIMEOUT_SECONDS: int = 300
    PERF_HEARTBEAT_TIMEOUT_SECONDS: int = 60
    RECORDING_PUBLISH_TIMEOUT_SECONDS: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
