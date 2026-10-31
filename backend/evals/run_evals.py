"""Runs the workout prompt against fixed athlete scenarios with the real model.

    cd backend && python -m evals.run_evals            # workout scenarios
    cd backend && python -m evals.run_evals --plan     # plus one 10-week plan

Needs OPENAI_API_KEY only. A scenario passes when the final workout satisfies the guardrails
and the scenario's expectations (forced recovery, sensible length). The report also shows how
often the first answer was already valid, which is the number to watch when a prompt changes.
Costs a few cents per run.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

for key, value in {
    "SUPABASE_URL": "http://unused", "SUPABASE_SERVICE_KEY": "unused",
    "STRAVA_CLIENT_ID": "0", "STRAVA_CLIENT_SECRET": "unused",
}.items():
    os.environ.setdefault(key, value)

import logic.ai as ai  # noqa: E402
from core.config import get_settings  # noqa: E402
from logic.ai import GenerationError, generate_structured  # noqa: E402
from logic.ai_planner import build_plan  # noqa: E402
from logic.coach import forced_recovery_reason, workout_input  # noqa: E402
from logic.guardrails import RECOVERY_MAX_POWER, validate_workout  # noqa: E402
from logic.schemas import Workout  # noqa: E402
from logic.workout_math import estimate_tss, max_power, total_duration_s  # noqa: E402

SCENARIOS = Path(__file__).with_name("scenarios.json")
attempt_log: list[dict] = []
ai._record = lambda **row: attempt_log.append(row)  # keep eval runs out of the database


def run_workout_scenario(s: dict) -> dict:
    ctx = {**s, "day": date.today(), "max_hr_is_estimate": False,
           "compliance": "- (no history in this scenario)"}
    reason = forced_recovery_reason(s["checkin"], s["stats"])
    start = len(attempt_log)
    started = time.monotonic()
    try:
        workout = generate_structured(
            kind="workout", model=get_settings().workout_model, prompt_name="workout",
            user_input=workout_input(ctx, s["available_time"], reason), schema=Workout,
            validate=lambda w: validate_workout(w, s["available_time"], s["max_hr"], reason is not None),
            user_id="eval",
        )
    except GenerationError as e:
        workout, failure = None, "; ".join(e.errors)
    attempts = attempt_log[start:]

    checks = []
    if workout:
        failure = None
        minutes = total_duration_s(workout) / 60
        if (reason is not None) != s["expect"]["recovery_only"]:
            checks.append("forced-recovery rule did not trigger as expected")
        if s["expect"]["recovery_only"] and max_power(workout) > RECOVERY_MAX_POWER:
            checks.append("recovery day with intensity")
        if minutes < s["expect"]["min_minutes"]:
            checks.append(f"only {minutes:.0f} min of {s['available_time']} used")
    return {
        "name": s["name"],
        "passed": workout is not None and not checks,
        "first_try": bool(attempts) and attempts[0]["ok"],
        "attempts": len(attempts),
        "seconds": round(time.monotonic() - started, 1),
        "tokens": sum((a.get("input_tokens") or 0) + (a.get("output_tokens") or 0) for a in attempts),
        "minutes": round(total_duration_s(workout) / 60) if workout else None,
        "tss": estimate_tss(workout) if workout else None,
        "problems": checks or ([failure] if failure else []),
    }


def run_plan_scenario() -> dict:
    start_date = date.today()
    start = len(attempt_log)
    started = time.monotonic()
    try:
        days = build_plan(
            user_id="eval", journey_id=None, goal="Gran Fondo, 160 km with 1800 m climbing",
            start_date=start_date, race_date=start_date + timedelta(days=69),
            current_date=start_date, ftp=250, weight=75, current_ctl=55,
        )
        problems = []
    except GenerationError as e:
        days, problems = [], e.errors
    attempts = attempt_log[start:]
    return {
        "name": "plan_10_weeks",
        "passed": len(days) == 70,
        "first_try": all(a["ok"] for a in attempts),
        "attempts": len(attempts),
        "seconds": round(time.monotonic() - started, 1),
        "tokens": sum((a.get("input_tokens") or 0) + (a.get("output_tokens") or 0) for a in attempts),
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="also generate a 10-week plan")
    args = parser.parse_args()

    results = [run_workout_scenario(s) for s in json.loads(SCENARIOS.read_text())]
    if args.plan:
        results.append(run_plan_scenario())

    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        extra = f" {r['minutes']} min, {r['tss']} TSS" if r.get("minutes") else ""
        print(f"{mark}  {r['name']:<36} attempts={r['attempts']} {r['seconds']}s"
              f" tokens={r['tokens']}{extra}")
        for p in r["problems"]:
            print(f"      - {p}")
    passed = sum(r["passed"] for r in results)
    first = sum(r["first_try"] for r in results)
    print(f"\n{passed}/{len(results)} passed, {first}/{len(results)} valid on the first answer")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
