from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:password@localhost:5432/ux_benchmarks"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    assets_dir: Path = Path("/app/assets")
    secret_key: str = "dev-secret"
    debug: bool = False

settings = Settings()
