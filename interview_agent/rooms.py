"""The room of a session and the dispatch metadata (docs/DECISIONS.md D58, D79): the room is `HMAC-SHA256(secret, session id)`, the formula of the backend's
`app/core/agent_auth.py`. The agent never imports the backend (D56), so it is written here again; a backend test checks that both agree."""
import hashlib
import hmac
import json

ROOM_PREFIX = "cs-iv-"


def room_name(session_id: int, secret: str) -> str:
    return ROOM_PREFIX + hmac.new(secret.encode("utf-8"), str(session_id).encode("ascii"), hashlib.sha256).hexdigest()


def session_id_from_metadata(metadata: str | None) -> int | None:
    """The session id the backend's join token puts in the dispatch metadata, `{"session_id": 12}`; None for anything else (D58: nothing else
    is in it, because a participant can read the metadata of its own token)."""
    try:
        data = json.loads(metadata or "")
    except ValueError:
        return None
    value = data.get("session_id") if isinstance(data, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value < 2**31 else None
