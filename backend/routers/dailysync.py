from fastapi import APIRouter, BackgroundTasks, Depends

from core.auth import current_athlete
from logic.workers import run_sync
from models import SyncRequest

router = APIRouter()


@router.post("/sync")
def sync_user(
    payload: SyncRequest,
    background_tasks: BackgroundTasks,
    athlete_id: int = Depends(current_athlete),
):
    """Called by the app on startup; imports new Strava rides in the background."""
    background_tasks.add_task(run_sync, athlete_id, payload.days_back)
    return {"status": "queued", "message": "Sync started in background"}
