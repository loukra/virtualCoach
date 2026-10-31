"""Deterministic checks on everything the LLM returns.

Each check returns a list of violations in plain language. An empty list means the output
may be used; otherwise the violations go back to the model as a repair request
(logic.ai.generate_structured). The rules are deliberately coarse: they catch unsafe or
broken plans, not stylistic preferences.
"""
import math
from collections.abc import Collection

from logic.ftp import TEST_DURATION_MIN, TEST_TSS
from logic.schemas import MacroPlan, PlanDay, Workout
from logic.workout_math import max_power, step_segments, total_duration_s

MAX_DAY_MINUTES = 360
MAX_DAY_TSS = 450
# TSS per minute at IF 1.04: anything above cannot be ridden for the whole duration.
MAX_TSS_PER_MINUTE = 1.8
# TSS per minute at IF 0.39 (a very easy spin) and IF 0.57 (the easiest pace a race is ridden at).
MIN_TSS_PER_MINUTE = 0.25
MIN_RACE_TSS_PER_MINUTE = 0.55
EASY_TYPES = {"Rest", "Recovery"}
# Sustained efforts (>= 10 min) above this fraction of FTP are not realistic.
MAX_SUSTAINED_POWER = 1.05
# Upper bound for any target, incl. short sprints.
MAX_POWER = 2.0
RECOVERY_MAX_POWER = 0.75


def build_peak_tss(ctl: float, weeks: int, share: float = 1.0) -> int:
    """Peak weekly load of a fitness block: fitness (CTL) rising about one point per week.

    A week at a steady CTL carries about 7 × CTL TSS; `share` 0.8 gives the lower bound.
    """
    return round(7 * (ctl + share * weeks))


def validate_macro(
    macro: MacroPlan, total_days: int, goal_type: str = "race", ctl: float | None = None
) -> list[str]:
    errors: list[str] = []
    expected = math.ceil(total_days / 7)
    weeks = macro.weeks
    if [w.week_number for w in weeks] != list(range(1, expected + 1)):
        errors.append(f"Return exactly {expected} weeks numbered 1 to {expected}.")
        return errors

    for w in weeks:
        if not 0 <= w.target_tss <= 1500:
            errors.append(f"Week {w.week_number}: target_tss {w.target_tss} is outside 0-1500.")

    for prev, cur in zip(weeks, weeks[1:], strict=False):
        if cur.target_tss > prev.target_tss * 1.25 + 60:
            errors.append(
                f"Week {cur.week_number}: load jumps from {prev.target_tss} to {cur.target_tss} TSS;"
                " keep week-over-week increases at or below about 25 %."
            )

    if goal_type == "build":
        if any(w.phase in ("Race", "Taper") for w in weeks):
            errors.append("This plan builds fitness without a race: use no Race or Taper weeks.")
        least = build_peak_tss(ctl, expected, 0.8) if ctl is not None and expected >= 8 else 0
        if max(w.target_tss for w in weeks) < least:
            errors.append(
                f"The load never rises enough to raise fitness: let the build weeks grow to a peak"
                f" of about {build_peak_tss(ctl, expected)} TSS (at least {least})."
            )
    elif weeks[-1].phase not in ("Race", "Taper"):
        errors.append("The last week must be a Race or Taper week.")
    if goal_type == "race" and expected >= 4:
        build = [w.target_tss for w in weeks[-4:-1]]
        if weeks[-1].target_tss >= sum(build) / len(build):
            errors.append("Race week load must be below the average of the three weeks before it.")

    for start in range(0, len(weeks) - 4):
        window = weeks[start : start + 5]
        has_easier_week = any(
            w.phase in ("Recovery", "Taper", "Race") or w.target_tss < p.target_tss
            for p, w in zip(window, window[1:], strict=False)
        )
        if not has_easier_week:
            errors.append(
                f"Weeks {window[0].week_number}-{window[-1].week_number} build for five weeks"
                " without a recovery week; add one."
            )
    return errors


def validate_days(
    days: list[PlanDay],
    first_day: int,
    last_day: int,
    total_days: int,
    week_targets: dict[int, int],
    goal_type: str = "race",
    test_days: Collection[int] = (),
) -> list[str]:
    errors: list[str] = []
    if [d.day_number for d in days] != list(range(first_day, last_day + 1)):
        return [f"Return exactly the days {first_day} to {last_day}, one entry per day, in order."]
    by_number = {d.day_number: d for d in days}

    for d in days:
        prefix = f"Day {d.day_number}"
        if not 0 <= d.planned_duration_min <= MAX_DAY_MINUTES:
            errors.append(f"{prefix}: duration must be 0-{MAX_DAY_MINUTES} minutes.")
        if not 0 <= d.planned_tss <= MAX_DAY_TSS:
            errors.append(f"{prefix}: TSS must be 0-{MAX_DAY_TSS}.")
        if d.planned_workout_type == "Rest":
            if d.planned_duration_min or d.planned_tss:
                errors.append(f"{prefix}: a Rest day has duration 0 and TSS 0.")
        elif d.planned_duration_min < 20 or d.planned_tss <= 0:
            errors.append(f"{prefix}: a training day needs at least 20 minutes and TSS above 0.")
        floor = MIN_RACE_TSS_PER_MINUTE if d.planned_workout_type == "Race" else MIN_TSS_PER_MINUTE
        if d.planned_workout_type != "Rest" and d.planned_tss < d.planned_duration_min * floor:
            errors.append(
                f"{prefix}: {d.planned_tss} TSS in {d.planned_duration_min} minutes is too little for a"
                f" {d.planned_workout_type} day; plan at least {round(d.planned_duration_min * floor)} TSS."
            )
        if d.planned_tss > d.planned_duration_min * MAX_TSS_PER_MINUTE:
            errors.append(
                f"{prefix}: {d.planned_tss} TSS in {d.planned_duration_min} minutes is not physically"
                " possible; lower the TSS or extend the duration."
            )

    if goal_type == "race" and last_day == total_days and days[-1].planned_workout_type != "Race":
        errors.append(f"Day {total_days} is race day: planned_workout_type must be Race.")
    if goal_type == "build" and any(d.planned_workout_type == "Race" for d in days):
        errors.append("This plan has no race: use no Race days.")

    for d in days:
        if d.planned_workout_type == "FTP Test" and d.day_number not in test_days:
            errors.append(f"Day {d.day_number}: FTP Test only on the days listed under FTP TESTS.")
    for n in test_days:
        test = by_number.get(n)
        if test is None:
            continue
        if (test.planned_workout_type, test.planned_duration_min, test.planned_tss) != (
            "FTP Test", TEST_DURATION_MIN, TEST_TSS
        ):
            errors.append(
                f"Day {n}: FTP Test with {TEST_DURATION_MIN} minutes and {TEST_TSS} TSS, as listed."
            )
        before = by_number.get(n - 1)
        if before is not None and before.planned_workout_type not in EASY_TYPES:
            errors.append(f"Day {n - 1} is the day before an FTP test: make it Rest or Recovery.")

    by_week: dict[int, list[PlanDay]] = {}
    for d in days:
        by_week.setdefault((d.day_number - 1) // 7 + 1, []).append(d)
    for week, week_days in by_week.items():
        if len(week_days) < 7:
            continue  # partial week at the block edge or before race day
        if not any(d.planned_workout_type in EASY_TYPES for d in week_days):
            errors.append(f"Week {week}: include at least one Rest or Recovery day.")
        target = week_targets.get(week)
        actual = sum(d.planned_tss for d in week_days)
        if target and abs(actual - target) > target * 0.25 + 30:
            errors.append(
                f"Week {week}: days sum to {actual} TSS but the week target is {target};"
                " stay within about 25 %."
            )
    return errors


def validate_workout(
    workout: Workout,
    available_min: int,
    max_hr: int,
    recovery_only: bool,
    allow_freeride: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not workout.steps:
        return ["The workout has no steps."]
    if workout.steps[0].kind != "warmup":
        errors.append("Start with a warmup step.")
    if workout.steps[-1].kind != "cooldown":
        errors.append("End with a cooldown step.")

    required = {
        "warmup": ("duration_s", "power_low", "power_high"),
        "ramp": ("duration_s", "power_low", "power_high"),
        "cooldown": ("duration_s", "power_low", "power_high"),
        "steady": ("duration_s", "power"),
        "intervals": ("repeat", "on_s", "off_s", "on_power", "off_power"),
        "freeride": ("duration_s",),
    }
    for i, step in enumerate(workout.steps, start=1):
        if step.kind == "freeride" and not allow_freeride:
            errors.append(f"Step {i}: freeride is only used in FTP tests, which the app builds itself.")
            continue
        missing = [f for f in required[step.kind] if not getattr(step, f)]
        if missing:
            errors.append(f"Step {i} ({step.kind}): set {', '.join(missing)} to positive values.")
            continue
        for sec, lo, hi in step_segments(step):
            peak = max(lo, hi)
            if peak > MAX_POWER or min(lo, hi) < 0.3:
                errors.append(
                    f"Step {i}: power must be a fraction of FTP between 0.30 and {MAX_POWER}."
                    " Did you use watts instead of a fraction?"
                )
                break
            if sec >= 600 and peak > MAX_SUSTAINED_POWER:
                errors.append(
                    f"Step {i}: {sec // 60} minutes at {peak:.2f} FTP is not sustainable;"
                    f" efforts of 10+ minutes stay at or below {MAX_SUSTAINED_POWER}."
                )
                break
        if step.hr_cap_bpm is not None and not 90 <= step.hr_cap_bpm <= max_hr:
            errors.append(f"Step {i}: HR cap must be between 90 and the athlete's max of {max_hr} bpm.")

    if errors:
        return errors

    minutes = total_duration_s(workout) / 60
    if minutes > available_min:
        errors.append(
            f"The steps add up to {minutes:.0f} minutes but the athlete only has {available_min};"
            " shorten them."
        )
    if minutes < 15:
        errors.append("The workout must be at least 15 minutes long.")
    if recovery_only and max_power(workout) > RECOVERY_MAX_POWER:
        errors.append(
            f"Today is a forced recovery day: keep every target at or below {RECOVERY_MAX_POWER} FTP."
        )
    return errors
