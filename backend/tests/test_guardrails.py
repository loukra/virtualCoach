from logic.guardrails import validate_days, validate_macro, validate_workout
from logic.schemas import Workout
from tests.factories import macro, step, sweet_spot_workout, week_of_days

GOOD_WEEK = [0, 60, 80, 50, 0, 120, 90]  # 400 TSS, two rest days


# --- workout ---

def test_valid_workout_passes():
    assert validate_workout(sweet_spot_workout(), available_min=60, max_hr=190, recovery_only=False) == []


def test_workout_longer_than_available_time_fails():
    errors = validate_workout(sweet_spot_workout(), available_min=45, max_hr=190, recovery_only=False)
    assert any("only has 45" in e for e in errors)


def test_forced_recovery_rejects_intensity():
    errors = validate_workout(sweet_spot_workout(), available_min=60, max_hr=190, recovery_only=True)
    assert any("forced recovery" in e for e in errors)


def test_watts_instead_of_fraction_is_caught():
    w = sweet_spot_workout()
    w.steps[1].on_power = 225
    errors = validate_workout(w, available_min=60, max_hr=190, recovery_only=False)
    assert any("watts instead of a fraction" in e for e in errors)


def test_long_effort_above_threshold_is_caught():
    w = Workout(
        name="Too hard", rationale="-", hr_guidance="-",
        steps=[
            step("warmup", duration_s=600, power_low=0.5, power_high=0.7),
            step("steady", duration_s=1200, power=1.15),
            step("cooldown", duration_s=300, power_low=0.6, power_high=0.4),
        ],
    )
    errors = validate_workout(w, available_min=60, max_hr=190, recovery_only=False)
    assert any("not sustainable" in e for e in errors)


def test_missing_fields_and_structure_are_reported():
    w = Workout(
        name="Broken", rationale="-", hr_guidance="-",
        steps=[step("steady", duration_s=None, power=0.7)],
    )
    errors = validate_workout(w, available_min=60, max_hr=190, recovery_only=False)
    assert "Start with a warmup step." in errors
    assert any("set duration_s" in e for e in errors)


def test_hr_cap_above_max_hr_fails():
    w = sweet_spot_workout()
    w.steps[1].hr_cap_bpm = 200
    errors = validate_workout(w, available_min=60, max_hr=185, recovery_only=False)
    assert any("HR cap" in e for e in errors)


# --- macro plan ---

def test_valid_macro_passes():
    m = macro([300, 360, 420, 280, 400, 460, 300, 200],
              ["Base", "Build", "Build", "Recovery", "Build", "Peak", "Taper", "Race"])
    assert validate_macro(m, total_days=56) == []


def test_macro_week_count_must_match_timeline():
    assert validate_macro(macro([300, 300, 200]), total_days=30)[0].startswith("Return exactly 5 weeks")


def test_macro_rejects_load_jumps_missing_taper_and_no_recovery():
    m = macro([200, 400, 450, 500, 550, 600], ["Build"] * 6)
    errors = validate_macro(m, total_days=42)
    assert any("load jumps" in e for e in errors)
    assert "The last week must be a Race or Taper week." in errors
    assert any("Race week load" in e for e in errors)
    assert any("without a recovery week" in e for e in errors)


# --- daily blocks ---

def test_valid_days_pass():
    days = week_of_days(1, GOOD_WEEK) + week_of_days(8, GOOD_WEEK)
    assert validate_days(days, 1, 14, total_days=28, week_targets={1: 400, 2: 400}) == []


def test_days_must_cover_the_requested_range():
    days = week_of_days(1, GOOD_WEEK)
    assert validate_days(days, 1, 8, total_days=28, week_targets={})[0].startswith("Return exactly the days")


def test_week_without_easy_day_and_wrong_total_fails():
    days = week_of_days(1, [100] * 7)
    errors = validate_days(days, 1, 7, total_days=28, week_targets={1: 400})
    assert any("Rest or Recovery day" in e for e in errors)
    assert any("week target is 400" in e for e in errors)


def test_impossible_tss_and_inconsistent_rest_day_fail():
    days = week_of_days(1, GOOD_WEEK)
    days[1].planned_duration_min = 30
    days[1].planned_tss = 120  # 4 TSS per minute
    days[0].planned_tss = 10  # Rest day with load
    errors = validate_days(days, 1, 7, total_days=28, week_targets={})
    assert any("not physically possible" in e for e in errors)
    assert any("Rest day has duration 0" in e for e in errors)


def test_last_day_must_be_the_race():
    days = week_of_days(1, GOOD_WEEK)
    errors = validate_days(days, 1, 7, total_days=7, week_targets={})
    assert "Day 7 is race day: planned_workout_type must be Race." in errors


def test_token_load_for_a_long_day_or_race_is_rejected():
    # The real model planned a 4-hour Gran Fondo at 65 TSS (IF 0.4): no race is ridden like that.
    days = week_of_days(1, GOOD_WEEK)
    days[-1].planned_workout_type, days[-1].planned_duration_min, days[-1].planned_tss = "Race", 240, 65
    days[2].planned_duration_min, days[2].planned_tss = 180, 30  # three hours "endurance" at 30 TSS
    errors = validate_days(days, 1, 7, total_days=7, week_targets={})
    assert any("Day 7: 65 TSS in 240 minutes is too little for a Race day" in e for e in errors)
    assert any(e.startswith("Day 3:") and "too little" in e for e in errors)


def test_block_ranges_never_leave_race_week_alone():
    from logic.ai_planner import block_ranges
    assert block_ranges(85) == [(1, 28), (29, 56), (57, 85)]
    assert block_ranges(70) == [(1, 28), (29, 56), (57, 70)]
    assert block_ranges(30) == [(1, 30)]
    assert block_ranges(7) == [(1, 7)]


def test_blocks_end_on_sundays_after_a_short_first_week():
    from logic.ai_planner import block_ranges

    # Wednesday start: the first block holds the five-day week 1 plus three full weeks.
    assert block_ranges(5 + 7 * 15, offset=2) == [(1, 26), (27, 54), (55, 82), (83, 110)]


def test_returning_to_build_load_after_a_recovery_week_is_no_jump():
    phases = ["Build", "Build", "Build", "Recovery", "Build", "Race"]
    def jumps(tss):
        return any("load jumps" in e for e in validate_macro(macro(tss, phases), 42))

    assert not jumps([400, 440, 470, 280, 470, 250])
    assert jumps([400, 440, 470, 280, 700, 250])
