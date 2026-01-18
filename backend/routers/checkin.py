from fastapi import APIRouter
from datetime import date
from models import CheckInRequest
from core.db import supabase

router = APIRouter()

@router.post("/check-in")
async def save_checkin(payload: CheckInRequest):
    today = date.today().isoformat()
    
    data = {
        "user_id": payload.user_id,
        "date": today,
        "feel_score": payload.feel_score,
        "soreness_score": payload.soreness_score
    }
    
    # 👇 FIX: Explicitly tell Supabase to check 'user_id' and 'date' for conflicts
    supabase.table("daily_checkins").upsert(data, on_conflict="user_id, date").execute()
    
    return {"status": "success", "data": data}
