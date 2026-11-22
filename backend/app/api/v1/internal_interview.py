"""Internal API of the practice interview, for the Interview Agent only (M5 S1; docs/DECISIONS.md D56, D58, D79).

Two routes, both bound to one session's room and authenticated with the shared agent secret (`app/core/agent_auth.py`), never with a JWT:

- `GET /api/internal/interview-sessions/{session_id}/context`: what the agent needs to run the engine (`interview_agent_service.context`).
  It is also the agent's status poll: a deleted or expired session is 404, an ended one reads `completed` or `aborted`.
- `POST /api/internal/interview-sessions/{session_id}/events`: one turn (`interview_ingest_service.record_turn`) or the end of the
  interview (`record_end`), unchanged. The status codes are the service's (409 `INTERVIEW_SEQ_GAP` with `expected_seq`,
  `INTERVIEW_SEQ_CONFLICT`, `INTERVIEW_ALREADY_ENDED`, `INTERVIEW_NOT_ACTIVE`, 404 `INTERVIEW_NOT_FOUND`, 422 `INTERVIEW_BAD_TURN`, ...).

The secret is checked before the path and the body are validated, so a caller without it only ever gets the 401. The paths are interview
paths: every response carries `Cache-Control: no-store` (D67) and a validation error is sanitized (D68). The clock is the seeker router's
overridable dependency, so one override serves every interview test.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.interview_sessions import ClockDep, SessionIdPath
from app.core import agent_auth
from app.core.deps import DbSession
from app.core.errors import AppError
from app.schemas.interview_internal import AgentContextOut, AgentEventIn, AgentEventOut, TurnEventIn
from app.services import interview_agent_service
from app.services import interview_ingest_service as ingest

router = APIRouter(prefix="/internal/interview-sessions", tags=["interview-agent"])


def bound_session(session_id: SessionIdPath, room: agent_auth.AgentRoom) -> int:
    """The session id, once the agent's secret is right and its room is this session's room."""
    agent_auth.require_room(session_id, room)
    return session_id


BoundSession = Annotated[int, Depends(bound_session)]


def _bad_event() -> AppError:
    return AppError(422, "INTERVIEW_BAD_TURN", "면접 이벤트가 올바르지 않습니다.", field="event")


def _turn(body: TurnEventIn) -> ingest.TurnEvent:
    return ingest.TurnEvent(**body.model_dump())


@router.get(
    "/{session_id}/context",
    response_model=AgentContextOut,
    summary="The Interview Agent reads what it needs to run one session: plan, limits, status, last seq (agent secret and room; read-only)",
)
def agent_context(session_id: BoundSession, db: DbSession, clock: ClockDep):
    return interview_agent_service.context(db, session_id, clock=clock)


@router.post(
    "/{session_id}/events",
    response_model=AgentEventOut,
    summary="The Interview Agent posts one turn or the end of the interview (agent secret and room); stored by the ingestion service",
)
def agent_event(body: AgentEventIn, session_id: BoundSession, db: DbSession, clock: ClockDep):
    if body.type == "turn":
        if body.turn is None or body.coverage is not None or body.closing is not None:
            raise _bad_event()
        turn = ingest.record_turn(db, session_id, _turn(body.turn), clock=clock)
        return {"type": "turn", "outcome": turn.outcome, "seq": turn.seq, "started": turn.started, "dropped_quotes": turn.dropped_quotes}
    if body.turn is not None:
        raise _bad_event()
    end = ingest.record_end(db, session_id, ingest.EndEvent(body.coverage, _turn(body.closing) if body.closing is not None else None), clock=clock)
    return {"type": "end", "outcome": end.outcome, "status": end.status, "end_reason": end.end_reason}
