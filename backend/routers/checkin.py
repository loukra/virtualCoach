from fastapi import APIRouter, Depends

from core import db
from core.auth import current_athlete
from core.dates import today
from models import CheckInRequest

router = APIRouter()


@router.post("/check-in")
def save_checkin(payload: CheckInRequest, athlete_id: int = Depends(current_athlete)):
    data = {
        "date": today().isoformat(),
        "feel_score": payload.feel_score,
        "soreness_score": payload.soreness_score,
        "motivation_score": payload.motivation_score,
        "notes": (payload.notes or "").strip() or None,
    }
    # One check-in per day; checking in again replaces it (feelings change during the day).
    db.execute(
        "INSERT OR REPLACE INTO daily_checkins (athlete_id, date, feel_score, soreness_score,"
        " motivation_score, notes) VALUES (?, ?, ?, ?, ?, ?)",
        [athlete_id, *data.values()],
    )
    return {"status": "success", "data": data}
