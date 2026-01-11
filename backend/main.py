from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from db import supabase

# Import your existing logic
from auth import exchange_code_for_token
from sync import fetch_past_activities
# from coach import generate_workout # Uncomment this when you are ready for AI generation

app = FastAPI()

# --- 1. Data Models (What the App sends us) ---
class ConnectRequest(BaseModel):
    user_id: str
    code: str

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