"""Today's workout: gather the athlete's context, apply hard rules, let the LLM prescribe."""
import json
from datetime import date, timedelta

from core.config import get_settings
from core.dates import today
from core.db import get_db
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


def get_todays_context(user_id: str, journey: dict) -> dict:
    db = get_db()
    day = today()
    week_ago = (day - timedelta(days=7)).isoformat()

    profile = (
        db.table("profiles").select("ftp, weight_kg, max_heart_rate")
        .eq("id", user_id).maybe_single().execute()
    )
    profile = (profile.data if profile else None) or {}
    stats = (
        db.table("daily_metrics").select("ctl, atl, tsb")
        .eq("user_id", user_id).lte("date", day.isoformat())
        .order("date", desc=True).limit(1).execute()
    ).data
    plan = (
        db.table("master_plan").select("*")
        .eq("journey_id", journey["id"]).eq("date", day.isoformat()).execute()
    ).data
    checkin = (
        db.table("daily_checkins").select("feel_score, soreness_score, notes")
        .eq("user_id", user_id).eq("date", day.isoformat()).execute()
    ).data
    recent_plans = (
        db.table("master_plan")
        .select("date, planned_workout_type, planned_duration_min, planned_tss")
        .eq("journey_id", journey["id"]).gte("date", week_ago).lt("date", day.isoformat())
        .execute()
    ).data
    recent_rides = (
        db.table("activities").select("start_date_local, sport_type, tss, moving_time")
        .eq("user_id", user_id).gte("start_date_local", week_ago)
        .lt("start_date_local", day.isoformat()).execute()
    ).data

    start, race = date.fromisoformat(journey["start_date"]), date.fromisoformat(journey["race_date"])
    return {
        "day": day,
        "ftp": profile.get("ftp") or DEFAULT_FTP,
        "max_hr": profile.get("max_heart_rate") or DEFAULT_MAX_HR,
        "max_hr_is_estimate": not profile.get("max_heart_rate"),
        "stats": stats[0] if stats else None,
        "plan": plan[0] if plan else None,
        "checkin": checkin[0] if checkin else None,
        "goal": journey["name"],
        "days_until_race": (race - day).days,
        "current_week": (day - start).days // 7 + 1,
        "total_weeks": (race - start).days // 7 + 1,
        "compliance": format_compliance_history(recent_plans, recent_rides, day),
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


def generate_workout(user_id: str, journey: dict, available_time: int) -> dict:
    ctx = get_todays_context(user_id, journey)
    recovery_reason = forced_recovery_reason(ctx["checkin"], ctx["stats"])
    workout = generate_structured(
        kind="workout",
        model=get_settings().workout_model,
        prompt_name="workout",
        user_input=workout_input(ctx, available_time, recovery_reason),
        schema=Workout,
        validate=lambda w: validate_workout(w, available_time, ctx["max_hr"], recovery_reason is not None),
        user_id=user_id,
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
