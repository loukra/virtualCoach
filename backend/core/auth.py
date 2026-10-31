import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import get_settings
from core.db import get_db

log = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def current_user_id(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Resolves the caller from their Supabase access token. Never trust a user id from the body."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    try:
        res = get_db().auth.get_user(creds.credentials)
    except Exception:
        log.info("Rejected an invalid or expired token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    if not res or not res.user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user_id = res.user.id
    allowed = get_settings().allowed_ids
    if allowed and user_id not in allowed:
        log.warning("User %s is not in ALLOWED_USER_IDS", user_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This user may not use this backend")
    return user_id
