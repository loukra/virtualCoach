"""Training plan generation in two stages.

1. Macro plan: one call returns the weekly structure (phase, target TSS) for the whole plan.
2. Daily detail: the days are filled in blocks of four weeks, each checked against the weekly
   targets. Blocks keep every answer well inside the output limit, even for long plans.
"""
import json
from datetime import date, timedelta

from core.config import get_settings
from logic import ftp
from logic.ai import generate_structured
from logic.guardrails import build_peak_tss, validate_days, validate_macro
from logic.schemas import MacroPlan, PlanBlock, PlanDay

BLOCK_DAYS = 28  # a multiple of 7, so no week is split across two calls


def block_ranges(total_days: int) -> list[tuple[int, int]]:
    """Day ranges for the block calls. A tail shorter than a week joins the block before it, so
    race day is never planned alone, without the long rides that lead up to it."""
    ranges = []
    first = 1
    while first <= total_days:
        last = min(first + BLOCK_DAYS - 1, total_days)
        if total_days - last < 7:
            last = total_days
        ranges.append((first, last))
        first = last + 1
    return ranges


def athlete_level(ctl: float) -> str:
    if ctl >= 110:
        return "Elite / Pro"
    if ctl >= 85:
        return "Advanced / Competitive"
    if ctl >= 40:
        return "Intermediate"
    return "Recreational / Beginner"


GOAL_TYPES = {
    "race": "RACE: prepare for the event on the last day of the plan",
    "build": "BUILD FITNESS: raise fitness and FTP over the whole plan; there is no race",
}


def plan_context(
    goal, start_date, race_date, current_date, ftp_watts, weight, ctl, longest_ride_min=None,
    goal_type="race",
) -> str:
    total_days = (race_date - start_date).days + 1
    days_elapsed = max(0, (current_date - start_date).days + 1)
    longest = (
        f"{longest_ride_min} minutes" if longest_ride_min else "unknown (no ride history)"
    )
    last_day = "Race day" if goal_type == "race" else "Last day of the plan"
    return f"""ATHLETE
- Plan type: {GOAL_TYPES[goal_type]}
- Goal (athlete's own words): {json.dumps(goal)}
- FTP: {ftp_watts} W, weight: {weight} kg
- Current CTL: {ctl:.0f} ({athlete_level(ctl)})
- Longest ride in the last 90 days: {longest}

TIMELINE
- Plan start (day 1): {start_date.isoformat()} ({start_date.strftime('%A')})
- {last_day} (day {total_days}): {race_date.isoformat()} ({race_date.strftime('%A')})
- Today: {current_date.isoformat()}, which is day {days_elapsed} of the plan"""


def tests_text(test_days: list[int], first: int = 1, last: int | None = None) -> str:
    listed = [n for n in test_days if first <= n <= (last or n)]
    if not listed:
        return ""
    lines = "\n".join(
        f"- Day {n} (week {(n - 1) // 7 + 1}): FTP Test, {ftp.TEST_DURATION_MIN} min,"
        f" {ftp.TEST_TSS} TSS. Day {n - 1} is Rest or Recovery."
        for n in listed
    )
    return f"FTP TESTS (fixed protocol, built by the app)\n{lines}\n\n"


def build_plan(
    *,
    athlete_id: int | None,
    journey_id: str | None,
    goal: str,
    start_date: date,
    race_date: date,
    current_date: date,
    ftp_watts: int,
    weight: float,
    current_ctl: float,
    longest_ride_min: int | None = None,
    goal_type: str = "race",
) -> list[PlanDay]:
    settings = get_settings()
    total_days = (race_date - start_date).days + 1
    test_days = ftp.test_days(total_days, goal_type)
    context = plan_context(
        goal, start_date, race_date, current_date, ftp_watts, weight, current_ctl, longest_ride_min,
        goal_type,
    )

    weeks = -(-total_days // 7)
    load_target = (
        f"LOAD TARGET\n- The peak build week reaches about {build_peak_tss(current_ctl, weeks)} TSS"
        " (fitness rising about one CTL point per week).\n\n"
        if goal_type == "build" and weeks >= 8 else ""
    )
    macro = generate_structured(
        kind="plan_macro",
        model=settings.plan_model,
        prompt_name="plan_macro",
        user_input=f"{context}\n\n{tests_text(test_days)}{load_target}Return {weeks} weeks.",
        schema=MacroPlan,
        validate=lambda m: validate_macro(m, total_days, goal_type, current_ctl),
        athlete_id=athlete_id,
        journey_id=journey_id,
    )
    week_targets = {w.week_number: w.target_tss for w in macro.weeks}
    weeks_text = "\n".join(
        f"- Week {w.week_number}: {w.phase}, {w.target_tss} TSS. {w.focus}" for w in macro.weeks
    )

    days: list[PlanDay] = []
    for first, last in block_ranges(total_days):
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
            + tests_text(test_days, first, last)
            + f"FILL DAYS {first} TO {last}\n{calendar}"
        )
        block = generate_structured(
            kind="plan_block",
            model=settings.plan_model,
            prompt_name="plan_block",
            user_input=user_input,
            schema=PlanBlock,
            validate=lambda b, lo=first, hi=last: validate_days(
                b.days, lo, hi, total_days, week_targets, goal_type, test_days
            ),
            athlete_id=athlete_id,
            journey_id=journey_id,
        )
        days.extend(block.days)
    return days
