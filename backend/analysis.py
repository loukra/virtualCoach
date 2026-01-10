import math
import numpy as np
from datetime import date, timedelta, datetime
from db import supabase
from auth_manager import login_user  # <--- THIS WAS MISSING

def calculate_daily_metrics(user_id: str):
    print(f"--- 📊 STARTING ANALYSIS WITH EXACT BANISTER FORMULA ---")
    
    # 1. Fetch all rides
    response = supabase.table("activities")\
        .select("start_date, tss, efficiency_factor")\
        .eq("user_id", user_id)\
        .order("start_date")\
        .execute()
    
    rides = response.data
    if not rides:
        print("❌ No rides found.")
        return

    # 2. Map Data
    daily_data_map = {}
    for r in rides:
        d_str = r['start_date'].split('T')[0] 
        d_date = date.fromisoformat(d_str)
        
        if d_date not in daily_data_map:
            daily_data_map[d_date] = {'tss': 0, 'ef': []}
        
        daily_data_map[d_date]['tss'] += (r['tss'] or 0)
        if r['efficiency_factor']:
            daily_data_map[d_date]['ef'].append(r['efficiency_factor'])

    # 3. SEEDING (First 7 days average)
    first_date = sorted(daily_data_map.keys())[0]
    
    first_week_tss = []
    for i in range(7):
        d = first_date + timedelta(days=i)
        val = daily_data_map.get(d, {}).get('tss', 0)
        first_week_tss.append(val)
    
    avg_start_tss = sum(first_week_tss) / 7
    if avg_start_tss == 0: avg_start_tss = 10 
    
    print(f"   🌱 Seeding Initial Fitness (CTL) at: {round(avg_start_tss, 1)}")

    ctl = float(avg_start_tss)
    atl = float(avg_start_tss) 
    
    # 4. EXACT CONSTANTS (Pre-calculated for speed)
    # Formula: Factor = e^(-1/k)
    k_ctl = 42.0
    k_atl = 7.0
    
    # Weight for Yesterday
    ctl_factor = math.exp(-1 / k_ctl)  # ~0.976
    atl_factor = math.exp(-1 / k_atl)  # ~0.867
    
    # Weight for Today (1 - Factor)
    ctl_inv = 1.0 - ctl_factor
    atl_inv = 1.0 - atl_factor
    
    tss_history_7d = [] 
    updates = []
    
    today = date.today()
    current_date = first_date
    prev_ctl = ctl

    while current_date <= today:
        day_data = daily_data_map.get(current_date, {'tss': 0, 'ef': []})
        todays_tss = day_data['tss']
        
        # --- THE EXACT MATH ---
        # CTL = (CTL_yesterday * e^-1/42) + (TSS_today * (1 - e^-1/42))
        ctl = (ctl * ctl_factor) + (todays_tss * ctl_inv)
        
        # ATL = (ATL_yesterday * e^-1/7) + (TSS_today * (1 - e^-1/7))
        atl = (atl * atl_factor) + (todays_tss * atl_inv)
        
        tsb = ctl - atl
        
        ramp_rate = ctl - prev_ctl
        prev_ctl = ctl
        
        # Monotony & Strain
        tss_history_7d.append(todays_tss)
        if len(tss_history_7d) > 7: tss_history_7d.pop(0)
            
        if len(tss_history_7d) > 1:
            avg = np.mean(tss_history_7d)
            std = np.std(tss_history_7d)
            monotony = avg / std if std > 0 else 0
            strain = avg * monotony
        else:
            monotony = 0
            strain = 0

        # Save
        updates.append({
            "user_id": user_id,
            "date": current_date.isoformat(),
            "ctl": round(ctl, 2),
            "atl": round(atl, 2),
            "tsb": round(tsb, 2),
            "ramp_rate": round(ramp_rate, 3),
            "monotony": round(monotony, 2),
            "strain": round(strain, 1)
        })
        
        current_date += timedelta(days=1)

    # Bulk Insert
    batch_size = 100
    for i in range(0, len(updates), batch_size):
        try:
            supabase.table("daily_metrics").upsert(updates[i:i+batch_size]).execute()
        except Exception as e:
            print(f"Error saving batch: {e}")

    print(f"✅ DONE. Exact Math Applied -> Fitness: {round(ctl,1)} | Form: {round(tsb,1)}")

if __name__ == "__main__":
    CURRENT_USER_ID = login_user()
    calculate_daily_metrics(CURRENT_USER_ID)