import os
import re
import xml.etree.ElementTree as ET
from datetime import date
from openai import OpenAI
from dotenv import load_dotenv 
from db import supabase
from auth_manager import login_user

# 1. LOAD ENV
load_dotenv() 
client = OpenAI()

def get_todays_context(user_id):
    today = date.today().isoformat()
    today_date_obj = date.today()
    
    print(f"--- 🧠 GATHERING CONTEXT FOR {today} ---")

    # 1. PROFILE
# 1. PROFILE (Now fetching Max HR)
    profile = supabase.table("profiles").select("ftp, weight_kg, max_heart_rate").eq("id", user_id).execute()
    ftp = profile.data[0]['ftp'] if profile.data else 200
    weight = profile.data[0]['weight_kg'] if profile.data else 75
    max_hr = profile.data[0].get('max_heart_rate', 190) # Default to 190 if missing

    # 2. METRICS (Fitness Level)
    metrics = supabase.table("daily_metrics").select("*").eq("user_id", user_id).eq("date", today).execute()
    stats = metrics.data[0] if metrics.data else None
    
    # 3. JOURNEY MACRO CONTEXT (The "Big Picture")
    # We fetch start_date and race_date to calculate timeline
    journey = supabase.table("journeys")\
        .select("id, name, start_date, race_date")\
        .eq("user_id", user_id)\
        .eq("status", "active")\
        .limit(1)\
        .execute()
    
    plan_data = None
    macro_context = {
        "days_until_race": 999,
        "current_week": 1,
        "total_weeks": 12,
        "journey_name": "General Fitness"
    }
    
    if journey.data:
        j = journey.data[0]
        journey_id = j['id']
        
        # Calculate Timeline
        start_date = date.fromisoformat(j['start_date'])
        race_date = date.fromisoformat(j['race_date'])
        
        days_until = (race_date - today_date_obj).days
        days_since_start = (today_date_obj - start_date).days
        current_week = (days_since_start // 7) + 1
        total_weeks = ((race_date - start_date).days // 7) + 1
        
        macro_context = {
            "days_until_race": days_until,
            "current_week": current_week,
            "total_weeks": total_weeks,
            "journey_name": j['name']
        }

        # Get specific plan for TODAY
        plan = supabase.table("master_plan").select("*").eq("journey_id", journey_id).eq("date", today).execute()
        if plan.data: plan_data = plan.data[0]

    # 4. CHECK-IN
    checkin = supabase.table("daily_checkins").select("*").eq("user_id", user_id).eq("date", today).execute()
    user_feel = checkin.data[0] if checkin.data else None

    # 5. HISTORY
    recent_rides = supabase.table("activities").select("name, tss, start_date").eq("user_id", user_id).order("start_date", desc=True).limit(3).execute()

    return {
        "ftp": ftp,
        "weight": weight,
        "max_hr": max_hr,
        "stats": stats,
        "plan": plan_data,
        "macro": macro_context, # <--- NEW: Contains the timeline info
        "checkin": user_feel,
        "history": recent_rides.data
    }

def create_zwift_file(workout_text, ftp):
    """
    Takes the text workout and converts it into a valid Zwift XML file (.zwo).
    Includes an AI 'Self-Correction' step to minimize errors.
    """
    print("\n--- 🎮 GENERATING ZWIFT FILE ---")
    
    # PROMPT 1: The Draft
    prompt = f"""
You are an expert Zwift Workout converter. Convert the following cycling workout text into a VALID Zwift .zwo XML format.

User FTP: {ftp}

WORKOUT TEXT:
{workout_text}

INSTRUCTIONS & RULES:

1. **File Structure**:
   - The root element must be `<workout_file>`.
   - Inside `<workout_file>`, include the following metadata tags immediately:
     - `<author>Coach</author>`
     - `<name>Zwift Workout</name>` (Or extract a name from the text if present)
     - `<description>Converted from text.</description>` (Or extract a description)
     - `<sportType>bike</sportType>`
   - After the metadata, open a `<workout>` tag. This is where the specific workout steps will go.

2. **Workout Steps (Tag Mapping)**:
   - **Warmup**: Use `<Warmup Duration="seconds" PowerLow="decimal" PowerHigh="decimal"/>` for the initial warming up phase.
   - **Cooldown**: Use `<Cooldown Duration="seconds" PowerLow="decimal" PowerHigh="decimal"/>` for the final cooling down phase.
   - **Steady Efforts**: Use `<SteadyState Duration="seconds" Power="decimal"/>` for blocks of constant intensity.
   - **Intervals**: Use `<IntervalsT Repeat="integer" OnDuration="seconds" OffDuration="seconds" OnPower="decimal" OffPower="decimal"/>` for sets of repeating work/rest efforts.
   - **Ramps**: Use `<Ramp Duration="seconds" PowerLow="decimal" PowerHigh="decimal"/>` for linear increases or decreases in power (that are not the main Warmup or Cooldown).

3. **Calculations**:
   - **Power**: All power values must be relative to the User FTP. Formula: `(Target Watts / {ftp})`.
   - **Rounding**: Round all power fractions to 2 decimal places (e.g., 200W / 250FTP = 0.80).
   - **Duration**: Convert all time inputs (minutes) into seconds (e.g., 10 mins = 600).

4. **Output Format**:
   - Return **ONLY** the raw XML code.
   - Do not include markdown code blocks (```xml).
   - Do not include any conversational text.

Example Output Structure:
<workout_file>
  <author>Coach</author>
  <name>Example</name>
  <description>Test</description>
  <sportType>bike</sportType>
  <workout>
    <Warmup Duration="600" PowerLow="0.50" PowerHigh="0.75"/>
    <SteadyState Duration="300" Power="0.90"/>
    <Cooldown Duration="300" PowerLow="0.75" PowerHigh="0.50"/>
  </workout>
</workout_file>
    """
    
    try:
        # Step 1: Draft using Responses API
        print("   Drafting XML structure...")
        response = client.responses.create(
            model="gpt-5-mini", # Updated model for Responses API
            input=[
                {"role": "system", "content": "You are a Zwift zwo coding expert."}, 
                {"role": "user", "content": prompt}
            ]
        )
        # Use output_text helper
        raw_xml = response.output_text.strip()
        
        # Cleanup Markdown if AI added it
        if raw_xml.startswith("```xml"): raw_xml = raw_xml[6:-3]
        if raw_xml.startswith("```"): raw_xml = raw_xml[3:-3]

        # Step 2: The "Recheck" (AI Peer Review)
        print("   🕵️  AI Re-checking syntax & logic...")
        validation_prompt = f"""
        You are a Zwift XML Validator. Your goal is to ensure the code below is a 100% valid .zwo file.

        XML TO CHECK:
        {raw_xml}

        VALIDATION RULES:
        1. **Structure Check**: 
        - Root element must be `<workout_file>`. 
        - Must contain `<author>`, `<name>`, `<description>`, `<sportType>`, and `<workout>` tags.
        - All tags must be properly closed.

        2. **Attribute Logic Check**:
        - `<SteadyState>` must have `Duration` and `Power`.
        - `<Warmup>` and `<Cooldown>` and `<Ramp>` must have `Duration`, `PowerLow`, and `PowerHigh`. (Do NOT use just `Power` for these).
        - `<IntervalsT>` must have `Repeat`, `OnDuration`, `OffDuration`, `OnPower`, `OffPower`.
        - All `Power` values must be decimals (0.0 to ~2.0). If you see absolute watts (e.g., "200"), convert them assuming an FTP of 250 unless specified otherwise, or flag it.
        - All `Duration` values must be integers (seconds).

        3. **Logical Sanity**:
        - `PowerLow` should generally be lower than `PowerHigh` for Warmups.
        - `Repeat` in IntervalsT must be an integer > 0.

        OUTPUT INSTRUCTIONS:
        - If the XML is perfect: Return the code exactly as is.
        - If there are errors: Fix them silently and return ONLY the corrected XML code.
        - Do NOT include markdown formatting (```xml) or conversational text.
        """
        
        response_val = client.responses.create(
            model="gpt-5-mini",
            input=[
                {"role": "system", "content": "You are a code validator."}, 
                {"role": "user", "content": validation_prompt}
            ]
        )
        final_xml = response_val.output_text.strip()
        
        # Cleanup again just in case
        if final_xml.startswith("```xml"): final_xml = final_xml[6:-3]
        if final_xml.startswith("```"): final_xml = final_xml[3:-3]

        # Step 3: Python Validation (The Final Gatekeeper)
        try:
            ET.fromstring(final_xml)
        except ET.ParseError as e:
            print(f"❌ Python Parse Error: {e}")
            print("   The AI failed to generate valid XML. Skipping file creation.")
            return

        # Step 4: Save File (FORCE UTF-8 ENCODING)
        filename = f"workout_{date.today()}.zwo"
        
        # ⚠️ FIX IS HERE: encoding='utf-8'
        with open(filename, "w", encoding='utf-8') as f:
            f.write(final_xml)
            
        print(f"✅ SUCCESS! File saved: {os.path.abspath(filename)}")
        print("   -> Drag this file into your Documents/Zwift/Workouts folder.")

    except Exception as e:
        print(f"❌ Error creating Zwift file: {e}")

def generate_workout(user_id):
    context = get_todays_context(user_id)
    ftp = context['ftp']
    max_hr = context['max_hr']
    stats = context['stats']
    plan = context['plan']
    macro = context['macro'] # <--- NEW
    checkin = context['checkin']

# --- 1. ASK FOR TIME CONSTRAINT (CRITICAL) ---
    print("\n--- ⏱️ TIME CHECK ---")
    try:
        available_time = int(input("How many minutes do you have to ride today? (e.g. 60): "))
    except ValueError:
        available_time = 60 # Default to 1 hour if user messes up
        print("   (Defaulting to 60 mins)")

    # --- CALCULATE HR ZONES (Standard Cycling Estimates) ---
    # Z1: <60%, Z2: 60-70%, Z3: 70-80%, Z4: 80-90%, Z5: >90%
    hr_zones = {
        "Z1 (Recovery)": f"<{int(max_hr * 0.60)} bpm",
        "Z2 (Endurance)": f"{int(max_hr * 0.60)}-{int(max_hr * 0.70)} bpm",
        "Z3 (Tempo)": f"{int(max_hr * 0.70)}-{int(max_hr * 0.80)} bpm",
        "Z4 (Threshold)": f"{int(max_hr * 0.80)}-{int(max_hr * 0.90)} bpm",
        "Z5 (VO2 Max)": f">{int(max_hr * 0.90)} bpm"
    }
    
    # SYSTEM PROMPT
    system_prompt = """
    You are an elite cycling coach. Prescribe the EXACT daily workout.
    
    TOOLS AVAILABLE:
    - Use Web Search to check route details of the user's Race Goal if applicable.
    
    OUTPUT FORMAT:
    1. TITLE
    2. CONTEXT
    3. THE WORKOUT (Warmup -> Main Set -> Cooldown)
       - For EVERY interval, provide:
         a) Power Target (Watts)
         b) Heart Rate Cap (bpm)
       - Explicitly state: "If HR exceeds [X] bpm, reduce power immediately."
    4. TSS ESTIMATE
    """
    
    # USER SCENARIO
    # We now explicitly explain the "Phase" based on fitness and timeline
    ##(Note: <40 is Beginner, 40-80 is Intermediate, >80 is Advanced)
    user_scenario = f"""
    MACRO CONTEXT:
    - Goal: {macro['journey_name']}
    - Timeline: {macro['days_until_race']} days until race.
    - Phase: Week {macro['current_week']} of {macro['total_weeks']}.
    
    ATHLETE FITNESS:
    - FTP: {ftp}W
    - Max HR: {max_hr} bpm
    - CTL (Fitness): {stats['ctl'] if stats else '0'}  
    
    - TSB (Freshness): {stats['tsb'] if stats else '0'}
    
    HEART RATE ZONES (REFERENCE):
    - {hr_zones}

    TODAY'S PLAN (FROM CALENDAR):
    {f"- Type: {plan['planned_workout_type']}" if plan else "- No scheduled workout."}
    {f"- Description: {plan['description']}" if plan else ""}

    REALITY CHECK (CONSTRAINT):
    - **The user ONLY has {available_time} minutes to ride today.**

    USER FEEDBACK:
    {f"- Mood: {checkin['feel_score']}/5" if checkin else "- No check-in today."}
    {f"- Legs: {checkin['soreness_score']}/5" if checkin else ""}
    
    RECENT HISTORY:
    {context['history']}
    
INSTRUCTIONS:
    1. **TIME LIMIT IS LAW:** The Total Workout Duration MUST be <= {available_time} minutes.
    2. **ADAPT:** If the Planned Duration ({plan['planned_duration_min'] if plan else 0} min) > Available Time ({available_time} min), you MUST increase the intensity to compensate (e.g. change Endurance -> Tempo/Sweet Spot).
    3. **PRESCRIBE:** Define Watt targets based on {ftp}W and HR caps from the zone list.
    4. **SAFETY:** Add the Heart Rate safety valve instruction for every interval.
    """

    print("\n--- 🤖 COACH IS THINKING... ---")
    
    try:
        # UPDATED TO RESPONSES API
        response = client.responses.create(
            model="gpt-5-mini", 
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_scenario}
            ],
            tools=[{"type": "web_search"}]  # <--- Native Web Search Enabled
        )
        
        # Access content via the new helper
        workout_text = response.output_text
        
        print("\n" + "="*40)
        print(workout_text)
        print("="*40)
        
        # --- NEW SECTION: ASK FOR ZWIFT FILE ---
        ask_zwift = input("\n🎮 Do you want to create a Zwift (.zwo) file for this? (y/N): ").lower().strip()
        
        if ask_zwift == 'y':
            create_zwift_file(workout_text, ftp)
        
        return workout_text

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    CURRENT_USER_ID = login_user()
    generate_workout(CURRENT_USER_ID)