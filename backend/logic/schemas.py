"""Output schemas the LLM must fill (OpenAI Structured Outputs).

Strict mode requires every field, so optional values are nullable instead of defaulted.
Whatever the model returns is checked again in logic.guardrails before it is used.
"""
from typing import Literal

from pydantic import BaseModel, Field

Phase = Literal["Base", "Build", "Peak", "Taper", "Recovery", "Race"]
WorkoutType = Literal[
    "Rest",
    "Recovery",
    "Endurance",
    "Tempo",
    "Sweet Spot",
    "Threshold",
    "VO2 Max",
    "Anaerobic",
    "FTP Test",  # placed and built by code (logic.ftp), never written by the model
    "Race",
]


class PlanWeek(BaseModel):
    week_number: int
    phase: Phase
    target_tss: int = Field(description="Total planned TSS for this week")
    focus: str = Field(description="One sentence on what this week trains")


class MacroPlan(BaseModel):
    summary: str = Field(description="Two sentences on the overall periodization")
    weeks: list[PlanWeek]


class PlanDay(BaseModel):
    day_number: int
    phase: Phase
    planned_workout_type: WorkoutType
    planned_duration_min: int
    planned_tss: int
    description: str = Field(description="One or two sentences, no markdown")


class PlanBlock(BaseModel):
    days: list[PlanDay]


# freeride: no power target (ERG off), for the all-out part of an FTP test only.
StepKind = Literal["warmup", "steady", "intervals", "ramp", "cooldown", "freeride"]


class WorkoutStep(BaseModel):
    """One block of the session. Power values are fractions of FTP (0.75 = 75 % FTP).

    warmup / ramp / cooldown: duration_s, power_low, power_high
    steady:                   duration_s, power
    intervals:                repeat, on_s, off_s, on_power, off_power
    Fields that do not apply to the kind are null.
    """

    kind: StepKind
    duration_s: int | None
    power: float | None
    power_low: float | None
    power_high: float | None
    repeat: int | None
    on_s: int | None
    off_s: int | None
    on_power: float | None
    off_power: float | None
    hr_cap_bpm: int | None = Field(description="Ease off if heart rate goes above this")
    instruction: str = Field(description="Short cue for the rider, no markdown")


class Workout(BaseModel):
    name: str = Field(description="Descriptive session name, e.g. 'VO2 Max Pyramids'")
    rationale: str = Field(description="One sentence: why this session today")
    steps: list[WorkoutStep]
    hr_guidance: str = Field(description="What to do if heart rate drifts above the caps")
