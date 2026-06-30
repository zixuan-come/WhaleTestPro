from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5672//"
    FEISHU_WEBHOOK: str = ""
    LOCUST_MASTER_URL: str = "http://localhost:8089"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


