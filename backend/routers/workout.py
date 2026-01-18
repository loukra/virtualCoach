from fastapi import APIRouter
from datetime import date
from core.db import supabase
from models import GenerateWorkoutRequest
from coach import generate_workout

router = APIRouter()

@router.post("/generate-workout")
async def generate_workout_endpoint(payload: GenerateWorkoutRequest):
    print(f"🤖 Generating workout for {payload.user_id} ({payload.available_time} mins)")
    print(f"🤖 Generating workout for Journey {payload.journey_id}...")
    workout_text = generate_workout(payload.user_id, payload.available_time)

    # 4. Save to DB
    today = date.today().isoformat()
    save_data = {
        "user_id": payload.user_id,
        "journey_id": payload.journey_id, # 👈 SAVE THIS
        "date": today,
        "workout_text": workout_text,
        "duration_min": payload.available_time
    }
    
    # Update constraint check to use the new journey_id + date logic
    supabase.table("daily_prescriptions")\
        .upsert(save_data, on_conflict="journey_id, date")\
        .execute()

    return {"status": "success", "workout": workout_text}