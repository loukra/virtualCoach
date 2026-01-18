from pydantic import BaseModel

class CheckInRequest(BaseModel):
    user_id: str
    feel_score: int
    soreness_score: int

class GenerateWorkoutRequest(BaseModel):
    user_id: str
    journey_id: str
    available_time: int = 60

class CreateJourneyRequest(BaseModel):
    user_id: str
    journey_name: str
    race_date: str
    start_date: str = None
    current_ftp: int
    current_weight: float

class ConnectRequest(BaseModel):
    user_id: str
    code: str

class SyncRequest(BaseModel):
    user_id: str