from datetime import timedelta
from core.db import supabase
from auth import exchange_code_for_token
from sync import fetch_past_activities
from analysis import calculate_daily_metrics
from logic.ai_planner import generate_ai_plan_logic

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

        # E. Update DB Status -> 'completed'
        supabase.table("profiles").update({"sync_status": "completed"}).eq("id", user_id).execute()
        print(f"✅ [Background] Success! User {user_id} is ready.")

    except Exception as e:
        print(f"❌ [Background] FAILED: {e}")
        # Update DB Status -> 'failed' so the App can show an error message
        supabase.table("profiles").update({"sync_status": "failed"}).eq("id", user_id).execute()

def run_daily_sync(user_id: str):
    print(f"🔄 [Background] Syncing daily activities for {user_id}...")
    try:
        # 1. Fetch only recent history (last 3 days is enough for daily)
        fetch_past_activities(user_id, days_back=10)
        
        # 2. Recalculate metrics
        calculate_daily_metrics(user_id)
        
        print(f"✅ [Background] Sync complete for {user_id}")
    except Exception as e:
        print(f"❌ [Background] Sync failed: {e}")
      

