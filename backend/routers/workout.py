import json
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from core import db
from core.auth import current_athlete
from core.dates import today
from logic import sessions
from logic.coach import NotEnoughTime, generate_workout
from logic.schemas import Workout
from logic.workout_math import to_zwo
from models import GenerateWorkoutRequest
from routers.journeys import owned_journey

router = APIRouter()


def session_for(journey: dict, plan_id: int | None) -> dict | None:
    """The chosen session of this journey, or today's suggestion when none was chosen."""
    if plan_id is not None:
        row = db.query_one(
            "SELECT * FROM master_plan WHERE id = ? AND journey_id = ?", [plan_id, journey["id"]]
        )
        if row is None:
            raise HTTPException(404, "Session not found")
        if row["status"] == "done":
            raise HTTPException(409, "This session is already done.")
        return row
    day = today()
    week, _, last, _ = sessions.week_sessions(journey, day)
    choice = sessions.choose_session(week, day, last, sessions.readiness(journey["athlete_id"], day))
    return choice["session"]


# A plain `def`: FastAPI runs it in a worker thread, so the LLM call does not block other requests.
@router.post("/generate-workout")
def generate_workout_endpoint(payload: GenerateWorkoutRequest, athlete_id: int = Depends(current_athlete)):
    journey = owned_journey(str(payload.journey_id), athlete_id)
    if journey["status"] != "active":
        raise HTTPException(409, "The plan for this journey is not ready yet.")
    session = session_for(journey, payload.plan_id)

    if not payload.force:
        cached = db.query_one(
            "SELECT workout_text, duration_min, chosen_plan_id FROM daily_prescriptions"
            " WHERE journey_id = ? AND date = ?",
            [journey["id"], today().isoformat()],
        )
        if cached and cached["duration_min"] == payload.available_time and \
                cached["chosen_plan_id"] == (session["id"] if session else None):
            return {"status": "success", "workout": cached["workout_text"], "cached": True}

    try:
        result = generate_workout(athlete_id, journey, payload.available_time, session)
    except NotEnoughTime as e:
        raise HTTPException(400, str(e)) from None

    db.execute(
        "INSERT INTO daily_prescriptions (journey_id, date, workout_text, workout_json, duration_min,"
        " estimated_tss, recovery_reason, plan_id, chosen_plan_id, source)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (journey_id, date) DO UPDATE SET workout_text = excluded.workout_text,"
        " workout_json = excluded.workout_json, duration_min = excluded.duration_min,"
        " estimated_tss = excluded.estimated_tss, recovery_reason = excluded.recovery_reason,"
        " plan_id = excluded.plan_id, chosen_plan_id = excluded.chosen_plan_id, source = excluded.source,"
        " created_at = CURRENT_TIMESTAMP",
        [journey["id"], result["date"].isoformat(), result["markdown"],
         result["workout"].model_dump_json(), payload.available_time, result["estimated_tss"],
         result["recovery_reason"], result["plan_id"], session["id"] if session else None, result["source"]],
    )
    return {"status": "success", "workout": result["markdown"], "cached": False, "source": result["source"]}


@router.get("/workouts/{journey_id}/{day}.zwo")
def download_zwo(journey_id: str, day: date, athlete_id: int = Depends(current_athlete)):
    """The day's workout as a Zwift file (drop it into Documents/Zwift/Workouts)."""
    owned_journey(journey_id, athlete_id)
    row = db.query_one(
        "SELECT workout_json, workout_text FROM daily_prescriptions WHERE journey_id = ? AND date = ?",
        [journey_id, day.isoformat()],
    )
    if not row or not row["workout_json"]:
        raise HTTPException(404, "No workout for this day")
    return Response(
        to_zwo(Workout.model_validate(json.loads(row["workout_json"]))),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{zwo_filename(row, day)}"'},
    )


def zwo_filename(row: dict, day: date) -> str:
    """'2026-11-03 Sweet Spot 3x10.zwo': sorts by date in Zwift's folder and says what it is."""
    name = Workout.model_validate(json.loads(row["workout_json"])).name
    safe = re.sub(r"[^A-Za-z0-9 ()+x-]", "", name).strip()[:60] or "Workout"
    return f"{day.isoformat()} {safe}.zwo"
