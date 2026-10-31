"""A second model grades workouts on what code cannot check: is it good coaching?

Only used in the evals (`run_evals --judge`), never in the app: a judge's opinion is useful to
compare prompt versions, but not reliable enough to accept or reject a workout for an athlete.
"""
from pydantic import BaseModel, Field

from logic.ai import generate_structured
from logic.schemas import Workout
from logic.workout_math import to_markdown

PASS_SCORE = 3  # every criterion must reach this


class Verdict(BaseModel):
    plan_fit: int = Field(description="1-5")
    safety: int = Field(description="1-5")
    clarity: int = Field(description="1-5")
    issues: list[str]


def _validate(v: Verdict) -> list[str]:
    scores = {"plan_fit": v.plan_fit, "safety": v.safety, "clarity": v.clarity}
    return [f"{name} must be an integer from 1 to 5." for name, s in scores.items() if not 1 <= s <= 5]


def judge_workout(coach_input: str, workout: Workout, ftp: int, model: str) -> Verdict:
    return generate_structured(
        kind="eval_judge",
        model=model,
        prompt_name="eval_judge",
        user_input=f"WHAT THE COACH WAS GIVEN\n{coach_input}\n\nTHE WORKOUT\n{to_markdown(workout, ftp)}",
        schema=Verdict,
        validate=_validate,
        athlete_id=None,
    )


def verdict_problems(v: Verdict) -> list[str]:
    low = [f"{name} {score}/5" for name, score in
           (("plan_fit", v.plan_fit), ("safety", v.safety), ("clarity", v.clarity)) if score < PASS_SCORE]
    return [f"judge: {', '.join(low)}: {'; '.join(v.issues) or 'no reason given'}"] if low else []
