-- Why the last Strava import failed, in words the app can show; NULL after a successful one.
ALTER TABLE athletes ADD COLUMN sync_error TEXT;
