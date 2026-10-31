import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from core import db
from core.auth import current_athlete
from core.dates import today
from logic.ai import GenerationError
from logic.coach import generate_workout
from logic.schemas import Workout
from logic.workout_math import to_zwo
from models import GenerateWorkoutRequest
from routers.journeys import owned_journey

router = APIRouter()


# A plain `def`: FastAPI runs it in a worker thread, so the LLM call does not block other requests.
@router.post("/generate-workout")
def generate_workout_endpoint(payload: GenerateWorkoutRequest, athlete_id: int = Depends(current_athlete)):
    journey = owned_journey(str(payload.journey_id), athlete_id)
    if journey["status"] != "active":
        raise HTTPException(409, "The plan for this journey is not ready yet.")

    if not payload.force:
        cached = db.query_one(
            "SELECT workout_text, duration_min FROM daily_prescriptions WHERE journey_id = ? AND date = ?",
            [journey["id"], today().isoformat()],
        )
        if cached and cached["duration_min"] == payload.available_time:
            return {"status": "success", "workout": cached["workout_text"], "cached": True}

    try:
        result = generate_workout(athlete_id, journey, payload.available_time)
    except GenerationError:
        raise HTTPException(502, "The coach could not produce a valid workout. Please try again.") from None

    db.execute(
        "INSERT INTO daily_prescriptions (journey_id, date, workout_text, workout_json, duration_min,"
        " estimated_tss, recovery_reason) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (journey_id, date) DO UPDATE SET workout_text = excluded.workout_text,"
        " workout_json = excluded.workout_json, duration_min = excluded.duration_min,"
        " estimated_tss = excluded.estimated_tss, recovery_reason = excluded.recovery_reason,"
        " created_at = CURRENT_TIMESTAMP",
        [journey["id"], result["date"].isoformat(), result["markdown"],
         result["workout"].model_dump_json(), payload.available_time, result["estimated_tss"],
         result["recovery_reason"]],
    )
    return {"status": "success", "workout": result["markdown"], "cached": False}


@router.get("/workouts/{journey_id}/{day}.zwo")
def download_zwo(journey_id: str, day: date, athlete_id: int = Depends(current_athlete)):
    """The day's workout as a Zwift file (drop it into Documents/Zwift/Workouts)."""
    owned_journey(journey_id, athlete_id)
    row = db.query_one(
        "SELECT workout_json FROM daily_prescriptions WHERE journey_id = ? AND date = ?",
        [journey_id, day.isoformat()],
    )
    if not row or not row["workout_json"]:
        raise HTTPException(404, "No workout for this day")
    return Response(
        to_zwo(Workout.model_validate(json.loads(row["workout_json"]))),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="workout_{day.isoformat()}.zwo"'},
    )
