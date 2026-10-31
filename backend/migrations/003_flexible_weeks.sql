-- Plans become weeks of sessions: a session has a suggested day but stays open until a ride
-- completes it, whatever day that ride happens on.

-- 'race': prepare for an event on race_date. 'build': raise fitness until race_date, which is
-- then simply the last day of the block.
ALTER TABLE journeys ADD COLUMN goal_type TEXT NOT NULL DEFAULT 'race'
    CHECK (goal_type IN ('race', 'build'));

ALTER TABLE master_plan ADD COLUMN status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'done'));
ALTER TABLE master_plan ADD COLUMN activity_id INTEGER; -- the ride that completed the session

-- The session a workout was written for, so the ride that follows completes that session.
ALTER TABLE daily_prescriptions ADD COLUMN plan_id INTEGER;

-- How motivated the athlete is; several low days in a row are an early sign of overreaching.
ALTER TABLE daily_checkins ADD COLUMN motivation_score INTEGER CHECK (motivation_score BETWEEN 1 AND 5);

-- Best 20-minute average power of a ride: an FTP test result, or a hint that FTP has gone up.
ALTER TABLE activities ADD COLUMN best_20min_watts INTEGER;

