from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.config import get_settings


def today() -> date:
    """The athlete's calendar day, not the server's (a VPS usually runs on UTC)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()
