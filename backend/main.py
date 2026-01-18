from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from db import supabase
from datetime import date, datetime, timedelta
import json
from openai import OpenAI
from dotenv import load_dotenv
import os

# Import your existing logic
from auth import exchange_code_for_token
from sync import fetch_past_activities
from analysis import calculate_daily_metrics
from coach import generate_workout
# from coach import generate_workout # Uncomment this when you are ready for AI generation

# Load .env file to get OPENAI_API_KEY
load_dotenv()

# Initialize OpenAI Client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()
class CheckInRequest(BaseModel):
    user_id: str
    feel_score: int
    soreness_score: int

class GenerateWorkoutRequest(BaseModel):
    user_id: str
    journey_id: str  # 👈 NEW FIELD
    available_time: int = 60

class CreateJourneyRequest(BaseModel):
    user_id: str
    journey_name: str
    race_date: str
    start_date: str = None  # 👈 New Optional Field
    current_ftp: int
    current_weight: float

# --- 1. Data Models (What the App sends us) ---
class ConnectRequest(BaseModel):
    user_id: str
    code: str

class SyncRequest(BaseModel):  # <--- NEW
    user_id: str

def generate_ai_plan_logic(goal, start_date, race_date, current_date, ftp, weight, current_ctl):
    """
    Generates the training plan using OpenAI.
    Calculates specific duration and phase context based on dates.
    """
    # 1. Calculate Timeline Stats
    total_days = (race_date - start_date).days + 1

    days_elapsed = (current_date - start_date).days + 1 
    # Safety check: avoid negative elapsed days if start date is in future
    if days_elapsed < 0: days_elapsed = 0

    # 2. Determine Athlete Level
    athlete_level = "Recreational / Beginner"
    if current_ctl >= 40: athlete_level = "Intermediate"
    if current_ctl >= 85: athlete_level = "Advanced / Competitive"
    if current_ctl >= 110: athlete_level = "Elite / Pro"

    print(f"\n🧠 Consulting AI for {total_days} day plan.")
    print(f"   -> Timeline: Day {days_elapsed} of {total_days}")
    print(f"   -> Fitness: CTL {current_ctl} ({athlete_level})")
    
    prompt = f"""
    You are an expert cycling coach. Create a {total_days}-day training plan for a cyclist.
    
    TIMELINE CONTEXT:
    - **Plan Start Date:** {start_date}
    - **Race Date:** {race_date} (Day {total_days})
    - **Current Date:** {current_date} (We are currently at Day {days_elapsed} of the plan).
    
    ATHLETE PROFILE:
    - FTP: {ftp}W
    - Weight: {weight}kg
    - Current CTL: {current_ctl} ({athlete_level})
    - Goal: {goal}
    
    INSTRUCTIONS:
    1. **Structure:** Create a full plan from Day 1 to Day {total_days}.
    2. **Adaptation:** - Since we are currently at Day {days_elapsed}, the phase corresponding to this day should match the athlete's current fitness ({current_ctl} CTL).
       - If {days_elapsed} > 0, assume the athlete has been training up to this point.
    3. **Periodization:** Ensure the plan peaks exactly on Day {total_days} (Race Day).
    
    OUTPUT FORMAT:
    Return ONLY a raw JSON list of objects. Do not use Markdown.
    Keys: "day_number", "phase", "planned_workout_type", "planned_duration_min", "planned_tss", "description".
    """

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a professional cycling coach backend API."},
                {"role": "user", "content": prompt}
            ]
        )
        
        raw_content = response.choices[0].message.content.strip()
        if raw_content.startswith("```json"): raw_content = raw_content[7:-3]
        elif raw_content.startswith("```"): raw_content = raw_content[3:-3]
            
        return json.loads(raw_content)
        
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return None

# --- 2. Background Worker (The Heavy Lifter) ---
def run_onboarding_process(user_id: str, code: str):
    """
    This runs in the background. It connects Strava, downloads history,
    and marks the profile as 'ready'.
    """
    print(f"⏳ [Background] Starting full onboarding for {user_id}...")
    
    # A. Update DB Status -> 'syncing'
    # (This lets the App know to keep showing the loading spinner)
    supabase.table("profiles").update({"sync_status": "syncing"}).eq("id", user_id).execute()

    try:
        # B. Exchange Code for Access Keys
        print(f"   -> Exchanging OAuth Code...")
        auth_success = exchange_code_for_token(user_id, code)
        
        if not auth_success:
            raise Exception("Strava Token Exchange Failed")

        # C. Download History (The slow part)
        print(f"   -> Fetching History...")
        fetch_past_activities(user_id, days_back=10)
        calculate_daily_metrics(user_id)
        # D. (Optional) Generate First Workout
        # print(f"   -> Generating AI Plan...")
        # generate_workout(user_id)

        # E. Update DB Status -> 'completed'
        supabase.table("profiles").update({"sync_status": "completed"}).eq("id", user_id).execute()
        print(f"✅ [Background] Success! User {user_id} is ready.")

    except Exception as e:
        print(f"❌ [Background] FAILED: {e}")
        # Update DB Status -> 'failed' so the App can show an error message
        supabase.table("profiles").update({"sync_status": "failed"}).eq("id", user_id).execute()

def run_daily_sync(user_id: str): # <--- NEW WORKER
    print(f"🔄 [Background] Syncing daily activities for {user_id}...")
    try:
        # 1. Fetch only recent history (last 3 days is enough for daily)
        fetch_past_activities(user_id, days_back=10)
        
        # 2. Recalculate metrics
        calculate_daily_metrics(user_id)
        
        print(f"✅ [Background] Sync complete for {user_id}")
    except Exception as e:
        print(f"❌ [Background] Sync failed: {e}")

# --- 3. API Endpoints (The Public Door) ---

@app.get("/")
def read_root():
    return {"status": "Virtual Coach Backend is Running 🚀"}

@app.post("/connect-strava")
async def connect_strava(payload: ConnectRequest, background_tasks: BackgroundTasks):
    """
    Receives the Strava Code from the App.
    Returns immediately, but starts the sync in the background.
    """
    # 1. Add the heavy function to the background queue
    background_tasks.add_task(run_onboarding_process, payload.user_id, payload.code)
    
    # 2. Reply instantly to the phone (prevent timeout)
    return {
        "message": "Onboarding started", 
        "user_id": payload.user_id,
        "status": "processing"
    }

@app.post("/sync")
async def sync_user(payload: SyncRequest, background_tasks: BackgroundTasks):
    """
    Called by the App on startup.
    Triggers a background update of Strava activities.
    """
    # Run in background so the App doesn't wait/freeze
    background_tasks.add_task(run_daily_sync, payload.user_id)
    
    return {"status": "queued", "message": "Sync started in background"}

@app.post("/create-journey")
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

# --- 4. The Background Worker ---
def run_ai_plan_generation(journey_id, goal, ftp, weight, start_date, race_date, current_date, current_ctl):
    """
    Background worker that calls the AI and saves the result to the DB.
    """
    # Calculate days just for the log message
    days_count = (race_date - start_date).days + 1
    print(f"🧠 [AI Worker] Generating {days_count} day plan for Journey {journey_id}...")
    
    # 1. Call OpenAI with the specific Dates
    plan_json = generate_ai_plan_logic(goal, start_date, race_date, current_date, ftp, weight, current_ctl) 
    
    if not plan_json:
        supabase.table("journeys").update({"status": "failed"}).eq("id", journey_id).execute()
        return

    # 2. Prepare Rows for Database
    plan_rows = []
    try:
        for day_obj in plan_json:
            # Calculate the actual calendar date: Start Date + (Day Number - 1)
            day_offset = day_obj['day_number'] - 1
            actual_date = start_date + timedelta(days=day_offset)
            
            plan_rows.append({
                "journey_id": journey_id,
                "date": actual_date.isoformat(),
                "day_number": day_obj['day_number'],
                "phase": day_obj.get('phase', 'Build'),
                "planned_workout_type": day_obj.get('planned_workout_type', 'Rest'),
                "planned_duration_min": day_obj.get('planned_duration_min', 0),
                "planned_tss": day_obj.get('planned_tss', 0),
                "description": day_obj.get('description', '')
            })

        # 3. Batch Insert
        print(f"   -> Saving {len(plan_rows)} workouts to database...")
        for k in range(0, len(plan_rows), 100):
            supabase.table("master_plan").insert(plan_rows[k:k+100]).execute()
            
        # 4. Mark Journey as Active
        supabase.table("journeys").update({"status": "active"}).eq("id", journey_id).execute()
        print(f"✅ [AI Worker] Plan saved successfully for Journey {journey_id}")
        
    except Exception as e:
        print(f"❌ [AI Worker] Database Error: {e}")
        supabase.table("journeys").update({"status": "failed"}).eq("id", journey_id).execute()

# --- API: SAVE CHECK-IN ---
@app.post("/check-in")
async def save_checkin(payload: CheckInRequest):
    today = date.today().isoformat()
    
    data = {
        "user_id": payload.user_id,
        "date": today,
        "feel_score": payload.feel_score,
        "soreness_score": payload.soreness_score
    }
    
    # 👇 FIX: Explicitly tell Supabase to check 'user_id' and 'date' for conflicts
    supabase.table("daily_checkins").upsert(data, on_conflict="user_id, date").execute()
    
    return {"status": "success", "data": data}

# --- API: GENERATE WORKOUT ---
@app.post("/generate-workout")
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
