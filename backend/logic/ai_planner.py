"""Training plan generation in two stages.

1. Macro plan: one call returns the weekly structure (phase, target TSS) for the whole plan.
2. Daily detail: the days are filled in blocks of four weeks, each checked against the weekly
   targets. Blocks keep every answer well inside the output limit, even for long plans.
"""
import json
from datetime import date, timedelta

from core.config import get_settings
from core.dates import plan_week
from logic import ftp
from logic.ai import generate_structured
from logic.events import events_text, place_tests, plan_events
from logic.guardrails import build_peak_tss, validate_days, validate_macro
from logic.schemas import MacroPlan, PlanBlock, PlanDay, PlanWeek

BLOCK_DAYS = 28  # a multiple of 7, so no week is split across two calls
AFTER_RACE_EASY_DAYS = 3  # no hard session in the first days after a race


def block_ranges(total_days: int, offset: int = 0, first_day: int = 1) -> list[tuple[int, int]]:
    """Day ranges for the block calls, ending on Sundays (a short first week shortens the first
    block; a rebuilt plan starts on a Monday, `first_day`). A tail shorter than a week joins the
    block before it, so race day is never planned alone, without the long rides that lead up to it."""
    ranges = []
    first = first_day
    while first <= total_days:
        size = BLOCK_DAYS - (offset if first == 1 else 0)
        last = min(first + size - 1, total_days)
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
    "build": "BUILD FITNESS: raise fitness and FTP over the whole plan; no goal race at the end",
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
- Today: {current_date.isoformat()}, which is day {days_elapsed} of the plan
{weeks_text(total_days, start_date.weekday())}"""


def weeks_text(total_days: int, offset: int) -> str:
    """How the plan days fall into calendar weeks; only needed when the first week is short."""
    if offset == 0:
        return "- Plan weeks run Monday to Sunday."
    short = 7 - offset
    return (f"- Plan weeks run Monday to Sunday. Week 1 is short: only days 1-{min(short, total_days)}"
            " (the start day to Sunday); its target covers those days only. Week 2 is the first full week.")


def tests_text(test_days: list[int], offset: int = 0, first: int = 1, last: int | None = None) -> str:
    listed = [n for n in test_days if first <= n <= (last or n)]
    if not listed:
        return ""
    lines = "\n".join(
        f"- Day {n} (week {plan_week(n, offset)}): FTP Test, {ftp.TEST_DURATION_MIN} min,"
        f" {ftp.TEST_TSS} TSS. Day {n - 1} is Rest or Recovery."
        for n in listed
    )
    return f"FTP TESTS (fixed protocol, built by the app)\n{lines}\n\n"


def kept_weeks(days: list[PlanDay], offset: int) -> list[PlanWeek]:
    """The weeks of a plan that stay when it is rebuilt from a Monday on."""
    by_week: dict[int, list[PlanDay]] = {}
    for d in days:
        by_week.setdefault(plan_week(d.day_number, offset), []).append(d)
    return [
        PlanWeek(week_number=w, phase=max({d.phase for d in ds}, key=[d.phase for d in ds].count),
                 target_tss=sum(d.planned_tss for d in ds), focus="Already planned.")
        for w, ds in sorted(by_week.items())
    ]


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
    after_race: date | None = None,
    events: list[dict] = (),
    kept_days: list[PlanDay] = (),
) -> list[PlanDay]:
    """The plan's days. With `kept_days` (the days up to a Sunday) only the days after them are
    planned: a plan rebuilt after an event changed keeps what is behind the athlete."""
    settings = get_settings()
    total_days = (race_date - start_date).days + 1
    offset = start_date.weekday()
    first_day = len(kept_days) + 1
    easy_days = 0
    if after_race:
        # Recover first: no hard session for the first days, no FTP test that week (the race
        # itself says how fit the athlete is).
        easy_days = max(0, AFTER_RACE_EASY_DAYS - ((start_date - after_race).days - 1))
    ev = plan_events(list(events), start_date, total_days, goal_type, goal, easy_days)
    test_days = ftp.test_days(total_days, goal_type, offset)
    if after_race:
        test_days = [n for n in test_days if n > 7]
    last_test_day = total_days - 1 if goal_type == "race" else total_days
    test_days = [n for n in place_tests(test_days, ev, last_test_day) if n >= first_day]
    context = plan_context(
        goal, start_date, race_date, current_date, ftp_watts, weight, current_ctl, longest_ride_min,
        goal_type,
    )
    if after_race:
        context += (
            f"\n- The athlete raced on {after_race.isoformat()}, just before this plan:"
            + (f" days 1-{easy_days} are Rest, Recovery or Endurance." if easy_days else " recovered by now.")
        )

    weeks = plan_week(total_days, offset)
    fixed = kept_weeks(list(kept_days), offset)
    load_target = (
        f"LOAD TARGET\n- The peak build week reaches about {build_peak_tss(current_ctl, weeks)} TSS"
        " (fitness rising about one CTL point per week).\n\n"
        if goal_type == "build" and weeks >= 8 else ""
    )
    if fixed:
        done = "\n".join(f"- Week {w.week_number}: {w.phase}, {w.target_tss} TSS" for w in fixed)
        ask = (f"WEEKS ALREADY PLANNED (fixed; the plan is rebuilt because the athlete's events changed)\n"
               f"{done}\n\nReturn weeks {len(fixed) + 1} to {weeks} only.")
    else:
        ask = f"Return {weeks} weeks."
    macro = generate_structured(
        kind="plan_macro",
        model=settings.plan_model,
        prompt_name="plan_macro",
        user_input=(f"{context}\n\n{events_text(ev, start_date, macro=True)}{tests_text(test_days, offset)}"
                    f"{load_target}{ask}"),
        schema=MacroPlan,
        validate=lambda m: validate_macro(m, total_days, goal_type, current_ctl, offset, ev, fixed),
        athlete_id=athlete_id,
        journey_id=journey_id,
    )
    all_weeks = [*fixed, *macro.weeks]
    week_targets = {w.week_number: w.target_tss for w in all_weeks}
    weeks_text = "\n".join(
        f"- Week {w.week_number}: {w.phase}, {w.target_tss} TSS. {w.focus}" for w in all_weeks
    )

    days: list[PlanDay] = list(kept_days)
    for first, last in block_ranges(total_days, offset, first_day):
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
            + events_text(ev, start_date, first, last)
            + tests_text(test_days, offset, first, last)
            + f"FILL DAYS {first} TO {last}\n{calendar}"
        )
        block = generate_structured(
            kind="plan_block",
            model=settings.plan_model,
            prompt_name="plan_block",
            user_input=user_input,
            schema=PlanBlock,
            validate=lambda b, lo=first, hi=last: validate_days(
                b.days, lo, hi, total_days, week_targets, goal_type, test_days, offset, events=ev
            ),
            athlete_id=athlete_id,
            journey_id=journey_id,
        )
        days.extend(block.days)
    return days[len(kept_days):]
