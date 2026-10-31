"""Flexible weeks: a plan week is a set of sessions, not a timetable.

Every session has a suggested day but stays open until a ride completes it, on whatever day
that ride happens. Today's session is chosen in code from the open sessions of the current
week: what was planned for today, what is overdue, what matters most, and whether the athlete
is fresh enough for it. Missed sessions of past weeks are not carried over; the next week's
load already builds on what was really ridden.
"""
import math
from datetime import date, timedelta

from core import db

KEY_TYPES = {"FTP Test", "VO2 Max", "Anaerobic", "Threshold", "Sweet Spot"}
INTENSE_TYPES = {"FTP Test", "VO2 Max", "Anaerobic", "Threshold"}  # never the day after a hard ride
EASY_TYPES = {"Recovery", "Endurance"}
HARD_RIDE_IF = 0.75  # a ride at this intensity factor or above was a quality session
MIN_RIDE_S = 15 * 60  # shorter rides (a spin to the shop) complete nothing
LONG_RIDE_S = 90 * 60
FRESH_ENOUGH_TSB = -15  # an FTP test needs reasonably fresh legs to mean anything


# --- plan weeks ---

def week_number(start: date, day: date) -> int:
    return (day - start).days // 7 + 1


def week_bounds(start: date, end: date, week: int) -> tuple[date, date]:
    first = start + timedelta(days=(week - 1) * 7)
    return first, min(first + timedelta(days=6), end)


def ride_intensity(ride: dict) -> float | None:
    """Intensity factor from TSS: TSS = hours × IF² × 100. None if the load is only estimated."""
    if ride.get("tss_source") == "time" or not ride.get("tss") or not ride.get("moving_time"):
        return None
    return math.sqrt(ride["tss"] * 36 / ride["moving_time"])


def is_hard(ride: dict) -> bool:
    return (ride_intensity(ride) or 0) >= HARD_RIDE_IF


# --- matching rides to sessions ---

def _candidates(ride: dict, sessions: list[dict]) -> list[dict]:
    """Open sessions this ride could stand for, best fit first."""
    ride_day = ride["start_date_local"][:10]
    usable = [s for s in sessions if s["planned_workout_type"] not in ("Rest", "Race")]
    usable += [s for s in sessions if s["planned_workout_type"] == "Race" and s["date"] == ride_day]

    def by_day(group):
        """Nearest day first; between equally near days, the session closest in load."""
        ridden, load = date.fromisoformat(ride_day), ride.get("tss") or 0
        return sorted(group, key=lambda s: (abs((date.fromisoformat(s["date"]) - ridden).days),
                                            abs(s["planned_tss"] - load), s["date"]))

    if "ftp" in (ride.get("name") or "").lower():
        tests = [s for s in usable if s["planned_workout_type"] == "FTP Test"]
        if tests:
            return by_day(tests)
    usable = [s for s in usable if s["planned_workout_type"] != "FTP Test"]
    races = [s for s in usable if s["planned_workout_type"] == "Race"]
    if races:
        return races
    if is_hard(ride):
        groups = [[s for s in usable if s["planned_workout_type"] in KEY_TYPES | {"Tempo"}]]
    else:
        endurance = [s for s in usable if s["planned_workout_type"] == "Endurance"]
        longest = max((s["planned_duration_min"] for s in endurance), default=0)
        long_ride = ride["moving_time"] >= max(LONG_RIDE_S, longest * 60 * 0.75) if longest else False
        groups = [[s for s in endurance if s["planned_duration_min"] == longest]] if long_ride else []
        groups.append([s for s in usable if s["planned_workout_type"] in EASY_TYPES | {"Tempo"}])
    for group in groups:
        if group:
            return by_day(group)
    # Nothing of the same kind is open: the ride still counts as the closest session by load.
    return sorted(usable, key=lambda s: abs(s["planned_tss"] - (ride.get("tss") or 0)))


def assign_rides(
    sessions: list[dict], rides: list[dict], prescribed: dict[str, int], start: date, end: date
) -> list[tuple[int, int]]:
    """Pairs (session id, ride id): each ride completes at most one open session of its week.

    A ride on a day with a prescribed workout completes the session that workout was written
    for; other rides complete the open session of their week that fits them best.
    """
    open_by_id = {s["id"]: s for s in sessions if s["status"] == "open"}
    matches = []
    for ride in sorted(rides, key=lambda r: r["start_date_local"]):
        ride_day = date.fromisoformat(ride["start_date_local"][:10])
        if (ride.get("moving_time") or 0) < MIN_RIDE_S or not start <= ride_day <= end:
            continue
        week = week_number(start, ride_day)
        week_open = [s for s in open_by_id.values()
                     if week_number(start, date.fromisoformat(s["date"])) == week]
        chosen = open_by_id.get(prescribed.get(ride_day.isoformat()))
        if chosen and chosen["planned_workout_type"] in KEY_TYPES and ride_intensity(ride) is not None \
                and ride_intensity(ride) < 0.65:
            chosen = None  # an easy spin does not complete the quality session it replaced
        if chosen is None:
            chosen = next(iter(_candidates(ride, week_open)), None)
        if chosen:
            matches.append((chosen["id"], ride["id"]))
            del open_by_id[chosen["id"]]
    return matches


def match_rides(journey: dict) -> int:
    """Marks the sessions that new rides completed; returns how many."""
    sessions = db.query(
        "SELECT id, date, planned_workout_type, planned_duration_min, planned_tss, status, activity_id"
        " FROM master_plan WHERE journey_id = ?",
        [journey["id"]],
    )
    linked = {s["activity_id"] for s in sessions if s["activity_id"]}
    rides = [
        r for r in db.query(
            "SELECT id, start_date_local, name, moving_time, tss, tss_source FROM activities"
            " WHERE athlete_id = ? AND substr(start_date_local, 1, 10) BETWEEN ? AND ?",
            [journey["athlete_id"], journey["start_date"], journey["race_date"]],
        )
        if r["id"] not in linked
    ]
    prescribed = {
        p["date"]: p["plan_id"]
        for p in db.query(
            "SELECT date, plan_id FROM daily_prescriptions WHERE journey_id = ? AND plan_id IS NOT NULL",
            [journey["id"]],
        )
    }
    matches = assign_rides(sessions, rides, prescribed, date.fromisoformat(journey["start_date"]),
                           date.fromisoformat(journey["race_date"]))
    if matches:
        with db.transaction() as conn:
            conn.executemany(
                "UPDATE master_plan SET status = 'done', activity_id = ? WHERE id = ? AND status = 'open'",
                [(ride_id, session_id) for session_id, ride_id in matches],
            )
    return len(matches)


def match_athlete_rides(athlete_id: int) -> None:
    for journey in db.query(
        "SELECT id, athlete_id, start_date, race_date FROM journeys"
        " WHERE athlete_id = ? AND status = 'active'",
        [athlete_id],
    ):
        match_rides(journey)


# --- readiness ---

def forced_recovery_reason(checkin: dict | None, stats: dict | None) -> str | None:
    """Today's hard rules: a recovery session whatever the plan says."""
    if checkin and checkin["feel_score"] <= 2:
        return f"the athlete rates mood/energy {checkin['feel_score']}/5"
    if checkin and checkin["soreness_score"] <= 2:
        return f"the athlete rates their legs {checkin['soreness_score']}/5"
    if stats and stats.get("tsb") is not None and stats["tsb"] <= -30:
        return f"form (TSB) is {stats['tsb']:.0f}"
    return None


def warning_signals(checkins: list[dict], stats: dict | None) -> list[dict]:
    """Patterns over several days that a single check-in does not show.

    `checkins` are the last seven days, newest first. Each signal says whether it forces
    recovery or only rules out hard sessions.
    """
    signals = []
    last5 = checkins[:5]
    low = [c for c in last5 if c["feel_score"] <= 2 or (c.get("motivation_score") or 5) <= 2]
    if len(low) >= 3:
        signals.append({
            "kind": "burnout", "forces": "recovery",
            "message": f"Low energy or motivation on {len(low)} of your last {len(last5)} check-ins."
                       " A few easy days now keep you from burning out.",
        })
    sore = [c for c in checkins[:3] if c["soreness_score"] <= 2]
    if len(sore) >= 2:
        signals.append({
            "kind": "heavy_legs", "forces": "easy",
            "message": "Your legs have been heavy for several days: no hard sessions until they recover.",
        })
    if stats and (stats.get("ctl") or 0) >= 15 and (stats.get("atl") or 0) > 1.5 * stats["ctl"]:
        signals.append({
            "kind": "load_spike", "forces": "easy",
            "message": "This week's load is far above what you are used to: keep today easy.",
        })
    return signals


def readiness(athlete_id: int, day: date) -> dict:
    """Today's check-in, the last week's check-ins, fitness and what they allow today."""
    week_ago = (day - timedelta(days=6)).isoformat()
    checkins = db.query(
        "SELECT date, feel_score, soreness_score, motivation_score, notes FROM daily_checkins"
        " WHERE athlete_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC",
        [athlete_id, week_ago, day.isoformat()],
    )
    stats = db.query_one(
        "SELECT date, ctl, atl, tsb FROM daily_metrics WHERE athlete_id = ? AND date <= ?"
        " ORDER BY date DESC LIMIT 1",
        [athlete_id, day.isoformat()],
    )
    today_checkin = next((c for c in checkins if c["date"] == day.isoformat()), None)
    signals = warning_signals(checkins, stats)
    recovery = forced_recovery_reason(today_checkin, stats) or next(
        (s["message"] for s in signals if s["forces"] == "recovery"), None
    )
    easy = next((s["message"] for s in signals if s["forces"] == "easy"), None)
    fresh = (stats is None or stats.get("tsb") is None or stats["tsb"] >= FRESH_ENOUGH_TSB) and not (
        today_checkin and min(today_checkin["feel_score"], today_checkin["soreness_score"]) < 3
    )
    yesterday = (day - timedelta(days=1)).isoformat()
    rides = db.query(
        "SELECT tss, moving_time, tss_source FROM activities"
        " WHERE athlete_id = ? AND substr(start_date_local, 1, 10) = ?",
        [athlete_id, yesterday],
    )
    return {
        "checkin": today_checkin,
        "checkins": checkins,
        "stats": stats,
        "signals": signals,
        "recovery": recovery,
        "easy": easy,
        "ready_for_test": fresh and not recovery and not easy,
        "hard_yesterday": any(is_hard(r) for r in rides),
    }


# --- today's choice ---

def _weekday(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%A")


def choose_session(week: list[dict], day: date, week_end: date, ready: dict) -> dict:
    """The session to ride today, or a reason to rest or ride easy.

    Returns {"mode": "session" | "recovery" | "rest" | "done", "session": row or None, "reason"}.
    `week` holds the current week's sessions with `status` and, when done, `done_on`.
    """
    today_iso = day.isoformat()
    done_today = [s for s in week if s["status"] == "done" and s.get("done_on") == today_iso]
    if done_today:
        kind = done_today[0]["planned_workout_type"]
        return {"mode": "done", "session": None,
                "reason": f"You rode today's {kind} session. Enjoy the rest."}

    open_ = [s for s in week if s["status"] == "open" and s["planned_workout_type"] != "Rest"
             and (s["planned_workout_type"] != "Race" or s["date"] == today_iso)]
    if ready["recovery"]:
        # A planned recovery ride can be done now; otherwise the spin is extra, outside the plan.
        easy = sorted([s for s in open_ if s["planned_workout_type"] == "Recovery"],
                      key=lambda s: abs((date.fromisoformat(s["date"]) - day).days))
        return {"mode": "recovery", "session": easy[0] if easy else None,
                "reason": f"Recovery today: {ready['recovery']}"}
    if not open_:
        return {"mode": "rest", "session": None,
                "reason": "Every session of this week is done. Rest, or ride easy if you feel like it."}

    blocked = {}
    for s in open_:
        kind = s["planned_workout_type"]
        if ready["easy"] and kind not in EASY_TYPES:
            blocked[s["id"]] = ready["easy"]
        elif kind == "FTP Test" and not ready["ready_for_test"]:
            blocked[s["id"]] = "The FTP test waits for a fresher day, so the result means something."
        elif ready["hard_yesterday"] and kind in INTENSE_TYPES:
            blocked[s["id"]] = "Yesterday was hard, so no intense session today."
    allowed = [s for s in open_ if s["id"] not in blocked]
    planned = next((s for s in open_ if s["date"] == today_iso), None)
    # The FTP test first (later sessions are set from its result), then other key sessions.
    overdue_key = sorted(
        [s for s in allowed if s["date"] < today_iso and s["planned_workout_type"] in KEY_TYPES],
        key=lambda s: (s["planned_workout_type"] != "FTP Test", s["date"]),
    )
    if planned in allowed and (planned["planned_workout_type"] in KEY_TYPES or not overdue_key):
        return {"mode": "session", "session": planned, "reason": "Planned for today."}
    if overdue_key:
        s = overdue_key[0]
        return {"mode": "session", "session": s,
                "reason": f"Moved from {_weekday(s['date'])}: the key session of this week is still open."}
    overdue = sorted([s for s in allowed if s["date"] < today_iso], key=lambda s: s["date"])
    if overdue and not planned:
        s = overdue[0]
        return {"mode": "session", "session": s,
                "reason": f"Moved from {_weekday(s['date'])}; there is still time for it this week."}

    days_left = (week_end - day).days + 1
    if planned is None and len(open_) < days_left:
        return {"mode": "rest", "session": None,
                "reason": f"Rest day. {len(open_)} session{'s' if len(open_) != 1 else ''} left"
                          f" for the {days_left} days until the week ends."}
    upcoming = sorted([s for s in allowed if s["date"] > today_iso], key=lambda s: s["date"])
    if planned and planned["id"] in blocked:
        # Swap with a later session, an easy one if there is one: the blocked session moves back.
        swaps = sorted(upcoming, key=lambda s: s["planned_workout_type"] not in EASY_TYPES)
        if swaps:
            s = swaps[0]
            return {"mode": "session", "session": s,
                    "reason": f"{blocked[planned['id']]} Swapped with {_weekday(s['date'])}'s session."}
        if overdue:
            return {"mode": "session", "session": overdue[0], "reason": blocked[planned["id"]]}
        return {"mode": "recovery", "session": None, "reason": blocked[planned["id"]]}
    if overdue:
        return {"mode": "session", "session": overdue[0],
                "reason": f"Moved from {_weekday(overdue[0]['date'])}."}
    if upcoming:
        s = upcoming[0]
        return {"mode": "session", "session": s,
                "reason": f"Pulled forward from {_weekday(s['date'])}: this week has no spare day for it."}
    reason = next(iter(blocked.values()), "Nothing suits today.")
    return {"mode": "recovery", "session": None, "reason": reason}


def week_sessions(journey: dict, day: date) -> tuple[list[dict], date, date, int]:
    """The plan week that contains `day`, its sessions with status and completing ride."""
    start, end = date.fromisoformat(journey["start_date"]), date.fromisoformat(journey["race_date"])
    clamped = min(max(day, start), end)
    week = week_number(start, clamped)
    first, last = week_bounds(start, end, week)
    rows = db.query(
        "SELECT p.id, p.date, p.phase, p.planned_workout_type, p.planned_duration_min, p.planned_tss,"
        " p.description, p.status, p.activity_id, substr(a.start_date_local, 1, 10) AS done_on,"
        " a.moving_time AS done_moving_time, a.tss AS done_tss"
        " FROM master_plan p LEFT JOIN activities a ON a.id = p.activity_id"
        " WHERE p.journey_id = ? AND p.date BETWEEN ? AND ? ORDER BY p.date",
        [journey["id"], first.isoformat(), last.isoformat()],
    )
    for row in rows:
        row["week_end"] = last.isoformat()
    return rows, first, last, week
