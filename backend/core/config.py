from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, read from the environment (or backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Athletes and their access tokens live in the database (python -m manage add-athlete).
    database_path: str = "data/coach.db"

    openai_api_key: str
    strava_client_id: str
    strava_client_secret: str

    # "Today" for check-ins, workouts and plan dates is computed in this timezone.
    timezone: str = "Europe/Berlin"

    plan_model: str = "gpt-6-luna"
    workout_model: str = "gpt-6-luna"
    # Only for `evals.run_evals --judge`. A different, stronger model gives a more independent
    # opinion than the coach grading itself.
    judge_model: str = "gpt-6-luna"
    openai_timeout_s: float = 120
    # One generation may try this often: the first answer plus repairs after failed checks.
    ai_max_attempts: int = 3
    # Model calls per athlete and day (every attempt counts). A plan takes 10-30, a workout 1-3;
    # beyond the limit workouts fall back to standard sessions built in code.
    ai_daily_call_limit: int = 150

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
