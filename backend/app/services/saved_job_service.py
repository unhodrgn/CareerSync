"""Saved jobs (공고 저장, docs/DECISIONS.md D45): a seeker's own bookmarks.

Seeker only. Saving needs a job the seeker can see (`job_service.get_visible_job`); removing does not, so a seeker
can drop a job that was closed since. Saving never creates or queues an evaluation (cost rule of D31/D44), and no
company-facing query reads `saved_jobs`, so companies cannot see who saved their jobs.
"""
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import JobPosting, SavedJob, User
from app.services import job_service


def _seeker_only(user: User) -> None:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")


def save(db: Session, user: User, job_id: int) -> None:
    """Idempotent: saving a saved job changes nothing (its saved time stays)."""
    _seeker_only(user)
    job = job_service.get_visible_job(db, job_id, user)
    if db.get(SavedJob, (user.id, job.id)) is not None:
        return
    db.add(SavedJob(user_id=user.id, job_id=job.id))
    try:
        db.commit()
    except IntegrityError:  # the same save from a parallel request won
        db.rollback()


def unsave(db: Session, user: User, job_id: int) -> None:
    """Idempotent: removing a job that is not saved (or no longer exists) is not an error."""
    _seeker_only(user)
    db.execute(delete(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id))
    db.commit()


def list_mine(db: Session, user: User) -> list[JobPosting]:
    """Newest saved first. Closed and expired jobs stay in the list (the response says so)."""
    _seeker_only(user)
    return list(
        db.scalars(
            select(JobPosting)
            .join(SavedJob, SavedJob.job_id == JobPosting.id)
            .where(SavedJob.user_id == user.id)
            .order_by(SavedJob.created_at.desc(), JobPosting.id.desc())
        ).all()
    )
