from fastapi import APIRouter, BackgroundTasks, HTTPException
from datetime import date
from core.db import supabase
from models import CreateJourneyRequest
from logic.workers import run_ai_plan_generation

router = APIRouter()

@router.post("/create-journey")
async def create_journey_endpoint(payload: CreateJourneyRequest, background_tasks: BackgroundTasks):
    """
    Creates a journey and triggers AI plan generation in the background.
    """
    print(f"🚀 Creating Journey '{payload.journey_name}' for {payload.user_id}")
    
    # A. Calculate Days Until Race
    try:
# 1. Determine Dates
        today = date.today()
    
        # If user provided a start date, use it. Otherwise default to today.
        if payload.start_date:
            macro_start_date = date.fromisoformat(payload.start_date)
        else:
            macro_start_date = today

        race_date_obj = date.fromisoformat(payload.race_date)
        days_until = (race_date_obj - macro_start_date).days + 1
        
        if days_until < 7:
            raise HTTPException(status_code=400, detail="Race date must be at least 1 week away.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # B. Update User Profile (FTP/Weight)
    supabase.table("profiles").update({
        "ftp": payload.current_ftp, 
        "weight_kg": payload.current_weight
    }).eq("id", payload.user_id).execute()


# --- 👇 NEW LOGIC: FETCH CURRENT CTL ---
    print(f"🔍 Checking fitness history for {payload.user_id}...")
    
    # Query the LAST recorded metric for this user
    metrics_res = supabase.table("daily_metrics")\
        .select("ctl")\
        .eq("user_id", payload.user_id)\
        .order("date", desc=True)\
        .limit(1)\
        .execute()
    
    # If they have history, use it. If not, assume 0 (Beginner).
    current_ctl = 0
    if metrics_res.data and len(metrics_res.data) > 0:
        current_ctl = metrics_res.data[0]['ctl']
        print(f"   -> Found existing fitness: CTL {current_ctl}")
    else:
        print("   -> No history found. Starting at CTL 0 (Beginner).")
    # C. Create Journey Record
    journey_data = {
        "user_id": payload.user_id,
        "name": payload.journey_name,
        "start_date": macro_start_date.isoformat(),
        "race_date": payload.race_date,
        "status": "creating" # Mark as creating so app knows to wait
    }
    res = supabase.table("journeys").insert(journey_data).execute()
    journey_id = res.data[0]['id']

    # D. Run AI Generation in Background (So app doesn't freeze)
    background_tasks.add_task(
        run_ai_plan_generation, 
        journey_id,
        payload.journey_name,       # goal
        payload.current_ftp,        # ftp
        payload.current_weight,     # weight
        macro_start_date,           # start_date
        race_date_obj,              # race_date (Ensure this var exists from step A)
        date.today(),               # current_date (To know "where we are now")
        current_ctl                 # current_ctl
    )

    return {"status": "processing", "message": "AI is building your plan...", "journey_id": journey_id}
