-- Virtual Coach schema (SQLite). A few athletes on one server, each with their own token.
-- Dates are ISO strings: 'YYYY-MM-DD' for days, 'YYYY-MM-DDTHH:MM:SS' for times.

CREATE TABLE athletes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE, -- sha256 of the access token; the token itself is never stored
    goal TEXT,
    ftp INTEGER CHECK (ftp BETWEEN 50 AND 600),
    weight_kg REAL CHECK (weight_kg BETWEEN 30 AND 200),
    max_heart_rate INTEGER CHECK (max_heart_rate BETWEEN 120 AND 230),
    strava_connected INTEGER NOT NULL DEFAULT 0,
    sync_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (sync_status IN ('pending', 'syncing', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE strava_connection (
    athlete_id INTEGER PRIMARY KEY REFERENCES athletes (id) ON DELETE CASCADE,
    strava_athlete_id INTEGER NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- FTP valid from a date on, so older rides are scored with the FTP of their day.
CREATE TABLE ftp_history (
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    valid_from TEXT NOT NULL,
    ftp INTEGER NOT NULL CHECK (ftp BETWEEN 50 AND 600),
    PRIMARY KEY (athlete_id, valid_from)
);

CREATE TABLE activities (
    id INTEGER PRIMARY KEY, -- Strava activity id
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    start_date TEXT NOT NULL, -- UTC
    start_date_local TEXT NOT NULL, -- wall-clock time where the ride happened
    sport_type TEXT,
    name TEXT,
    duration_seconds INTEGER,
    moving_time INTEGER,
    tss INTEGER,
    tss_source TEXT CHECK (tss_source IN ('power', 'heart_rate', 'time')),
    average_watts REAL,
    weighted_average_watts INTEGER,
    max_watts INTEGER,
    variability_index REAL,
    average_heartrate REAL,
    max_heartrate INTEGER,
    efficiency_factor REAL,
    elevation_gain INTEGER,
    kilojoules REAL
);
CREATE INDEX activities_local_idx ON activities (athlete_id, start_date_local);

CREATE TABLE daily_metrics (
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    ctl REAL,
    atl REAL,
    tsb REAL,
    ramp_rate REAL,
    monotony REAL,
    strain REAL,
    PRIMARY KEY (athlete_id, date)
);

CREATE TABLE journeys (
    id TEXT PRIMARY KEY, -- uuid
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    race_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'creating'
        CHECK (status IN ('creating', 'active', 'failed', 'archived')),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (race_date >= start_date)
);
CREATE INDEX journeys_athlete_idx ON journeys (athlete_id, created_at);

CREATE TABLE master_plan (
    id INTEGER PRIMARY KEY,
    journey_id TEXT NOT NULL REFERENCES journeys (id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    phase TEXT,
    planned_workout_type TEXT NOT NULL,
    planned_duration_min INTEGER NOT NULL DEFAULT 0,
    planned_tss INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    UNIQUE (journey_id, date)
);

CREATE TABLE daily_checkins (
    athlete_id INTEGER NOT NULL REFERENCES athletes (id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    feel_score INTEGER NOT NULL CHECK (feel_score BETWEEN 1 AND 5),
    soreness_score INTEGER NOT NULL CHECK (soreness_score BETWEEN 1 AND 5),
    notes TEXT,
    PRIMARY KEY (athlete_id, date)
);

CREATE TABLE daily_prescriptions (
    id INTEGER PRIMARY KEY,
    journey_id TEXT NOT NULL REFERENCES journeys (id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    workout_text TEXT NOT NULL, -- markdown rendered by the backend
    workout_json TEXT, -- structured workout (logic.schemas.Workout), source of the .zwo export
    duration_min INTEGER,
    estimated_tss INTEGER,
    recovery_reason TEXT, -- set when a hard rule forced a recovery session
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (journey_id, date)
);

-- One row per LLM attempt: what was asked, how it went, what it cost.
CREATE TABLE ai_generations (
    id INTEGER PRIMARY KEY,
    athlete_id INTEGER, -- no foreign keys: the log outlives deleted athletes and journeys
    journey_id TEXT,
    kind TEXT NOT NULL, -- plan_macro | plan_block | workout
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL, -- prompt file name + content hash
    attempt INTEGER NOT NULL,
    ok INTEGER NOT NULL,
    errors TEXT NOT NULL DEFAULT '[]', -- JSON list of guardrail violations
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ai_generations_created_idx ON ai_generations (created_at);
