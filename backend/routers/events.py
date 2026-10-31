from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core import db
from core.auth import current_athlete
from core.dates import today
from logic.events import MAX_OFF_DAYS
from logic.workers import replan_from, replan_journey, request_replan
from models import CreateEventRequest

router = APIRouter()

PAST_DAYS_SHOWN = 90


@router.get("/events")
def list_events(athlete_id: int = Depends(current_athlete)):
    """Races, group rides and days off, from three months back on."""
    return db.query(
        "SELECT id, kind, name, start_date, end_date, priority, duration_min FROM events"
        " WHERE athlete_id = ? AND end_date >= ? ORDER BY start_date",
        [athlete_id, (today() - timedelta(days=PAST_DAYS_SHOWN)).isoformat()],
    )


def check_event(payload: CreateEventRequest, athlete_id: int) -> tuple[date, date]:
    start = payload.start_date
    end = (payload.end_date or start) if payload.kind == "off" else start
    if start < today():
        raise HTTPException(400, "Choose a date from today on.")
    if end < start:
        raise HTTPException(400, "The last day comes after the first.")
    if (end - start).days + 1 > MAX_OFF_DAYS:
        raise HTTPException(400, f"A break can last at most {MAX_OFF_DAYS} days.")
    if payload.kind == "race" and payload.priority is None:
        raise HTTPException(400, "Choose whether this is a main or a secondary race.")
    # Days off exclude races and rides; two races or rides never share a day.
    clash = db.query_one(
        "SELECT name, kind FROM events WHERE athlete_id = ? AND start_date <= ? AND end_date >= ?"
        " AND (? = 'off' OR kind = 'off' OR start_date = ?)",
        [athlete_id, end.isoformat(), start.isoformat(), payload.kind, start.isoformat()],
    )
    if clash:
        raise HTTPException(409, f"\"{clash['name']}\" is already on these days.")
    goal = db.query_one(
        "SELECT name FROM journeys WHERE athlete_id = ? AND goal_type = 'race' AND status != 'archived'"
        " AND race_date BETWEEN ? AND ?",
        [athlete_id, start.isoformat(), end.isoformat()],
    )
    if goal:
        raise HTTPException(409, f"That day is the race of your journey \"{goal['name']}\".")
    return start, end


def update_plans(athlete_id: int, start: date, end: date, background_tasks: BackgroundTasks) -> list[dict]:
    """What happens to each journey covering the event's days: an active plan is rebuilt from next
    Monday, a scheduled one plans for it on its start day."""
    outcome = []
    for journey in db.query(
        "SELECT id, name, status FROM journeys WHERE athlete_id = ? AND status IN"
        " ('scheduled', 'creating', 'active') AND start_date <= ? AND race_date >= ?",
        [athlete_id, end.isoformat(), start.isoformat()],
    ):
        if journey["status"] == "scheduled":
            result = "scheduled"
        elif end < replan_from(today()):
            result = "this_week"  # the plan from Monday on is untouched; today's suggestion knows
        else:
            result = request_replan(journey["id"])
            if result == "replanning":
                background_tasks.add_task(replan_journey, journey["id"])
        outcome.append({"journey_id": journey["id"], "name": journey["name"], "plan": result})
    return outcome


@router.post("/events")
def create_event(
    payload: CreateEventRequest, background_tasks: BackgroundTasks, athlete_id: int = Depends(current_athlete)
):
    start, end = check_event(payload, athlete_id)
    with db.transaction() as conn:
        event_id = conn.execute(
            "INSERT INTO events (athlete_id, kind, name, start_date, end_date, priority, duration_min)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [athlete_id, payload.kind, payload.name.strip(), start.isoformat(), end.isoformat(),
             payload.priority if payload.kind == "race" else None,
             payload.duration_min if payload.kind != "off" else None],
        ).lastrowid
    return {"id": event_id, "journeys": update_plans(athlete_id, start, end, background_tasks)}


@router.delete("/events/{event_id}")
def delete_event(
    event_id: int, background_tasks: BackgroundTasks, athlete_id: int = Depends(current_athlete)
):
    event = db.query_one("SELECT * FROM events WHERE id = ? AND athlete_id = ?", [event_id, athlete_id])
    if event is None:
        raise HTTPException(404, "Event not found")
    db.execute("DELETE FROM events WHERE id = ?", [event_id])
    start, end = date.fromisoformat(event["start_date"]), date.fromisoformat(event["end_date"])
    if end < today():
        return {"journeys": []}  # over already: nothing to plan around any more
    return {"journeys": update_plans(athlete_id, max(start, today()), end, background_tasks)}
