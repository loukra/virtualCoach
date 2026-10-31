"""Coaching checks for the evals: does the answer fit the plan, not only the safety rules?

The guardrails (logic/guardrails.py) decide whether an answer may be used at all. These checks
go further and are only run in the evals, because they judge coaching intent, where a single
miss is a signal to look at the prompt, not a reason to reject a workout in the app.
Each function returns a list of problems in plain language; an empty list means it passed.
"""
from logic.guardrails import RECOVERY_MAX_POWER
from logic.schemas import PlanDay, Workout
from logic.workout_math import estimate_tss, step_segments

# Power of the main set (fraction of FTP) that each planned session type calls for. Wide on
# purpose: a coach may pitch a threshold day at 0.95 or 1.05, but not at 0.75.
TYPE_INTENSITY = {
    "Recovery": (0.40, 0.70),
    "Endurance": (0.55, 0.82),
    "Tempo": (0.75, 0.93),
    "Sweet Spot": (0.83, 0.98),
    "Threshold": (0.93, 1.07),
    "VO2 Max": (1.05, 1.35),
    "Anaerobic": (1.20, 2.00),
}
# Minimum minutes inside that range, so one short block does not count as the session.
MIN_WORK_MIN = {"Tempo": 15, "Sweet Spot": 15, "Threshold": 12, "VO2 Max": 6, "Anaerobic": 2}
# Shortest segment that counts as work; anaerobic efforts are short by nature.
MIN_SEGMENT_S = {"Anaerobic": 15}
HARD_TYPES = {"Sweet Spot", "Threshold", "VO2 Max", "Anaerobic"}


def main_set(workout: Workout, workout_type: str) -> list[tuple[int, float]]:
    """(seconds, power) of the work segments: everything between warmup and cooldown."""
    shortest = MIN_SEGMENT_S.get(workout_type, 60)
    return [
        (sec, max(lo, hi))
        for step in workout.steps
        if step.kind not in ("warmup", "cooldown")
        for sec, lo, hi in step_segments(step)
        if sec >= shortest
    ]


def workout_checks(
    workout: Workout, plan: dict | None, available_min: int, forced_recovery: bool
) -> list[str]:
    problems: list[str] = []
    if forced_recovery:
        peak = max((p for _, p in main_set(workout, "Recovery")), default=0.0)
        if peak > RECOVERY_MAX_POWER:
            problems.append(f"forced recovery day, but the main set reaches {peak:.2f} FTP")
        return problems
    if not plan or plan["planned_workout_type"] in ("Rest", "Race"):
        return problems

    workout_type = plan["planned_workout_type"]
    low, high = TYPE_INTENSITY[workout_type]
    work = main_set(workout, workout_type)
    peak = max((p for _, p in work), default=0.0)
    if not low <= peak <= high:
        problems.append(
            f"planned {workout_type} ({low:.2f}-{high:.2f} FTP) but the main set peaks at {peak:.2f}"
        )
    in_range_min = sum(sec for sec, p in work if low <= p <= high) / 60
    needed = MIN_WORK_MIN.get(workout_type, 0)
    if in_range_min < needed:
        problems.append(f"only {in_range_min:.0f} min at {workout_type} intensity, want at least {needed}")

    # The planned load, scaled down when the athlete has less time than planned.
    planned_min = plan["planned_duration_min"] or available_min
    expected_tss = plan["planned_tss"] * min(1.0, available_min / planned_min)
    tss = estimate_tss(workout)
    if not 0.6 * expected_tss <= tss <= 1.4 * expected_tss:
        problems.append(f"{tss} TSS where about {expected_tss:.0f} fits the plan and the time")
    return problems


def plan_checks(days: list[PlanDay], current_ctl: float) -> list[str]:
    """Shape of a whole plan: sensible start, a build, a taper, not too many hard days."""
    problems: list[str] = []
    weeks = [days[i : i + 7] for i in range(0, len(days), 7)]
    full_weeks = [w for w in weeks if len(w) == 7]
    weekly_tss = [sum(d.planned_tss for d in w) for w in full_weeks]
    if len(weekly_tss) < 3:
        return problems

    # A first week far from the current load either wastes fitness or risks overload.
    usual = current_ctl * 7
    if usual and not 0.6 * usual <= weekly_tss[0] <= 1.4 * usual:
        problems.append(f"first week has {weekly_tss[0]} TSS, current fitness suggests about {usual:.0f}")
    if max(weekly_tss) < 1.1 * weekly_tss[0]:
        problems.append("load never builds above the first week")
    last_seven = sum(d.planned_tss for d in days[-7:])
    if last_seven > 0.75 * max(weekly_tss):
        problems.append(f"no taper: the last 7 days have {last_seven} TSS, the peak week {max(weekly_tss)}")
    for number, week in enumerate(full_weeks, start=1):
        hard = sum(d.planned_workout_type in HARD_TYPES for d in week)
        if hard > 3:
            problems.append(f"week {number} has {hard} hard days")
    return problems
