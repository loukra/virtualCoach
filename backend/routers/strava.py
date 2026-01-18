from fastapi import APIRouter, BackgroundTasks
from datetime import date
from models import ConnectRequest
from logic.workers import run_onboarding_process

router = APIRouter()

@router.post("/connect-strava")
async def connect_strava(payload: ConnectRequest, background_tasks: BackgroundTasks):
    """
    Receives the Strava Code from the App.
    Returns immediately, but starts the sync in the background.
    """
    # 1. Add the heavy function to the background queue
    background_tasks.add_task(run_onboarding_process, payload.user_id, payload.code)
    
    # 2. Reply instantly to the phone (prevent timeout)
    return {
        "message": "Onboarding started", 
        "user_id": payload.user_id,
        "status": "processing"
    }
