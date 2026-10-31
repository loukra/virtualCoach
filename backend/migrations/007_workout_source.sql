-- Who wrote the day's workout: 'ai' (the model, checked by the guardrails), 'code' (the FTP test)
-- or 'fallback' (a standard session built in code when the model could not deliver).
ALTER TABLE daily_prescriptions ADD COLUMN source TEXT NOT NULL DEFAULT 'ai'
    CHECK (source IN ('ai', 'code', 'fallback'));
