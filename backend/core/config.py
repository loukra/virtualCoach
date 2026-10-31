from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, read from the environment (or backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    # Must be the service-role (secret) key: the backend writes on the user's behalf
    # and Row Level Security blocks the anon key from doing that.
    supabase_service_key: str = Field(
        validation_alias=AliasChoices("SUPABASE_SERVICE_KEY", "SUPABASE_KEY")
    )
    openai_api_key: str
    strava_client_id: str
    strava_client_secret: str

    # Comma-separated Supabase user ids that may use the API. Empty = any signed-in user.
    allowed_user_ids: str = ""
    # "Today" for check-ins, workouts and plan dates is computed in this timezone.
    timezone: str = "Europe/Berlin"

    plan_model: str = "gpt-5-mini"
    workout_model: str = "gpt-5-mini"
    openai_timeout_s: float = 120
    # One generation may try this often: the first answer plus repairs after failed checks.
    ai_max_attempts: int = 3

    log_level: str = "INFO"

    @property
    def allowed_ids(self) -> set[str]:
        return {uid.strip() for uid in self.allowed_user_ids.split(",") if uid.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
