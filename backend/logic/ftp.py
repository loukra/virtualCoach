"""FTP tests: when they happen, what they look like, and what a test ride says about FTP.

Tests are placed and built by code, never by the model: a test is only useful if every one is
ridden the same way, so the results can be compared over the winter.
"""
import math
from datetime import date, timedelta

import numpy as np

from core import db
from logic.schemas import Workout, WorkoutStep

TEST_EVERY_WEEKS = 5
TEST_DAY_IN_WEEK = 2  # the day before (day 1 of the week) is kept easy
TEST_DURATION_MIN = 51
TEST_TSS = 65
FTP_FROM_20MIN = 0.95  # FTP is about 95 % of the best 20-minute power
MIN_CHANGE = 0.02  # smaller differences are measurement noise
LOOKBACK_DAYS = 28
MAX_FILL_GAP_S = 3  # longer gaps in the power stream are stops, counted as 0 W


def test_weeks(total_days: int, goal_type: str) -> list[int]:
    """Weeks with an FTP test: the first, then every five weeks.

    A fitness block also ends with a test, to show what the winter brought. A race plan keeps
    the last three weeks free of tests, so the taper is not spent on a maximal effort.
    """
    weeks = math.ceil(total_days / 7)
    if goal_type == "build":
        tests = list(range(1, weeks + 1, TEST_EVERY_WEEKS))
        if weeks - tests[-1] >= 3:
            tests.append(weeks)
        return tests
    return list(range(1, weeks - 2, TEST_EVERY_WEEKS)) if weeks >= 6 else []


def test_days(total_days: int, goal_type: str) -> list[int]:
    days = [(w - 1) * 7 + TEST_DAY_IN_WEEK for w in test_weeks(total_days, goal_type)]
    last_training_day = total_days - 1 if goal_type == "race" else total_days
    return [d for d in days if d <= last_training_day]


def _step(kind, **fields) -> WorkoutStep:
    base = dict(duration_s=None, power=None, power_low=None, power_high=None, repeat=None, on_s=None,
                off_s=None, on_power=None, off_power=None, hr_cap_bpm=None)
    return WorkoutStep(kind=kind, **{**base, **fields})


def test_workout() -> Workout:
    """A 20-minute test: warm up with three short openers, then 20 minutes all out."""
    return Workout(
        name="FTP Test (20 min)",
        rationale="Measures your current FTP, so every workout targets the right watts.",
        steps=[
            _step("warmup", duration_s=600, power_low=0.5, power_high=0.75,
                  instruction="Easy start, build gradually."),
            _step("intervals", repeat=3, on_s=60, off_s=60, on_power=1.0, off_power=0.55,
                  instruction="Short openers at FTP to wake the legs up."),
            _step("steady", duration_s=300, power=0.6, instruction="Easy, get ready for the test."),
            _step("freeride", duration_s=1200,
                  instruction="20 minutes as hard as you can hold evenly. Start a little careful,"
                              " finish strong. Turn ERG off if your trainer uses it."),
            _step("cooldown", duration_s=600, power_low=0.6, power_high=0.4,
                  instruction="Spin out easily."),
        ],
        hr_guidance="No heart-rate cap during the test; stop if you feel unwell.",
    )


def best_power(watts, times, window_s: int = 1200) -> int | None:
    """Highest average power over `window_s` seconds of riding time, from Strava streams.

    Streams are resampled to one value per second: short recording gaps keep the last value,
    longer ones are stops and count as zero, so a coffee break never inflates the result.
    """
    if watts is None or times is None or len(watts) == 0 or len(watts) != len(times):
        return None
    offsets = (np.asarray(times, dtype=float) - times[0]).round().astype(int)
    per_second = np.zeros(offsets[-1] + 1)
    known = np.zeros(offsets[-1] + 1, dtype=bool)
    per_second[offsets] = watts
    known[offsets] = True
    last, last_at = 0.0, -MAX_FILL_GAP_S - 1
    for t in range(len(per_second)):
        if known[t]:
            last, last_at = per_second[t], t
        elif t - last_at <= MAX_FILL_GAP_S:
            per_second[t] = last
    if len(per_second) < window_s:
        return None
    sums = np.cumsum(np.insert(per_second, 0, 0.0))
    return round(float(np.max(sums[window_s:] - sums[:-window_s]) / window_s))


def suggestion(athlete_id: int, day: date) -> dict | None:
    """A new FTP worth taking over, or None.

    After an FTP test the test decides, up or down. Without a recent test, a ride whose best
    20 minutes point to a clearly higher FTP is enough to suggest raising it.
    """
    current = (db.query_one("SELECT ftp FROM athletes WHERE id = ?", [athlete_id]) or {}).get("ftp")
    if not current:
        return None
    since = (day - timedelta(days=LOOKBACK_DAYS)).isoformat()
    test = db.query_one(
        "SELECT a.id, a.start_date_local, a.best_20min_watts FROM master_plan p"
        " JOIN journeys j ON j.id = p.journey_id JOIN activities a ON a.id = p.activity_id"
        " WHERE j.athlete_id = ? AND p.planned_workout_type = 'FTP Test' AND p.status = 'done'"
        " AND a.best_20min_watts IS NOT NULL AND a.start_date_local >= ?"
        " ORDER BY a.start_date_local DESC LIMIT 1",
        [athlete_id, since],
    )
    ride = test or db.query_one(
        "SELECT id, start_date_local, best_20min_watts FROM activities"
        " WHERE athlete_id = ? AND best_20min_watts IS NOT NULL AND start_date_local >= ?"
        " ORDER BY best_20min_watts DESC LIMIT 1",
        [athlete_id, since],
    )
    if not ride:
        return None
    suggested = round(ride["best_20min_watts"] * FTP_FROM_20MIN)
    change = (suggested - current) / current
    if abs(change) < MIN_CHANGE or (not test and change < 0):
        return None
    # Once FTP was set (or kept) after that ride, its result has been dealt with.
    ride_day = ride["start_date_local"][:10]
    decided = db.query_one(
        "SELECT 1 FROM ftp_history WHERE athlete_id = ? AND valid_from >= ?", [athlete_id, ride_day]
    )
    if decided:
        return None
    return {
        "current": current,
        "suggested": suggested,
        "change_pct": round(change * 100, 1),
        "source": "test" if test else "ride",
        "date": ride_day,
        "activity_id": ride["id"],
    }
