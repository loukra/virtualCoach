"""Sync jobs record why they failed, so the app can tell the athlete instead of failing silently."""
import pytest
from stravalib import exc as strava_exc

import logic.workers as workers
from core import db
from core.auth import hash_token


@pytest.fixture
def athlete():
    db.execute("INSERT INTO athletes (name, token_hash, strava_connected) VALUES ('louis', ?, 1)",
               [hash_token("t")])
    return db.query_one("SELECT id FROM athletes")["id"]


def status(athlete_id):
    return db.query_one("SELECT sync_status, sync_error FROM athletes WHERE id = ?", [athlete_id])


def fail_with(error):
    def backfill(*_):
        raise error
    return backfill


def test_inactive_strava_app_is_explained(athlete, monkeypatch):
    monkeypatch.setattr(workers, "backfill_missing_activities",
                        fail_with(strava_exc.ApplicationInactive("inactive")))
    workers.run_sync(athlete)
    row = status(athlete)
    assert row["sync_status"] == "failed" and "Strava subscription" in row["sync_error"]


def test_successful_sync_clears_the_error(athlete, monkeypatch):
    db.execute("UPDATE athletes SET sync_status = 'failed', sync_error = 'old' WHERE id = ?", [athlete])
    monkeypatch.setattr(workers, "backfill_missing_activities", lambda *_: 3)
    monkeypatch.setattr(workers, "calculate_daily_metrics", lambda *_: None)
    workers.run_sync(athlete)
    assert status(athlete) == {"sync_status": "completed", "sync_error": None}


def test_skipped_sync_leaves_a_running_import_alone(athlete, monkeypatch):
    db.execute("UPDATE athletes SET sync_status = 'syncing' WHERE id = ?", [athlete])
    monkeypatch.setattr(workers, "backfill_missing_activities", lambda *_: None)
    workers.run_sync(athlete)
    assert status(athlete)["sync_status"] == "syncing"


def test_unknown_errors_stay_in_the_log(athlete, monkeypatch):
    monkeypatch.setattr(workers, "backfill_missing_activities", fail_with(RuntimeError("secret detail")))
    workers.run_sync(athlete)
    assert status(athlete)["sync_error"] == "The Strava import failed. Try again later."
