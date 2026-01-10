from db import supabase
from datetime import date
from auth_manager import login_user

def submit_checkin(user_id):
    print("\n--- ☀️ GOOD MORNING! DAILY CHECK-IN ---")
    
    try:
        # We use 'or 3' to provide a default if you just press Enter
        feel_input = input("How do you feel today? (1=Terrible, 5=Great): ")
        feel = int(feel_input) if feel_input else 3
        
        soreness_input = input("How are the legs? (1=Painful, 5=Fresh): ")
        soreness = int(soreness_input) if soreness_input else 3
        
        notes = input("Any notes? (e.g. 'Bad sleep'): ")
        
        data = {
            "user_id": user_id,
            "date": date.today().isoformat(),
            "feel_score": feel,
            "soreness_score": soreness,
            "notes": notes
        }
        
        # ⚠️ THE FIX IS HERE:
        # We add 'on_conflict' to tell Supabase: 
        # "If this User+Date combination exists, UPDATE it instead of crashing."
        supabase.table("daily_checkins").upsert(data, on_conflict="user_id, date").execute()
        
        print("✅ Check-in saved.")
        
    except ValueError:
        print("❌ Please enter numbers for scores.")

if __name__ == "__main__":
    # Ensure we use the logged-in user, not a hardcoded ID
    CURRENT_USER_ID = login_user()
    submit_checkin(CURRENT_USER_ID)