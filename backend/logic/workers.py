"""Background jobs. Each reports its outcome in the database so the app can poll for it."""
import logging
from datetime import date, timedelta

from stravalib import exc as strava_exc

from core import db
from core.dates import today
from logic.ai import GenerationError
from logic.ai_planner import build_plan
from logic.metrics import calculate_daily_metrics
from logic.sessions import match_athlete_rides
from logic.strava_auth import exchange_code_for_token
from logic.strava_sync import backfill_missing_activities

log = logging.getLogger(__name__)


def run_ai_plan_generation(
    journey_id: str,
    athlete_id: int,
    goal: str,
    ftp: int,
    weight: float,
    start_date: date,
    race_date: date,
    current_date: date,
    current_ctl: float,
    goal_type: str = "race",
) -> None:
    try:
        # A plan that starts right after a race (the end of the journey before) opens easy.
        previous_race = db.query_one(
            "SELECT MAX(race_date) AS d FROM journeys WHERE athlete_id = ? AND id != ? AND goal_type = 'race'"
            " AND status != 'archived' AND race_date BETWEEN ? AND ?",
            [athlete_id, journey_id, (start_date - timedelta(days=4)).isoformat(),
             (start_date - timedelta(days=1)).isoformat()],
        )
        longest = db.query_one(
            "SELECT MAX(moving_time) AS s FROM activities WHERE athlete_id = ? AND start_date_local >= ?",
            [athlete_id, (current_date - timedelta(days=90)).isoformat()],
        )
        days = build_plan(
            athlete_id=athlete_id, journey_id=journey_id, goal=goal, start_date=start_date,
            race_date=race_date, current_date=current_date, ftp_watts=ftp, weight=weight,
            current_ctl=current_ctl, goal_type=goal_type,
            after_race=date.fromisoformat(previous_race["d"]) if previous_race["d"] else None,
            longest_ride_min=round(longest["s"] / 60) if longest and longest["s"] else None,
        )
        rows = [
            (
                journey_id,
                (start_date + timedelta(days=d.day_number - 1)).isoformat(),
                d.day_number, d.phase, d.planned_workout_type, d.planned_duration_min,
                d.planned_tss, d.description,
            )
            for d in days
        ]
        with db.transaction() as conn:  # the plan appears complete or not at all
            conn.executemany(
                "INSERT INTO master_plan (journey_id, date, day_number, phase, planned_workout_type,"
                " planned_duration_min, planned_tss, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.execute("UPDATE journeys SET status = 'active', error = NULL WHERE id = ?", [journey_id])
        log.info("Plan with %d days saved for journey %s", len(rows), journey_id)
    except GenerationError as e:
        log.error("Plan generation failed for journey %s: %s", journey_id, e.errors)
        _fail_journey(journey_id, "The AI could not produce a valid plan. Please try again.")
    except Exception:
        log.exception("Plan generation crashed for journey %s", journey_id)
        _fail_journey(journey_id, "Plan generation failed unexpectedly.")


def claim_due_journeys(athlete_id: int, day: date) -> list[dict]:
    """Scheduled journeys whose start day has come, switched to 'creating' (each by one caller)."""
    claimed = []
    for journey in db.query(
        "SELECT id, name, goal_type, start_date, race_date FROM journeys"
        " WHERE athlete_id = ? AND status = 'scheduled' AND start_date <= ?",
        [athlete_id, day.isoformat()],
    ):
        if db.execute("UPDATE journeys SET status = 'creating' WHERE id = ? AND status = 'scheduled'",
                      [journey["id"]]):
            claimed.append({**journey, "athlete_id": athlete_id})
    return claimed


def generate_scheduled_plan(journey: dict) -> None:
    """The plan of a journey created ahead of time, from the athlete's fitness and FTP of today."""
    athlete_id = journey["athlete_id"]
    profile = db.query_one("SELECT ftp, weight_kg FROM athletes WHERE id = ?", [athlete_id]) or {}
    latest = db.query_one(
        "SELECT ctl FROM daily_metrics WHERE athlete_id = ? ORDER BY date DESC LIMIT 1", [athlete_id]
    )
    run_ai_plan_generation(
        journey["id"], athlete_id, journey["name"], profile.get("ftp") or 200, profile.get("weight_kg") or 75,
        date.fromisoformat(journey["start_date"]), date.fromisoformat(journey["race_date"]), today(),
        float(latest["ctl"]) if latest else 0.0, journey["goal_type"],
    )


def _fail_journey(journey_id: str, message: str) -> None:
    db.execute("UPDATE journeys SET status = 'failed', error = ? WHERE id = ?", [message, journey_id])


def _set_sync_status(athlete_id: int, status: str, error: str | None = None) -> None:
    db.execute(
        "UPDATE athletes SET sync_status = ?, sync_error = ? WHERE id = ?", [status, error, athlete_id]
    )


def sync_error_message(e: Exception) -> str:
    """What the athlete should know and do; the details stay in the server log."""
    if isinstance(e, strava_exc.ApplicationInactive):
        return ("Strava has deactivated the API app: its owner needs a Strava subscription."
                " Reactivate the app at strava.com/settings/api, then try again.")
    if isinstance(e, strava_exc.AccessUnauthorized | strava_exc.AuthError):
        return "Strava no longer accepts the connection. Please connect Strava again."
    if isinstance(e, strava_exc.RateLimitExceeded | strava_exc.RateLimitTimeout):
        return "Strava's request limit is reached. Try again in 15 minutes."
    return "The Strava import failed. Try again later."


def run_onboarding_process(athlete_id: int, code: str) -> None:
    """Connects Strava, downloads 90 days of history and marks the profile as ready."""
    _set_sync_status(athlete_id, "syncing")
    try:
        if not exchange_code_for_token(athlete_id, code):
            raise strava_exc.AuthError("Strava token exchange failed")
        backfill_missing_activities(athlete_id, days_back=90)
        calculate_daily_metrics(athlete_id)
        match_athlete_rides(athlete_id)
        _set_sync_status(athlete_id, "completed")
    except Exception as e:
        log.exception("Onboarding failed for athlete %s", athlete_id)
        _set_sync_status(athlete_id, "failed", sync_error_message(e))


def run_sync(athlete_id: int, days_back: int = 7) -> None:
    try:
        if backfill_missing_activities(athlete_id, days_back) is None:
            return  # another sync is running and will report the outcome
        calculate_daily_metrics(athlete_id)
        match_athlete_rides(athlete_id)
        _set_sync_status(athlete_id, "completed")
    except Exception as e:
        log.exception("Sync failed for athlete %s", athlete_id)
        _set_sync_status(athlete_id, "failed", sync_error_message(e))
    # Fitness is as fresh as it gets right after a sync: the moment to build a plan that starts today.
    for journey in claim_due_journeys(athlete_id, today()):
        generate_scheduled_plan(journey)
