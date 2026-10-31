"""API tests against a real (temporary) SQLite database; only the LLM and Strava are faked."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import routers.journeys
import routers.workout
from core import db
from core.auth import hash_token
from core.dates import today
from main import app
from tests.factories import sweet_spot_workout


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def athletes(database):
    """Two athletes, to prove that nobody sees the other one's data."""
    for name in ("louis", "anna"):
        db.execute(
            "INSERT INTO athletes (name, token_hash) VALUES (?, ?)", [name, hash_token(f"token-{name}")]
        )
    return {"louis": {"Authorization": "Bearer token-louis"}, "anna": {"Authorization": "Bearer token-anna"}}


@pytest.fixture
def no_background_plan(monkeypatch):
    calls = []
    monkeypatch.setattr(routers.journeys, "run_ai_plan_generation", lambda *a: calls.append(a))
    return calls


def create_journey(client, headers, name="Gran Fondo"):
    res = client.post("/create-journey", headers=headers, json={
        "journey_name": name, "race_date": "2099-06-01", "start_date": "2099-03-01",
        "current_ftp": 250, "current_weight": 75,
    })
    assert res.status_code == 200, res.text
    return res.json()["journey_id"]


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_missing_or_unknown_token_is_rejected(client, athletes):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer forged"}).status_code == 401


def test_profile_round_trip_and_onboarding_state(client, athletes):
    me = client.get("/me", headers=athletes["louis"]).json()
    assert me["name"] == "louis" and me["profile_complete"] is False and me["strava_connected"] is False

    res = client.put("/profile", headers=athletes["louis"],
                     json={"goal": "Gran Fondo", "ftp": 260, "max_heart_rate": 188, "weight_kg": 74.5})
    assert res.status_code == 200
    me = client.get("/me", headers=athletes["louis"]).json()
    assert me["profile_complete"] is True and me["ftp"] == 260
    assert db.query("SELECT ftp FROM ftp_history") == [{"ftp": 260}]


def test_checkin_belongs_to_token_owner(client, athletes):
    body = {"feel_score": 4, "soreness_score": 3, "athlete_id": 2}
    assert client.post("/check-in", headers=athletes["louis"], json=body).status_code == 200
    rows = db.query("SELECT athlete_id, feel_score FROM daily_checkins")
    assert rows == [{"athlete_id": 1, "feel_score": 4}]


def test_scores_are_validated(client, athletes):
    res = client.post("/check-in", headers=athletes["louis"], json={"feel_score": 9, "soreness_score": 3})
    assert res.status_code == 422


def test_journeys_are_private_per_athlete(client, athletes, no_background_plan):
    journey_id = create_journey(client, athletes["louis"])
    assert len(no_background_plan) == 1

    assert [j["id"] for j in client.get("/journeys", headers=athletes["louis"]).json()] == [journey_id]
    assert client.get("/journeys", headers=athletes["anna"]).json() == []
    assert client.get(f"/journeys/{journey_id}", headers=athletes["anna"]).status_code == 404
    assert client.get(f"/journeys/{journey_id}/calendar", headers=athletes["anna"]).status_code == 404


def test_archived_journeys_disappear_and_stay_private(client, athletes, no_background_plan):
    journey_id = create_journey(client, athletes["louis"])
    assert client.delete(f"/journeys/{journey_id}", headers=athletes["anna"]).status_code == 404

    assert client.delete(f"/journeys/{journey_id}", headers=athletes["louis"]).status_code == 200
    assert client.get("/journeys", headers=athletes["louis"]).json() == []


def test_journey_date_rules(client, athletes, no_background_plan):
    res = client.post("/create-journey", headers=athletes["louis"], json={
        "journey_name": "Too soon", "race_date": "2099-03-03", "start_date": "2099-03-01",
        "current_ftp": 250, "current_weight": 75,
    })
    assert res.status_code == 400 and no_background_plan == []


def test_workout_is_generated_once_per_day_and_exported(client, athletes, no_background_plan, monkeypatch):
    journey_id = create_journey(client, athletes["louis"])
    db.execute("UPDATE journeys SET status = 'active' WHERE id = ?", [journey_id])
    calls = []

    def fake_generate(athlete_id, journey, available_time):
        calls.append((athlete_id, journey["id"], available_time))
        return {"date": today(), "workout": sweet_spot_workout(), "markdown": "# Sweet Spot 3x10",
                "estimated_tss": 57, "recovery_reason": None}

    monkeypatch.setattr(routers.workout, "generate_workout", fake_generate)
    body = {"journey_id": journey_id, "available_time": 60}

    first = client.post("/generate-workout", headers=athletes["louis"], json=body).json()
    second = client.post("/generate-workout", headers=athletes["louis"], json=body).json()
    assert first["cached"] is False and second["cached"] is True and len(calls) == 1
    forced = client.post("/generate-workout", headers=athletes["louis"], json={**body, "force": True}).json()
    assert forced["cached"] is False and len(calls) == 2

    today_view = client.get(f"/journeys/{journey_id}/today", headers=athletes["louis"]).json()
    assert today_view["workout"]["estimated_tss"] == 57

    zwo = client.get(f"/workouts/{journey_id}/{today().isoformat()}.zwo", headers=athletes["louis"])
    assert zwo.status_code == 200 and "<IntervalsT" in zwo.text
    assert client.get(f"/workouts/{journey_id}/{today().isoformat()}.zwo",
                      headers=athletes["anna"]).status_code == 404


def test_workout_needs_an_active_plan(client, athletes, no_background_plan):
    journey_id = create_journey(client, athletes["louis"])
    res = client.post("/generate-workout", headers=athletes["louis"], json={"journey_id": journey_id})
    assert res.status_code == 409


def test_workout_generation_runs_end_to_end_with_a_fake_model(
    client, athletes, no_background_plan, monkeypatch
):
    """Everything real except the model: context from the database, guardrails, storage, .zwo."""
    import logic.ai as ai
    from tests.test_ai import FakeResponses

    journey_id = create_journey(client, athletes["louis"])
    day = today()
    db.execute("UPDATE journeys SET status = 'active', start_date = ? WHERE id = ?",
               [(day - timedelta(days=3)).isoformat(), journey_id])
    db.execute(
        "INSERT INTO master_plan (journey_id, date, day_number, phase, planned_workout_type,"
        " planned_duration_min, planned_tss, description)"
        " VALUES (?, ?, 4, 'Base', 'Sweet Spot', 60, 60, 'SS.')",
        [journey_id, day.isoformat()],
    )
    responses = FakeResponses([sweet_spot_workout()])
    monkeypatch.setattr(ai, "get_openai", lambda: type("Client", (), {"responses": responses})())

    res = client.post("/generate-workout", headers=athletes["louis"],
                      json={"journey_id": journey_id, "available_time": 60})
    assert res.status_code == 200, res.text
    assert "LAST SEVEN DAYS" in responses.calls[0]["input"][0]["content"]
    zwo = client.get(f"/workouts/{journey_id}/{day.isoformat()}.zwo", headers=athletes["louis"])
    assert zwo.status_code == 200
