"""The eval checks and runner, offline: a wrong check would make every real eval run misleading."""
import json
import sys

import pytest

import logic.ai as ai
from evals import run_evals
from evals.checks import plan_checks, workout_checks
from evals.judge import Verdict
from logic.schemas import PlanDay
from tests.factories import sweet_spot_workout
from tests.test_ai import FakeResponses


def plan(workout_type, minutes=60, tss=60):
    return {"planned_workout_type": workout_type, "planned_duration_min": minutes, "planned_tss": tss,
            "description": "Session."}


def test_sweet_spot_workout_fits_a_sweet_spot_day():
    assert workout_checks(sweet_spot_workout(), plan("Sweet Spot"), 60, forced_recovery=False) == []


@pytest.mark.parametrize("workout_type", ["Threshold", "VO2 Max", "Endurance", "Recovery"])
def test_sweet_spot_workout_does_not_fit_other_days(workout_type):
    problems = workout_checks(sweet_spot_workout(), plan(workout_type), 60, forced_recovery=False)
    assert any(f"planned {workout_type}" in p for p in problems)


def test_load_is_compared_with_the_plan_scaled_to_the_time():
    # 57 TSS in 60 minutes: right for a 60 TSS hour, far too little for 150 TSS in 2 hours ridden in 1 hour.
    assert workout_checks(sweet_spot_workout(), plan("Sweet Spot", 120, 120), 60, False) == []
    problems = workout_checks(sweet_spot_workout(), plan("Sweet Spot", 60, 150), 60, False)
    assert any("TSS" in p for p in problems)


def test_forced_recovery_only_accepts_easy_work():
    problems = workout_checks(sweet_spot_workout(), plan("Sweet Spot"), 60, forced_recovery=True)
    assert problems == ["forced recovery day, but the main set reaches 0.90 FTP"]


def week(tss_per_day, hard=0):
    types = ["Threshold"] * hard + ["Endurance"] * (6 - hard) + ["Rest"]
    return [
        PlanDay(day_number=0, phase="Build", planned_workout_type=t,
                planned_duration_min=0 if t == "Rest" else 60, planned_tss=0 if t == "Rest" else tss_per_day,
                description="Session.")
        for t in types
    ]


def test_building_plan_with_taper_passes():
    days = week(60) + week(70) + week(80) + week(40)  # first week 360 TSS at CTL 55 (385 usual)
    assert plan_checks(days, current_ctl=55) == []


def test_plan_shape_problems_are_named():
    flat = week(60) * 4
    problems = plan_checks(flat, current_ctl=55)
    assert "load never builds above the first week" in problems
    assert any(p.startswith("no taper") for p in problems)
    assert any("4 hard days" in p for p in plan_checks(week(60) + week(70, hard=4) + week(30), 55))


SCENARIO = {
    "name": "sweet_spot_day", "available_time": 60, "ftp": 250, "max_hr": 188,
    "stats": {"ctl": 60, "atl": 55, "tsb": 5}, "plan": plan("Sweet Spot"),
    "checkin": {"feel_score": 4, "soreness_score": 4, "notes": None}, "goal": "Gran Fondo",
    "days_until_race": 40, "current_week": 5, "total_weeks": 12,
    "expect": {"recovery_only": False, "min_minutes": 45},
}


@pytest.fixture
def fake_models(monkeypatch, tmp_path):
    """Queues answers for coach and judge; keeps reports in a temporary folder."""
    run_evals.attempt_log.clear()
    monkeypatch.setattr(ai, "_record", run_evals._record)
    monkeypatch.setattr(run_evals, "REPORT_DIR", tmp_path / "reports")

    def install(outputs):
        responses = FakeResponses(outputs)
        monkeypatch.setattr(ai, "get_openai", lambda: type("Client", (), {"responses": responses})())
        return responses

    return install


def test_scenario_runs_coach_then_judge(fake_models):
    responses = fake_models([sweet_spot_workout(), Verdict(plan_fit=5, safety=5, clarity=4, issues=[])])
    result = run_evals.run_workout_scenario(SCENARIO, judge_model="judge-model")
    assert result["passed"] and result["first_try"] and result["judge"]["clarity"] == 4
    assert [c["model"] for c in responses.calls][1] == "judge-model"
    assert "225 W" in responses.calls[1]["input"][0]["content"]  # the judge sees watts, not fractions


def test_low_judge_score_fails_the_scenario(fake_models):
    low = Verdict(plan_fit=2, safety=4, clarity=4, issues=["Ignores the plan."])
    fake_models([sweet_spot_workout(), low])
    result = run_evals.run_workout_scenario(SCENARIO, judge_model="judge-model")
    assert not result["passed"]
    assert result["problems"] == ["judge: plan_fit 2/5: Ignores the plan."]


def test_runner_repeats_scenarios_and_writes_a_report(fake_models, monkeypatch):
    fake_models([sweet_spot_workout()] * 2)
    scenarios = run_evals.REPORT_DIR.parent / "scenarios.json"
    scenarios.write_text(json.dumps([SCENARIO]))
    monkeypatch.setattr(run_evals, "SCENARIOS", scenarios)
    monkeypatch.setattr(sys, "argv", ["run_evals", "--runs", "2"])
    assert run_evals.main() == 0

    report = json.loads(next(run_evals.REPORT_DIR.glob("*.json")).read_text())
    assert report["summary"]["sweet_spot_day"] == {"runs": 2, "passed": 2, "first_try": 2, "tokens": 2400}
    assert report["prompts"]["workout"].startswith("workout@")
    assert report["results"][0]["workout"]["name"] == "Sweet Spot 3x10"


def test_race_far_longer_than_any_build_up_ride_is_flagged():
    days = week(60) + week(70) + week(80) + week(90) + week(95) + week(40)
    days[-1] = PlanDay(day_number=0, phase="Race", planned_workout_type="Race",
                       planned_duration_min=300, planned_tss=220, description="Race.")
    assert any("longest ride in the build-up is 60 min" in p for p in plan_checks(days, current_ctl=55))


def test_race_day_itself_does_not_count_against_the_taper():
    taper = week(60) + week(80) + week(90) + week(30)
    taper[-1] = PlanDay(day_number=0, phase="Race", planned_workout_type="Race",
                        planned_duration_min=330, planned_tss=232, description="Race.")
    assert not any(p.startswith("no taper") for p in plan_checks(taper, current_ctl=25))
