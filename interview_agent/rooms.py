"""The LiveKit room of a session (docs/DECISIONS.md D79): `HMAC-SHA256(secret, session id)`, the formula of the backend's
`app/core/agent_auth.py`. The agent never imports the backend (D56), so it is written here again; a backend test checks that both agree."""
import hashlib
import hmac

ROOM_PREFIX = "cs-iv-"


def room_name(session_id: int, secret: str) -> str:
    return ROOM_PREFIX + hmac.new(secret.encode("utf-8"), str(session_id).encode("ascii"), hashlib.sha256).hexdigest()
