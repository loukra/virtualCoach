-- The session the athlete picked, so a cached workout is reused only for the same choice.
-- plan_id stays empty when a recovery spin replaced a quality session it does not complete.
ALTER TABLE daily_prescriptions ADD COLUMN chosen_plan_id INTEGER;

-- Workouts written before sessions could move were always for the session of their own day.
UPDATE daily_prescriptions SET chosen_plan_id = (
    SELECT p.id FROM master_plan p
    WHERE p.journey_id = daily_prescriptions.journey_id AND p.date = daily_prescriptions.date
      AND p.planned_workout_type != 'Rest'
);
UPDATE daily_prescriptions SET plan_id = chosen_plan_id WHERE recovery_reason IS NULL;
