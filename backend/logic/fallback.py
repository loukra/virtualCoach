"""Standard sessions built in code, for when the model cannot deliver a valid workout.

The athlete still gets something sensible to ride: the planned session type as a classic
interval set, fitted to the available time and checked by the same guardrails as the model's
workouts. The app labels it, so it is clear that the coach did not tailor it.
"""
from logic.schemas import Workout, WorkoutStep

ENDURANCE = 0.68
RECOVERY = 0.5
# Main sets per session type: (on seconds, off seconds, on power, most repeats). None: steady.
SETS: dict[str, tuple[int, int, float, int] | None] = {
    "Recovery": None,
    "Endurance": None,
    "Race": None,
    "Tempo": (12 * 60, 4 * 60, 0.83, 4),
    "Sweet Spot": (10 * 60, 5 * 60, 0.90, 4),
    "Threshold": (8 * 60, 4 * 60, 0.98, 5),
    "VO2 Max": (3 * 60, 3 * 60, 1.15, 6),
    "Anaerobic": (60, 4 * 60, 1.30, 8),
}


def _step(kind: str, instruction: str, **fields) -> WorkoutStep:
    base = dict(duration_s=None, power=None, power_low=None, power_high=None, repeat=None, on_s=None,
                off_s=None, on_power=None, off_power=None, hr_cap_bpm=None)
    return WorkoutStep(kind=kind, instruction=instruction, **{**base, **fields})


def standard_workout(session_type: str | None, available_min: int, recovery_only: bool) -> Workout:
    kind = "Recovery" if recovery_only else (session_type if session_type in SETS else "Endurance")
    total = available_min * 60
    warmup = 600 if total >= 40 * 60 else 300
    cooldown = 300
    main = total - warmup - cooldown
    easy = RECOVERY if kind == "Recovery" else ENDURANCE

    steps = [_step("warmup", "Easy start, build gradually.", duration_s=warmup, power_low=0.45,
                   power_high=min(0.7, easy + 0.05))]
    name = f"Standard {kind}"
    spec = SETS[kind]
    if spec:
        on, off, power, most = spec
        repeat = min(most, main // (on + off))
        if repeat:
            steps.append(_step("intervals", f"{repeat} x {on // 60 or 1} min hard, easy in between.",
                               repeat=repeat, on_s=on, off_s=off, on_power=power, off_power=0.55))
            main -= repeat * (on + off)
            name = f"Standard {kind} {repeat}x{on // 60}" if on >= 60 else name
    if main >= 60:
        steps.append(_step("steady", "Steady and comfortable." if kind != "Recovery" else "Very easy spin.",
                           duration_s=main, power=easy))
    steps.append(_step("cooldown", "Spin out easily.", duration_s=cooldown, power_low=easy, power_high=0.4))
    return Workout(
        name=name,
        rationale="A standard session for today's plan, built by the app: the coach could not"
                  " tailor a workout just now.",
        steps=steps,
        hr_guidance="Ride by feel: if your breathing gets ragged on the easy parts, ease off.",
    )
