"""What the Interview Agent may read of a session (M5 S1; docs/DECISIONS.md D58, D79).

The internal context route calls `context`. It takes a session id and no user: the route authenticates the agent and binds it to the
session's room first (`app/core/agent_auth.py`). It is a read: nothing is settled, purged or written, and no model is called.

What the agent gets: the plan the backend stored (canonical, no CV quote, no weight), its digest, the limits the session runs with, the
effective status and deadlines (`interview_time.derive`, so a session past its deadline reads `aborted`), the last stored sequence number,
whether the seeker has the current AI consent (D80), and the seeker's display name as `mask_names`, so that the agent masks the name before
any model sees an answer (D79 (3); the agent keeps it in memory only). Never: the CV, the email, a weight, the feedback, the coverage.
An unknown, deleted or expired session is 404 `INTERVIEW_NOT_FOUND`, as everywhere in the interview API.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn, User
from app.services import interview_service
from app.services.interview_time import Clock, now_from, utcnow


@dataclass(frozen=True)
class AgentContext:
    session_id: int
    status: str  # effective: planning, created, live, completed or aborted
    end_reason: str | None
    joinable: bool
    accepting_turns: bool
    end_grace_open: bool
    active_until: datetime | None
    plan: dict | None
    plan_sha256: str | None
    limits: dict
    last_seq: int
    ai_consent: bool
    mask_names: tuple[str, ...]


def context(db: Session, session_id: int, *, clock: Clock = utcnow) -> AgentContext:
    now = now_from(clock)
    row = db.scalars(select(InterviewSession).where(InterviewSession.id == session_id, InterviewSession.expires_at > now)).first()
    if row is None:
        raise AppError(404, "INTERVIEW_NOT_FOUND", "모의 면접을 찾을 수 없습니다.")
    eff = interview_service.effective(row, now)
    seeker = db.get(User, row.seeker_id)
    last_seq = db.scalar(select(func.coalesce(func.max(InterviewTurn.seq), 0)).where(InterviewTurn.session_id == session_id))
    name = (seeker.display_name or "").strip() if seeker is not None else ""
    result = AgentContext(
        session_id=row.id,
        status=eff.status,
        end_reason=eff.end_reason,
        joinable=eff.joinable,
        accepting_turns=eff.accepting_turns,
        end_grace_open=eff.end_grace_open,
        active_until=eff.active_until,
        plan=row.plan if isinstance(row.plan, dict) else None,
        plan_sha256=row.plan_sha256,
        limits=dict(row.limits) if isinstance(row.limits, dict) else {},
        last_seq=int(last_seq or 0),
        ai_consent=seeker is not None and interview_service.has_ai_consent(seeker),
        mask_names=(name,) if name else (),
    )
    db.rollback()  # a read: end the transaction it opened
    return result
