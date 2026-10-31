"""Today's workout: gather the athlete's context, apply hard rules, let the LLM prescribe."""
import json
from datetime import date, timedelta

from core import db
from core.config import get_settings
from core.dates import today
from logic.ai import generate_structured
from logic.guardrails import validate_workout
from logic.schemas import Workout
from logic.workout_math import estimate_tss, to_markdown

DEFAULT_FTP = 200
DEFAULT_MAX_HR = 190
# Form this negative means accumulated fatigue; no intensity until it recovers.
FORCED_RECOVERY_TSB = -30


def forced_recovery_reason(checkin: dict | None, stats: dict | None) -> str | None:
    """Hard rules that override the plan. Decided in code, not left to the model."""
    if checkin and checkin["feel_score"] <= 2:
        return f"the athlete rates mood/energy {checkin['feel_score']}/5"
    if checkin and checkin["soreness_score"] <= 2:
        return f"the athlete rates their legs {checkin['soreness_score']}/5"
    if stats and stats.get("tsb") is not None and stats["tsb"] <= FORCED_RECOVERY_TSB:
        return f"form (TSB) is {stats['tsb']:.0f}"
    return None


def hr_zones(max_hr: int) -> str:
    bounds = [("Z1 Recovery", 0, 0.60), ("Z2 Endurance", 0.60, 0.70), ("Z3 Tempo", 0.70, 0.80),
              ("Z4 Threshold", 0.80, 0.90), ("Z5 VO2 Max", 0.90, 1.0)]
    return "\n".join(f"- {n}: {int(max_hr * lo)}-{int(max_hr * hi)} bpm" for n, lo, hi in bounds)


def format_compliance_history(plans: list[dict], activities: list[dict], day: date) -> str:
    """Plan versus actual for the last seven days, one line per day."""
    lines = []
    for i in range(7, 0, -1):
        d = (day - timedelta(days=i)).isoformat()
        plan = next((p for p in plans if p["date"] == d), None)
        rides = [a for a in activities if (a.get("start_date_local") or "")[:10] == d]
        plan_str = (
            f"{plan['planned_workout_type']} ({plan['planned_duration_min']} min, {plan['planned_tss']} TSS)"
            if plan else "before plan start"
        )
        # Ride names are left out: they are free text and may hold personal details.
        actual_str = " + ".join(
            f"{a.get('sport_type') or 'Ride'} ({(a.get('moving_time') or 0) // 60} min,"
            f" {a.get('tss') or 0} TSS)"
            for a in rides
        ) or "no activity"
        lines.append(f"- {d}: plan {plan_str} | actual {actual_str}")
    return "\n".join(lines)


def get_todays_context(athlete_id: int, journey: dict) -> dict:
    current = today()
    day = current.isoformat()
    week_ago = (current - timedelta(days=7)).isoformat()

    profile = db.query_one("SELECT ftp, max_heart_rate FROM athletes WHERE id = ?", [athlete_id]) or {}
    stats = db.query_one(
        "SELECT ctl, atl, tsb FROM daily_metrics WHERE athlete_id = ? AND date <= ?"
        " ORDER BY date DESC LIMIT 1",
        [athlete_id, day],
    )
    plan = db.query_one("SELECT * FROM master_plan WHERE journey_id = ? AND date = ?", [journey["id"], day])
    checkin = db.query_one(
        "SELECT feel_score, soreness_score, notes FROM daily_checkins WHERE athlete_id = ? AND date = ?",
        [athlete_id, day],
    )
    recent_plans = db.query(
        "SELECT date, planned_workout_type, planned_duration_min, planned_tss FROM master_plan"
        " WHERE journey_id = ? AND date >= ? AND date < ?",
        [journey["id"], week_ago, day],
    )
    recent_rides = db.query(
        "SELECT start_date_local, sport_type, tss, moving_time FROM activities"
        " WHERE athlete_id = ? AND start_date_local >= ? AND start_date_local < ?",
        [athlete_id, week_ago, day],
    )

    start, race = date.fromisoformat(journey["start_date"]), date.fromisoformat(journey["race_date"])
    return {
        "day": today(),
        "ftp": profile.get("ftp") or DEFAULT_FTP,
        "max_hr": profile.get("max_heart_rate") or DEFAULT_MAX_HR,
        "max_hr_is_estimate": not profile.get("max_heart_rate"),
        "stats": stats,
        "plan": plan,
        "checkin": checkin,
        "goal": journey["name"],
        "days_until_race": (race - today()).days,
        "current_week": (today() - start).days // 7 + 1,
        "total_weeks": (race - start).days // 7 + 1,
        "compliance": format_compliance_history(recent_plans, recent_rides, current),
    }


def workout_input(ctx: dict, available_time: int, recovery_reason: str | None) -> str:
    stats, plan, checkin = ctx["stats"], ctx["plan"], ctx["checkin"]
    fitness = (
        f"CTL {stats['ctl']:.0f}, ATL {stats['atl']:.0f}, TSB {stats['tsb']:.0f}"
        if stats else "no training history yet"
    )
    planned = (
        f"{plan['planned_workout_type']}, {plan['planned_duration_min']} min, {plan['planned_tss']} TSS."
        f" {plan['description']}"
        if plan else "No session scheduled today."
    )
    feel = (
        f"mood {checkin['feel_score']}/5, legs {checkin['soreness_score']}/5"
        + (f", note: {json.dumps(checkin['notes'])}" if checkin.get("notes") else "")
        if checkin else "no check-in today"
    )
    hr_note = " (estimated, athlete has not set it)" if ctx["max_hr_is_estimate"] else ""
    recovery = (
        f"\n\nFORCED RECOVERY: {recovery_reason}. Keep every target at or below 0.75 FTP."
        if recovery_reason else ""
    )
    return f"""GOAL
- Event (athlete's own words): {json.dumps(ctx['goal'])}
- {ctx['days_until_race']} days until race, week {ctx['current_week']} of {ctx['total_weeks']}

ATHLETE
- FTP {ctx['ftp']} W, max HR {ctx['max_hr']} bpm{hr_note}
- Fitness: {fitness}
- Heart-rate zones:
{hr_zones(ctx['max_hr'])}

TODAY ({ctx['day'].isoformat()})
- Planned: {planned}
- Check-in: {feel}
- Available time: {available_time} minutes

LAST SEVEN DAYS (plan vs actual)
{ctx['compliance']}{recovery}"""


def generate_workout(athlete_id: int, journey: dict, available_time: int) -> dict:
    ctx = get_todays_context(athlete_id, journey)
    recovery_reason = forced_recovery_reason(ctx["checkin"], ctx["stats"])
    workout = generate_structured(
        kind="workout",
        model=get_settings().workout_model,
        prompt_name="workout",
        user_input=workout_input(ctx, available_time, recovery_reason),
        schema=Workout,
        validate=lambda w: validate_workout(w, available_time, ctx["max_hr"], recovery_reason is not None),
        athlete_id=athlete_id,
        journey_id=journey["id"],
        max_output_tokens=16000,
    )
    return {
        "date": ctx["day"],
        "workout": workout,
        "markdown": to_markdown(workout, ctx["ftp"]),
        "estimated_tss": estimate_tss(workout),
        "recovery_reason": recovery_reason,
    }
