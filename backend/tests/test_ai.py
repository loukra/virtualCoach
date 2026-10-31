from types import SimpleNamespace

import pytest

import logic.ai as ai
from logic.ai import GenerationError, generate_structured
from logic.guardrails import validate_workout
from logic.schemas import Workout
from tests.factories import sweet_spot_workout


class FakeResponses:
    """Stands in for client.responses: returns the queued workouts one per call."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        parsed = self.outputs.pop(0)
        return SimpleNamespace(
            output_parsed=parsed,
            output_text=parsed.model_dump_json() if parsed else "",
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        )


@pytest.fixture
def fake_llm(monkeypatch):
    logged = []
    monkeypatch.setattr(ai, "_record", lambda **row: logged.append(row))

    def install(outputs):
        responses = FakeResponses(outputs)
        monkeypatch.setattr(ai, "get_openai", lambda: SimpleNamespace(responses=responses))
        return responses, logged

    return install


def run(validate=None):
    return generate_structured(
        kind="workout", model="test-model", prompt_name="workout", user_input="ATHLETE ...",
        schema=Workout,
        validate=validate or (lambda w: validate_workout(w, 60, 190, False)),
        athlete_id=1,
    )


def test_valid_answer_is_returned_and_logged(fake_llm):
    responses, logged = fake_llm([sweet_spot_workout()])
    assert run().name == "Sweet Spot 3x10"
    call = responses.calls[0]
    assert call["text_format"] is Workout and call["store"] is False
    assert logged[0]["ok"] is True and logged[0]["prompt_version"].startswith("workout@")


def test_violations_are_sent_back_for_repair(fake_llm):
    too_long = sweet_spot_workout()
    too_long.steps[1].repeat = 6  # 105 minutes in a 60-minute slot
    responses, logged = fake_llm([too_long, sweet_spot_workout()])

    assert run().steps[1].repeat == 3
    repair = responses.calls[1]["input"][-1]["content"]
    assert "only has 60" in repair
    assert [row["ok"] for row in logged] == [False, True]


def test_gives_up_after_max_attempts(fake_llm):
    bad = sweet_spot_workout()
    bad.steps[1].on_power = 230
    _, logged = fake_llm([bad, bad, bad])
    with pytest.raises(GenerationError) as exc:
        run()
    assert any("watts" in e for e in exc.value.errors)
    assert len(logged) == 3


def test_refusal_counts_as_failed_attempt(fake_llm):
    _, logged = fake_llm([None, sweet_spot_workout()])
    assert run().name == "Sweet Spot 3x10"
    assert logged[0]["errors"] == ["The model refused to answer."]
