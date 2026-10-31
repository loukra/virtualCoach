from functools import lru_cache

from openai import OpenAI

from core.config import get_settings


@lru_cache
def get_openai() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_s,
        max_retries=2,  # SDK retries on connection errors, 429 and 5xx with backoff
    )
