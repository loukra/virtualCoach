from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.auth import current_user_id
from core.dates import today
from core.db import get_db
from logic.workers import run_ai_plan_generation
from models import CreateJourneyRequest

router = APIRouter()

MIN_PLAN_DAYS = 7
MAX_PLAN_DAYS = 365


@router.post("/create-journey")
def create_journey_endpoint(
    payload: CreateJourneyRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user_id),
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

    db = get_db()
    db.table("profiles").update({
        "ftp": payload.current_ftp,
        "weight_kg": payload.current_weight,
    }).eq("id", user_id).execute()
    # FTP history lets the sync score older rides with the FTP that was valid back then.
    db.table("athlete_history").upsert(
        {"user_id": user_id, "valid_from": day.isoformat(), "ftp": payload.current_ftp},
        on_conflict="user_id,valid_from",
    ).execute()

    metrics = (
        db.table("daily_metrics").select("ctl").eq("user_id", user_id)
        .order("date", desc=True).limit(1).execute()
    ).data
    current_ctl = float(metrics[0]["ctl"]) if metrics else 0.0

    journey = db.table("journeys").insert({
        "user_id": user_id,
        "name": payload.journey_name,
        "start_date": start_date.isoformat(),
        "race_date": payload.race_date.isoformat(),
        "status": "creating",
    }).execute().data[0]

    background_tasks.add_task(
        run_ai_plan_generation,
        journey["id"], user_id, payload.journey_name, payload.current_ftp, payload.current_weight,
        start_date, payload.race_date, day, current_ctl,
    )
    return {"status": "processing", "message": "AI is building your plan...", "journey_id": journey["id"]}
