"""Application settings loaded from the local environment."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    model: str
    base_url: str


def get_settings() -> Settings:
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower() or "openai"
    return Settings(
        provider=provider,
        api_key=(os.getenv("LLM_API_KEY") or (os.getenv("OPENAI_API_KEY") if provider == "openai" else "") or "").strip(),
        model=(os.getenv("LLM_MODEL") or (os.getenv("OPENAI_MODEL") if provider == "openai" else "") or ("gpt-4.1-mini" if provider == "openai" else "")).strip(),
        base_url=os.getenv("LLM_BASE_URL", "").strip(),
    )
