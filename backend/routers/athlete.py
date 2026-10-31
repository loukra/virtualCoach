from datetime import timedelta

from fastapi import APIRouter, Depends, Query

from core import db
from core.auth import current_athlete
from core.dates import today
from logic import ftp
from models import FtpUpdate, ProfileUpdate

router = APIRouter()


@router.get("/me")
def me(athlete_id: int = Depends(current_athlete)):
    """Profile plus the onboarding state the app routes on."""
    row = db.query_one(
        "SELECT name, goal, ftp, weight_kg, max_heart_rate, strava_connected, sync_status, sync_error"
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


@router.get("/ftp")
def ftp_overview(athlete_id: int = Depends(current_athlete)):
    """FTP over time, the FTP test results and a suggested new FTP if a ride points to one."""
    tests = db.query(
        "SELECT a.id, substr(a.start_date_local, 1, 10) AS date, a.best_20min_watts FROM master_plan p"
        " JOIN journeys j ON j.id = p.journey_id JOIN activities a ON a.id = p.activity_id"
        " WHERE j.athlete_id = ? AND p.planned_workout_type = 'FTP Test' AND a.best_20min_watts IS NOT NULL"
        " ORDER BY a.start_date_local",
        [athlete_id],
    )
    for test in tests:
        test["ftp_estimate"] = round(test["best_20min_watts"] * ftp.FTP_FROM_20MIN)
    return {
        "current": db.query_one("SELECT ftp FROM athletes WHERE id = ?", [athlete_id])["ftp"],
        "history": db.query(
            "SELECT valid_from, ftp FROM ftp_history WHERE athlete_id = ? ORDER BY valid_from", [athlete_id]
        ),
        "tests": tests,
        "suggestion": ftp.suggestion(athlete_id, today()),
    }


@router.put("/ftp")
def set_ftp(payload: FtpUpdate, athlete_id: int = Depends(current_athlete)):
    """Takes over a new FTP (or confirms the old one, which dismisses the suggestion)."""
    with db.transaction() as conn:
        conn.execute("UPDATE athletes SET ftp = ? WHERE id = ?", [payload.ftp, athlete_id])
        conn.execute(
            "INSERT OR REPLACE INTO ftp_history (athlete_id, valid_from, ftp) VALUES (?, ?, ?)",
            [athlete_id, today().isoformat(), payload.ftp],
        )
    return {"status": "success", "ftp": payload.ftp}
