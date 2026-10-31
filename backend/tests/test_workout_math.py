import xml.etree.ElementTree as ET

from logic.schemas import Workout
from logic.workout_math import (
    estimate_tss,
    max_power,
    step_segments,
    to_markdown,
    to_zwo,
    total_duration_s,
)
from tests.factories import step, sweet_spot_workout


def test_one_hour_at_ftp_is_100_tss():
    w = Workout(
        name="FTP hour", rationale="Test.", hr_guidance="-",
        steps=[step("steady", duration_s=3600, power=1.0)],
    )
    assert estimate_tss(w) == 100


def test_ramp_uses_mean_of_squared_intensity():
    # mean of IF^2 over a 0 -> 1 ramp is 1/3, so one hour gives 33 TSS
    w = Workout(
        name="Ramp", rationale="Test.", hr_guidance="-",
        steps=[step("ramp", duration_s=3600, power_low=0.0, power_high=1.0)],
    )
    assert estimate_tss(w) == 33


def test_duration_and_peak_power_include_interval_repeats():
    w = sweet_spot_workout()
    assert total_duration_s(w) == 600 + 3 * (600 + 300) + 300
    assert max_power(w) == 0.9


def test_zwo_is_valid_xml_with_one_element_per_step():
    root = ET.fromstring(to_zwo(sweet_spot_workout()))
    assert root.tag == "workout_file"
    tags = [el.tag for el in root.find("workout")]
    assert tags == ["Warmup", "IntervalsT", "Cooldown"]
    intervals = root.find("workout/IntervalsT")
    assert intervals.get("Repeat") == "3" and intervals.get("OnPower") == "0.90"


def _replay_zwo(xml: str) -> list[tuple[int, float, float]]:
    """Reads a .zwo the way Zwift does: (seconds, start power, end power) per segment.

    Warmup, Cooldown and Ramp run from PowerLow to PowerHigh (a cooldown has PowerLow > PowerHigh).
    """
    segments = []
    for el in ET.fromstring(xml).find("workout"):
        if el.tag == "IntervalsT":
            for _ in range(int(el.get("Repeat"))):
                on, off = float(el.get("OnPower")), float(el.get("OffPower"))
                segments += [(int(el.get("OnDuration")), on, on), (int(el.get("OffDuration")), off, off)]
        elif el.tag == "SteadyState":
            power = float(el.get("Power"))
            segments.append((int(el.get("Duration")), power, power))
        else:
            assert el.tag in {"Warmup", "Cooldown", "Ramp"}, el.tag
            segments.append((int(el.get("Duration")), float(el.get("PowerLow")), float(el.get("PowerHigh"))))
    return segments


def test_zwo_replays_to_exactly_the_planned_workout():
    w = Workout(
        name="Mixed", rationale="Test.", hr_guidance="-",
        steps=[
            step("warmup", duration_s=600, power_low=0.5, power_high=0.75),
            step("steady", duration_s=1200, power=0.7),
            step("ramp", duration_s=300, power_low=0.8, power_high=1.0),
            step("intervals", repeat=5, on_s=240, off_s=240, on_power=1.15, off_power=0.5),
            step("cooldown", duration_s=600, power_low=0.6, power_high=0.4),
        ],
    )
    planned = [seg for s in w.steps for seg in step_segments(s)]
    # The file stores two decimals, which is all the plan uses.
    assert _replay_zwo(to_zwo(w)) == [(sec, round(lo, 2), round(hi, 2)) for sec, lo, hi in planned]
    assert sum(sec for sec, _, _ in planned) == total_duration_s(w)


def test_zwo_cooldown_runs_downwards():
    cooldown = ET.fromstring(to_zwo(sweet_spot_workout())).find("workout/Cooldown")
    assert float(cooldown.get("PowerLow")) > float(cooldown.get("PowerHigh"))


def test_zwo_escapes_text_from_the_model():
    w = sweet_spot_workout().model_copy(update={"name": 'Over & under <"hard">'})
    assert ET.fromstring(to_zwo(w)).find("name").text == 'Over & under <"hard">'


def test_markdown_converts_fractions_to_watts():
    text = to_markdown(sweet_spot_workout(), ftp=250)
    assert "# Sweet Spot 3x10" in text
    assert "225 W" in text  # 0.90 x 250
    assert "Duration: **60 min**" in text
