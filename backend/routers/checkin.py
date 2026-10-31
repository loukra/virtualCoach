from fastapi import APIRouter, Depends

from core.auth import current_user_id
from core.dates import today
from core.db import get_db
from models import CheckInRequest

router = APIRouter()


@router.post("/check-in")
def save_checkin(payload: CheckInRequest, user_id: str = Depends(current_user_id)):
    data = {
        "user_id": user_id,
        "date": today().isoformat(),
        "feel_score": payload.feel_score,
        "soreness_score": payload.soreness_score,
        "notes": payload.notes,
    }
    get_db().table("daily_checkins").upsert(data, on_conflict="user_id,date").execute()
    return {"status": "success", "data": data}
