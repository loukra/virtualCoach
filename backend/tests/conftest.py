import os

# Dummy configuration so modules import without a real .env; no test talks to a real service.
os.environ.update(
    SUPABASE_URL="http://supabase.test",
    SUPABASE_SERVICE_KEY="service-key",
    OPENAI_API_KEY="sk-test",
    STRAVA_CLIENT_ID="1",
    STRAVA_CLIENT_SECRET="secret",
    ALLOWED_USER_IDS="",
)
