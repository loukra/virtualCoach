from fastapi import APIRouter, BackgroundTasks, Depends

from core.auth import current_user_id
from logic.workers import run_onboarding_process
from models import ConnectRequest

router = APIRouter()


@router.post("/connect-strava")
def connect_strava(
    payload: ConnectRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user_id),
):
    """Receives the Strava OAuth code from the app; token exchange and import run in the background."""
    background_tasks.add_task(run_onboarding_process, user_id, payload.code)
    return {"message": "Onboarding started", "status": "processing"}
