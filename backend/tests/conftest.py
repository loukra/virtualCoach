import os

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
