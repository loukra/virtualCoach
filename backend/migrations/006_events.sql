-- Fixed dates the plan works around, kept per athlete: whichever journey covers the date plans
-- for it, also a journey that is only planned later.
--   race: 'A' is a main race (tapered for), 'B' a secondary race ridden from training.
--   ride: a group ride or sportive at endurance pace, on that day for about duration_min.
--   off:  days without training (holiday, travel, illness), start_date to end_date.
-- A race journey's own race stays journeys.race_date; it is not repeated here.
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('race', 'ride', 'off')),
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    priority TEXT CHECK (priority IN ('A', 'B')),
    duration_min INTEGER CHECK (duration_min BETWEEN 20 AND 720),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (end_date >= start_date),
    CHECK ((kind = 'race') = (priority IS NOT NULL)),
    CHECK (kind = 'off' OR end_date = start_date)
);
CREATE INDEX events_athlete_idx ON events (athlete_id, start_date);

-- Set while the plan is rebuilt from next Monday after an event changed; the old plan stays in
-- use until the new one is saved. replan_pending: an event changed during a generation.
ALTER TABLE journeys ADD COLUMN replanning INTEGER NOT NULL DEFAULT 0;
ALTER TABLE journeys ADD COLUMN replan_pending INTEGER NOT NULL DEFAULT 0;
