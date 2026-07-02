from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_DIR / ".env", extra="ignore")

    app_env: str = "dev"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str = "http://127.0.0.1:5173"

    docs_base_url: str = "https://docs.4gaboards.com/"
    target_app_url: str = "https://demo.4gaboards.com/"
    target_app_email: str = "demo"
    target_app_password: str = "demo"
    playwright_browser_executable: str | None = Field(
        default=None,
        validation_alias="PLAYWRIGHT_BROWSER_EXECUTABLE",
    )

    llm_provider: str = "auto"
    llm_timeout_seconds: int = 120
    minimax_api_key: str | None = Field(default=None, validation_alias="MINIMAX_API_KEY")
    minimax_base_url: str | None = Field(default=None, validation_alias="MINIMAX_BASE_URL")
    minimax_model: str | None = Field(default=None, validation_alias="MINIMAX_MODEL")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    openai_model: str | None = Field(default=None, validation_alias="OPENAI_MODEL")

    data_dir: Path = PROJECT_DIR / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


def read_codex_provider() -> dict[str, str | None]:
    """Read non-secret Codex model provider settings and secret token when locally available."""
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8", errors="ignore")
    provider_match = re.search(r'model_provider\s*=\s*"([^"]+)"', text)
    model_match = re.search(r'model\s*=\s*"([^"]+)"', text)
    provider = provider_match.group(1) if provider_match else None
    model = model_match.group(1) if model_match else None
    section = ""
    if provider:
        pattern = rf'\[model_providers\.{re.escape(provider)}\](.*?)(?:\n\[|\Z)'
        section_match = re.search(pattern, text, re.S)
        section = section_match.group(1) if section_match else ""
    base_url_match = re.search(r'base_url\s*=\s*"([^"]+)"', section)
    token_match = re.search(r'experimental_bearer_token\s*=\s*"([^"]+)"', section)
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url_match.group(1) if base_url_match else None,
        "api_key": token_match.group(1) if token_match else None,
    }


def get_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env", override=True)
    settings = Settings()
    provider = settings.llm_provider.lower()
    if provider == "minimax" or settings.minimax_api_key:
        settings.llm_provider = "minimax"
        settings.openai_api_key = settings.minimax_api_key or settings.openai_api_key
        settings.openai_base_url = settings.minimax_base_url or "https://api.minimaxi.com/v1"
        settings.openai_model = settings.minimax_model or "MiniMax-M3"
    else:
        codex = read_codex_provider()
        if not settings.openai_base_url and codex.get("base_url"):
            settings.openai_base_url = codex["base_url"]
        if not settings.openai_model and codex.get("model"):
            settings.openai_model = codex["model"]
        if not settings.openai_api_key and codex.get("api_key"):
            settings.openai_api_key = codex["api_key"]
        if os.getenv("DEEPSEEK_API_KEY") and not settings.openai_api_key:
            settings.openai_api_key = os.getenv("DEEPSEEK_API_KEY")
            settings.openai_base_url = settings.openai_base_url or "https://api.deepseek.com/v1"
            settings.openai_model = settings.openai_model or "deepseek-chat"
    return settings
