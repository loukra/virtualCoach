from fastapi import APIRouter, BackgroundTasks, Depends

from core import db
from core.auth import current_athlete
from logic.workers import run_onboarding_process
from models import ConnectRequest

router = APIRouter()


@router.post("/connect-strava")
def connect_strava(
    payload: ConnectRequest,
    background_tasks: BackgroundTasks,
    athlete_id: int = Depends(current_athlete),
):
    """Receives the Strava OAuth code from the app; token exchange and import run in the background."""
    # Set before answering, so the app's next /me already shows the import as running.
    db.execute("UPDATE athletes SET sync_status = 'syncing' WHERE id = ?", [athlete_id])
    background_tasks.add_task(run_onboarding_process, athlete_id, payload.code)
    return {"message": "Onboarding started", "status": "processing"}
