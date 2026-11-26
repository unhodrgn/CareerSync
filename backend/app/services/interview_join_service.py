"""The microphone-only LiveKit token of a practice interview (M5 S4; docs/DECISIONS.md D56, D58, D80 (4)).

`issue` is what `POST /api/interview-sessions/{id}/join` calls. It signs a token for the browser of the owning seeker, locally: no network
call, no model, no quota (the create already took the reservation), no database write. The token:

- is scoped to ONE room, the room of the session (`agent_auth.room_name`: HMAC-SHA256 of the session id under the agent secret), so it
  opens nothing else;
- lets the browser publish its MICROPHONE only (`can_publish_sources`), never a camera or a screen, and publish no data;
- lives `INTERVIEW_JOIN_TOKEN_TTL_SECONDS` (two minutes) at most and never past the join deadline of the session. A short lifetime does not
  disconnect a participant who is already in the room (LiveKit refreshes the token of a connected participant);
- carries a random identity and a fixed display name, so no personal data is in it;
- dispatches the Interview Agent into the room when the room is created, with ONLY the session id as metadata, because a participant can
  read the metadata inside its own token (D58). LiveKit applies the room configuration of a token only when it creates the room: a room
  that already exists gets no new dispatch, which is why the room is deleted by the agent and expires 30 seconds after it is empty.

Who may join, in the order of the checks: a seeker (403), the owner of an unexpired session (404, the same for another seeker's, a deleted
and an expired one), the current AI consent (409 `AI_CONSENT_REQUIRED`, the error of `interview_service.consent_required_error`), a session
that is `created` and inside its join time (409 `INTERVIEW_PLANNING` while it is being planned; 409 `INTERVIEW_NOT_JOINABLE` for anything
else: live, over, or past its join deadline; there is no way back into a live interview in M5), and a configured LiveKit project and agent
secret (503 `INTERVIEW_VOICE_UNAVAILABLE`). A joined session starts when the agent stores its first question.

The LiveKit key and secret are read here and in `core/config.py` only, and are never logged or returned.
"""
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from livekit import api
from sqlalchemy.orm import Session

from app.core import agent_auth
from app.core.config import settings
from app.core.errors import AppError
from app.models import User
from app.models.interview import InterviewStatus
from app.services import interview_service
from app.services.interview_time import Clock, as_utc, now_from, utcnow

DISPLAY_NAME = "Candidate"
EMPTY_TIMEOUT_SECONDS = 30  # a room nobody is in is removed after this, so a stale room cannot keep the agent from being dispatched
DEPARTURE_TIMEOUT_SECONDS = 30
MAX_PARTICIPANTS = 3  # the candidate, the agent, and one spare (an avatar worker, later)


@dataclass(frozen=True)
class JoinToken:
    url: str
    token: str
    room: str
    expires_at: datetime


def voice_configured() -> bool:
    return bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET and agent_auth.configured_secret())


def issue(db: Session, user: User, session_id: int, *, clock: Clock = utcnow) -> JoinToken:
    interview_service.seeker_only(user)
    now = now_from(clock)
    row, _title = interview_service.load_own(db, user.id, session_id, now)
    if not interview_service.has_ai_consent(user):
        raise interview_service.consent_required_error()
    eff = interview_service.effective(row, now)
    if eff.status == InterviewStatus.PLANNING:
        raise AppError(409, "INTERVIEW_PLANNING", "The interview is being prepared. Please try again shortly.")
    if not eff.joinable:
        raise AppError(409, "INTERVIEW_NOT_JOINABLE", "You cannot join this practice interview.", status=eff.status)
    if not voice_configured():
        raise AppError(503, "INTERVIEW_VOICE_UNAVAILABLE", "The voice interview cannot be prepared right now.")
    room = agent_auth.room_name(session_id, agent_auth.configured_secret() or "")
    remaining = int((as_utc(eff.active_until) - now).total_seconds())
    ttl = max(1, min(settings.INTERVIEW_JOIN_TOKEN_TTL_SECONDS, remaining))
    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(f"candidate-{secrets.token_hex(6)}")
        .with_name(DISPLAY_NAME)
        .with_ttl(timedelta(seconds=ttl))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
                can_update_own_metadata=True,  # the page sets one attribute, "ready", when it can hear the interviewer
                can_publish_sources=["microphone"],  # never a camera or a screen
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                max_participants=MAX_PARTICIPANTS,
                empty_timeout=EMPTY_TIMEOUT_SECONDS,
                departure_timeout=DEPARTURE_TIMEOUT_SECONDS,
                agents=[api.RoomAgentDispatch(agent_name=settings.INTERVIEW_AGENT_NAME, metadata=json.dumps({"session_id": session_id}))],
            )
        )
        .to_jwt()
    )
    return JoinToken(settings.LIVEKIT_URL, token, room, now + timedelta(seconds=ttl))
