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
    assert no_background_plan == []  # starts in the future: no plan yet

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

    def fake_generate(athlete_id, journey, available_time, session):
        calls.append((athlete_id, journey["id"], available_time))
        return {"date": today(), "workout": sweet_spot_workout(), "markdown": "# Sweet Spot 3x10",
                "estimated_tss": 57, "recovery_reason": None, "plan_id": None}

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
    assert f'"{today().isoformat()} Sweet Spot 3x10.zwo"' in zwo.headers["content-disposition"]
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


def test_build_journey_runs_for_the_chosen_weeks(client, athletes, no_background_plan):
    res = client.post("/create-journey", headers=athletes["louis"], json={
        "journey_name": "Winter fitness", "goal_type": "build", "weeks": 16, "start_date": "2099-11-02",
        "current_ftp": 250, "current_weight": 75,
    })
    assert res.status_code == 200, res.text
    journey = client.get(f"/journeys/{res.json()['journey_id']}", headers=athletes["louis"]).json()
    assert journey["goal_type"] == "build" and journey["race_date"] == "2100-02-21"  # 16 × 7 days
    assert journey["status"] == "scheduled"
    missing = client.post("/create-journey", headers=athletes["louis"], json={
        "journey_name": "Winter", "goal_type": "build", "current_ftp": 250, "current_weight": 75,
    })
    assert missing.status_code == 400


def active_week(client, headers, start, sessions):
    """An active journey starting at `start` with (day_number, type, minutes, tss) sessions."""
    journey_id = create_journey(client, headers)
    db.execute("UPDATE journeys SET status = 'active', start_date = ?, race_date = ? WHERE id = ?",
               [start.isoformat(), (start + timedelta(days=55)).isoformat(), journey_id])
    for number, kind, minutes, tss in sessions:
        db.execute(
            "INSERT INTO master_plan (journey_id, date, day_number, phase, planned_workout_type,"
            " planned_duration_min, planned_tss, description) VALUES (?, ?, ?, 'Build', ?, ?, ?, 'S.')",
            [journey_id, (start + timedelta(days=number - 1)).isoformat(), number, kind, minutes, tss],
        )
    return journey_id


def test_today_moves_a_missed_session_and_counts_the_ride(client, athletes, no_background_plan):
    day = today()
    start = day - timedelta(days=2)  # today is day 3 of the week
    journey_id = active_week(client, athletes["louis"], start, [
        (1, "Endurance", 60, 45), (2, "Threshold", 75, 85), (3, "Recovery", 45, 25), (4, "Rest", 0, 0),
    ])
    db.execute(
        "INSERT INTO activities (id, athlete_id, start_date, start_date_local, moving_time, tss, tss_source)"
        " VALUES (1, 1, ?, ?, 3600, 45, 'power')",
        [f"{start.isoformat()}T17:00:00", f"{start.isoformat()}T18:00:00"],
    )
    view = client.get(f"/journeys/{journey_id}/today", headers=athletes["louis"]).json()
    states = {s["planned_workout_type"]: s["state"] for s in view["week"]["sessions"]}
    assert states == {"Endurance": "done", "Threshold": "open", "Recovery": "open", "Rest": "rest"}
    assert view["suggestion"]["session"]["planned_workout_type"] == "Threshold"
    assert view["suggestion"]["reason"].startswith("Moved from")
    assert view["week"]["ridden_tss"] == 45 and view["week"]["planned_tss"] == 155


def test_ftp_test_is_built_by_code_and_needs_its_time(client, athletes, no_background_plan, monkeypatch):
    import logic.ai as ai

    monkeypatch.setattr(ai, "get_openai", lambda: pytest.fail("the FTP test needs no model"))
    journey_id = active_week(client, athletes["louis"], today() - timedelta(days=1),
                             [(1, "Rest", 0, 0), (2, "FTP Test", 51, 65)])
    body = {"journey_id": journey_id, "available_time": 45}
    assert client.post("/generate-workout", headers=athletes["louis"], json=body).status_code == 400
    res = client.post("/generate-workout", headers=athletes["louis"], json={**body, "available_time": 60})
    assert res.status_code == 200 and "FTP Test (20 min)" in res.json()["workout"]
    zwo = client.get(f"/workouts/{journey_id}/{today().isoformat()}.zwo", headers=athletes["louis"])
    assert "<FreeRide" in zwo.text
    row = db.query_one("SELECT plan_id, chosen_plan_id FROM daily_prescriptions")
    assert row["plan_id"] == row["chosen_plan_id"] is not None


def test_ftp_can_be_taken_over(client, athletes):
    assert client.put("/ftp", headers=athletes["louis"], json={"ftp": 265}).status_code == 200
    overview = client.get("/ftp", headers=athletes["louis"]).json()
    assert overview["current"] == 265 and overview["history"][-1]["ftp"] == 265
    assert overview["suggestion"] is None and overview["tests"] == []
    assert client.get("/ftp", headers=athletes["anna"]).json()["current"] is None


def test_checkin_keeps_motivation_and_trims_notes(client, athletes):
    body = {"feel_score": 3, "soreness_score": 4, "motivation_score": 2, "notes": "  "}
    assert client.post("/check-in", headers=athletes["louis"], json=body).status_code == 200
    row = db.query_one("SELECT motivation_score, notes FROM daily_checkins")
    assert row == {"motivation_score": 2, "notes": None}


def test_a_plan_can_start_mid_week_with_a_short_first_week(client, athletes, no_background_plan):
    res = client.post("/create-journey", headers=athletes["louis"], json={
        "journey_name": "Winter", "goal_type": "build", "weeks": 16, "start_date": "2099-10-28",  # Wednesday
        "current_ftp": 250, "current_weight": 75,
    })
    journey = client.get(f"/journeys/{res.json()['journey_id']}", headers=athletes["louis"]).json()
    # Week 1 runs Wednesday to Sunday, weeks 2-16 Monday to Sunday.
    assert (journey["start_date"], journey["race_date"]) == ("2099-10-28", "2100-02-14")


def test_today_before_the_plan_starts(client, athletes, no_background_plan):
    journey_id = active_week(client, athletes["louis"], today() + timedelta(days=2),
                             [(1, "Recovery", 30, 15), (2, "FTP Test", 51, 65)])
    view = client.get(f"/journeys/{journey_id}/today", headers=athletes["louis"]).json()
    assert view["starts_on"] == (today() + timedelta(days=2)).isoformat()
    assert view["suggestion"]["mode"] == "rest" and "Your plan starts on" in view["suggestion"]["reason"]


def test_a_journey_starting_today_gets_its_plan_now(client, athletes, no_background_plan):
    res = client.post("/create-journey", headers=athletes["louis"], json={
        "journey_name": "Winter", "goal_type": "build", "weeks": 8, "current_ftp": 250, "current_weight": 75,
    })
    assert res.json()["status"] == "processing"
    assert no_background_plan[0][-1] == "build"


def test_journeys_may_not_overlap(client, athletes, no_background_plan):
    create_journey(client, athletes["louis"])  # 2099-03-01 to 2099-06-01
    body = {"journey_name": "Second", "race_date": "2099-07-01", "current_ftp": 250, "current_weight": 75}
    res = client.post("/create-journey", headers=athletes["louis"], json={**body, "start_date": "2099-05-15"})
    assert res.status_code == 409 and "Gran Fondo" in res.json()["detail"]
    res = client.post("/create-journey", headers=athletes["louis"], json={**body, "start_date": "2099-06-02"})
    assert res.status_code == 200
    names = [j["name"] for j in client.get("/journeys", headers=athletes["louis"]).json()]
    assert names == ["Gran Fondo", "Second"]  # in time order
    # Anna's plans are her own business.
    assert client.post("/create-journey", headers=athletes["anna"],
                       json={**body, "start_date": "2099-05-15"}).status_code == 200


def test_scheduled_journey_gets_its_plan_on_its_start_day(client, athletes, no_background_plan, monkeypatch):
    journey_id = create_journey(client, athletes["louis"])
    started = []
    monkeypatch.setattr(routers.journeys, "generate_scheduled_plan", started.append)
    assert client.get("/journeys", headers=athletes["louis"]).json()[0]["status"] == "scheduled"
    assert started == []

    from datetime import date
    monkeypatch.setattr(routers.journeys, "today", lambda: date(2099, 3, 1))
    assert client.get("/journeys", headers=athletes["louis"]).json()[0]["status"] == "creating"
    assert [j["id"] for j in started] == [journey_id]
    client.get(f"/journeys/{journey_id}", headers=athletes["louis"])
    assert len(started) == 1  # claimed once
