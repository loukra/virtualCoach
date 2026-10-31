from datetime import date, timedelta

import numpy as np

from logic.coach import forced_recovery_reason, format_compliance_history
from logic.metrics import compute_daily_metrics
from logic.strava_sync import (
    calculate_hr_tss,
    calculate_normalized_power,
    calculate_tss_from_stream,
    get_ftp_for_date,
    ride_tss,
)


def test_normalized_power_of_constant_effort_is_that_power():
    assert calculate_normalized_power(np.full(600, 200.0)) == 200


def test_normalized_power_weights_surges_above_average():
    surges = np.tile(np.r_[np.full(30, 100.0), np.full(30, 300.0)], 10)
    assert calculate_normalized_power(surges) > np.mean(surges)


def test_tss_one_hour_at_ftp_is_100():
    assert calculate_tss_from_stream(3600, 250, 250) == 100


def test_hr_tss_is_on_the_same_scale():
    max_hr = 200
    lthr = max_hr * 0.91
    assert calculate_hr_tss(3600, lthr, max_hr) == 100
    assert calculate_hr_tss(3600, lthr * 0.8, max_hr) == 64


def test_tss_source_waterfall():
    assert ride_tss(3600, 250, 250, 150, 190) == (100, "power")
    assert ride_tss(3600, 0, 250, 150, 190)[1] == "heart_rate"
    assert ride_tss(3600, 0, 250, 0, 190) == (50, "time")


def test_ftp_lookup_uses_value_valid_on_ride_date():
    history = [{"ftp": 260, "valid_from": "2026-03-01"}, {"ftp": 240, "valid_from": "2026-01-01"}]
    assert get_ftp_for_date("2026-03-15T08:00:00", history, 200) == 260
    assert get_ftp_for_date("2026-02-01T08:00:00", history, 200) == 240
    assert get_ftp_for_date("2025-12-01T08:00:00", history, 200) == 240
    assert get_ftp_for_date("2026-02-01T08:00:00", [], 200) == 200


def test_ctl_converges_to_constant_daily_load():
    start = date(2026, 1, 1)
    daily = {start + timedelta(days=i): 80.0 for i in range(400)}
    rows = compute_daily_metrics(daily, start + timedelta(days=399))
    assert abs(rows[-1]["ctl"] - 80) < 0.5
    assert abs(rows[-1]["tsb"]) < 0.5


def test_rest_days_raise_form():
    start = date(2026, 1, 1)
    daily = {start + timedelta(days=i): 100.0 for i in range(60)}
    rows = compute_daily_metrics(daily, start + timedelta(days=67))
    assert rows[59]["tsb"] < rows[-1]["tsb"]
    assert rows[-1]["tsb"] > 0


def test_forced_recovery_rules():
    assert forced_recovery_reason({"feel_score": 2, "soreness_score": 4}, None)
    assert forced_recovery_reason({"feel_score": 4, "soreness_score": 1}, None)
    assert forced_recovery_reason(None, {"tsb": -35})
    assert forced_recovery_reason({"feel_score": 4, "soreness_score": 4}, {"tsb": -10}) is None


def test_compliance_history_uses_local_day_and_hides_ride_names():
    day = date(2026, 3, 10)
    plans = [{"date": "2026-03-09", "planned_workout_type": "Endurance",
              "planned_duration_min": 90, "planned_tss": 80}]
    rides = [{"start_date_local": "2026-03-09T23:30:00", "sport_type": "Ride", "name": "Ride to Anna's",
              "moving_time": 5400, "tss": 75}]
    text = format_compliance_history(plans, rides, day)
    assert "2026-03-09: plan Endurance (90 min, 80 TSS) | actual Ride (90 min, 75 TSS)" in text
    assert "Anna" not in text
