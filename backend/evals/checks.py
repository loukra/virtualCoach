"""Coaching checks for the evals: does the answer fit the plan, not only the safety rules?

The guardrails (logic/guardrails.py) decide whether an answer may be used at all. These checks
go further and are only run in the evals, because they judge coaching intent, where a single
miss is a signal to look at the prompt, not a reason to reject a workout in the app.
Each function returns a list of problems in plain language; an empty list means it passed.
"""
from core.dates import plan_week
from logic.guardrails import RECOVERY_MAX_POWER, build_peak_tss
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


def plan_checks(
    days: list[PlanDay], current_ctl: float, goal_type: str = "race", test_days: list[int] = (),
    offset: int = 0,
) -> list[str]:
    """Shape of a whole plan: sensible start, a build, not too many hard days; a race plan
    tapers, a fitness plan keeps its FTP tests and enough quality work to raise FTP."""
    problems: list[str] = []
    tests = [d.day_number for d in days if d.planned_workout_type == "FTP Test"]
    if tests != list(test_days):
        problems.append(f"FTP tests on days {tests}, expected {list(test_days)}")
    by_week: dict[int, list[PlanDay]] = {}
    for number, d in enumerate(days, start=1):  # days are in order from day 1
        by_week.setdefault(plan_week(number, offset), []).append(d)
    weeks = list(by_week.values())  # calendar weeks; the first and last may be short
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
    for number, week in enumerate(full_weeks, start=1):
        hard = sum(d.planned_workout_type in HARD_TYPES for d in week)
        if hard > 3:
            problems.append(f"week {number} has {hard} hard days")
    if goal_type == "build":
        return problems + build_checks(full_weeks, current_ctl)

    race_week = sum(d.planned_tss for d in days[-8:-1])  # the seven days before race day
    if race_week > 0.75 * max(weekly_tss):
        problems.append(
            f"no taper: the week before the race has {race_week} TSS, the peak week {max(weekly_tss)}"
        )
    # Nobody should race far longer than they ever trained in the build-up.
    race = days[-1]
    if race.planned_workout_type == "Race" and race.planned_duration_min >= 120:
        build_up = days[-36:-8]  # the four weeks before race week
        longest = max((d.planned_duration_min for d in build_up), default=0)
        if longest < race.planned_duration_min * 2 / 3:
            problems.append(
                f"longest ride in the build-up is {longest} min, the race {race.planned_duration_min} min"
            )
    return problems


def build_checks(full_weeks: list[list[PlanDay]], current_ctl: float) -> list[str]:
    """A fitness block without a race: FTP only rises with regular quality work and growing load."""
    problems = []
    weekly = [sum(d.planned_tss for d in w) for w in full_weeks]
    least = build_peak_tss(current_ctl, len(full_weeks), 0.8)
    if len(weekly) >= 8 and max(weekly) < least:
        problems.append(f"peak week {max(weekly)} TSS, fitness only grows from about {least}")
    if any(d.planned_workout_type == "Race" for w in full_weeks for d in w):
        problems.append("a fitness plan contains a Race day")
    build_weeks = [w for w in full_weeks if sum(d.phase == "Build" for d in w) >= 4]
    thin = [w for w in build_weeks if sum(d.planned_workout_type in HARD_TYPES for d in w) < 2]
    if build_weeks and len(thin) > len(build_weeks) / 2:
        problems.append(f"{len(thin)} of {len(build_weeks)} build weeks have fewer than two quality sessions")
    if not build_weeks:
        problems.append("no Build weeks")
    return problems
