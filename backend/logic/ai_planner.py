import json
from core.config import client

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