-- A journey can be created ahead of time ('scheduled'); its plan is generated on its start day,
-- from the fitness of that day. SQLite cannot change a CHECK constraint, so the table is rebuilt
-- (db.migrate turns foreign keys off while migrations run, so plans and workouts stay).
CREATE TABLE journeys_new (
    id TEXT PRIMARY KEY, -- uuid
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    goal_type TEXT NOT NULL DEFAULT 'race' CHECK (goal_type IN ('race', 'build')),
    start_date TEXT NOT NULL,
    race_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'creating'
        CHECK (status IN ('scheduled', 'creating', 'active', 'failed', 'archived')),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (race_date >= start_date)
);
INSERT INTO journeys_new (id, athlete_id, name, goal_type, start_date, race_date, status, error, created_at)
    SELECT id, athlete_id, name, goal_type, start_date, race_date, status, error, created_at FROM journeys;
DROP TABLE journeys;
ALTER TABLE journeys_new RENAME TO journeys;
CREATE INDEX journeys_athlete_idx ON journeys (athlete_id, start_date);
