"""Authentication of the Interview Agent on the internal API (M5 S1; docs/DECISIONS.md D58, D79).

The agent is a separate runtime with no database access (D56). It calls the internal routes with two headers:

- `X-Interview-Agent-Secret`: the shared service secret `INTERVIEW_AGENT_SECRET`. The browser never sees it. Unset, or shorter than
  `INTERVIEW_AGENT_SECRET_MIN_CHARS`, refuses every call (fail closed). A wrong or missing secret is 401 with a fixed body.
- `X-Interview-Agent-Room`: the LiveKit room the agent is in. The room of a session is `room_name(session_id)`, an HMAC-SHA256 of the
  session id under the same secret: derived, never stored, so no migration. A room that is not the session's is the same 404 as an
  unknown session, so a mismatch reveals nothing.

Both comparisons are constant time (`hmac.compare_digest`). The binding keeps one agent job from writing into another session; it does
not protect against someone who holds the secret. `core/security.py` and `core/deps.py` are not used and not changed: these routes never
accept a JWT, and the seeker's routes never accept the secret.
"""
import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import settings
from app.core.errors import AppError

SECRET_HEADER = "X-Interview-Agent-Secret"
ROOM_HEADER = "X-Interview-Agent-Room"
ROOM_PREFIX = "cs-iv-"


def configured_secret() -> str | None:
    """The secret, or None when it is unset or too short to be used."""
    secret = settings.INTERVIEW_AGENT_SECRET
    return secret if len(secret) >= settings.INTERVIEW_AGENT_SECRET_MIN_CHARS else None


def room_name(session_id: int, secret: str) -> str:
    """The LiveKit room of a session (D79). `interview_agent/rooms.py` computes the same; a test checks that both agree."""
    return ROOM_PREFIX + hmac.new(secret.encode("utf-8"), str(session_id).encode("ascii"), hashlib.sha256).hexdigest()


def _same(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _unauthorized() -> AppError:
    return AppError(401, "AGENT_UNAUTHORIZED", "인증되지 않은 요청입니다.")


def authenticated_room(
    secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
    room: Annotated[str | None, Header(alias=ROOM_HEADER)] = None,
) -> str:
    """The room the agent names, once its secret is right. Takes headers only, so FastAPI calls it before it validates the path: a caller
    without the secret gets the 401 and never a validation error."""
    expected = configured_secret()
    if expected is None or secret is None or not _same(secret, expected):
        raise _unauthorized()
    return room or ""


AgentRoom = Annotated[str, Depends(authenticated_room)]


def require_room(session_id: int, room: str) -> None:
    """404 unless `room` is the session's room. Called after `authenticated_room`, so the secret is known to be configured."""
    expected = room_name(session_id, configured_secret() or "")
    if not _same(room, expected):
        raise AppError(404, "INTERVIEW_NOT_FOUND", "모의 면접을 찾을 수 없습니다.")
