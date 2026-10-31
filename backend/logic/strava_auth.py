import logging
import time

from stravalib.client import Client

from core.config import get_settings
from core.db import get_db

log = logging.getLogger(__name__)


def exchange_code_for_token(user_id: str, code: str) -> bool:
    """Swaps the OAuth code for tokens and stores them (server-side only, see the RLS migration)."""
    settings = get_settings()
    client = Client()
    try:
        token_response, athlete = client.exchange_code_for_token(
            client_id=int(settings.strava_client_id),
            client_secret=settings.strava_client_secret,
            code=code,
            return_athlete=True,
        )
    except Exception:
        log.exception("Strava token exchange failed")
        return False

    if athlete is None:
        client.access_token = token_response["access_token"]
        athlete = client.get_athlete()
    athlete_id = athlete.id

    db = get_db()
    db.table("strava_connection").upsert({
        "user_id": user_id,
        "athlete_id": athlete_id,
        "access_token": token_response["access_token"],
        "refresh_token": token_response["refresh_token"],
        "expires_at": token_response["expires_at"],
    }).execute()
    db.table("profiles").update({"strava_connected": True}).eq("id", user_id).execute()
    log.info("Strava connected for user %s", user_id)
    return True


def refresh_access_token(user_id: str, refresh_token: str) -> str:
    settings = get_settings()
    new_tokens = Client().refresh_access_token(
        client_id=int(settings.strava_client_id),
        client_secret=settings.strava_client_secret,
        refresh_token=refresh_token,
    )
    get_db().table("strava_connection").update({
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "expires_at": new_tokens["expires_at"],
    }).eq("user_id", user_id).execute()
    return new_tokens["access_token"]


def get_valid_token(user_id: str) -> str:
    """Returns a usable access token, refreshing it when it expires within five minutes."""
    rows = get_db().table("strava_connection").select("*").eq("user_id", user_id).execute().data
    if not rows:
        raise LookupError(f"User {user_id} has not connected Strava yet")
    conn = rows[0]
    if conn["expires_at"] < time.time() + 300:
        return refresh_access_token(user_id, conn["refresh_token"])
    return conn["access_token"]
