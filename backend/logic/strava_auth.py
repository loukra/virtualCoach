import logging
import time

from stravalib.client import Client

from core import db
from core.config import get_settings

log = logging.getLogger(__name__)


def exchange_code_for_token(athlete_id: int, code: str) -> bool:
    """Swaps the OAuth code for tokens and stores them; they never leave the server."""
    settings = get_settings()
    client = Client()
    try:
        token_response, strava_athlete = client.exchange_code_for_token(
            client_id=int(settings.strava_client_id),
            client_secret=settings.strava_client_secret,
            code=code,
            return_athlete=True,
        )
    except Exception:
        log.exception("Strava token exchange failed")
        return False

    if strava_athlete is None:
        client.access_token = token_response["access_token"]
        strava_athlete = client.get_athlete()

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO strava_connection"
            " (athlete_id, strava_athlete_id, access_token, refresh_token, expires_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (athlete_id) DO UPDATE SET strava_athlete_id = excluded.strava_athlete_id,"
            " access_token = excluded.access_token, refresh_token = excluded.refresh_token,"
            " expires_at = excluded.expires_at, updated_at = CURRENT_TIMESTAMP",
            [athlete_id, strava_athlete.id, token_response["access_token"],
             token_response["refresh_token"], token_response["expires_at"]],
        )
        conn.execute("UPDATE athletes SET strava_connected = 1 WHERE id = ?", [athlete_id])
    log.info("Strava connected for athlete %s", athlete_id)
    return True


def refresh_access_token(athlete_id: int, refresh_token: str) -> str:
    settings = get_settings()
    new_tokens = Client().refresh_access_token(
        client_id=int(settings.strava_client_id),
        client_secret=settings.strava_client_secret,
        refresh_token=refresh_token,
    )
    db.execute(
        "UPDATE strava_connection SET access_token = ?, refresh_token = ?, expires_at = ?,"
        " updated_at = CURRENT_TIMESTAMP WHERE athlete_id = ?",
        [new_tokens["access_token"], new_tokens["refresh_token"], new_tokens["expires_at"], athlete_id],
    )
    return new_tokens["access_token"]


def get_valid_token(athlete_id: int) -> str:
    """Returns a usable access token, refreshing it when it expires within five minutes."""
    conn = db.query_one("SELECT * FROM strava_connection WHERE athlete_id = ?", [athlete_id])
    if conn is None:
        raise LookupError(f"Athlete {athlete_id} has not connected Strava yet")
    if conn["expires_at"] < time.time() + 300:
        return refresh_access_token(athlete_id, conn["refresh_token"])
    return conn["access_token"]
