"""Training plan generation in two stages.

1. Macro plan: one call returns the weekly structure (phase, target TSS) for the whole plan.
2. Daily detail: the days are filled in blocks of four weeks, each checked against the weekly
   targets. Blocks keep every answer well inside the output limit, even for long plans.
"""
import json
from datetime import date, timedelta

from core.config import get_settings
from logic.ai import generate_structured
from logic.guardrails import validate_days, validate_macro
from logic.schemas import MacroPlan, PlanBlock, PlanDay

BLOCK_DAYS = 28  # a multiple of 7, so no week is split across two calls


def athlete_level(ctl: float) -> str:
    if ctl >= 110:
        return "Elite / Pro"
    if ctl >= 85:
        return "Advanced / Competitive"
    if ctl >= 40:
        return "Intermediate"
    return "Recreational / Beginner"


def plan_context(goal, start_date, race_date, current_date, ftp, weight, ctl) -> str:
    total_days = (race_date - start_date).days + 1
    days_elapsed = max(0, (current_date - start_date).days + 1)
    return f"""ATHLETE
- Goal (athlete's own words): {json.dumps(goal)}
- FTP: {ftp} W, weight: {weight} kg
- Current CTL: {ctl:.0f} ({athlete_level(ctl)})

TIMELINE
- Plan start (day 1): {start_date.isoformat()} ({start_date.strftime('%A')})
- Race day (day {total_days}): {race_date.isoformat()} ({race_date.strftime('%A')})
- Today: {current_date.isoformat()}, which is day {days_elapsed} of the plan"""


def build_plan(
    *,
    user_id: str,
    journey_id: str,
    goal: str,
    start_date: date,
    race_date: date,
    current_date: date,
    ftp: int,
    weight: float,
    current_ctl: float,
) -> list[PlanDay]:
    settings = get_settings()
    total_days = (race_date - start_date).days + 1
    context = plan_context(goal, start_date, race_date, current_date, ftp, weight, current_ctl)

    macro = generate_structured(
        kind="plan_macro",
        model=settings.plan_model,
        prompt_name="plan_macro",
        user_input=f"{context}\n\nReturn {-(-total_days // 7)} weeks.",
        schema=MacroPlan,
        validate=lambda m: validate_macro(m, total_days),
        user_id=user_id,
        journey_id=journey_id,
    )
    week_targets = {w.week_number: w.target_tss for w in macro.weeks}
    weeks_text = "\n".join(
        f"- Week {w.week_number}: {w.phase}, {w.target_tss} TSS. {w.focus}" for w in macro.weeks
    )

    days: list[PlanDay] = []
    for first in range(1, total_days + 1, BLOCK_DAYS):
        last = min(first + BLOCK_DAYS - 1, total_days)
        calendar = "\n".join(
            f"- Day {n}: {(start_date + timedelta(days=n - 1)).strftime('%a %Y-%m-%d')}"
            for n in range(first, last + 1)
        )
        previous = "\n".join(
            f"- Day {d.day_number}: {d.planned_workout_type}, {d.planned_duration_min} min,"
            f" {d.planned_tss} TSS"
            for d in days[-3:]
        )
        user_input = (
            f"{context}\n\nWEEKLY STRUCTURE\n{macro.summary}\n{weeks_text}\n\n"
            + (f"LAST DAYS ALREADY PLANNED\n{previous}\n\n" if previous else "")
            + f"FILL DAYS {first} TO {last}\n{calendar}"
        )
        block = generate_structured(
            kind="plan_block",
            model=settings.plan_model,
            prompt_name="plan_block",
            user_input=user_input,
            schema=PlanBlock,
            validate=lambda b, lo=first, hi=last: validate_days(b.days, lo, hi, total_days, week_targets),
            user_id=user_id,
            journey_id=journey_id,
        )
        days.extend(block.days)
    return days
