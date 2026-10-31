from datetime import timedelta

from fastapi import APIRouter, Depends, Query

from core import db
from core.auth import current_athlete
from core.dates import today
from models import ProfileUpdate

router = APIRouter()


@router.get("/me")
def me(athlete_id: int = Depends(current_athlete)):
    """Profile plus the onboarding state the app routes on."""
    row = db.query_one(
        "SELECT name, goal, ftp, weight_kg, max_heart_rate, strava_connected, sync_status"
        " FROM athletes WHERE id = ?",
        [athlete_id],
    )
    return {
        **row,
        "strava_connected": bool(row["strava_connected"]),
        "profile_complete": bool((row["goal"] or "").strip() and row["ftp"]),
    }


@router.put("/profile")
def update_profile(payload: ProfileUpdate, athlete_id: int = Depends(current_athlete)):
    db.execute(
        "UPDATE athletes SET goal = ?, ftp = ?, max_heart_rate = ?, weight_kg = ? WHERE id = ?",
        [payload.goal, payload.ftp, payload.max_heart_rate, payload.weight_kg, athlete_id],
    )
    db.execute(
        "INSERT OR REPLACE INTO ftp_history (athlete_id, valid_from, ftp) VALUES (?, ?, ?)",
        [athlete_id, today().isoformat(), payload.ftp],
    )
    return {"status": "success"}


@router.get("/metrics")
def metrics(days: int = Query(default=90, ge=7, le=730), athlete_id: int = Depends(current_athlete)):
    """Daily fitness (CTL), fatigue (ATL) and form (TSB), oldest first."""
    since = (today() - timedelta(days=days)).isoformat()
    return db.query(
        "SELECT date, ctl, atl, tsb FROM daily_metrics WHERE athlete_id = ? AND date >= ? ORDER BY date",
        [athlete_id, since],
    )
