import time
from db import supabase
from auth import get_authorization_url, exchange_code_for_token

# --- CONFIGURATION ---
# This is the fake login your "App" will use
TEST_EMAIL = "admin@virtualcoach.app"
TEST_PASSWORD = "secure_password_123"

def run_first_login():
    print("🚀 STARTING FIRST USER LOGIN...")

    # 1. SIMULATE APP SIGNUP
    # We try to create a user. If they exist, we just log them in.
    print(f"\n--- STEP 1: Creating User ({TEST_EMAIL}) ---")
    
    user_id = None
    
    try:
        # Try to Sign Up (Create new user)
        response = supabase.auth.sign_up({
            "email": TEST_EMAIL, 
            "password": TEST_PASSWORD
        })
        
        # If successful, getting the ID is tricky depending on auto-confirm settings
        if response.user:
            user_id = response.user.id
            print(f"✅ Created New User! ID: {user_id}")
        else:
            # If sign up didn't return a user (maybe requires email confirmation),
            # try signing in instead.
            print("ℹ️ User might already exist, trying to login...")
            raise Exception("Try Login")

    except Exception:
        try:
            # Try to Sign In (Login existing user)
            response = supabase.auth.sign_in_with_password({
                "email": TEST_EMAIL, 
                "password": TEST_PASSWORD
            })
            user_id = response.user.id
            print(f"✅ Logged in as existing user! ID: {user_id}")
        except Exception as e:
            print(f"❌ Login Failed: {e}")
            return

    # 2. CHECK PROFILE (The "Trigger" verification)
    # We pause for 1 second to let the SQL Trigger finish running
    time.sleep(1) 
    
    profile_check = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if profile_check.data:
        print("✅ Profile check passed (SQL Trigger worked).")
    else:
        print("⚠️ Warning: Profile not found. Did you run the SQL Trigger code?")
        # Force create it just in case, so the script doesn't crash
        supabase.table("profiles").insert({"id": user_id, "ftp": 200}).execute()
        print("   (Manually created profile to save you)")

    # 3. CONNECT STRAVA
    print("\n--- STEP 2: Connect Strava ---")
    
    # Generate the link
    url = get_authorization_url()
    print(f"\n👉 CLICK THIS LINK TO AUTHORIZE:\n{url}\n")
    
    print("1. Authorize the App in your browser.")
    print("2. Copy the 'code=' part from the localhost URL.")
    code = input("Paste code here: ").strip()
    
    if not code:
        print("❌ No code entered. Aborting.")
        return

    # Exchange and Save
    success = exchange_code_for_token(user_id, code)
    
    if success:
        print("\n🎉🎉🎉 COMPLETE! 🎉🎉🎉")
        print(f"User {TEST_EMAIL} is now fully ready.")
        print("You can now run 'python sync.py' to get your data.")

if __name__ == "__main__":
    run_first_login()