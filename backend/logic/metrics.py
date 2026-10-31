"""Fitness (CTL), fatigue (ATL) and form (TSB) with the exact Banister exponential weights."""
import logging
import math
from datetime import date, timedelta

import numpy as np

from core.dates import today
from core.db import fetch_all, get_db

log = logging.getLogger(__name__)

K_CTL = 42.0
K_ATL = 7.0
CTL_FACTOR = math.exp(-1 / K_CTL)  # ~0.976, weight of yesterday's value
ATL_FACTOR = math.exp(-1 / K_ATL)  # ~0.867


def compute_daily_metrics(daily_tss: dict[date, float], end_date: date) -> list[dict]:
    """One row per day from the first ride to `end_date`.

    CTL and ATL start at the first week's average TSS instead of 0, so the first weeks of
    history do not read as an athlete coming back from a long break.
    """
    if not daily_tss:
        return []
    first_date = min(daily_tss)
    seed = sum(daily_tss.get(first_date + timedelta(days=i), 0) for i in range(7)) / 7 or 10.0
    ctl = atl = prev_ctl = float(seed)
    window: list[float] = []
    rows = []

    current = first_date
    while current <= end_date:
        tss = daily_tss.get(current, 0)
        # CTL = CTL_yesterday * e^(-1/42) + TSS_today * (1 - e^(-1/42)), ATL likewise with 7
        ctl = ctl * CTL_FACTOR + tss * (1 - CTL_FACTOR)
        atl = atl * ATL_FACTOR + tss * (1 - ATL_FACTOR)

        window = (window + [tss])[-7:]
        std = float(np.std(window)) if len(window) > 1 else 0.0
        mean = float(np.mean(window))
        monotony = mean / std if std > 0 else 0.0

        rows.append({
            "date": current.isoformat(),
            "ctl": round(ctl, 2),
            "atl": round(atl, 2),
            "tsb": round(ctl - atl, 2),
            "ramp_rate": round(ctl - prev_ctl, 3),
            "monotony": round(monotony, 2),
            "strain": round(mean * monotony, 1),
        })
        prev_ctl = ctl
        current += timedelta(days=1)
    return rows


def calculate_daily_metrics(user_id: str) -> None:
    db = get_db()
    rides = fetch_all(
        lambda: db.table("activities").select("start_date_local, tss")
        .eq("user_id", user_id).order("start_date_local")
    )
    daily_tss: dict[date, float] = {}
    for r in rides:
        day = date.fromisoformat(r["start_date_local"][:10])
        daily_tss[day] = daily_tss.get(day, 0) + (r["tss"] or 0)

    rows = [{"user_id": user_id, **row} for row in compute_daily_metrics(daily_tss, today())]
    for i in range(0, len(rows), 500):
        db.table("daily_metrics").upsert(rows[i : i + 500]).execute()
    if rows:
        log.info("Metrics for %s: CTL %.1f, TSB %.1f", user_id, rows[-1]["ctl"], rows[-1]["tsb"])
