from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

# The caller's user id always comes from the access token (core.auth), never from these bodies.


class CheckInRequest(BaseModel):
    feel_score: int = Field(ge=1, le=5)
    soreness_score: int = Field(ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class GenerateWorkoutRequest(BaseModel):
    journey_id: UUID
    available_time: int = Field(default=60, ge=15, le=360)
    # Regenerate even if today's workout already exists for this duration.
    force: bool = False


class CreateJourneyRequest(BaseModel):
    journey_name: str = Field(min_length=1, max_length=100)
    race_date: date
    start_date: date | None = None
    current_ftp: int = Field(ge=50, le=600)
    current_weight: float = Field(ge=30, le=200)


class ConnectRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class SyncRequest(BaseModel):
    days_back: int = Field(default=7, ge=1, le=365)
