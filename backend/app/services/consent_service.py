"""Re-consent and withdrawal of AI-analysis consent (docs/DECISIONS.md D17, D81).

No history is kept: `users.consent_*` hold the latest consent only. Withdrawing AI consent stops
every new AI use of the seeker's data (CV upload, apply, recommendation, 다시 분석, a new practice interview or feedback) and takes the
seeker out of the talent pool. A practice interview that is in progress ends with it (D81): the seeker's planning, created and live
sessions become `aborted` with the reason `consent_withdrawn`, in the same transaction, so the Interview Agent and every reader see one state.
Data already stored stays, and a scoring run already queued finishes.
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models import SeekerPreference, User
from app.schemas.auth import ConsentIn
from app.services.interview_service import abort_for_consent_withdrawal


def consent(db: Session, user: User, data: ConsentIn) -> User:
    if data.version != settings.CONSENT_VERSION:
        raise AppError(
            409,
            "CONSENT_VERSION_OUTDATED",
            "동의 문구가 변경되었습니다. 새로고침 후 최신 내용을 확인해 주세요.",
            current_version=settings.CONSENT_VERSION,
        )
    now = datetime.now(UTC)
    user.consent_privacy_at = now
    user.consent_ai_at = now
    user.consent_version = settings.CONSENT_VERSION
    db.commit()
    db.refresh(user)
    return user


def withdraw_ai(db: Session, user: User, *, now: datetime | None = None) -> User:
    """Keeps `consent_version` (the version last agreed to); turns the talent-pool opt-in off; ends the seeker's practice interviews that are
    in progress (D81). All of it is one transaction. `now`: for tests; the real clock by default."""
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")
    user.consent_ai_at = None
    pref = db.scalars(select(SeekerPreference).where(SeekerPreference.seeker_id == user.id)).first()
    if pref is not None:
        pref.profile_public, pref.profile_public_at = False, None
    abort_for_consent_withdrawal(db, user.id, now or datetime.now(UTC))
    db.commit()
    db.refresh(user)
    return user
