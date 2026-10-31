from functools import lru_cache

from supabase import Client, create_client

from core.config import get_settings

PAGE_SIZE = 1000  # PostgREST returns at most this many rows per request


@lru_cache
def get_db() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


def fetch_all(build_query) -> list[dict]:
    """Pages through a query so results beyond PostgREST's row limit are not cut off.

    `build_query` must return a fresh, ordered query builder on every call.
    """
    rows: list[dict] = []
    start = 0
    while True:
        page = build_query().range(start, start + PAGE_SIZE - 1).execute().data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE
