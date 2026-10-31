from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# The athlete always comes from the access token (core.auth), never from these bodies.


class ProfileUpdate(BaseModel):
    goal: str = Field(min_length=1, max_length=200)
    ftp: int = Field(ge=50, le=600)
    max_heart_rate: int = Field(ge=120, le=230)
    weight_kg: float = Field(ge=30, le=200)


class CheckInRequest(BaseModel):
    feel_score: int = Field(ge=1, le=5)
    soreness_score: int = Field(ge=1, le=5)
    motivation_score: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class GenerateWorkoutRequest(BaseModel):
    journey_id: UUID
    available_time: int = Field(default=60, ge=15, le=360)
    # The session to ride; without it, today's suggestion.
    plan_id: int | None = None
    # Regenerate even if today's workout already exists for this duration.
    force: bool = False


class CreateJourneyRequest(BaseModel):
    journey_name: str = Field(min_length=1, max_length=100)
    # race: prepare for the event on race_date. build: raise fitness for `weeks` weeks.
    goal_type: Literal["race", "build"] = "race"
    race_date: date | None = None
    weeks: int | None = Field(default=None, ge=2, le=52)
    start_date: date | None = None
    current_ftp: int = Field(ge=50, le=600)
    current_weight: float = Field(ge=30, le=200)


class FtpUpdate(BaseModel):
    ftp: int = Field(ge=50, le=600)


class ConnectRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class SyncRequest(BaseModel):
    days_back: int = Field(default=7, ge=1, le=365)
