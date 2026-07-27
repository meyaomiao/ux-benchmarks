from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:password@localhost:5432/ux_benchmarks"
    redis_url: str = "redis://localhost:6379/0"
    assets_dir: Path = Path("/app/assets")
    secret_key: str = "dev-secret"
    debug: bool = False
    # When True (default), collection adapters return deterministic fixtures
    # instead of hitting the network, so the whole chain runs offline / in CI.
    # Set to False to enable real httpx/BeautifulSoup fetches.
    use_collection_mock: bool = True

    # Search engine for live collection (A1). Provider: "brave" | "serpapi".
    # Brave free tier: 2000 req/month (https://brave.com/search/api/).
    # When key is empty or use_collection_mock=True, mock URLs are used instead.
    search_api_key: str = ""
    search_api_provider: str = "brave"

    # GPT relay (OpenAI-compatible) — the ONLY LLM path in the project. Every
    # generator (M0 discovery, M1 grid, M2 mapping cards, M3 scoring/expansion,
    # L3 insights, L5 reports) goes through it, so one key and one base URL
    # control all of them. Empty key => every caller uses its deterministic mock.
    gpt_api_key: str = ""
    gpt_base_url: str = "https://deepkey.top/v1"
    gpt_scorer_model: str = "gpt-5.6-luna"       # text-mode scoring
    gpt_vision_model: str = "gpt-5.6-luna"       # image-mode scoring (vision)

settings = Settings()
