
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core import db
from core.auth import current_athlete
from core.dates import today
from logic.workers import run_ai_plan_generation
from models import CreateJourneyRequest

router = APIRouter()

MIN_PLAN_DAYS = 7
MAX_PLAN_DAYS = 365


def owned_journey(journey_id: str, athlete_id: int) -> dict:
    row = db.query_one("SELECT * FROM journeys WHERE id = ? AND athlete_id = ?", [journey_id, athlete_id])
    if row is None:
        raise HTTPException(404, "Journey not found")
    return row


@router.post("/create-journey")
def create_journey_endpoint(
    payload: CreateJourneyRequest,
    background_tasks: BackgroundTasks,
    athlete_id: int = Depends(current_athlete),
):
    """Creates a journey and generates its plan in the background (status creating -> active)."""
    day = today()
    start_date = payload.start_date or day
    plan_days = (payload.race_date - start_date).days + 1
    if plan_days < MIN_PLAN_DAYS:
        raise HTTPException(400, "Race date must be at least 1 week after the start date.")
    if plan_days > MAX_PLAN_DAYS:
        raise HTTPException(400, "Plans can cover at most one year.")
    if payload.race_date < day:
        raise HTTPException(400, "Race date is in the past.")

    journey_id = str(uuid.uuid4())
    with db.transaction() as conn:
        conn.execute(
            "UPDATE athletes SET ftp = ?, weight_kg = ? WHERE id = ?",
            [payload.current_ftp, payload.current_weight, athlete_id],
        )
        # FTP history lets the sync score older rides with the FTP that was valid back then.
        conn.execute(
            "INSERT OR REPLACE INTO ftp_history (athlete_id, valid_from, ftp) VALUES (?, ?, ?)",
            [athlete_id, day.isoformat(), payload.current_ftp],
        )
        conn.execute(
            "INSERT INTO journeys (id, athlete_id, name, start_date, race_date) VALUES (?, ?, ?, ?, ?)",
            [journey_id, athlete_id, payload.journey_name, start_date.isoformat(),
             payload.race_date.isoformat()],
        )
    latest = db.query_one(
        "SELECT ctl FROM daily_metrics WHERE athlete_id = ? ORDER BY date DESC LIMIT 1", [athlete_id]
    )

    background_tasks.add_task(
        run_ai_plan_generation,
        journey_id, athlete_id, payload.journey_name, payload.current_ftp, payload.current_weight,
        start_date, payload.race_date, day, float(latest["ctl"]) if latest else 0.0,
    )
    return {"status": "processing", "message": "AI is building your plan...", "journey_id": journey_id}


@router.get("/journeys")
def list_journeys(athlete_id: int = Depends(current_athlete)):
    return db.query(
        "SELECT id, name, start_date, race_date, status, error, created_at FROM journeys"
        " WHERE athlete_id = ? AND status != 'archived' ORDER BY created_at DESC",
        [athlete_id],
    )


@router.get("/journeys/{journey_id}")
def get_journey(journey_id: str, athlete_id: int = Depends(current_athlete)):
    return owned_journey(journey_id, athlete_id)


@router.delete("/journeys/{journey_id}")
def archive_journey(journey_id: str, athlete_id: int = Depends(current_athlete)):
    """Hides a journey from the app; its plan and workouts stay in the database."""
    owned_journey(journey_id, athlete_id)
    db.execute("UPDATE journeys SET status = 'archived' WHERE id = ?", [journey_id])
    return {"status": "archived"}


@router.get("/journeys/{journey_id}/today")
def journey_today(journey_id: str, athlete_id: int = Depends(current_athlete)):
    """Everything the journey screen shows for today."""
    owned_journey(journey_id, athlete_id)
    day = today().isoformat()
    prescription = db.query_one(
        "SELECT workout_text, duration_min, estimated_tss, recovery_reason FROM daily_prescriptions"
        " WHERE journey_id = ? AND date = ?",
        [journey_id, day],
    )
    return {
        "date": day,
        "planned": db.query_one(
            "SELECT planned_workout_type, planned_duration_min, planned_tss, description, phase"
            " FROM master_plan WHERE journey_id = ? AND date = ?",
            [journey_id, day],
        ),
        "checkin": db.query_one(
            "SELECT feel_score, soreness_score, notes FROM daily_checkins WHERE athlete_id = ? AND date = ?",
            [athlete_id, day],
        ),
        "workout": prescription,
        "fitness": db.query_one(
            "SELECT date, ctl, atl, tsb FROM daily_metrics WHERE athlete_id = ? AND date <= ?"
            " ORDER BY date DESC LIMIT 1",
            [athlete_id, day],
        ),
    }


@router.get("/journeys/{journey_id}/calendar")
def journey_calendar(journey_id: str, athlete_id: int = Depends(current_athlete)):
    """Planned days and the rides done in the journey's date range."""
    journey = owned_journey(journey_id, athlete_id)
    plan = db.query(
        "SELECT p.id, p.date, p.day_number, p.phase, p.planned_workout_type, p.planned_duration_min,"
        " p.planned_tss, p.description, d.workout_text, d.workout_json"
        " FROM master_plan p LEFT JOIN daily_prescriptions d"
        " ON d.journey_id = p.journey_id AND d.date = p.date"
        " WHERE p.journey_id = ? ORDER BY p.date",
        [journey_id],
    )
    for day in plan:
        day["has_workout_file"] = bool(day.pop("workout_json"))
    activities = db.query(
        "SELECT id, start_date_local, sport_type, name, moving_time, tss, tss_source FROM activities"
        " WHERE athlete_id = ? AND substr(start_date_local, 1, 10) BETWEEN ? AND ?"
        " ORDER BY start_date_local",
        [athlete_id, journey["start_date"], journey["race_date"]],
    )
    return {"journey": journey, "plan": plan, "activities": activities}
