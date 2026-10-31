from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from core.auth import current_user_id
from core.dates import today
from core.db import get_db
from logic.ai import GenerationError
from logic.coach import generate_workout
from logic.schemas import Workout
from logic.workout_math import to_zwo
from models import GenerateWorkoutRequest

router = APIRouter()


def owned_journey(journey_id: UUID, user_id: str) -> dict:
    rows = (
        get_db().table("journeys").select("*")
        .eq("id", str(journey_id)).eq("user_id", user_id).execute()
    ).data
    if not rows:
        raise HTTPException(404, "Journey not found")
    return rows[0]


# A plain `def`: FastAPI runs it in a worker thread, so the LLM call does not block other requests.
@router.post("/generate-workout")
def generate_workout_endpoint(payload: GenerateWorkoutRequest, user_id: str = Depends(current_user_id)):
    journey = owned_journey(payload.journey_id, user_id)
    if journey["status"] != "active":
        raise HTTPException(409, "The plan for this journey is not ready yet.")
    db = get_db()

    if not payload.force:
        cached = (
            db.table("daily_prescriptions").select("workout_text, duration_min")
            .eq("journey_id", journey["id"]).eq("date", today().isoformat()).execute()
        ).data
        if cached and cached[0]["duration_min"] == payload.available_time:
            return {"status": "success", "workout": cached[0]["workout_text"], "cached": True}

    try:
        result = generate_workout(user_id, journey, payload.available_time)
    except GenerationError:
        raise HTTPException(502, "The coach could not produce a valid workout. Please try again.") from None

    db.table("daily_prescriptions").upsert({
        "user_id": user_id,
        "journey_id": journey["id"],
        "date": result["date"].isoformat(),
        "workout_text": result["markdown"],
        "workout_json": result["workout"].model_dump(),
        "duration_min": payload.available_time,
        "estimated_tss": result["estimated_tss"],
        "recovery_reason": result["recovery_reason"],
    }, on_conflict="journey_id,date").execute()

    return {"status": "success", "workout": result["markdown"], "cached": False}


@router.get("/workouts/{journey_id}/{day}.zwo")
def download_zwo(journey_id: UUID, day: date, user_id: str = Depends(current_user_id)):
    """The day's workout as a Zwift file (drop it into Documents/Zwift/Workouts)."""
    owned_journey(journey_id, user_id)
    rows = (
        get_db().table("daily_prescriptions").select("workout_json")
        .eq("journey_id", str(journey_id)).eq("date", day.isoformat()).execute()
    ).data
    if not rows or not rows[0]["workout_json"]:
        raise HTTPException(404, "No workout for this day")
    return Response(
        to_zwo(Workout.model_validate(rows[0]["workout_json"])),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="workout_{day.isoformat()}.zwo"'},
    )
