"""Structured LLM calls with validation, repair and logging.

Every call: the model fills a Pydantic schema (Structured Outputs), the result is checked by a
deterministic validator, and on violations the model gets another chance with the exact
problems listed. Each attempt is logged to `ai_generations` (model, prompt version, tokens,
latency, violations) so quality and cost can be followed over time.
"""
import hashlib
import json
import logging
import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import openai
from pydantic import BaseModel

from core import db
from core.config import get_settings
from core.llm import get_openai

log = logging.getLogger(__name__)
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class GenerationError(Exception):
    def __init__(self, kind: str, errors: list[str]):
        super().__init__(f"{kind} generation failed: {'; '.join(errors)}")
        self.kind = kind
        self.errors = errors


class BudgetExceeded(GenerationError):
    """The athlete's daily number of model calls is used up; nothing was sent to the model."""


def calls_today(athlete_id: int) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM ai_generations WHERE athlete_id = ? AND created_at >= date('now')",
        [athlete_id],
    )
    return row["n"]


@lru_cache
def load_prompt(name: str) -> tuple[str, str]:
    """Returns the prompt text and a version tag that changes whenever the file changes."""
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text, f"{name}@{hashlib.sha256(text.encode()).hexdigest()[:8]}"


def repair_message(errors: list[str]) -> str:
    listed = "\n".join(f"- {e}" for e in errors)
    return (
        "Your previous answer violated these rules:\n"
        f"{listed}\n"
        "Return the complete corrected answer in the same format."
    )


def _record(**row) -> None:
    row["errors"] = json.dumps(row.get("errors", []))
    columns = ", ".join(row)
    try:
        db.execute(
            f"INSERT INTO ai_generations ({columns}) VALUES ({', '.join('?' * len(row))})",
            row.values(),
        )
    except Exception:
        log.exception("Could not log an AI generation")  # logging must never break a generation


def generate_structured[T: BaseModel](
    *,
    kind: str,
    model: str,
    prompt_name: str,
    user_input: str,
    schema: type[T],
    validate: Callable[[T], list[str]],
    athlete_id: int | None,
    journey_id: str | None = None,
    max_output_tokens: int = 32000,
) -> T:
    instructions, prompt_version = load_prompt(prompt_name)
    messages: list[dict] = [{"role": "user", "content": user_input}]
    errors: list[str] = []

    settings = get_settings()
    for attempt in range(1, settings.ai_max_attempts + 1):
        if athlete_id is not None and calls_today(athlete_id) >= settings.ai_daily_call_limit:
            raise BudgetExceeded(kind, [f"Daily limit of {settings.ai_daily_call_limit} AI calls reached."])
        started = time.monotonic()
        response = None
        try:
            response = get_openai().responses.parse(
                model=model,
                instructions=instructions,
                input=messages,
                text_format=schema,
                max_output_tokens=max_output_tokens,
                store=False,  # the athlete's data is not kept on OpenAI's side
            )
            parsed = response.output_parsed
            if getattr(response, "status", None) == "incomplete":
                reason = getattr(response.incomplete_details, "reason", "unknown")
                parsed, errors = None, [f"The answer was cut off ({reason}). Keep the text fields short."]
            elif parsed is None:
                errors = ["The model refused to answer."]
            else:
                errors = validate(parsed)
        except openai.OpenAIError as e:
            _record(
                athlete_id=athlete_id, journey_id=journey_id, kind=kind, model=model,
                prompt_version=prompt_version,
                attempt=attempt, ok=False, errors=[f"API error: {e}"],
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            raise GenerationError(kind, [f"OpenAI API error: {e}"]) from e
        except ValueError as e:  # truncated or malformed JSON that does not fit the schema
            parsed = None
            errors = [f"The answer was not valid JSON for the schema ({e.__class__.__name__})."]

        usage = getattr(response, "usage", None)
        _record(
            athlete_id=athlete_id, journey_id=journey_id, kind=kind, model=model,
            prompt_version=prompt_version,
            attempt=attempt, ok=not errors, errors=errors,
            latency_ms=int((time.monotonic() - started) * 1000),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
        if not errors:
            return parsed

        log.warning("%s attempt %d failed checks: %s", kind, attempt, errors)
        if response is not None and response.output_text:
            messages.append({"role": "assistant", "content": response.output_text})
        messages.append({"role": "user", "content": repair_message(errors)})

    raise GenerationError(kind, errors)
