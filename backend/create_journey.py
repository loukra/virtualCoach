import os
import json
import time
from datetime import date, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from db import supabase
from auth_manager import login_user

# Load API Keys
load_dotenv()

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_ai_plan(goal, days, current_ftp, current_weight):
    """
    Asks OpenAI to generate a daily schedule in JSON format.
    """
    print(f"\n🧠 Consulting the AI Coach for a {days}-day plan...")
    
    prompt = f"""
    You are an expert cycling coach. Create a {days}-day training plan for a cyclist.
    
    User Stats:
    - FTP: {current_ftp}W
    - Weight: {current_weight}kg
    - Goal: {goal}
    
    Requirements:
    1. The plan must start at Day 1 and go exactly to Day {days}.
    2. Structure it with Periodization e.g.: Base -> Build -> Peak -> Taper -> Race Day.
    3. Include Rest days.
    
    OUTPUT FORMAT:
    Return ONLY a raw JSON list of objects. Do not use Markdown formatting (no ```json blocks).
    Each object must have these exact keys:
    - "day_number": (integer, 1 to {days})
    - "phase": (string, e.g., "Base 1", "Build 2", "Taper")
    - "planned_workout_type": (string, e.g., "Endurance", "Intervals", "Rest", "Tempo", "Sweet Spot")
    - "planned_duration_min": (integer, 0 for rest)
    - "planned_tss": (integer, 0 for rest)
    - "description": (string, short motivation or focus for the day)
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Use "gpt-3.5-turbo" if you want to save money
            messages=[
                {"role": "system", "content": "You are a professional cycling coach backend API."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        # Clean response (sometimes AI adds markdown backticks)
        raw_content = response.choices[0].message.content.strip()
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:-3]
        elif raw_content.startswith("```"):
            raw_content = raw_content[3:-3]
            
        plan_json = json.loads(raw_content)
        return plan_json
        
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return None

def create_journey(user_id):
    print("\n--- 🏁 START NEW JOURNEY (AI POWERED) ---")
    
    # 1. FETCH & UPDATE PROFILE
    profile_res = supabase.table("profiles").select("ftp, weight_kg").eq("id", user_id).execute()
    current_ftp = profile_res.data[0]['ftp'] if profile_res.data else 200
    current_weight = profile_res.data[0]['weight_kg'] if profile_res.data else 75
    
    print(f"\n📊 Current Stats: FTP {current_ftp}w | Weight {current_weight}kg")
    
    update_q = input("Do you want to update these? (y/N): ").lower().strip()
    if update_q == 'y':
        try:
            new_ftp = int(input(f"New FTP [{current_ftp}]: ") or current_ftp)
            new_weight = float(input(f"New Weight [{current_weight}]: ") or current_weight)
            
            # Update DB (Profile & History)
            supabase.table("profiles").update({"ftp": new_ftp, "weight_kg": new_weight}).eq("id", user_id).execute()
            supabase.table("athlete_history").insert({
                "user_id": user_id,
                "ftp": new_ftp,
                "weight_kg": new_weight,
                "valid_from": date.today().isoformat()
            }).execute()
            print("✅ Profile updated.")
            current_ftp = new_ftp
            current_weight = new_weight
        except ValueError:
            print("❌ Invalid input. Keeping old values.")

    # 2. JOURNEY DETAILS
    journey_name = input("\nName your Goal (e.g. 'Gran Fondo 2026'): ")
    days_until_race = int(input("How many days until the race? (e.g. 90): "))
    
    start_date = date.today()
    race_date = start_date + timedelta(days=days_until_race)
    
    print(f"\nCreating Journey: '{journey_name}'")
    print(f"Start: {start_date} -> Race: {race_date}")
    
    # 3. SAVE JOURNEY TO DB
    data = {
        "user_id": user_id,
        "name": journey_name,
        "start_date": start_date.isoformat(),
        "race_date": race_date.isoformat(),
        "status": "active"
    }
    
    res = supabase.table("journeys").insert(data).execute()
    journey_id = res.data[0]['id']
    
    # 4. GENERATE AI PLAN
    ai_plan = generate_ai_plan(journey_name, days_until_race, current_ftp, current_weight)
    
    if not ai_plan:
        print("❌ Failed to generate plan via AI. Aborting.")
        return

    print(f"   🤖 AI generated {len(ai_plan)} workouts. Saving to database...")

    # 5. PARSE & SAVE TO DB
    plan_rows = []
    
    for day_obj in ai_plan:
        # Calculate the actual calendar date for this "Day X"
        # Day 1 = Start Date, Day 2 = Start Date + 1, etc.
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
        
    # Batch Insert (100 rows at a time)
    for k in range(0, len(plan_rows), 100):
        try:
            supabase.table("master_plan").insert(plan_rows[k:k+100]).execute()
            print(f"      Saved batch {k}-{k+100}...")
        except Exception as e:
            print(f"      ❌ Error saving batch: {e}")
        
    print(f"\n✅ SUCCESS! Your AI Training Plan is ready.")

if __name__ == "__main__":
    current_user_id = login_user()
    create_journey(current_user_id)