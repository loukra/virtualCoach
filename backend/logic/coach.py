"""Today's workout: gather the athlete's context, apply hard rules, let the LLM prescribe."""
import json
from datetime import date, timedelta

from core import db
from core.config import get_settings
from core.dates import today
from logic import ftp, sessions
from logic.ai import generate_structured
from logic.guardrails import validate_workout
from logic.schemas import Workout
from logic.sessions import forced_recovery_reason  # noqa: F401 (part of this module's interface)
from logic.workout_math import estimate_tss, to_markdown

DEFAULT_FTP = 200
DEFAULT_MAX_HR = 190


class NotEnoughTime(Exception):
    """The chosen session cannot be shortened (the FTP test) and does not fit the time."""


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


def format_week(week: list[dict], day: date) -> str:
    """This plan week's sessions and what became of them, one line each."""
    lines = []
    for row in week:
        kind = row["planned_workout_type"]
        when = date.fromisoformat(row["date"]).strftime("%a %d %b")
        if kind == "Rest":
            lines.append(f"- {when}: rest day")
            continue
        if row["status"] == "done":
            ridden = (row["done_moving_time"] or 0) // 60
            state = f"done on {row['done_on']} ({ridden} min, {row['done_tss']} TSS)"
        else:
            state = "open" if row["date"] >= day.isoformat() else "open, its day has passed"
        lines.append(f"- {when}: {kind} {row['planned_duration_min']} min, {row['planned_tss']} TSS: {state}")
    return "\n".join(lines)


def format_checkins(checkins: list[dict]) -> str:
    if not checkins:
        return "- no check-ins this week"
    lines = []
    for c in checkins:
        motivation = f", motivation {c['motivation_score']}/5" if c.get("motivation_score") else ""
        note = f", note: {json.dumps(c['notes'])}" if c.get("notes") else ""
        scores = f"energy {c['feel_score']}/5, legs {c['soreness_score']}/5"
        lines.append(f"- {c['date']}: {scores}{motivation}{note}")
    return "\n".join(lines)


def get_context(athlete_id: int, journey: dict, session: dict | None) -> dict:
    current = today()
    week_ago = (current - timedelta(days=7)).isoformat()
    profile = db.query_one("SELECT ftp, max_heart_rate FROM athletes WHERE id = ?", [athlete_id]) or {}
    ready = sessions.readiness(athlete_id, current)
    week, _, _, week_no = sessions.week_sessions(journey, current)
    recent_plans = db.query(
        "SELECT date, planned_workout_type, planned_duration_min, planned_tss FROM master_plan"
        " WHERE journey_id = ? AND date >= ? AND date < ?",
        [journey["id"], week_ago, current.isoformat()],
    )
    recent_rides = db.query(
        "SELECT start_date_local, sport_type, tss, moving_time FROM activities"
        " WHERE athlete_id = ? AND start_date_local >= ? AND start_date_local < ?",
        [athlete_id, week_ago, current.isoformat()],
    )
    start, end = date.fromisoformat(journey["start_date"]), date.fromisoformat(journey["race_date"])
    return {
        "day": current,
        "ftp": profile.get("ftp") or DEFAULT_FTP,
        "max_hr": profile.get("max_heart_rate") or DEFAULT_MAX_HR,
        "max_hr_is_estimate": not profile.get("max_heart_rate"),
        "stats": ready["stats"],
        "plan": session,
        "checkin": ready["checkin"],
        "ready": ready,
        "goal": journey["name"],
        "goal_type": journey.get("goal_type") or "race",
        "days_until_race": (end - current).days,
        "current_week": week_no,
        "total_weeks": sessions.week_number(start, end),
        "compliance": format_compliance_history(recent_plans, recent_rides, current),
        "week": format_week(week, current),
        "checkins": format_checkins(ready["checkins"]),
        "signals": [s["message"] for s in ready["signals"]],
    }


def workout_input(ctx: dict, available_time: int, recovery_reason: str | None) -> str:
    stats, plan, checkin = ctx["stats"], ctx["plan"], ctx["checkin"]
    fitness = (
        f"CTL {stats['ctl']:.0f}, ATL {stats['atl']:.0f}, TSB {stats['tsb']:.0f}"
        if stats else "no training history yet"
    )
    moved = (
        f" (planned for {date.fromisoformat(plan['date']).strftime('%A')}, ridden today instead)"
        if plan and plan.get("date") and plan["date"] != ctx["day"].isoformat() else ""
    )
    planned = (
        f"{plan['planned_workout_type']}, {plan['planned_duration_min']} min,"
        f" {plan['planned_tss']} TSS{moved}. {plan['description']}"
        if plan else "No session of the plan today; the athlete still wants to ride."
    )
    feel = (
        f"mood {checkin['feel_score']}/5, legs {checkin['soreness_score']}/5"
        + (f", motivation {checkin['motivation_score']}/5" if checkin.get("motivation_score") else "")
        + (f", note: {json.dumps(checkin['notes'])}" if checkin.get("notes") else "")
        if checkin else "no check-in today"
    )
    hr_note = " (estimated, athlete has not set it)" if ctx["max_hr_is_estimate"] else ""
    recovery = (
        f"\n\nFORCED RECOVERY: {recovery_reason.rstrip('.')}. Keep every target at or below 0.75 FTP."
        if recovery_reason else ""
    )
    timeline = (
        f"{ctx['days_until_race']} days until race, week {ctx['current_week']} of {ctx['total_weeks']}"
        if ctx.get("goal_type", "race") == "race"
        else f"building fitness, no race; week {ctx['current_week']} of {ctx['total_weeks']}"
    )
    week = f"\n\nTHIS PLAN WEEK (sessions can move between days)\n{ctx['week']}" if ctx.get("week") else ""
    checkins = f"\n\nCHECK-INS, LAST SEVEN DAYS\n{ctx['checkins']}" if ctx.get("checkins") else ""
    signals = (
        "\n\nWARNING SIGNS\n" + "\n".join(f"- {m}" for m in ctx["signals"]) if ctx.get("signals") else ""
    )
    return f"""GOAL
- Aim (athlete's own words): {json.dumps(ctx['goal'])}
- {timeline}

ATHLETE
- FTP {ctx['ftp']} W, max HR {ctx['max_hr']} bpm{hr_note}
- Fitness: {fitness}
- Heart-rate zones:
{hr_zones(ctx['max_hr'])}

TODAY ({ctx['day'].isoformat()})
- Session: {planned}
- Check-in: {feel}
- Available time: {available_time} minutes

LAST SEVEN DAYS (plan vs actual)
{ctx['compliance']}{week}{checkins}{signals}{recovery}"""


def generate_workout(athlete_id: int, journey: dict, available_time: int, session: dict | None) -> dict:
    """A workout for `session` (a master_plan row, or None for a ride outside the plan)."""
    ctx = get_context(athlete_id, journey, session)
    recovery_reason = ctx["ready"]["recovery"]
    is_test = session is not None and session["planned_workout_type"] == "FTP Test"
    if is_test and not recovery_reason:
        if available_time < ftp.TEST_DURATION_MIN:
            raise NotEnoughTime(f"The FTP test takes {ftp.TEST_DURATION_MIN} minutes.")
        workout = ftp.test_workout()
    else:
        workout = generate_structured(
            kind="workout",
            model=get_settings().workout_model,
            prompt_name="workout",
            user_input=workout_input(ctx, available_time, recovery_reason),
            schema=Workout,
            validate=lambda w: validate_workout(
                w, available_time, ctx["max_hr"], recovery_reason is not None
            ),
            athlete_id=athlete_id,
            journey_id=journey["id"],
            max_output_tokens=16000,
        )
    # A recovery spin in place of a quality session does not complete that session.
    counts_for_session = session is not None and not (
        recovery_reason and session["planned_workout_type"] not in sessions.EASY_TYPES
    )
    return {
        "date": ctx["day"],
        "workout": workout,
        "markdown": to_markdown(workout, ctx["ftp"]),
        "estimated_tss": estimate_tss(workout),
        "recovery_reason": recovery_reason,
        "plan_id": session["id"] if counts_for_session else None,
    }
