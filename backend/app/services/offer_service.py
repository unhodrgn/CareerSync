"""Talent offers: a company invites an anonymous seeker; the seeker accepts or rejects (docs/DECISIONS.md D3, D20).

- One live offer per (company, seeker): a pending (not expired) or accepted one blocks a new offer for any job.
  After a rejection the company cannot offer the same job again; another job is fine (issue 23).
- A company sends at most OFFER_DAILY_LIMIT offers per day (KST). Creation locks the `companies` row, so
  two recruiters of one company cannot create duplicates or overrun the limit at the same time.
- A pending offer expires OFFER_EXPIRY_DAYS after `created_at` (computed, shown as `expired`).
- Accept, reject and cancel are one conditional UPDATE each (`WHERE status = 'pending'` and not expired),
  so of two concurrent answers exactly one wins.
- Contact details (`display_name`, email) reach the company only after `accepted`. The anonymous profile
  is shown only while the seeker is public with current AI consent (Q10); answering stays possible.
"""
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models import Company, JobPosting, TalentOffer, User
from app.models.matching import TalentOfferStatus
from app.schemas.offer import Contact, OfferCreate, OfferJob, SeekerOffer, SentOffer
from app.services import talent_service

KST = timezone(timedelta(hours=9))


def _not_found() -> AppError:
    return AppError(404, "OFFER_NOT_FOUND", "제안을 찾을 수 없습니다.")


def _utc(dt: datetime | None) -> datetime | None:
    """Timestamps out of the API always carry UTC (SQLite returns them naive)."""
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def _expires_at(offer: TalentOffer) -> datetime:
    return _utc(offer.created_at) + timedelta(days=settings.OFFER_EXPIRY_DAYS)


def sent_today(db: Session, company_id: int) -> int:
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return db.scalar(
        select(func.count()).select_from(TalentOffer).where(TalentOffer.company_id == company_id, TalentOffer.created_at >= start)
    )


# ── Company ──


def create(db: Session, user: User, data: OfferCreate) -> TalentOffer:
    job = talent_service.published_own_job(db, user, data.job_id)
    db.execute(select(Company.id).where(Company.id == job.company_id).with_for_update())

    found = next(
        (
            (seeker, pref, profile)
            for seeker, pref, profile in talent_service.public_pool(db, job)
            if talent_service.anonymous_id(job.company_id, seeker.id) == data.anonymous_id
        ),
        None,
    )
    if found is None:
        raise AppError(404, "TALENT_NOT_FOUND", "제안할 수 있는 인재를 찾을 수 없습니다.")
    seeker, pref, profile = found
    offers = list(db.scalars(select(TalentOffer).where(TalentOffer.company_id == job.company_id, TalentOffer.seeker_id == seeker.id)))
    blocking = talent_service.blocking_offer(offers, job.id)
    if blocking is not None and blocking.status == TalentOfferStatus.REJECTED:
        raise AppError(409, "OFFER_REJECTED", "이 공고에 대한 제안을 이미 거절한 인재입니다.")
    if blocking is not None:
        raise AppError(409, "OFFER_EXISTS", "이 인재에게 이미 진행 중이거나 수락된 제안이 있습니다.", offer_id=blocking.id)
    # Same rule as the talent list: the seeker must currently pass Pref and Fit for this job
    if not talent_service.qualifies(db, job, pref, profile):
        raise AppError(404, "TALENT_NOT_FOUND", "제안할 수 있는 인재를 찾을 수 없습니다.")
    if sent_today(db, job.company_id) >= settings.OFFER_DAILY_LIMIT:
        raise AppError(429, "OFFER_DAILY_LIMIT", f"하루에 보낼 수 있는 제안은 {settings.OFFER_DAILY_LIMIT}건입니다.")

    offer = TalentOffer(
        company_id=job.company_id,
        seeker_id=seeker.id,
        job_id=job.id,
        status=TalentOfferStatus.PENDING,
        message=data.message,
        created_at=datetime.now(UTC),
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def sent(db: Session, user: User, job_id: int | None) -> list[TalentOffer]:
    q = select(TalentOffer).where(TalentOffer.company_id == user.company_id)
    if job_id is not None:
        q = q.where(TalentOffer.job_id == job_id)
    return list(db.scalars(q.order_by(TalentOffer.created_at.desc(), TalentOffer.id.desc())))


def _answer(db: Session, offer_id: int, owner, status: str) -> TalentOffer:
    """One conditional UPDATE: only a pending, unexpired offer of this owner changes."""
    now = datetime.now(UTC)
    result = db.execute(
        update(TalentOffer)
        .where(
            TalentOffer.id == offer_id,
            owner,
            TalentOffer.status == TalentOfferStatus.PENDING,
            TalentOffer.created_at > now - timedelta(days=settings.OFFER_EXPIRY_DAYS),
        )
        .values(status=status, responded_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        offer = db.scalars(select(TalentOffer).where(TalentOffer.id == offer_id, owner)).first()
        if offer is None:
            raise _not_found()
        if talent_service.offer_expired(offer):
            raise AppError(409, "OFFER_EXPIRED", "기간이 지난 제안입니다.")
        raise AppError(409, "OFFER_NOT_PENDING", "이미 처리된 제안입니다.", status=offer.status)
    db.commit()
    offer = db.get(TalentOffer, offer_id)
    db.refresh(offer)
    return offer


def cancel(db: Session, user: User, offer_id: int) -> TalentOffer:
    return _answer(db, offer_id, TalentOffer.company_id == user.company_id, TalentOfferStatus.CANCELLED)


# ── Seeker ──


def _seeker_only(user: User) -> None:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")


def mine(db: Session, user: User) -> list[TalentOffer]:
    _seeker_only(user)
    return list(
        db.scalars(
            select(TalentOffer).where(TalentOffer.seeker_id == user.id).order_by(TalentOffer.created_at.desc(), TalentOffer.id.desc())
        )
    )


def respond(db: Session, user: User, offer_id: int, accept: bool) -> TalentOffer:
    """Allowed even after the seeker turned the opt-in off or withdrew AI consent (Q10)."""
    _seeker_only(user)
    status = TalentOfferStatus.ACCEPTED if accept else TalentOfferStatus.REJECTED
    return _answer(db, offer_id, TalentOffer.seeker_id == user.id, status)


# ── Output ──


def _job(db: Session, offer: TalentOffer) -> JobPosting | None:
    return db.get(JobPosting, offer.job_id) if offer.job_id is not None else None


def to_seeker_out(db: Session, offer: TalentOffer) -> SeekerOffer:
    job = _job(db, offer)
    return SeekerOffer(
        offer_id=offer.id,
        company_name=offer.company.name,
        job=OfferJob(job_id=job.id, title=job.title, location=job.location, employment_type=job.employment_type) if job else None,
        message=offer.message,
        status=talent_service.offer_status(offer),
        created_at=_utc(offer.created_at),
        expires_at=_expires_at(offer),
        responded_at=_utc(offer.responded_at),
    )


def to_sent_out(db: Session, offer: TalentOffer) -> SentOffer:
    job = _job(db, offer)
    visible = talent_service.visible_profile(db, offer.seeker_id)
    accepted = offer.status == TalentOfferStatus.ACCEPTED
    return SentOffer(
        offer_id=offer.id,
        job_id=offer.job_id,
        job_title=job.title if job else None,
        anonymous_id=talent_service.anonymous_id(offer.company_id, offer.seeker_id),
        message=offer.message,
        status=talent_service.offer_status(offer),
        created_at=_utc(offer.created_at),
        expires_at=_expires_at(offer),
        responded_at=_utc(offer.responded_at),
        candidate=talent_service.anonymous_profile(*visible) if visible else None,
        contact=Contact(display_name=offer.seeker.display_name, email=offer.seeker.email) if accepted else None,
    )
