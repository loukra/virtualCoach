import getpass
from backend.core.db import supabase
from auth import get_authorization_url, exchange_code_for_token
from auth_manager import login_user

def reconnect_strava():
    print("\n🔗 --- RECONNECT STRAVA ACCOUNT ---")
    
    # 1. Log in to get your User ID
    # This verifies you are who you say you are
    user_id = login_user()
    
    print(f"\n✅ Logged in as User ID: {user_id}")
    print("   (Your database was likely wiped, so we need to link Strava again.)")

    # 2. Re-Initialize Profile (if missing)
    # If you wiped the DB, your profile row is gone too. We need to put it back.
    profile = supabase.table("profiles").select("*").eq("id", user_id).execute()
    
    if not profile.data:
        print("\n🛠  Re-creating missing Profile...")
        try:
            ftp = int(input("   Enter FTP [200]: ") or 200)
            weight = float(input("   Enter Weight [75]: ") or 75)
            max_hr = int(input("   Enter Max HR [190]: ") or 190)
            
            supabase.table("profiles").insert({
                "id": user_id, 
                "ftp": ftp, 
                "weight_kg": weight,
                "max_heart_rate": max_hr
            }).execute()
            print("   ✅ Profile restored.")
        except Exception as e:
            print(f"   ⚠️ Profile Error: {e}")

    # 3. Strava OAuth Flow
    print("\n🌊 Starting Strava Authorization...")
    url = get_authorization_url()
    
    print(f"\n👉 CLICK THIS LINK TO RE-AUTHORIZE:\n{url}\n")
    
    code = input("Paste the 'code' from the URL here: ").strip()
    
    if exchange_code_for_token(user_id, code):
        print("\n🎉 SUCCESS! Strava is re-connected.")
        print("   You can now run 'python sync.py'")
    else:
        print("\n❌ Failed to connect. Check the code and try again.")

if __name__ == "__main__":
    reconnect_strava()