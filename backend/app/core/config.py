from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:password@localhost:5432/ux_benchmarks"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    # Optional override for a self-hosted / proxy Anthropic-compatible endpoint.
    # Empty => the SDK default (api.anthropic.com). Set e.g. to a relay base URL.
    anthropic_base_url: str = ""
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

    # GPT relay (OpenAI-compatible) for FAST parallel scoring of TEXT candidates.
    # When set, text-mode relevance scoring uses this instead of Claude (much
    # faster + cheaper, enabling parallel scoring of many candidates per probe).
    # Image candidates still use Claude Vision. Empty => fall back to Claude.
    gpt_api_key: str = ""
    gpt_base_url: str = "https://deepkey.top/v1"
    gpt_scorer_model: str = "gpt-5.6-luna"

settings = Settings()
