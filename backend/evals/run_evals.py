"""Runs the coach prompts against fixed athlete scenarios with the real model.

    cd backend && python -m evals.run_evals                     # six workout scenarios, once each
    cd backend && python -m evals.run_evals --runs 3            # each scenario three times
    cd backend && python -m evals.run_evals --plan --judge      # plus a 10-week plan and a judge model

Needs OPENAI_API_KEY only. A workout passes when it satisfies the guardrails, the scenario's
expectations and the coaching checks in evals/checks.py (does it fit the planned session?);
with --judge, a second model must also rate plan fit, safety and clarity at least 3 of 5.
Models answer differently each time, so --runs repeats every scenario and the report counts
how often it passed. "Valid on the first answer" is the number to watch when a prompt changes.

Every run writes evals/reports/<time>.json (models, prompt versions, every workout and
verdict) and prints the difference to the previous report. Costs a few cents per scenario run;
the judge and the plan cost more.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

for key, value in {"STRAVA_CLIENT_ID": "0", "STRAVA_CLIENT_SECRET": "unused"}.items():
    os.environ.setdefault(key, value)

import logic.ai as ai  # noqa: E402
from core.config import get_settings  # noqa: E402
from evals.checks import plan_checks, workout_checks  # noqa: E402
from evals.judge import judge_workout, verdict_problems  # noqa: E402
from logic.ai import GenerationError, generate_structured, load_prompt  # noqa: E402
from logic.ai_planner import build_plan  # noqa: E402
from logic.coach import forced_recovery_reason, workout_input  # noqa: E402
from logic.guardrails import validate_workout  # noqa: E402
from logic.schemas import Workout  # noqa: E402
from logic.workout_math import estimate_tss, total_duration_s  # noqa: E402

SCENARIOS = Path(__file__).with_name("scenarios.json")
REPORT_DIR = Path(__file__).with_name("reports")
PLAN_CTL = 55
attempt_log: list[dict] = []


def _record(**row) -> None:
    attempt_log.append(row)  # eval runs stay out of the database


def _tokens(attempts: list[dict]) -> int:
    return sum((a.get("input_tokens") or 0) + (a.get("output_tokens") or 0) for a in attempts)


def run_workout_scenario(s: dict, judge_model: str | None = None) -> dict:
    ctx = {**s, "day": date.today(), "max_hr_is_estimate": False,
           "compliance": "- (no history in this scenario)"}
    reason = forced_recovery_reason(s["checkin"], s["stats"])
    coach_input = workout_input(ctx, s["available_time"], reason)
    start = len(attempt_log)
    started = time.monotonic()
    problems: list[str] = []
    try:
        workout = generate_structured(
            kind="workout", model=get_settings().workout_model, prompt_name="workout",
            user_input=coach_input, schema=Workout,
            validate=lambda w: validate_workout(w, s["available_time"], s["max_hr"], reason is not None),
            athlete_id=None,
        )
    except GenerationError as e:
        workout = None
        problems.append("; ".join(e.errors))
    attempts = attempt_log[start:]
    seconds = round(time.monotonic() - started, 1)

    verdict = None
    if workout:
        expect = s["expect"]
        if (reason is not None) != expect["recovery_only"]:
            problems.append("forced-recovery rule did not trigger as expected")
        minutes = total_duration_s(workout) / 60
        if minutes < expect["min_minutes"]:
            problems.append(f"only {minutes:.0f} min of {s['available_time']} used")
        problems += workout_checks(workout, s["plan"], s["available_time"], reason is not None)
        if judge_model:
            try:
                verdict = judge_workout(coach_input, workout, s["ftp"], judge_model)
                problems += verdict_problems(verdict)
            except GenerationError as e:
                problems.append(f"judge failed: {'; '.join(e.errors)}")

    return {
        "name": s["name"],
        "passed": workout is not None and not problems,
        "first_try": bool(attempts) and attempts[0]["ok"],
        "attempts": len(attempts),
        "seconds": seconds,
        "tokens": _tokens(attempts),
        "minutes": round(total_duration_s(workout) / 60) if workout else None,
        "tss": estimate_tss(workout) if workout else None,
        "problems": problems,
        "judge": verdict.model_dump() if verdict else None,
        "workout": workout.model_dump() if workout else None,
    }


def run_plan_scenario() -> dict:
    start_date = date.today()
    start = len(attempt_log)
    started = time.monotonic()
    try:
        days = build_plan(
            athlete_id=None, journey_id=None, goal="Gran Fondo, 160 km with 1800 m climbing",
            start_date=start_date, race_date=start_date + timedelta(days=69),
            current_date=start_date, ftp=250, weight=75, current_ctl=PLAN_CTL,
        )
        problems = [] if len(days) == 70 else [f"{len(days)} days instead of 70"]
        problems += plan_checks(days, PLAN_CTL)
    except GenerationError as e:
        days, problems = [], e.errors
    attempts = attempt_log[start:]
    return {
        "name": "plan_10_weeks",
        "passed": bool(days) and not problems,
        "first_try": bool(attempts) and all(a["ok"] for a in attempts),
        "attempts": len(attempts),
        "seconds": round(time.monotonic() - started, 1),
        "tokens": _tokens(attempts),
        "problems": problems,
        "plan": [d.model_dump() for d in days],
    }


def summarize(results: list[dict]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for r in results:
        s = summary.setdefault(r["name"], {"runs": 0, "passed": 0, "first_try": 0, "tokens": 0, "judge": []})
        s["runs"] += 1
        s["passed"] += r["passed"]
        s["first_try"] += r["first_try"]
        s["tokens"] += r["tokens"]
        if r.get("judge"):
            s["judge"].append(r["judge"])
    for s in summary.values():
        verdicts = s.pop("judge")
        if verdicts:
            s["judge_avg"] = {
                k: round(sum(v[k] for v in verdicts) / len(verdicts), 1)
                for k in ("plan_fit", "safety", "clarity")
            }
    return summary


def totals(summary: dict[str, dict]) -> tuple[int, int, int]:
    runs = sum(s["runs"] for s in summary.values())
    return sum(s["passed"] for s in summary.values()), sum(s["first_try"] for s in summary.values()), runs


def previous_report() -> dict | None:
    reports = sorted(REPORT_DIR.glob("*.json"))
    return json.loads(reports[-1].read_text()) if reports else None


def print_report(report: dict, before: dict | None) -> None:
    for r in report["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        extra = f" {r['minutes']} min, {r['tss']} TSS" if r.get("minutes") else ""
        judge = r.get("judge")
        scores = f" judge {judge['plan_fit']}/{judge['safety']}/{judge['clarity']}" if judge else ""
        print(f"{mark}  {r['name']:<36} attempts={r['attempts']} {r['seconds']}s"
              f" tokens={r['tokens']}{extra}{scores}")
        for p in r["problems"]:
            print(f"      - {p}")

    passed, first, runs = totals(report["summary"])
    print(f"\n{passed}/{runs} passed, {first}/{runs} valid on the first answer")
    if report["runs"] > 1:
        for name, s in report["summary"].items():
            print(f"  {name:<36} passed {s['passed']}/{s['runs']}, first try {s['first_try']}/{s['runs']}")

    if before:
        b_passed, b_first, b_runs = totals(before["summary"])
        print(f"Previous report ({before['created']}): {b_passed}/{b_runs} passed,"
              f" {b_first}/{b_runs} valid on the first answer")
        changed = [
            f"{name}: {old} -> {report['prompts'].get(name)}"
            for name, old in before["prompts"].items()
            if report["prompts"].get(name) not in (None, old)
        ]
        models = [f"{k}: {v} -> {report['models'].get(k)}" for k, v in before["models"].items()
                  if report["models"].get(k) not in (None, v)]
        if changed or models:
            print("Changed since then: " + ", ".join(changed + models))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="repeat every scenario this often")
    parser.add_argument("--plan", action="store_true", help="also generate a 10-week plan (once)")
    parser.add_argument("--judge", action="store_true", help="let a second model grade each workout")
    parser.add_argument("--min-pass", type=float, default=1.0,
                        help="share of runs that must pass for exit code 0 (default: all)")
    args = parser.parse_args()

    ai._record = _record
    settings = get_settings()
    judge_model = settings.judge_model if args.judge else None
    scenarios = json.loads(SCENARIOS.read_text())

    results = [run_workout_scenario(s, judge_model) for _ in range(args.runs) for s in scenarios]
    if args.plan:
        results.append(run_plan_scenario())

    prompt_names = ["workout"] + (["plan_macro", "plan_block"] if args.plan else []) + (
        ["eval_judge"] if args.judge else [])
    report = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "runs": args.runs,
        "models": {"workout": settings.workout_model, **({"plan": settings.plan_model} if args.plan else {}),
                   **({"judge": judge_model} if judge_model else {})},
        "prompts": {name: load_prompt(name)[1] for name in prompt_names},
        "summary": summarize(results),
        "results": results,
    }
    before = previous_report()
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print_report(report, before)
    print(f"Report: {path}")

    passed, _, runs = totals(report["summary"])
    return 0 if passed >= args.min_pass * runs else 1


if __name__ == "__main__":
    sys.exit(main())
