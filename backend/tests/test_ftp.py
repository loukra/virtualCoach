"""FTP tests: placement, the fixed protocol, the 20-minute power and the suggested FTP."""
from datetime import date

import numpy as np
import pytest

from core import db
from core.auth import hash_token
from logic import ftp
from logic.guardrails import validate_days, validate_macro, validate_workout
from logic.workout_math import to_zwo, total_duration_s
from tests.factories import macro, week_of_days


@pytest.mark.parametrize(("weeks", "goal", "expected"), [
    (16, "build", [1, 6, 11, 16]),
    (12, "build", [1, 6, 11]),
    (20, "build", [1, 6, 11, 16, 20]),  # the block ends with a test
    (12, "race", [1, 6]),  # none in the last three weeks
    (5, "race", []),
])
def test_test_weeks(weeks, goal, expected):
    assert ftp.test_weeks(weeks * 7, goal) == expected


def test_test_days_are_day_two_of_their_week():
    assert ftp.test_days(16 * 7, "build") == [2, 37, 72, 107]


def test_protocol_is_valid_and_exports_as_free_ride():
    workout = ftp.test_workout()
    assert validate_workout(workout, 60, 190, recovery_only=False, allow_freeride=True) == []
    assert round(total_duration_s(workout) / 60) == ftp.TEST_DURATION_MIN
    assert '<FreeRide Duration="1200" FlatRoad="1"' in to_zwo(workout)


def test_the_model_may_not_write_free_rides():
    errors = validate_workout(ftp.test_workout(), 60, 190, recovery_only=False)
    assert errors == ["Step 4: freeride is only used in FTP tests, which the app builds itself."]


def test_best_power_ignores_stops():
    times = np.arange(3600)
    watts = np.full(3600, 200.0)
    watts[1000:2200] = 280  # 20 minutes at 280 W
    assert ftp.best_power(watts, times) == 280
    # A recording gap of ten minutes is a stop, not ten minutes at the last value.
    gap_times = np.concatenate([np.arange(600), np.arange(1200, 2400)])
    gap_watts = np.full(len(gap_times), 300.0)
    assert ftp.best_power(gap_watts, gap_times) == 300  # the 20 minutes after the stop
    assert ftp.best_power(np.full(600, 300.0), np.arange(600)) is None  # ride too short


@pytest.fixture
def athlete():
    db.execute("INSERT INTO athletes (name, token_hash, ftp) VALUES ('louis', ?, 250)", [hash_token("t")])
    db.execute("INSERT INTO ftp_history VALUES (1, '2099-01-01', 250)")
    db.execute("INSERT INTO journeys (id, athlete_id, name, goal_type, start_date, race_date, status)"
               " VALUES ('j', 1, 'Winter', 'build', '2099-03-01', '2099-06-20', 'active')")
    return 1


def add_ride(id, day, best20, test=False):
    db.execute("INSERT INTO activities (id, athlete_id, start_date, start_date_local, best_20min_watts)"
               " VALUES (?, 1, ?, ?, ?)", [id, f"{day}T17:00:00", f"{day}T18:00:00", best20])
    if test:
        db.execute("INSERT INTO master_plan (journey_id, date, day_number, planned_workout_type, status,"
                   " activity_id) VALUES ('j', ?, 2, 'FTP Test', 'done', ?)", [day, id])


def test_a_test_result_is_suggested_up_or_down(athlete):
    add_ride(1, "2099-03-02", 250, test=True)  # 0.95 × 250 = 238 W, below the current 250
    suggestion = ftp.suggestion(athlete, date(2099, 3, 3))
    assert suggestion["suggested"] == 238 and suggestion["source"] == "test"


def test_a_hard_ride_only_ever_raises_ftp(athlete):
    add_ride(1, "2099-03-04", 250)
    assert ftp.suggestion(athlete, date(2099, 3, 5)) is None
    add_ride(2, "2099-03-05", 290)  # 276 W
    assert ftp.suggestion(athlete, date(2099, 3, 6))["suggested"] == 276


def test_suggestion_disappears_once_ftp_was_set(athlete):
    add_ride(1, "2099-03-02", 290, test=True)
    db.execute("INSERT INTO ftp_history VALUES (1, '2099-03-03', 276)")
    assert ftp.suggestion(athlete, date(2099, 3, 4)) is None


def test_build_plans_have_no_race_and_fixed_test_days():
    weeks = macro([300, 330, 360, 250], ["Base", "Build", "Build", "Recovery"])
    assert validate_macro(weeks, 28, "build") == []
    assert "no Race or Taper" in validate_macro(macro([300, 330, 360, 250]), 28, "build")[0]

    days = week_of_days(1, [0, 65, 50, 50, 0, 90, 55])
    days[1].planned_workout_type, days[1].planned_duration_min = "FTP Test", 51
    assert validate_days(days, 1, 7, 28, {1: 310}, "build", [2]) == []

    days[0].planned_workout_type, days[0].planned_duration_min, days[0].planned_tss = "Tempo", 60, 50
    errors = validate_days(days, 1, 7, 28, {1: 360}, "build", [2])
    assert errors == ["Day 1 is the day before an FTP test: make it Rest or Recovery."]
    errors = validate_days(week_of_days(1, [0, 65, 50, 50, 0, 90, 55]), 1, 7, 28, {1: 310}, "build", [2])
    assert errors == ["Day 2: FTP Test with 51 minutes and 65 TSS, as listed."]


def test_fitness_plan_load_must_grow_with_the_weeks():
    phases = ["Base", "Build", "Build", "Recovery"] * 4
    flat = macro([180, 190, 200, 140] * 4, phases)  # 16 weeks from CTL 25, never above 200 TSS
    errors = validate_macro(flat, 16 * 7, "build", ctl=25)
    assert errors == ["The load never rises enough to raise fitness: let the build weeks grow to a peak"
                      " of about 287 TSS (at least 265)."]
    growing = macro([180, 195, 210, 150, 215, 230, 245, 175, 245, 260, 275, 195, 270, 285, 295, 210], phases)
    assert validate_macro(growing, 16 * 7, "build", ctl=25) == []


def test_a_mid_week_start_moves_the_first_test_to_the_first_full_week():
    # Wednesday start (offset 2), 16 calendar weeks: week 1 has five days.
    total = 5 + 15 * 7
    assert ftp.test_weeks(total, "build", offset=2) == [2, 7, 12, 16]
    assert ftp.test_days(total, "build", offset=2) == [7, 42, 77, 105]  # all Tuesdays


def test_short_first_week_is_judged_by_its_days():
    weeks = macro([150, 300, 330, 360], ["Base", "Base", "Build", "Build"])
    # Five-day first week (Wednesday start): 150 TSS is about 210 for a full week, so 300 is fine.
    assert validate_macro(weeks, 5 + 21, "build", ctl=30, offset=2) == []
    too_much = macro([400, 300, 330, 360], ["Base", "Base", "Build", "Build"])
    assert validate_macro(too_much, 5 + 21, "build", ctl=30, offset=2) == [
        "Week 1 has only 5 days: plan load for those days only, at most about 193 TSS."
    ]
