"""The AI layer degrades instead of failing: standard sessions, a daily budget, cut-off answers."""
from datetime import timedelta
from types import SimpleNamespace

import openai
import pytest
from fastapi.testclient import TestClient

import logic.ai as ai
from core import db
from core.auth import hash_token
from core.dates import today
from logic.fallback import SETS, standard_workout
from logic.guardrails import validate_workout
from logic.workout_math import total_duration_s
from main import app
from tests.factories import sweet_spot_workout
from tests.test_ai import FakeResponses, run

J = "6c1f0a52-8f0e-4d2b-9a8e-3b4f2a1c9d10"


@pytest.mark.parametrize("kind", [*SETS, "FTP Test", None])
@pytest.mark.parametrize("minutes", [15, 20, 30, 45, 60, 90, 120, 180, 360])
def test_standard_sessions_pass_the_guardrails(kind, minutes):
    for recovery in (False, True):
        workout = standard_workout(kind, minutes, recovery)
        assert validate_workout(workout, minutes, 190, recovery) == [], (kind, minutes, recovery)
        assert total_duration_s(workout) / 60 >= min(minutes, 15) - 0.01


def test_standard_session_keeps_the_planned_type():
    assert standard_workout("Sweet Spot", 60, False).name == "Standard Sweet Spot 3x10"
    assert standard_workout("Threshold", 20, False).name == "Standard Threshold"  # no room for a set
    assert standard_workout("VO2 Max", 60, True).name == "Standard Recovery"  # a forced recovery day wins


def test_the_daily_budget_stops_calls_before_the_model(monkeypatch):
    db.execute("INSERT INTO athletes (name, token_hash) VALUES ('louis', ?)", [hash_token("t")])
    for _ in range(3):
        db.execute("INSERT INTO ai_generations (athlete_id, kind, model, prompt_version, attempt, ok)"
                   " VALUES (1, 'workout', 'm', 'workout@x', 1, 1)")
    monkeypatch.setattr(ai, "get_settings", lambda: SimpleNamespace(ai_max_attempts=3, ai_daily_call_limit=3))
    monkeypatch.setattr(ai, "get_openai", lambda: pytest.fail("no call over the budget"))
    with pytest.raises(ai.BudgetExceeded):
        run()


class CutOffFirst(FakeResponses):
    """The first answer stops at max_output_tokens, the second is complete."""

    def parse(self, **kwargs):
        response = super().parse(**kwargs)
        cut = len(self.calls) == 1
        response.status = "incomplete" if cut else "completed"
        response.incomplete_details = SimpleNamespace(reason="max_output_tokens") if cut else None
        return response


def test_a_cut_off_answer_is_named_in_the_repair(monkeypatch):
    monkeypatch.setattr(ai, "_record", lambda **row: None)
    responses = CutOffFirst([sweet_spot_workout(), sweet_spot_workout()])
    monkeypatch.setattr(ai, "get_openai", lambda: SimpleNamespace(responses=responses))
    assert run().name == "Sweet Spot 3x10"
    assert "cut off (max_output_tokens)" in responses.calls[1]["input"][-1]["content"]


def test_a_failing_model_still_gives_a_workout(monkeypatch):
    db.execute("INSERT INTO athletes (name, token_hash, ftp) VALUES ('louis', ?, 250)", [hash_token("t")])
    day = today()
    db.execute("INSERT INTO journeys (id, athlete_id, name, goal_type, start_date, race_date, status)"
               " VALUES (?, 1, 'Winter', 'build', ?, ?, 'active')",
               [J, (day - timedelta(days=2)).isoformat(), (day + timedelta(days=60)).isoformat()])
    db.execute("INSERT INTO master_plan (journey_id, date, day_number, phase, planned_workout_type,"
               " planned_duration_min, planned_tss) VALUES (?, ?, 3, 'Build', 'Threshold', 60, 70)",
               [J, day.isoformat()])

    class Down:
        def parse(self, **_):
            raise openai.APIConnectionError(request=None)

    monkeypatch.setattr(ai, "get_openai", lambda: SimpleNamespace(responses=Down()))
    headers = {"Authorization": "Bearer t"}
    with TestClient(app) as client:
        body = {"journey_id": J, "available_time": 60}
        res = client.post("/generate-workout", headers=headers, json=body)
        assert res.status_code == 200 and res.json()["source"] == "fallback"
        assert "Standard Threshold" in res.json()["workout"]
        assert client.get(f"/journeys/{J}/today", headers=headers).json()["workout"]["source"] == "fallback"
        assert client.get(f"/workouts/{J}/{day.isoformat()}.zwo", headers=headers).status_code == 200


def test_ai_stats_report():
    from logic.ai_stats import report

    for attempt, ok, errors in ((1, 0, '["Week 7: days sum to 455 TSS"]'), (2, 1, "[]"), (1, 1, "[]")):
        db.execute("INSERT INTO ai_generations (athlete_id, kind, model, prompt_version, attempt, ok, errors,"
                   " latency_ms, input_tokens, output_tokens) VALUES (1, 'plan_block', 'm', 'plan_block@a',"
                   " ?, ?, ?, 1000, 3000, 900)", [attempt, ok, errors])
    [row] = report(7)
    assert (row["generations"], row["first_try"], row["succeeded"], row["calls"]) == (2, 1, 2, 3)
    assert row["top_violations"] == [("Week N: days sum to N TSS", 1)]
    assert row["input_tokens"] == 9000 and row["latency_p50_ms"] == 1000
