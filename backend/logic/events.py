"""Races, group rides and days off inside a plan, and what each means for the days around it.

Events belong to the athlete, not to a journey: the journey whose dates cover an event plans
for it, also when that journey is only planned later. A race journey's own race (its last day)
counts as a main race.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from core import db
from core.dates import plan_week

EASY_BEFORE = {"A": 2, "B": 1}  # days before a race without hard training
EASY_AFTER = {"A": 2, "B": 1}
DURATION_TOLERANCE = 0.3  # a race or ride day lasts the given time within ±30 %
MAX_OFF_DAYS = 60
PRIORITY_NAMES = {"A": "main race", "B": "secondary race"}


@dataclass
class PlanEvents:
    """Events by plan day number (day 1 is the start date)."""

    races: dict[int, dict] = field(default_factory=dict)  # day -> {priority, name, duration_min}
    rides: dict[int, dict] = field(default_factory=dict)  # day -> {name, duration_min}
    off: dict[int, str] = field(default_factory=dict)  # day -> event name
    easy: dict[int, str] = field(default_factory=dict)  # day -> why it has no hard training
    offset: int = 0

    def week(self, day: int) -> int:
        return plan_week(day, self.offset)

    @property
    def main_race_weeks(self) -> dict[int, str]:
        return {self.week(n): r["name"] for n, r in self.races.items() if r["priority"] == "A"}

    @property
    def race_weeks(self) -> set[int]:
        return {self.week(n) for n in self.races}

    def off_days_in_week(self) -> Counter:
        return Counter(self.week(n) for n in self.off)

    def fixed_days(self) -> set[int]:
        return set(self.races) | set(self.rides) | set(self.off)


def load_events(athlete_id: int, first: date, last: date) -> list[dict]:
    """The athlete's events that touch the days from `first` to `last`."""
    return db.query(
        "SELECT id, kind, name, start_date, end_date, priority, duration_min FROM events"
        " WHERE athlete_id = ? AND start_date <= ? AND end_date >= ? ORDER BY start_date",
        [athlete_id, last.isoformat(), first.isoformat()],
    )


def plan_events(
    rows: list[dict], start: date, total_days: int, goal_type: str = "build", goal_name: str = "",
    after_race_easy_days: int = 0,
) -> PlanEvents:
    ev = PlanEvents(offset=start.weekday())

    def number(iso: str) -> int:
        return (date.fromisoformat(iso) - start).days + 1

    for row in rows:
        first, last = number(row["start_date"]), number(row["end_date"])
        if row["kind"] == "off":
            for n in range(max(1, first), min(last, total_days) + 1):
                ev.off[n] = row["name"]
        elif 1 <= first <= total_days:
            info = {"name": row["name"], "duration_min": row.get("duration_min")}
            if row["kind"] == "race":
                ev.races[first] = {**info, "priority": row["priority"]}
            else:
                ev.rides[first] = info
    if goal_type == "race":
        ev.races[total_days] = {"name": goal_name or "the goal race", "duration_min": None, "priority": "A"}

    for n in range(1, after_race_easy_days + 1):
        ev.easy[n] = "the race just before this plan"
    for n, race in ev.races.items():
        p = race["priority"]
        around = list(range(n - EASY_BEFORE[p], n)) + list(range(n + 1, n + EASY_AFTER[p] + 1))
        for m in around:
            if 1 <= m <= total_days and m not in ev.races and m not in ev.off:
                ev.easy.setdefault(m, f"{PRIORITY_NAMES[p]} \"{race['name']}\"")
    return ev


def place_tests(test_days: list[int], ev: PlanEvents, last_day: int) -> list[int]:
    """FTP tests moved one week later when a race, ride or day off is in the way (the test and
    the easy day before it need to be free); dropped when the next week is no better."""
    after_main = {w + 1 for w in ev.main_race_weeks}
    blocked = ev.fixed_days() | set(ev.easy)

    def fits(n: int) -> bool:
        week = ev.week(n)
        return (n <= last_day and week not in ev.race_weeks and week not in after_main
                and n not in blocked and n - 1 not in blocked)

    placed: list[int] = []
    for n in test_days:
        moved = next((m for m in (n, n + 7) if fits(m) and m not in placed), None)
        if moved is not None:
            placed.append(moved)
    return placed


def _when(n: int, start: date) -> str:
    return f"day {n} ({(start + timedelta(days=n - 1)).strftime('%a %Y-%m-%d')})"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _span(days: list[int]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for n in sorted(days):
        if spans and spans[-1][1] == n - 1:
            spans[-1] = (spans[-1][0], n)
        else:
            spans.append((n, n))
    return spans


def events_text(
    ev: PlanEvents, start: date, first: int = 1, last: int | None = None, macro: bool = False
) -> str:
    """The EVENTS section of a prompt: for the day blocks only the events from `first` to `last`."""
    last = last or 10_000

    def near(n: int) -> bool:  # a race just outside the block still shapes the days next to it
        return first - 3 <= n <= last + 3

    lines = []
    for n, r in sorted(ev.races.items()):
        if not near(n):
            continue
        length = f", about {r['duration_min']} minutes" if r["duration_min"] else ""
        taper = ("taper into it" if r["priority"] == "A"
                 else "no taper, it is ridden from normal training")
        lines.append(f"- {_cap(_when(n, start))}: {PRIORITY_NAMES[r['priority']]} \"{r['name']}\""
                     f"{length}. Race on that day; {taper}.")
    for n, r in sorted(ev.rides.items()):
        if near(n):
            length = f" for about {r['duration_min']} minutes" if r["duration_min"] else ""
            lines.append(f"- {_cap(_when(n, start))}: group ride \"{r['name']}\": Endurance{length}.")
    for a, b in _span(list(ev.off)):
        if a <= last and b >= first:
            what = _when(a, start) if a == b else f"days {a}-{b}"
            lines.append(f"- {_cap(what)}: no training ({ev.off[a]}): Rest.")
    easy = [n for n in ev.easy if first <= n <= last]
    for a, b in _span(easy):
        what = f"Day {a}" if a == b else f"Days {a}-{b}"
        lines.append(f"- {what}: no hard training (next to {ev.easy[a]}): Rest, Recovery or Endurance.")
    if macro:
        for week, name in sorted(ev.main_race_weeks.items()):
            lines.append(f"- Week {week} holds the main race \"{name}\": phase Race, clearly less load"
                         " than the weeks before; the week before it may be a Taper week.")
        for week, count in sorted(ev.off_days_in_week().items()):
            lines.append(f"- Week {week} has {count} day{'s' if count > 1 else ''} without training:"
                         " plan its load for the days left.")
    if not lines:
        return ""
    return "EVENTS (dates fixed by the athlete)\n" + "\n".join(lines) + "\n\n"
