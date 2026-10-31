"""Fitness (CTL), fatigue (ATL) and form (TSB) with the exact Banister exponential weights."""
import logging
import math
from datetime import date, timedelta

import numpy as np

from core import db
from core.dates import today

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


def calculate_daily_metrics(athlete_id: int) -> None:
    rides = db.query(
        "SELECT start_date_local, tss FROM activities WHERE athlete_id = ? ORDER BY start_date_local",
        [athlete_id],
    )
    daily_tss: dict[date, float] = {}
    for r in rides:
        day = date.fromisoformat(r["start_date_local"][:10])
        daily_tss[day] = daily_tss.get(day, 0) + (r["tss"] or 0)

    rows = compute_daily_metrics(daily_tss, today())
    with db.transaction() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_metrics"
            " (athlete_id, date, ctl, atl, tsb, ramp_rate, monotony, strain)"
            " VALUES (:athlete_id, :date, :ctl, :atl, :tsb, :ramp_rate, :monotony, :strain)",
            [{"athlete_id": athlete_id, **row} for row in rows],
        )
    if rows:
        log.info("Metrics for athlete %s: CTL %.1f, TSB %.1f", athlete_id, rows[-1]["ctl"], rows[-1]["tsb"])
