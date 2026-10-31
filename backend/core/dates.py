from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.config import get_settings


def today() -> date:
    """The athlete's calendar day, not the server's (a VPS usually runs on UTC)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()



# Plan weeks are calendar weeks, Monday to Sunday. A plan may start on any day; its first week
# then only has the days from the start to Sunday. `offset` is the start's weekday (Monday 0).

def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def plan_week(day_number: int, offset: int) -> int:
    """The week (1-based) that plan day `day_number` falls in."""
    return (day_number - 1 + offset) // 7 + 1


def end_after_weeks(start: date, weeks: int) -> date:
    """The Sunday that closes week `weeks`, counting the (possibly short) first week."""
    return monday_of(start) + timedelta(days=weeks * 7 - 1)
