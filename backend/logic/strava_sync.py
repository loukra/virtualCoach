"""Strava import: fetches missing rides, computes power/HR metrics and TSS, stores them."""
import logging
import threading
import time
from datetime import UTC, datetime, timedelta

import numpy as np
from stravalib.client import Client

from core.db import fetch_all, get_db
from logic.strava_auth import get_valid_token

log = logging.getLogger(__name__)

CYCLING_TYPES = {"Ride", "VirtualRide", "GravelRide", "MountainBikeRide"}
# 1500 W is a safe hard cap for most non-pro sprinters; above that it is a sensor spike.
SAFE_MAX_WATTS = 1500
# Lactate threshold heart rate is roughly 91 % of max HR for trained cyclists.
LTHR_FRACTION = 0.91
# Without power or heart rate, assume a moderate endurance ride.
TIME_ONLY_TSS_PER_HOUR = 50
STREAM_PAUSE_S = 0.5  # spreads stream requests over time for Strava's rate limits

_sync_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


# --- 1. MATH HELPERS ---

def clean_power_spikes(watts_arr) -> np.ndarray:
    if watts_arr is None or len(watts_arr) == 0:
        return np.array([])
    return np.clip(watts_arr, 0, SAFE_MAX_WATTS)


def calculate_normalized_power(watts_stream) -> int:
    """Standard NP: 4th root of the mean of the 30 s rolling average to the 4th power."""
    if watts_stream is None or len(watts_stream) < 30:
        return 0
    rolling_avg = np.convolve(watts_stream, np.ones(30) / 30, mode="valid")
    # round, not int(): float error turns 200 W into 199.999... on some platforms
    return round(float(np.power(np.mean(np.power(rolling_avg, 4)), 0.25)))


def calculate_efficiency_factor(np_val, avg_hr) -> float:
    if not np_val or not avg_hr:
        return 0
    return round(np_val / avg_hr, 2)


def calculate_tss_from_stream(duration_sec, np_val, ftp) -> int:
    """TSS = (sec x NP x IF) / (FTP x 3600) x 100."""
    if not np_val or not ftp:
        return 0
    # An IF above 1.25 is bad data (or a very short sprint), not a real ride.
    intensity = min(np_val / ftp, 1.25)
    return round((duration_sec * np_val * intensity) / (ftp * 3600) * 100)


def calculate_hr_tss(duration_sec, avg_hr, max_hr) -> int:
    """hrTSS: hours x IF^2 x 100 with IF = avg HR / estimated LTHR, on the same scale as TSS."""
    if not avg_hr or not max_hr:
        return 0
    hr_if = min(avg_hr / (max_hr * LTHR_FRACTION), 1.05)
    return round(duration_sec / 3600 * hr_if * hr_if * 100)


def ride_tss(moving_time_sec, np_val, ftp, avg_hr, max_hr) -> tuple[int, str]:
    """Best available load estimate and where it came from."""
    if np_val > 0:
        return calculate_tss_from_stream(moving_time_sec, np_val, ftp), "power"
    if avg_hr > 0:
        return calculate_hr_tss(moving_time_sec, avg_hr, max_hr), "heart_rate"
    return round(moving_time_sec / 3600 * TIME_ONLY_TSS_PER_HOUR), "time"


def get_ftp_for_date(activity_date_str, history_list, default_ftp):
    """The FTP that was valid on the ride's date. `history_list` is sorted newest first."""
    if not history_list:
        return default_ftp
    act_date = activity_date_str[:10]
    for entry in history_list:
        if entry["valid_from"][:10] <= act_date:
            return entry["ftp"]
    return history_list[-1]["ftp"]  # older than all records: oldest known FTP


def _sport_type(act) -> str:
    return str(getattr(act.sport_type, "root", act.sport_type) or "")


def _stream(streams, key) -> np.ndarray:
    if key not in streams:
        return np.array([])
    return np.array([x if x is not None else 0 for x in streams[key].data], dtype=float)


def build_ride(act, streams, user_id, ftp, max_hr) -> dict:
    watts = clean_power_spikes(_stream(streams, "watts"))
    avg_watts = float(np.mean(watts)) if len(watts) else 0.0
    np_val = calculate_normalized_power(watts) if len(watts) else 0

    hr = _stream(streams, "heartrate")
    hr = hr[hr > 0]
    avg_hr = float(np.mean(hr)) if len(hr) else 0.0

    moving_time_sec = int(act.moving_time or 0)
    tss, source = ride_tss(moving_time_sec, np_val, ftp, avg_hr, max_hr)
    return {
        "id": act.id,
        "user_id": user_id,
        "start_date": act.start_date.isoformat(),
        # Strava's local wall-clock time; days are assigned by this, not by UTC.
        "start_date_local": act.start_date_local.replace(tzinfo=None).isoformat(),
        "sport_type": _sport_type(act),
        "name": act.name,
        "duration_seconds": int(act.elapsed_time or 0),
        "moving_time": moving_time_sec,
        "tss": tss,
        "tss_source": source,
        "average_watts": round(avg_watts, 1),
        "weighted_average_watts": np_val,
        "max_watts": int(np.max(watts)) if len(watts) else 0,
        "variability_index": round(np_val / avg_watts, 2) if avg_watts else 0,
        "average_heartrate": round(avg_hr, 1),
        "max_heartrate": int(np.max(hr)) if len(hr) else 0,
        "efficiency_factor": calculate_efficiency_factor(np_val, avg_hr),
        "elevation_gain": int(float(act.total_elevation_gain or 0)),
        "kilojoules": act.kilojoules or 0,
    }


# --- 2. SYNC ---

def _lock_for(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _sync_locks.setdefault(user_id, threading.Lock())


def backfill_missing_activities(user_id: str, days_back: int = 90) -> int | None:
    """Imports every cycling activity of the last `days_back` days that is not stored yet.

    Returns the number of new rides, or None if a sync for this user is already running.
    """
    lock = _lock_for(user_id)
    if not lock.acquire(blocking=False):
        log.info("Sync for %s already running, skipped", user_id)
        return None
    try:
        return _backfill(user_id, days_back)
    finally:
        lock.release()


def _backfill(user_id: str, days_back: int) -> int:
    db = get_db()
    profile = db.table("profiles").select("ftp, max_heart_rate").eq("id", user_id).execute().data
    current_ftp = (profile[0].get("ftp") if profile else None) or 200
    max_hr = (profile[0].get("max_heart_rate") if profile else None) or 190
    history = (
        db.table("athlete_history").select("ftp, valid_from")
        .eq("user_id", user_id).order("valid_from", desc=True).execute()
    ).data or []

    client = Client(access_token=get_valid_token(user_id))
    since = datetime.now(UTC) - timedelta(days=days_back)
    existing = {
        row["id"]
        for row in fetch_all(
            lambda: db.table("activities").select("id")
            .eq("user_id", user_id).gte("start_date", since.isoformat()).order("id")
        )
    }

    added = skipped = 0
    for act in client.get_activities(after=since):
        if _sport_type(act) not in CYCLING_TYPES:
            continue
        if act.id in existing:
            skipped += 1
            continue

        ftp = get_ftp_for_date(act.start_date.isoformat(), history, current_ftp)
        try:
            streams = client.get_activity_streams(
                act.id, types=["watts", "heartrate"], resolution="high"
            )
        except Exception:
            log.warning("No streams for activity %s, using summary data only", act.id)
            streams = {}
        time.sleep(STREAM_PAUSE_S)

        db.table("activities").upsert(build_ride(act, streams, user_id, ftp, max_hr)).execute()
        added += 1

    log.info("Strava sync for %s: %d new, %d already stored", user_id, added, skipped)
    return added
