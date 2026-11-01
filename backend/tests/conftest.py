import os
from datetime import date, datetime

import pytest

# Dummy configuration so modules import without a real .env; no test talks to a real service.
os.environ.update(
    OPENAI_API_KEY="sk-test",
    STRAVA_CLIENT_ID="1",
    STRAVA_CLIENT_SECRET="secret",
)


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    """Every test gets its own migrated SQLite file."""
    from core import db
    from core.config import get_settings

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "coach.db"))
    get_settings.cache_clear()
    db.migrate()
    yield db
    get_settings.cache_clear()


@pytest.fixture
def on_day(monkeypatch):
    """Pins the athlete's calendar day, for tests whose plan weeks depend on the weekday."""
    import core.dates

    def pin(day: date) -> date:
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(day.year, day.month, day.day, 12, tzinfo=tz)

        monkeypatch.setattr(core.dates, "datetime", Clock)
        return day

    return pin
