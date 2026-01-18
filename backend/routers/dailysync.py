from fastapi import APIRouter, BackgroundTasks
from core.db import supabase
from models import SyncRequest
from logic.workers import run_daily_sync

router = APIRouter()

@router.post("/sync")
async def sync_user(payload: SyncRequest, background_tasks: BackgroundTasks):
    """
    Called by the App on startup.
    Triggers a background update of Strava activities.
    """
    # Run in background so the App doesn't wait/freeze
    background_tasks.add_task(run_daily_sync, payload.user_id)
    
    return {"status": "queued", "message": "Sync started in background"}
