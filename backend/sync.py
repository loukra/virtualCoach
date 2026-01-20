import time
import numpy as np
from datetime import datetime, timedelta
from stravalib.client import Client
from core.db import supabase
from auth_manager import login_user

# --- 1. MATH HELPERS (Clean & Modular) ---

def clean_power_spikes(watts_arr, ftp):
    """
    Clips physically impossible power values.
    """
    if watts_arr is None or len(watts_arr) == 0: 
        return np.array([])
    
    # 1500w is a safe hard cap for most non-pro sprinters
    SAFE_MAX_WATTS = 1500 
    cleaned_watts = np.clip(watts_arr, 0, SAFE_MAX_WATTS)
    return cleaned_watts

def calculate_normalized_power(watts_stream):
    """
    Standard NP Formula (Rolling 30s avg ^ 4).
    """
    if watts_stream is None or len(watts_stream) < 30: 
        return 0
    
    rolling_avg = np.convolve(watts_stream, np.ones(30)/30, mode='valid')
    fourth_powers = np.power(rolling_avg, 4)
    avg_fourth = np.mean(fourth_powers)
    np_val = np.power(avg_fourth, 0.25)
    return int(np_val)

def calculate_efficiency_factor(np_val, avg_hr):
    if not np_val or not avg_hr or avg_hr == 0: 
        return 0
    return round(np_val / avg_hr, 2)

def calculate_tss_from_stream(duration_sec, np_val, ftp):
    """
    TSS = (Sec x NP x IF) / (FTP x 3600) x 100
    """
    if not np_val or not ftp: 
        return 0
    
    intensity = np_val / ftp
    # Safety cap: If Intensity Factor is > 1.25, it's likely bad data (or a very short sprint)
    if intensity > 1.25: intensity = 1.25 
    
    tss = (duration_sec * np_val * intensity) / (ftp * 3600) * 100
    return int(tss)

# --- 2. HISTORY ENGINE (The Time Machine) ---

def get_ftp_for_date(activity_date_str, history_list, default_ftp):
    """
    Finds the FTP that was valid on the specific date of the ride.
    """
    if not history_list:
        return default_ftp
        
    # We only need the YYYY-MM-DD part
    act_date = activity_date_str[:10]
    
    # History list is sorted Newest -> Oldest.
    # We look for the first entry that starts BEFORE or ON the activity date.
    for entry in history_list:
        hist_date = entry['valid_from'][:10]
        if hist_date <= act_date:
            return entry['ftp']
            
    # If the ride is older than all history records, use the oldest known FTP
    return history_list[-1]['ftp']

# --- 3. MAIN SYNC LOGIC ---

def fetch_past_activities(user_id: str, days_back=90):
    print(f"--- 🩺 STARTING HISTORICAL SYNC FOR {user_id} ---")
    
    # A. Get Defaults (Current Profile + MAX HR)
    user_profile = supabase.table("profiles").select("ftp, max_heart_rate").eq("id", user_id).execute()
    
    if user_profile.data:
        current_ftp = user_profile.data[0]['ftp']
        # Default to 190 if user hasn't set it yet
        user_max_hr = user_profile.data[0].get('max_heart_rate') or 190 
    else:
        current_ftp = 200
        user_max_hr = 190
        
    print(f"   ℹ️  Using Profile: FTP {current_ftp}w | Max HR {user_max_hr}bpm")

    # B. Get History (All snapshots sorted newest to oldest)
    hist_res = supabase.table("athlete_history")\
        .select("ftp, valid_from")\
        .eq("user_id", user_id)\
        .order("valid_from", desc=True)\
        .execute()
    history_list = hist_res.data if hist_res.data else []
    print(f"   📜 Found {len(history_list)} historical FTP records.")

    # C. Auth
    from auth import get_valid_token 
    try:
        token = get_valid_token(user_id)
    except Exception as e:
        print(f"Skipping: {e}")
        return

    client = Client(access_token=token)
    
    # D. Determine Start Date
    last_ride = supabase.table("activities").select("start_date").eq("user_id", user_id).order("start_date", desc=True).limit(1).execute()
    if last_ride.data:
        last_date_str = last_ride.data[0]['start_date']
        last_date = datetime.fromisoformat(last_date_str.replace('Z', '+00:00'))
        start_fetch_from = last_date + timedelta(seconds=1)
        print(f"🔄 Fetching from: {start_fetch_from}")
    else:
        start_fetch_from = datetime.now() - timedelta(days=days_back)
        print(f"🆕 Fetching last {days_back} days...")

    activities = list(client.get_activities(after=start_fetch_from))
    
    # E. Process Loop
    count = 0
    for act in activities:
        if act.type != "Ride" and act.type != "VirtualRide":
            continue
            
        # 1. Lookup Correct FTP for this specific date
        ride_ftp = get_ftp_for_date(act.start_date.isoformat(), history_list, current_ftp)
        
        print(f"\n   Processing: {act.name} (FTP used: {ride_ftp}w)...")
        
        try:
            streams = client.get_activity_streams(
                act.id, 
                types=['watts', 'heartrate', 'velocity_smooth', 'altitude'], 
                resolution='high'
            )
            time.sleep(0.3) 
        except:
            print("      ⚠️ Stream Error or API Limit")
            streams = {}

        # 2. Calculate Metrics
        np_val = 0
        avg_watts = 0
        max_watts = 0
        vi = 0.0
        
        if 'watts' in streams:
            raw_watts = np.array([x if x is not None else 0 for x in streams['watts'].data])
            # Clip spikes using standard safety limit
            watts_data = clean_power_spikes(raw_watts, ride_ftp)
            
            if len(watts_data) > 0:
                avg_watts = float(np.mean(watts_data))
                max_watts = int(np.max(watts_data))
                np_val = calculate_normalized_power(watts_data)
                
                if avg_watts > 0:
                    vi = round(np_val / avg_watts, 2)

        # Heart Rate
        avg_hr = 0
        max_hr = 0
        if 'heartrate' in streams:
            hr_data = np.array([x if x is not None else 0 for x in streams['heartrate'].data])
            valid_hr = hr_data[hr_data > 0]
            if len(valid_hr) > 0:
                avg_hr = float(np.mean(valid_hr))
                max_hr = int(np.max(valid_hr))
        
        # 3. Derived Calculations
        ef = calculate_efficiency_factor(np_val, avg_hr)
        
        # Duration Fix: Ensure we get integer seconds from timedelta
        moving_time_sec = int(act.moving_time)
        elapsed_time_sec = int(act.elapsed_time)
        
        # --- SMART TSS LOGIC (The Waterfall) ---
        source = "Unknown"
        
        # Priority 1: Power Data (Gold Standard) ⚡
        if np_val > 0:
            tss = calculate_tss_from_stream(moving_time_sec, np_val, ride_ftp)
            source = "Power Data"
            
        # Priority 2: Strava Score (Silver Standard) ❤️
        elif getattr(act, 'suffer_score', None):
            tss = act.suffer_score
            source = "Strava Score"

        # Priority 3: Heart Rate Estimate (Bronze Standard) 🫀
        elif avg_hr > 0:
            # Estimate LTHR as roughly 88% of Max HR
            estimated_lthr = user_max_hr * 0.91
            
            # Calculate Intensity Factor (HR-based)
            hr_if = avg_hr / estimated_lthr
            if hr_if > 1.1: hr_if = 1.1 # Cap for safety
            
            # hrTSS = Duration(hrs) * IF^2 * 100
            hours = moving_time_sec / 3600
            tss = int(hours * (hr_if * hr_if) * 100 / 1.375) 
            source = "HR Calc"

        # Priority 4: Time-Based Estimate (Fallback) ⏳
        else:
            hours = moving_time_sec / 3600
            if hours > 0:
                # Assume moderate pacing (50 TSS/hr)
                tss = int(hours * 50) 
                source = "Time Est"
            else:
                tss = 0

        # 4. Save
        ride_data = {
            "id": act.id,
            "user_id": user_id,
            "start_date": act.start_date.isoformat(),
            "name": act.name,
            "duration_seconds": elapsed_time_sec,
            "moving_time": moving_time_sec,
            "tss": int(tss),
            "average_watts": round(avg_watts, 1),
            "weighted_average_watts": int(np_val), # NP
            "max_watts": max_watts,
            "variability_index": vi,
            "average_heartrate": round(avg_hr, 1),
            "max_heartrate": max_hr,
            "efficiency_factor": ef,
            "elevation_gain": int(act.total_elevation_gain) if act.total_elevation_gain else 0,
            "calories": getattr(act, 'kilojoules', 0) or 0
        }

        try:
            supabase.table("activities").upsert(ride_data).execute()
            print(f"      ✅ Saved: TSS {int(tss)} ({source})")
            count += 1
        except Exception as e:
            print(f"      ❌ DB Error: {e}")

    print(f"\n✅ SYNC COMPLETE. Processed {count} activities.")


def backfill_missing_activities(user_id: str, days_back=90):
    print(f"--- 🕵️ STARTING GAP-FILL SYNC FOR {user_id} (Last {days_back} days) ---")
    
    # 1. SETUP: Get Profile & FTP History (Same as before)
    # We need this to calculate correct TSS for old rides
    user_profile = supabase.table("profiles").select("ftp, max_heart_rate").eq("id", user_id).execute()
    
    if user_profile.data:
        current_ftp = user_profile.data[0]['ftp']
        user_max_hr = user_profile.data[0].get('max_heart_rate') or 190 
    else:
        current_ftp = 200
        user_max_hr = 190

    # Get Historical FTP changes so we use the correct FTP for old rides
    hist_res = supabase.table("athlete_history")\
        .select("ftp, valid_from")\
        .eq("user_id", user_id)\
        .order("valid_from", desc=True)\
        .execute()
    history_list = hist_res.data if hist_res.data else []

    # 2. AUTHENTICATE
    from auth import get_valid_token 
    try:
        token = get_valid_token(user_id)
    except Exception as e:
        print(f"Skipping: {e}")
        return
    client = Client(access_token=token)

    # 3. FETCH LISTS TO COMPARE
    start_date = datetime.now() - timedelta(days=days_back)
    print(f"📅 Looking for gaps since: {start_date.strftime('%Y-%m-%d')}")

    # A. Get IDs we ALREADY have in DB (to avoid duplicates)
    # This prevents us from re-processing rides we already have
    existing_rides_query = supabase.table("activities")\
        .select("id")\
        .eq("user_id", user_id)\
        .gte("start_date", start_date.isoformat())\
        .execute()
    
    # Create a "Set" for instant lookup (O(1) complexity)
    existing_ids = {item['id'] for item in existing_rides_query.data}
    print(f"💾 Database contains {len(existing_ids)} rides in this period.")

    # B. Get list from Strava
    strava_activities = client.get_activities(after=start_date)

    # 4. LOOP AND FILL GAPS
    processed_count = 0
    skipped_count = 0

    for act in strava_activities:
        # CHECK 1: Is it a Ride?
        if act.type != "Ride" and act.type != "VirtualRide":
            continue

        # CHECK 2: Do we already have it? (The Gap-Fill Magic ✨)
        if act.id in existing_ids:
            skipped_count += 1
            continue # Skip immediately, don't fetch streams

        # --- IF WE ARE HERE, IT IS A MISSING RIDE. FETCH IT! ---
        print(f"📥 Found Missing Ride: {act.name} ({act.start_date.date()})")

        # 1. Lookup FTP for that specific date
        ride_ftp = get_ftp_for_date(act.start_date.isoformat(), history_list, current_ftp)

        # 2. Get Streams (This is the "expensive" API call)
        try:
            streams = client.get_activity_streams(
                act.id, 
                types=['watts', 'heartrate', 'velocity_smooth'], 
                resolution='high'
            )
            time.sleep(0.5) # 👈 Important: Sleep to respect rate limits during bulk sync
        except Exception as e:
            print(f"   ⚠️ Stream Error: {e}")
            streams = {}

        # 3. Calculate Metrics (Same logic as your original code)
        np_val = 0
        avg_watts = 0
        max_watts = 0
        vi = 0.0
        avg_hr = 0
        max_hr = 0
        ef = 0

        # -- Power --
        if 'watts' in streams:
            raw_watts = np.array([x if x is not None else 0 for x in streams['watts'].data])
            watts_data = clean_power_spikes(raw_watts, ride_ftp) # Assuming you have this helper
            if len(watts_data) > 0:
                avg_watts = float(np.mean(watts_data))
                max_watts = int(np.max(watts_data))
                np_val = calculate_normalized_power(watts_data) # Assuming helper
                if avg_watts > 0: vi = round(np_val / avg_watts, 2)

        # -- HR --
        if 'heartrate' in streams:
            hr_data = np.array([x if x is not None else 0 for x in streams['heartrate'].data])
            valid_hr = hr_data[hr_data > 0]
            if len(valid_hr) > 0:
                avg_hr = float(np.mean(valid_hr))
                max_hr = int(np.max(valid_hr))
        
        if avg_hr > 0:
            ef = calculate_efficiency_factor(np_val, avg_hr) # Assuming helper

        # 4. Calculate TSS (Waterfall Logic)
        moving_time_sec = int(act.moving_time) # StravaLib returns timedelta
        elapsed_time_sec = int(act.elapsed_time)
        
        tss = 0
        source = "Est"

        if np_val > 0:
            tss = calculate_tss_from_stream(moving_time_sec, np_val, ride_ftp)
            source = "Power"
        elif getattr(act, 'suffer_score', None):
            tss = act.suffer_score
            source = "Strava"
        elif avg_hr > 0:
            # HR Calc Fallback
            estimated_lthr = user_max_hr * 0.91
            hr_if = min((avg_hr / estimated_lthr), 1.1)
            hours = moving_time_sec / 3600
            tss = int(hours * (hr_if * hr_if) * 100 / 1.375)
            source = "HR"
        else:
            hours = moving_time_sec / 3600
            tss = int(hours * 50) # Just guessing

        # 5. Save to DB
        ride_data = {
            "id": act.id,
            "user_id": user_id,
            "start_date": act.start_date.isoformat(),
            "name": act.name,
            "duration_seconds": elapsed_time_sec,
            "moving_time": moving_time_sec,
            "tss": int(tss),
            "average_watts": round(avg_watts, 1),
            "weighted_average_watts": int(np_val),
            "max_watts": max_watts,
            "variability_index": vi,
            "average_heartrate": round(avg_hr, 1),
            "max_heartrate": max_hr,
            "efficiency_factor": ef,
            "elevation_gain": int(act.total_elevation_gain) if act.total_elevation_gain else 0,
            "calories": getattr(act, 'kilojoules', 0) or 0
        }

        try:
            supabase.table("activities").upsert(ride_data).execute()
            print(f"   ✅ Processed & Saved: {act.name} (TSS: {int(tss)})")
            processed_count += 1
        except Exception as e:
            print(f"   ❌ DB Save Error: {e}")

    print(f"\n🏁 BACKFILL COMPLETE.")
    print(f"   - Skipped (Already Existed): {skipped_count}")
    print(f"   - Processed (Newly Added): {processed_count}")


if __name__ == "__main__":
    user_id = login_user()
    fetch_past_activities(user_id)