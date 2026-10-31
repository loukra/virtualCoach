import hashlib
import logging
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import db

log = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def current_athlete(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    """Resolves the athlete from their access token (see manage.py). Never trust an id from the body."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    row = db.query_one("SELECT id FROM athletes WHERE token_hash = ?", [hash_token(creds.credentials)])
    if row is None:
        log.warning("Rejected a request with an unknown token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown token")
    return row["id"]
