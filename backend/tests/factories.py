from logic.schemas import MacroPlan, PlanDay, PlanWeek, Workout, WorkoutStep


def step(kind, **fields) -> WorkoutStep:
    base = dict(
        duration_s=None, power=None, power_low=None, power_high=None, repeat=None,
        on_s=None, off_s=None, on_power=None, off_power=None, hr_cap_bpm=None, instruction="Ride.",
    )
    return WorkoutStep(kind=kind, **{**base, **fields})


def sweet_spot_workout() -> Workout:
    """60 minutes: 10 warmup, 3 x 10 at 0.90 with 5 off, 5 cooldown."""
    return Workout(
        name="Sweet Spot 3x10",
        rationale="Builds sustainable power.",
        steps=[
            step("warmup", duration_s=600, power_low=0.5, power_high=0.75),
            step("intervals", repeat=3, on_s=600, off_s=300, on_power=0.9, off_power=0.55, hr_cap_bpm=170),
            step("cooldown", duration_s=300, power_low=0.6, power_high=0.4),
        ],
        hr_guidance="If heart rate passes the cap, ease off by 10 W.",
    )


def macro(tss: list[int], phases: list[str] | None = None) -> MacroPlan:
    phases = phases or ["Build"] * (len(tss) - 1) + ["Race"]
    return MacroPlan(
        summary="Plan.",
        weeks=[
            PlanWeek(week_number=i + 1, phase=p, target_tss=t, focus="Focus.")
            for i, (t, p) in enumerate(zip(tss, phases, strict=True))
        ],
    )


def week_of_days(first_day: int, tss_per_day: list[int]) -> list[PlanDay]:
    days = []
    for offset, tss in enumerate(tss_per_day):
        rest = tss == 0
        days.append(PlanDay(
            day_number=first_day + offset,
            phase="Build",
            planned_workout_type="Rest" if rest else "Endurance",
            planned_duration_min=0 if rest else max(20, round(tss / 0.9)),
            planned_tss=tss,
            description="Session.",
        ))
    return days
