"""Races, group rides and days off: what they do to the plan, the API and a running plan."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import logic.workers as workers
import routers.events
import routers.journeys
from core import db
from core.auth import hash_token
from core.dates import monday_of, today
from logic.ai_planner import block_ranges, kept_weeks
from logic.events import events_text, place_tests, plan_events
from logic.guardrails import validate_days, validate_macro
from logic.schemas import PlanDay
from main import app
from tests.factories import macro, week_of_days

START = date(2099, 3, 2)  # a Monday


def event(kind, day, name="E", priority=None, duration=None, end=None):
    return {"kind": kind, "name": name, "start_date": day.isoformat(),
            "end_date": (end or day).isoformat(), "priority": priority, "duration_min": duration}


def on(n):  # plan day n as a date
    return START + timedelta(days=n - 1)


def test_races_shape_the_days_around_them():
    ev = plan_events([event("race", on(20), "Spring Classic", "A", 180),
                      event("race", on(34), "Crit", "B", 60),
                      event("ride", on(13), "Club RTF", duration=240),
                      event("off", on(43), "Holiday", end=on(49))], START, 84)
    assert ev.races[20]["priority"] == "A" and ev.rides == {13: {"name": "Club RTF", "duration_min": 240}}
    assert sorted(ev.easy) == [18, 19, 21, 22, 33, 35]  # two days around a main race, one around a B
    assert sorted(ev.off) == list(range(43, 50))
    assert ev.main_race_weeks == {3: "Spring Classic"}
    assert ev.off_days_in_week() == {7: 7}
    text = events_text(ev, START, macro=True)
    assert 'Day 20 (Sat 2099-03-21): main race "Spring Classic", about 180 minutes' in text
    assert "Days 43-49: no training (Holiday): Rest." in text
    assert 'Week 3 holds the main race "Spring Classic"' in text


def test_a_race_plan_counts_its_own_race_as_main_race():
    ev = plan_events([], START, 70, "race", "Gran Fondo")
    assert ev.races == {70: {"name": "Gran Fondo", "duration_min": None, "priority": "A"}}


def test_ftp_tests_make_way_for_events():
    ev = plan_events([event("race", on(6), "Opener", "B"),  # week 1
                      event("off", on(37), "Trip", end=on(37))], START, 112)
    # Week 1's test moves to week 2; day 37 is a day off, so its test moves a week later too.
    assert place_tests([2, 37, 72], ev, 112) == [9, 44, 72]
    blocked = plan_events([event("race", on(6), "A", "A"), event("race", on(13), "B", "B")], START, 112)
    assert place_tests([2], blocked, 112) == []  # week 2 is no better: the test is dropped


def test_event_days_are_checked():
    ev = plan_events([event("race", on(6), "Crit", "B", 60), event("ride", on(7), "RTF", duration=240),
                      event("off", on(2), "Trip", end=on(3))], START, 28)
    days = week_of_days(1, [0, 50, 60, 70, 40, 90, 120])
    days[4].planned_workout_type = "Threshold"
    days[6].planned_workout_type = "Tempo"
    errors = validate_days(days, 1, 7, 28, {}, "build", events=ev)
    assert errors == [
        "Day 2 has no training (Trip): make it Rest.",
        "Day 3 has no training (Trip): make it Rest.",
        'Day 5 is next to secondary race "Crit": make it Rest, Recovery or Endurance.',
        'Day 6 is race day ("Crit"): planned_workout_type must be Race.',
        'Day 7 is the group ride "RTF": make it Endurance.',
    ]


def test_a_week_with_days_off_may_stay_below_its_target():
    days = week_of_days(1, [0, 0, 0, 0, 60, 90, 60])
    ev = plan_events([event("off", on(1), "Trip", end=on(4))], START, 28)
    assert validate_days(days, 1, 7, 28, {1: 400}, "build", events=ev) == []
    assert "week target is 400" in validate_days(days, 1, 7, 28, {1: 400}, "build")[0]


def test_race_days_need_their_length_and_no_race_elsewhere():
    ev = plan_events([event("race", on(7), "Crit", "B", 60)], START, 28)
    days = week_of_days(1, [0, 50, 60, 70, 40, 50, 120])
    for d, kind, minutes in ((days[1], "Race", 60), (days[6], "Race", 180)):
        d.planned_workout_type, d.planned_duration_min = kind, minutes
    days[5].planned_workout_type = "Recovery"
    errors = validate_days(days, 1, 7, 28, {}, "build", events=ev)
    assert errors == ["Day 2: Race only on the race days listed under EVENTS.",
                      'Day 7: the race "Crit" lasts about 60 minutes; plan the day for that.']


def test_a_main_race_inside_a_build_plan():
    ev = plan_events([event("race", on(34), "Spring Classic", "A")], START, 56)
    phases = ["Base", "Build", "Build", "Taper", "Race", "Build", "Build", "Recovery"]
    good = macro([300, 330, 360, 280, 200, 340, 370, 260], phases)
    assert validate_macro(good, 56, "build", 40, 0, ev) == []
    heavy = macro([300, 330, 360, 280, 380, 340, 370, 260], phases)
    assert validate_macro(heavy, 56, "build", 40, 0, ev) == [
        'Week 5 (main race "Spring Classic") load must be below the average of the three weeks before it.'
    ]
    misplaced = macro([300, 330, 360, 280, 200, 340, 370, 260], phases[:6] + ["Taper", "Recovery"])
    assert "only in a main race week" in validate_macro(misplaced, 56, "build", 40, 0, ev)[0]


def test_a_rebuilt_plan_keeps_its_first_weeks():
    kept = week_of_days(1, [0, 50, 60, 70, 0, 90, 50]) + week_of_days(8, [0, 55, 65, 75, 0, 95, 55])
    fixed = kept_weeks(kept, 0)
    assert [(w.week_number, w.target_tss) for w in fixed] == [(1, 320), (2, 345)]
    rest = macro([300, 370, 390, 260, 400, 420], ["Build"] * 6)
    rest.weeks = rest.weeks[2:]
    for i, w in enumerate(rest.weeks, start=3):
        w.week_number = i
    assert validate_macro(rest, 42, "build", 40, 0, fixed=fixed) == []
    assert validate_macro(macro([300] * 6), 42, "build", 40, 0, fixed=fixed) == [
        "Return only the weeks 3 to 6; weeks 1 to 2 are already planned."
    ]
    assert block_ranges(84, 0, first_day=15) == [(15, 42), (43, 70), (71, 84)]


# --- API -------------------------------------------------------------------------------------

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def louis(database):
    db.execute("INSERT INTO athletes (name, token_hash, ftp, weight_kg) VALUES ('louis', ?, 250, 75)",
               [hash_token("token-louis")])
    return {"Authorization": "Bearer token-louis"}


@pytest.fixture
def replans(monkeypatch):
    calls = []
    monkeypatch.setattr(routers.events, "replan_journey", calls.append)
    monkeypatch.setattr(routers.journeys, "replan_journey", calls.append)
    return calls


def add_journey(journey_id, start, end, status="active", goal_type="build"):
    db.execute("INSERT INTO journeys (id, athlete_id, name, goal_type, start_date, race_date, status)"
               " VALUES (?, 1, ?, ?, ?, ?, ?)",
               [journey_id, f"Journey {journey_id}", goal_type, start.isoformat(), end.isoformat(), status])


def post_event(client, headers, **body):
    body = {"kind": "race", "name": "Crit", "priority": "B", **body}
    return client.post("/events", headers=headers, json=body)


def test_event_rules(client, louis):
    day = today()
    assert post_event(client, louis, start_date=(day - timedelta(days=1)).isoformat()).status_code == 400
    assert post_event(client, louis, start_date="2099-05-01", priority=None).status_code == 400
    too_long = {"kind": "off", "start_date": "2099-05-01", "end_date": "2099-08-01"}
    assert post_event(client, louis, **too_long).status_code == 400
    assert post_event(client, louis, start_date="2099-05-03").status_code == 200
    clash = post_event(client, louis, kind="off", name="Trip", start_date="2099-05-01", end_date="2099-05-05")
    assert clash.status_code == 409 and '"Crit" is already on these days' in clash.json()["detail"]
    add_journey("r", date(2099, 4, 1), date(2099, 6, 1), "scheduled", "race")
    assert post_event(client, louis, start_date="2099-06-01").status_code == 409  # the journey's own race
    assert [e["name"] for e in client.get("/events", headers=louis).json()] == ["Crit"]


def test_an_event_rebuilds_a_running_plan_from_next_monday(client, louis, replans):
    day = today()
    add_journey("a", day - timedelta(days=10), day + timedelta(days=60))
    add_journey("s", day + timedelta(days=61), day + timedelta(days=120), "scheduled")
    later = monday_of(day) + timedelta(days=14)
    res = post_event(client, louis, start_date=later.isoformat())
    assert res.json()["journeys"] == [{"journey_id": "a", "name": "Journey a", "plan": "replanning"}]
    assert replans == ["a"]
    assert db.query_one("SELECT replanning FROM journeys WHERE id = 'a'")["replanning"] == 1

    # While it is rebuilt, a second change is queued instead of starting a second rebuild.
    next_day = (later + timedelta(days=1)).isoformat()
    res = post_event(client, louis, kind="ride", name="RTF", start_date=next_day)
    assert res.json()["journeys"][0]["plan"] == "queued" and replans == ["a"]

    res = post_event(client, louis, name="Spring", start_date=(day + timedelta(days=70)).isoformat())
    assert res.json()["journeys"] == [{"journey_id": "s", "name": "Journey s", "plan": "scheduled"}]


def test_an_event_this_week_leaves_the_plan_and_sets_today(client, louis, replans):
    day = today()
    add_journey("a", day - timedelta(days=10), day + timedelta(days=60))
    res = post_event(client, louis, kind="off", name="Cold", start_date=day.isoformat())
    assert res.json()["journeys"][0]["plan"] == "this_week" and replans == []
    suggestion = client.get("/journeys/a/today", headers=louis).json()["suggestion"]
    assert suggestion == {"mode": "rest", "session": None, "reason": "Cold: no training planned."}


def test_deleting_an_event_rebuilds_too(client, louis, replans):
    day = today()
    add_journey("a", day - timedelta(days=10), day + timedelta(days=60))
    later = monday_of(day) + timedelta(days=21)
    event_id = post_event(client, louis, start_date=later.isoformat()).json()["id"]
    db.execute("UPDATE journeys SET replanning = 0")
    assert client.delete(f"/events/{event_id}", headers=louis).json()["journeys"][0]["plan"] == "replanning"
    assert replans == ["a", "a"]
    assert client.delete(f"/events/{event_id}", headers=louis).status_code == 404


def test_calendar_is_one_timeline(client, louis):
    day = today()
    add_journey("a", day - timedelta(days=3), day + timedelta(days=30))
    add_journey("s", day + timedelta(days=31), day + timedelta(days=80), "scheduled")
    db.execute("INSERT INTO master_plan (journey_id, date, day_number, planned_workout_type,"
               " planned_duration_min, planned_tss) VALUES ('a', ?, 4, 'Endurance', 60, 50)",
               [day.isoformat()])
    post_event(client, louis, kind="off", name="Ski", start_date=(day + timedelta(days=90)).isoformat(),
               end_date=(day + timedelta(days=95)).isoformat())
    cal = client.get("/calendar", headers=louis).json()
    assert [j["id"] for j in cal["journeys"]] == ["a", "s"]
    assert [(p["journey_id"], p["state"]) for p in cal["plan"]] == [("a", "open")]
    assert cal["first"] == (day - timedelta(days=3)).isoformat()
    assert cal["last"] == (day + timedelta(days=95)).isoformat()
    assert cal["events"][0]["name"] == "Ski"


# --- Rebuilding a running plan -----------------------------------------------------------------

def test_replan_keeps_the_weeks_before_next_monday(louis, monkeypatch):
    day = today()
    start = monday_of(day) - timedelta(days=7)
    add_journey("a", start, start + timedelta(days=27))
    for n in range(1, 29):
        db.execute("INSERT INTO master_plan (journey_id, date, day_number, phase, planned_workout_type,"
                   " planned_duration_min, planned_tss, description) VALUES ('a', ?, ?, 'Base', 'Endurance',"
                   " 60, 50, 'Old.')", [(start + timedelta(days=n - 1)).isoformat(), n])
    seen = {}

    def fake_build_plan(**kw):
        seen.update(kw)
        return [PlanDay(day_number=n, phase="Build", planned_workout_type="Recovery", planned_duration_min=40,
                        planned_tss=25, description="New.") for n in range(len(kw["kept_days"]) + 1, 29)]

    monkeypatch.setattr(workers, "build_plan", fake_build_plan)
    db.execute("UPDATE journeys SET replanning = 1")
    workers.replan_journey("a")
    assert len(seen["kept_days"]) == 14  # this week and the one before stay
    rows = db.query("SELECT date, description FROM master_plan WHERE journey_id = 'a' ORDER BY date")
    assert len(rows) == 28
    assert {r["description"] for r in rows[:14]} == {"Old."}
    assert {r["description"] for r in rows[14:]} == {"New."}
    assert db.query_one("SELECT replanning, error FROM journeys") == {"replanning": 0, "error": None}


def test_a_failed_replan_keeps_the_old_plan(louis, monkeypatch):
    day = today()
    add_journey("a", day - timedelta(days=3), day + timedelta(days=40))
    db.execute("INSERT INTO master_plan (journey_id, date, day_number, planned_workout_type,"
               " planned_duration_min, planned_tss) VALUES ('a', ?, 30, 'Endurance', 60, 50)",
               [(day + timedelta(days=26)).isoformat()])

    def broken(**_):
        raise RuntimeError("model down")

    monkeypatch.setattr(workers, "build_plan", broken)
    workers.replan_journey("a")
    assert db.query_one("SELECT COUNT(*) AS n FROM master_plan")["n"] == 1
    assert "previous plan stays" in db.query_one("SELECT error FROM journeys")["error"]


def test_an_event_added_during_generation_is_planned_afterwards(louis, monkeypatch):
    add_journey("a", today(), today() + timedelta(days=40), "creating")
    assert workers.request_replan("a") == "queued"
    monkeypatch.setattr(workers, "build_plan", lambda **_: [])
    rebuilt = []
    monkeypatch.setattr(workers, "replan_journey", rebuilt.append)
    workers.run_ai_plan_generation("a", 1, "Goal", 250, 75, today(), today() + timedelta(days=40),
                                   today(), 30.0, "build")
    assert rebuilt == ["a"]


def test_sessions_on_days_off_drop_out_of_the_week(client, louis):
    day = today()
    start = monday_of(day)
    add_journey("a", start, start + timedelta(days=55))
    for n, kind in ((1, "Endurance"), (2, "Threshold"), (3, "Endurance")):
        db.execute("INSERT INTO master_plan (journey_id, date, day_number, planned_workout_type,"
                   " planned_duration_min, planned_tss) VALUES ('a', ?, ?, ?, 60, 60)",
                   [(start + timedelta(days=n - 1)).isoformat(), n, kind])
    trip = start + timedelta(days=1)
    db.execute("INSERT INTO events (athlete_id, kind, name, start_date, end_date)"
               " VALUES (1, 'off', 'Trip', ?, ?)", [trip.isoformat(), trip.isoformat()])
    week = client.get("/journeys/a/today", headers=louis).json()["week"]
    states = {s["planned_workout_type"]: s["state"] for s in week["sessions"]}
    assert states["Threshold"] == "off" and week["planned_tss"] == 120
    plan = client.get("/calendar", headers=louis).json()["plan"]
    assert [p["state"] for p in plan if p["date"] == trip.isoformat()] == ["off"]
