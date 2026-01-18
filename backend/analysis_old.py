import numpy as np
from datetime import date, timedelta, datetime
from backend.core.db import supabase

def calculate_daily_metrics(user_id: str):
    print(f"--- 📊 STARTING ADVANCED ANALYSIS FOR {user_id} ---")
    
    # 1. Fetch all rides (Now with accurate TSS & EF from your Pro Sync)
    response = supabase.table("activities")\
        .select("start_date, tss, efficiency_factor")\
        .eq("user_id", user_id)\
        .order("start_date")\
        .execute()
    
    rides = response.data
    if not rides:
        print("❌ No rides found. Run sync.py first.")
        return

    # 2. Map Data to Dates
    # We create a timeline dictionary: "2023-10-01" -> {tss: 50, ef: 1.2}
    daily_data_map = {}
    for r in rides:
        d_str = r['start_date'].split('T')[0] 
        d_date = date.fromisoformat(d_str)
        
        if d_date not in daily_data_map:
            daily_data_map[d_date] = {'tss': 0, 'ef': []}
        
        daily_data_map[d_date]['tss'] += (r['tss'] or 0)
        if r['efficiency_factor']:
            daily_data_map[d_date]['ef'].append(r['efficiency_factor'])

    # 3. Setup Math Variables
    # Standard Coggan Constants
    ctl = 0.0  # Fitness (42d avg)
    atl = 0.0  # Fatigue (7d avg)
    ctl_decay = 42.0
    atl_decay = 7.0
    
    # We need a history buffer for Monotony (last 7 days of TSS)
    tss_history_7d = [] 
    
    updates = []
    
    # Start loop from the first ride found
    first_date = sorted(daily_data_map.keys())[0]
    today = date.today()
    current_date = first_date
    
    # Store previous CTL to calculate Ramp Rate
    prev_ctl = 0.0

    while current_date <= today:
        # Get today's values
        day_data = daily_data_map.get(current_date, {'tss': 0, 'ef': []})
        todays_tss = day_data['tss']
        
        # 1. Basic Banister Model (Fitness/Fatigue)
        ctl = ctl + (todays_tss - ctl) / ctl_decay
        atl = atl + (todays_tss - atl) / atl_decay
        tsb = ctl - atl
        
        # 2. Ramp Rate (How much did Fitness increase since yesterday?)
        # A jump of >2.5 per week (approx 0.35 per day) is risky.
        ramp_rate = ctl - prev_ctl
        prev_ctl = ctl
        
        # 3. Monotony & Strain (The "Boredom" Safety Check)
        # Update rolling 7-day history
        tss_history_7d.append(todays_tss)
        if len(tss_history_7d) > 7:
            tss_history_7d.pop(0) # Keep size at 7
            
        if len(tss_history_7d) > 1:
            avg_daily_load = np.mean(tss_history_7d)
            std_dev_load = np.std(tss_history_7d)
            
            # Avoid division by zero if standard deviation is 0 (perfectly identical rides)
            if std_dev_load == 0:
                monotony = 0 # Or technically infinity, but 0 implies no variation logic
            else:
                monotony = avg_daily_load / std_dev_load
                
            strain = avg_daily_load * monotony
        else:
            monotony = 0
            strain = 0

        # 4. EF Trend (Aerobic Efficiency)
        # If there is EF data today, smooth it. 
        # (We could do a rolling average, but for now we store raw or simple trend)
        daily_ef_avg = np.mean(day_data['ef']) if day_data['ef'] else None

        # Prepare DB Row
        updates.append({
            "user_id": user_id,
            "date": current_date.isoformat(),
            "ctl": round(ctl, 2),
            "atl": round(atl, 2),
            "tsb": round(tsb, 2),
            "ramp_rate": round(ramp_rate, 3),
            "monotony": round(monotony, 2),
            "strain": round(strain, 1),
            "ef_trend": round(daily_ef_avg, 2) if daily_ef_avg else None
        })
        
        current_date += timedelta(days=1)

    # 4. Bulk Save (Chunks of 100)
    print(f"Calculated metrics for {len(updates)} days.")
    batch_size = 100
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]
        try:
            supabase.table("daily_metrics").upsert(batch).execute()
        except Exception as e:
            print(f"❌ Batch Error: {e}")

    # Summary
    print(f"✅ DONE.")
    print(f"   Fitness (CTL): {round(ctl,1)}")
    print(f"   Fatigue (ATL): {round(atl,1)}")
    print(f"   Form (TSB): {round(tsb,1)}")
    print(f"   Ramp Rate: {round(ramp_rate,3)} (Keep < 0.4/day)")
    print(f"   Monotony: {round(monotony,2)} (Keep < 2.0)")

if __name__ == "__main__":
    CURRENT_USER_ID = "138e040d-1572-4054-bc02-ac63d16edea0"
    calculate_daily_metrics(CURRENT_USER_ID)