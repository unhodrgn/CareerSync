"""JWT encode/decode. Login and password hashing belong to the auth feature."""
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings


def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes or settings.JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
