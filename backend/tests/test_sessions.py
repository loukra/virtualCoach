"""Flexible weeks: rides complete sessions on any day of their week, and today's choice follows."""
from datetime import date

from logic.sessions import assign_rides, choose_session, warning_signals

MONDAY = date(2099, 3, 2)  # plan day 1; the week runs Monday to Sunday
SUNDAY = date(2099, 3, 8)


def session(id, day, kind, minutes=60, tss=60, status="open", done_on=None):
    return {"id": id, "date": f"2099-03-{day:02d}", "planned_workout_type": kind,
            "planned_duration_min": 0 if kind == "Rest" else minutes,
            "planned_tss": 0 if kind == "Rest" else tss, "status": status, "done_on": done_on}


def week():
    return [
        session(1, 2, "Rest"),
        session(2, 3, "Endurance", 60, 45),
        session(3, 4, "Threshold", 75, 85),  # Wednesday
        session(4, 5, "Recovery", 45, 25),
        session(5, 6, "Rest"),
        session(6, 7, "Endurance", 180, 140),  # Saturday long ride
        session(7, 8, "Sweet Spot", 60, 70),
    ]


def ride(id, day, minutes, tss, name="Ride", source="power"):
    return {"id": id, "start_date_local": f"2099-03-{day:02d}T17:00:00", "name": name,
            "moving_time": minutes * 60, "tss": tss, "tss_source": source}


def fresh(**overrides):
    return {"recovery": None, "easy": None, "ready_for_test": True, "hard_yesterday": False, **overrides}


def test_threshold_ridden_on_thursday_completes_wednesdays_session():
    matches = assign_rides(week(), [ride(100, 5, 70, 80)], {}, MONDAY, SUNDAY)
    assert matches == [(3, 100)]


def test_easy_and_long_rides_complete_the_matching_sessions():
    rides = [ride(100, 3, 60, 42), ride(101, 7, 170, 130)]
    assert assign_rides(week(), rides, {}, MONDAY, SUNDAY) == [(2, 100), (6, 101)]


def test_prescribed_session_wins_over_the_best_guess():
    # The workout written on Tuesday was for Sunday's Sweet Spot session.
    assert assign_rides(week(), [ride(100, 3, 60, 62)], {"2099-03-03": 7}, MONDAY, SUNDAY) == [(7, 100)]


def test_an_easy_spin_does_not_complete_the_quality_session_it_was_written_for():
    matches = assign_rides(week(), [ride(100, 4, 40, 20)], {"2099-03-04": 3}, MONDAY, SUNDAY)
    assert matches == [(4, 100)]  # the recovery ride instead; the threshold stays open


def test_short_rides_and_rides_outside_the_plan_complete_nothing():
    rides = [ride(100, 3, 10, 8), ride(101, 9, 60, 50)]
    assert assign_rides(week(), rides, {}, MONDAY, SUNDAY) == []


def test_ftp_test_is_only_completed_by_a_test_ride():
    sessions = [session(1, 3, "FTP Test", 51, 65), session(2, 4, "Endurance", 60, 45)]
    assert assign_rides(sessions, [ride(100, 3, 55, 70)], {}, MONDAY, SUNDAY) == [(2, 100)]
    assert assign_rides(sessions, [ride(100, 3, 55, 70, name="Zwift - FTP Test (20 min)")], {},
                        MONDAY, SUNDAY) == [(1, 100)]


def test_missed_wednesday_is_suggested_on_thursday():
    choice = choose_session(week(), date(2099, 3, 5), SUNDAY, fresh())
    assert choice["session"]["id"] == 3 and choice["reason"].startswith("Moved from Wednesday")


def test_todays_session_is_suggested_when_nothing_key_is_overdue():
    sessions = week()
    sessions[2]["status"], sessions[2]["done_on"] = "done", "2099-03-04"
    choice = choose_session(sessions, date(2099, 3, 5), SUNDAY, fresh())
    assert choice["session"]["id"] == 4 and choice["reason"] == "Planned for today."


def test_no_intense_session_the_day_after_a_hard_ride():
    choice = choose_session(week(), date(2099, 3, 4), SUNDAY, fresh(hard_yesterday=True))
    assert choice["session"]["id"] == 4  # Thursday's recovery ride moves up, threshold moves back
    assert "Yesterday was hard" in choice["reason"]


def test_rest_day_stays_a_rest_day_while_the_week_has_room():
    choice = choose_session(week(), date(2099, 3, 6), SUNDAY, fresh())
    # Friday: Wednesday's threshold is still open and overdue, so it comes first.
    assert choice["session"]["id"] == 3
    done = [{**s, "status": "done"} if s["id"] in (2, 3, 4) else s for s in week()]
    assert choose_session(done, date(2099, 3, 6), SUNDAY, fresh())["mode"] == "rest"


def test_rest_day_is_used_when_the_week_has_no_room_left():
    sessions = week()
    sessions.append(session(8, 6, "Rest"))
    sessions[4] = session(5, 6, "Rest")
    # Saturday and Sunday hold the two open sessions; with only those days left there is no slack.
    done = [{**s, "status": "done"} if s["id"] in (2, 3, 4) else s for s in sessions]
    assert choose_session(done, date(2099, 3, 7), SUNDAY, fresh())["session"]["id"] == 6


def test_forced_recovery_picks_the_recovery_session_or_a_free_spin():
    choice = choose_session(week(), date(2099, 3, 4), SUNDAY, fresh(recovery="legs 1/5"))
    assert choice["mode"] == "recovery" and choice["session"]["id"] == 4
    no_recovery = [s for s in week() if s["planned_workout_type"] != "Recovery"]
    choice = choose_session(no_recovery, date(2099, 3, 4), SUNDAY, fresh(recovery="legs 1/5"))
    assert choice["mode"] == "recovery" and choice["session"] is None


def test_fatigue_signals_keep_the_ftp_test_for_a_fresher_day():
    sessions = [session(1, 3, "FTP Test", 51, 65), session(2, 4, "Endurance", 60, 45)]
    choice = choose_session(sessions, date(2099, 3, 3), SUNDAY, fresh(ready_for_test=False))
    assert choice["session"]["id"] == 2 and "FTP test waits" in choice["reason"]


def test_a_session_done_today_ends_the_day():
    sessions = week()
    sessions[1].update(status="done", done_on="2099-03-03")
    assert choose_session(sessions, date(2099, 3, 3), SUNDAY, fresh())["mode"] == "done"


def test_race_is_only_suggested_on_race_day():
    sessions = [session(1, 7, "Endurance", 60, 40), session(2, 8, "Race", 240, 200)]
    assert choose_session(sessions, date(2099, 3, 7), SUNDAY, fresh())["session"]["id"] == 1
    sessions[0]["status"] = "done"
    assert choose_session(sessions, date(2099, 3, 7), SUNDAY, fresh())["mode"] == "rest"
    assert choose_session(sessions, date(2099, 3, 8), SUNDAY, fresh())["session"]["id"] == 2


def checkin(feel=4, legs=4, motivation=None):
    return {"feel_score": feel, "soreness_score": legs, "motivation_score": motivation}


def test_burnout_shows_over_several_check_ins():
    tired = [checkin(2), checkin(4, motivation=2), checkin(2), checkin(4), checkin(4)]
    signals = warning_signals(tired, None)
    assert [s["kind"] for s in signals] == ["burnout"] and signals[0]["forces"] == "recovery"
    assert warning_signals([checkin(2), checkin(4), checkin(4)], None) == []


def test_heavy_legs_and_load_spikes_rule_out_hard_sessions():
    kinds = {s["kind"]: s["forces"] for s in warning_signals(
        [checkin(legs=2), checkin(legs=2), checkin()], {"ctl": 40, "atl": 65, "tsb": -25}
    )}
    assert kinds == {"heavy_legs": "easy", "load_spike": "easy"}


def test_weeks_are_calendar_weeks_when_the_plan_starts_mid_week():
    from logic.sessions import week_bounds, week_number

    wednesday, end = date(2099, 3, 4), date(2099, 6, 7)
    assert week_number(wednesday, date(2099, 3, 8)) == 1  # Sunday: still week 1
    assert week_number(wednesday, date(2099, 3, 9)) == 2  # Monday: week 2
    assert week_bounds(wednesday, end, 1) == (wednesday, date(2099, 3, 8))
    assert week_bounds(wednesday, end, 2) == (date(2099, 3, 9), date(2099, 3, 15))
