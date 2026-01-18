import time
import getpass
from backend.core.db import supabase
from auth import get_authorization_url, exchange_code_for_token

def register_new_user():
    print("\n🚀 --- NEW USER REGISTRATION ---")
    
    # 1. GET CREDENTIALS
    email = input("Enter new email: ").strip()
    password = getpass.getpass("Enter new password (min 6 chars): ").strip()
    
    # --- NEW: ASK FOR ATHLETE METRICS ---
    print("\n📝 --- ATHLETE PROFILE ---")
    try:
        ftp_input = input("Enter your FTP (Watts) [Default 200]: ").strip()
        ftp = int(ftp_input) if ftp_input else 200
        
        weight_input = input("Enter your Weight (kg) [Default 75]: ").strip()
        weight = float(weight_input) if weight_input else 75.0

        # MAX HEART RATE INPUT
        hr_input = input("Enter Max Heart Rate (bpm) [Default 190]: ").strip()
        max_hr = int(hr_input) if hr_input else 190

    except ValueError:
        print("❌ Invalid number entered. Using defaults (200w / 75kg / 190bpm).")
        ftp = 200
        weight = 75.0
        max_hr = 190
    
    print(f"\n1️⃣  Creating account for {email}...")
    
    try:
        # A. Sign Up
        response = supabase.auth.sign_up({
            "email": email, 
            "password": password
        })
        
        if not response.user:
            print("⚠️ Account created, but email verification is required!")
            return

        user_id = response.user.id
        print(f"✅ User Created! ID: {user_id}")
        
        # B. Create Profile with REAL NUMBERS
        time.sleep(2)
        
        # Check if profile exists (via trigger) or create it
        profile = supabase.table("profiles").select("*").eq("id", user_id).execute()
        
        if not profile.data:
            print(f"   ℹ️  Saving Profile (FTP: {ftp}w | Max HR: {max_hr})...")
            try:
                # 1. Update Current Profile (Fast Access)
                supabase.table("profiles").insert({
                    "id": user_id, 
                    "ftp": ftp, 
                    "weight_kg": weight,
                    "max_heart_rate": max_hr  # <--- ADDED
                }).execute()
                
                # 2. Log History (Permanent Record)
                # Note: We currently only track FTP/Weight changes in history.
                # Max HR rarely changes, so storing it in Profile is usually enough.
                supabase.table("athlete_history").insert({
                    "user_id": user_id,
                    "ftp": ftp,
                    "weight_kg": weight,
                    "valid_from": time.strftime('%Y-%m-%dT%H:%M:%S') 
                }).execute()

            except Exception as e:
                print(f"   ⚠️ Could not create profile: {e}")
        else:
            # If trigger created it with defaults, UPDATE it now
            print(f"   ℹ️  Updating Profile to FTP: {ftp}w...")
            supabase.table("profiles").update({
                "ftp": ftp,
                "weight_kg": weight,
                "max_heart_rate": max_hr  # <--- ADDED
            }).eq("id", user_id).execute()

        # 2. CONNECT STRAVA
        print("\n2️⃣  Connect Strava Account")
        url = get_authorization_url()
        print(f"\n👉 CLICK THIS LINK:\n{url}\n")
        code = input("Paste the 'code' here: ").strip()
        
        if exchange_code_for_token(user_id, code):
            print(f"\n🎉 REGISTRATION COMPLETE for {email}!")
        else:
            print("❌ Strava linking failed.")

    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    register_new_user()