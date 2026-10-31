
import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core import db
from core.auth import current_athlete
from core.dates import end_after_weeks, today
from logic import ftp, sessions
from logic.events import load_events
from logic.workers import (
    claim_due_journeys,
    generate_scheduled_plan,
    replan_journey,
    request_replan,
    run_ai_plan_generation,
)
from models import CreateJourneyRequest

router = APIRouter()

MIN_PLAN_DAYS = 7
MAX_PLAN_DAYS = 365


def owned_journey(journey_id: str, athlete_id: int) -> dict:
    row = db.query_one("SELECT * FROM journeys WHERE id = ? AND athlete_id = ?", [journey_id, athlete_id])
    if row is None:
        raise HTTPException(404, "Journey not found")
    return row


@router.post("/create-journey")
def create_journey_endpoint(
    payload: CreateJourneyRequest,
    background_tasks: BackgroundTasks,
    athlete_id: int = Depends(current_athlete),
):
    """Creates a journey. One starting today gets its plan now (creating -> active); a later one
    is 'scheduled' and gets its plan on its start day, from the fitness of that day."""
    day = today()
    start_date = payload.start_date or day
    if payload.goal_type == "build":
        if not payload.weeks:
            raise HTTPException(400, "Choose how many weeks the plan should run.")
        end_date = end_after_weeks(start_date, payload.weeks)  # a short first week counts as week 1
    elif payload.race_date is None:
        raise HTTPException(400, "Choose the race date.")
    else:
        end_date = payload.race_date
    plan_days = (end_date - start_date).days + 1
    if plan_days < MIN_PLAN_DAYS:
        raise HTTPException(400, "Race date must be at least 1 week after the start date.")
    if plan_days > MAX_PLAN_DAYS:
        raise HTTPException(400, "Plans can cover at most one year.")
    if end_date < day:
        raise HTTPException(400, "Race date is in the past.")
    # Journeys follow each other: a ride always belongs to exactly one plan.
    clash = db.query_one(
        "SELECT name, start_date, race_date FROM journeys WHERE athlete_id = ?"
        " AND status IN ('scheduled', 'creating', 'active') AND start_date <= ? AND race_date >= ?",
        [athlete_id, end_date.isoformat(), start_date.isoformat()],
    )
    if clash:
        raise HTTPException(
            409, f"This overlaps \"{clash['name']}\" ({clash['start_date']} to {clash['race_date']})."
            f" Start after {clash['race_date']}, or remove that journey first.",
        )
    scheduled = start_date > day

    journey_id = str(uuid.uuid4())
    with db.transaction() as conn:
        conn.execute(
            "UPDATE athletes SET ftp = ?, weight_kg = ? WHERE id = ?",
            [payload.current_ftp, payload.current_weight, athlete_id],
        )
        # FTP history lets the sync score older rides with the FTP that was valid back then.
        conn.execute(
            "INSERT OR REPLACE INTO ftp_history (athlete_id, valid_from, ftp) VALUES (?, ?, ?)",
            [athlete_id, day.isoformat(), payload.current_ftp],
        )
        conn.execute(
            "INSERT INTO journeys (id, athlete_id, name, goal_type, start_date, race_date, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [journey_id, athlete_id, payload.journey_name, payload.goal_type, start_date.isoformat(),
             end_date.isoformat(), "scheduled" if scheduled else "creating"],
        )
    if scheduled:
        return {"status": "scheduled", "journey_id": journey_id,
                "message": f"Your coach builds the plan on {start_date.isoformat()}, from your fitness then."}
    latest = db.query_one(
        "SELECT ctl FROM daily_metrics WHERE athlete_id = ? ORDER BY date DESC LIMIT 1", [athlete_id]
    )

    background_tasks.add_task(
        run_ai_plan_generation,
        journey_id, athlete_id, payload.journey_name, payload.current_ftp, payload.current_weight,
        start_date, end_date, day, float(latest["ctl"]) if latest else 0.0, payload.goal_type,
    )
    return {"status": "processing", "message": "AI is building your plan...", "journey_id": journey_id}


def start_due_journeys(athlete_id: int, background_tasks: BackgroundTasks) -> None:
    """Scheduled journeys whose day has come switch to 'creating' now; the plan follows."""
    for journey in claim_due_journeys(athlete_id, today()):
        background_tasks.add_task(generate_scheduled_plan, journey)


@router.get("/journeys")
def list_journeys(background_tasks: BackgroundTasks, athlete_id: int = Depends(current_athlete)):
    """The athlete's journeys in time order."""
    start_due_journeys(athlete_id, background_tasks)
    return db.query(
        "SELECT id, name, goal_type, start_date, race_date, status, error, replanning, created_at"
        " FROM journeys WHERE athlete_id = ? AND status != 'archived' ORDER BY start_date",
        [athlete_id],
    )


@router.get("/journeys/{journey_id}")
def get_journey(
    journey_id: str, background_tasks: BackgroundTasks, athlete_id: int = Depends(current_athlete)
):
    start_due_journeys(athlete_id, background_tasks)
    return owned_journey(journey_id, athlete_id)


@router.delete("/journeys/{journey_id}")
def archive_journey(journey_id: str, athlete_id: int = Depends(current_athlete)):
    """Hides a journey from the app; its plan and workouts stay in the database."""
    owned_journey(journey_id, athlete_id)
    db.execute("UPDATE journeys SET status = 'archived' WHERE id = ?", [journey_id])
    return {"status": "archived"}


@router.post("/journeys/{journey_id}/replan")
def replan(journey_id: str, background_tasks: BackgroundTasks, athlete_id: int = Depends(current_athlete)):
    """Rebuilds the plan from next Monday around the current events (also: retry after a failure)."""
    journey = owned_journey(journey_id, athlete_id)
    if journey["status"] != "active":
        raise HTTPException(409, "Only an active plan can be adapted.")
    if request_replan(journey_id) == "replanning":
        background_tasks.add_task(replan_journey, journey_id)
    return {"status": "replanning"}


def event_today(athlete_id: int, day: date) -> dict | None:
    """A race or a day off today decides the day, whatever the week's plan still holds."""
    for event in load_events(athlete_id, day, day):
        if event["kind"] == "race":
            return {"mode": "race", "session": None, "reason": f"Race day: {event['name']}. Ride well!"}
        if event["kind"] == "off":
            return {"mode": "rest", "session": None, "reason": f"{event['name']}: no training planned."}
    return None


@router.get("/journeys/{journey_id}/today")
def journey_today(journey_id: str, athlete_id: int = Depends(current_athlete)):
    """Everything the journey screen shows: today's suggestion, this week, check-in, signals."""
    journey = owned_journey(journey_id, athlete_id)
    day = today()
    if journey["status"] == "active":
        sessions.match_rides(journey)
    week, first, last, week_no = sessions.week_sessions(journey, day)
    ready = sessions.readiness(athlete_id, day)
    start = date.fromisoformat(journey["start_date"])
    if day < start:
        starts = start.strftime("%A, %d %B").replace(" 0", " ")
        choice = {"mode": "rest", "session": None,
                  "reason": f"Your plan starts on {starts}. Until then, ride as you like or rest."}
    else:
        choice = event_today(athlete_id, day) or sessions.choose_session(week, day, last, ready)
    prescription = db.query_one(
        "SELECT workout_text, duration_min, estimated_tss, recovery_reason, chosen_plan_id"
        " FROM daily_prescriptions WHERE journey_id = ? AND date = ?",
        [journey_id, day.isoformat()],
    )
    ridden = db.query_one(
        "SELECT COALESCE(SUM(tss), 0) AS tss FROM activities"
        " WHERE athlete_id = ? AND substr(start_date_local, 1, 10) BETWEEN ? AND ?",
        [athlete_id, first.isoformat(), last.isoformat()],
    )
    end = date.fromisoformat(journey["race_date"])
    return {
        "date": day.isoformat(),
        "goal_type": journey["goal_type"],
        "starts_on": journey["start_date"] if day < start else None,
        "suggestion": choice,
        "week": {
            "number": week_no,
            "total": sessions.week_number(start, end),
            "first_day": first.isoformat(),
            "last_day": last.isoformat(),
            "planned_tss": sum(s["planned_tss"] for s in week if s["status"] != "off"),
            "ridden_tss": ridden["tss"],
            "sessions": [{**s, "state": session_state(s, day)} for s in week],
        },
        "planned": next((s for s in week if s["date"] == day.isoformat()), None),
        "checkin": ready["checkin"],
        "signals": ready["signals"],
        "workout": prescription,
        "fitness": ready["stats"],
        "ftp": ftp.suggestion(athlete_id, day),
    }


def session_state(session: dict, day: date) -> str:
    """rest, done, off (on a day off), open, or missed (still open after its week has ended)."""
    if session["planned_workout_type"] == "Rest":
        return "rest"
    if session["status"] == "off":
        return "off"
    if session["status"] == "done":
        return "done"
    return "open" if session["week_end"] >= day.isoformat() else "missed"


def plan_days(journey: dict, day: date) -> list[dict]:
    """A journey's planned days with their state, workout and completing ride."""
    if journey["status"] == "active":
        sessions.match_rides(journey)
    plan = db.query(
        "SELECT p.id, p.journey_id, p.date, p.day_number, p.phase, p.planned_workout_type,"
        " p.planned_duration_min, p.planned_tss, p.description, p.status, p.activity_id, d.workout_text,"
        " d.workout_json, substr(a.start_date_local, 1, 10) AS done_on"
        " FROM master_plan p LEFT JOIN daily_prescriptions d"
        " ON d.journey_id = p.journey_id AND d.date = p.date"
        " LEFT JOIN activities a ON a.id = p.activity_id"
        " WHERE p.journey_id = ? ORDER BY p.date",
        [journey["id"]],
    )
    start, end = date.fromisoformat(journey["start_date"]), date.fromisoformat(journey["race_date"])
    sessions.mark_time_off(plan, journey["athlete_id"])
    for row in plan:
        row["has_workout_file"] = bool(row.pop("workout_json"))
        week = sessions.week_number(start, date.fromisoformat(row["date"]))
        row["week_end"] = sessions.week_bounds(start, end, week)[1].isoformat()
        row["state"] = session_state(row, day)
    return plan


def rides_between(athlete_id: int, first: str, last: str) -> list[dict]:
    return db.query(
        "SELECT id, start_date_local, sport_type, name, moving_time, tss, tss_source FROM activities"
        " WHERE athlete_id = ? AND substr(start_date_local, 1, 10) BETWEEN ? AND ?"
        " ORDER BY start_date_local",
        [athlete_id, first, last],
    )


@router.get("/journeys/{journey_id}/calendar")
def journey_calendar(journey_id: str, athlete_id: int = Depends(current_athlete)):
    """Planned days and the rides done in the journey's date range."""
    journey = owned_journey(journey_id, athlete_id)
    plan = plan_days(journey, today())
    return {"journey": journey, "plan": plan,
            "activities": rides_between(athlete_id, journey["start_date"], journey["race_date"])}


@router.get("/calendar")
def calendar(background_tasks: BackgroundTasks, athlete_id: int = Depends(current_athlete)):
    """One timeline over all journeys (they never overlap): planned days, rides and events."""
    start_due_journeys(athlete_id, background_tasks)
    day = today()
    journeys = db.query(
        "SELECT id, athlete_id, name, goal_type, start_date, race_date, status, replanning FROM journeys"
        " WHERE athlete_id = ? AND status != 'archived' ORDER BY start_date",
        [athlete_id],
    )
    plan = [row for j in journeys if j["status"] == "active" for row in plan_days(j, day)]
    events = db.query(
        "SELECT id, kind, name, start_date, end_date, priority, duration_min FROM events"
        " WHERE athlete_id = ? ORDER BY start_date",
        [athlete_id],
    )
    dates = [d for j in journeys for d in (j["start_date"], j["race_date"])]
    dates += [d for e in events for d in (e["start_date"], e["end_date"])]
    first, last = min([*dates, day.isoformat()]), max([*dates, day.isoformat()])
    return {"first": first, "last": last, "journeys": journeys, "plan": plan, "events": events,
            "activities": rides_between(athlete_id, first, last)}
