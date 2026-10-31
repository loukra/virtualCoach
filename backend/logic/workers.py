"""Background jobs. Each reports its outcome in the database so the app can poll for it."""
import logging
from datetime import date, timedelta

from core.db import get_db
from logic.ai import GenerationError
from logic.ai_planner import build_plan
from logic.metrics import calculate_daily_metrics
from logic.strava_auth import exchange_code_for_token
from logic.strava_sync import backfill_missing_activities

log = logging.getLogger(__name__)


def run_ai_plan_generation(
    journey_id: str,
    user_id: str,
    goal: str,
    ftp: int,
    weight: float,
    start_date: date,
    race_date: date,
    current_date: date,
    current_ctl: float,
) -> None:
    db = get_db()
    try:
        days = build_plan(
            user_id=user_id, journey_id=journey_id, goal=goal, start_date=start_date,
            race_date=race_date, current_date=current_date, ftp=ftp, weight=weight,
            current_ctl=current_ctl,
        )
        rows = [
            {
                "journey_id": journey_id,
                "date": (start_date + timedelta(days=d.day_number - 1)).isoformat(),
                "day_number": d.day_number,
                "phase": d.phase,
                "planned_workout_type": d.planned_workout_type,
                "planned_duration_min": d.planned_duration_min,
                "planned_tss": d.planned_tss,
                "description": d.description,
            }
            for d in days
        ]
        for k in range(0, len(rows), 100):
            db.table("master_plan").insert(rows[k : k + 100]).execute()
        db.table("journeys").update({"status": "active", "error": None}).eq("id", journey_id).execute()
        log.info("Plan with %d days saved for journey %s", len(rows), journey_id)
    except GenerationError as e:
        log.error("Plan generation failed for journey %s: %s", journey_id, e.errors)
        _fail_journey(journey_id, "The AI could not produce a valid plan. Please try again.")
    except Exception:
        log.exception("Plan generation crashed for journey %s", journey_id)
        _fail_journey(journey_id, "Plan generation failed unexpectedly.")


def _fail_journey(journey_id: str, message: str) -> None:
    db = get_db()
    db.table("master_plan").delete().eq("journey_id", journey_id).execute()  # no half plans
    db.table("journeys").update({"status": "failed", "error": message}).eq("id", journey_id).execute()


def run_onboarding_process(user_id: str, code: str) -> None:
    """Connects Strava, downloads 90 days of history and marks the profile as ready."""
    db = get_db()
    db.table("profiles").update({"sync_status": "syncing"}).eq("id", user_id).execute()
    try:
        if not exchange_code_for_token(user_id, code):
            raise RuntimeError("Strava token exchange failed")
        backfill_missing_activities(user_id, days_back=90)
        calculate_daily_metrics(user_id)
        db.table("profiles").update({"sync_status": "completed"}).eq("id", user_id).execute()
    except Exception:
        log.exception("Onboarding failed for %s", user_id)
        db.table("profiles").update({"sync_status": "failed"}).eq("id", user_id).execute()


def run_sync(user_id: str, days_back: int = 7) -> None:
    try:
        if backfill_missing_activities(user_id, days_back) is not None:
            calculate_daily_metrics(user_id)
    except Exception:
        log.exception("Sync failed for %s", user_id)
