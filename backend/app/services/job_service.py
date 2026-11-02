"""Job postings: draft → published → closed.

Only drafts can be deleted (applications exist only after publish). After publish only the
fields in EDITABLE_AFTER_PUBLISH change, because applicant scores were computed from the rest.
A passed deadline hides a job from the public list but never changes its status: status changes
are recruiter actions.
"""
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ai.jd.tags import job_tags, matches_tag
from app.core.config import settings
from app.core.errors import AppError
from app.models import JobCriterion, JobPosting, User
from app.models.job import EDITABLE_AFTER_PUBLISH, JobStatus
from app.schemas.job import JobCreate, JobUpdate
from app.services import ai_runtime


def _not_found() -> AppError:
    return AppError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")


def _check_deadline(deadline: date | None) -> None:
    if deadline is not None and deadline < date.today():
        raise AppError(422, "DEADLINE_IN_PAST", "마감일은 오늘 이후여야 합니다.")


def criteria_counts(db: Session, job_ids: list[int]) -> dict[int, int]:
    if not job_ids:
        return {}
    rows = db.execute(
        select(JobCriterion.job_id, func.count()).where(JobCriterion.job_id.in_(job_ids)).group_by(JobCriterion.job_id)
    )
    return dict(rows.all())


# ── Access ──


def get_owned_job(db: Session, job_id: int, user: User) -> JobPosting:
    """The job if it belongs to the user's company. 404 otherwise, so other companies' job ids are not probeable."""
    job = db.get(JobPosting, job_id)
    if job is None or user.role != "company" or job.company_id != user.company_id:
        raise _not_found()
    return job


def get_published_job(db: Session, job_id: int) -> JobPosting:
    job = db.get(JobPosting, job_id)
    if job is None or job.status != JobStatus.PUBLISHED:
        raise _not_found()
    return job


def get_visible_job(db: Session, job_id: int, user: User | None) -> JobPosting:
    """Guests (user None) see published, unexpired jobs. Logged-in users also see expired published
    jobs; the owner also sees drafts and closed jobs."""
    job = db.get(JobPosting, job_id)
    if job is None:
        raise _not_found()
    if user is None:
        if job.status == JobStatus.PUBLISHED and (job.deadline is None or job.deadline >= date.today()):
            return job
        raise _not_found()
    if job.status == JobStatus.PUBLISHED or (user.role == "company" and job.company_id == user.company_id):
        return job
    raise _not_found()


# ── Writes ──


def create(db: Session, user: User, data: JobCreate) -> JobPosting:
    _check_deadline(data.deadline)
    job = JobPosting(company_id=user.company_id, **data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update(db: Session, job: JobPosting, data: JobUpdate) -> JobPosting:
    changes = data.model_dump(exclude_unset=True)
    if job.status == JobStatus.CLOSED:
        raise AppError(409, "JOB_CLOSED", "마감된 공고는 수정할 수 없습니다.")
    if job.status == JobStatus.PUBLISHED and (locked := sorted(set(changes) - EDITABLE_AFTER_PUBLISH)):
        raise AppError(
            409,
            "JOB_FIELD_LOCKED",
            "게시된 공고는 마감일, 근무지, 급여 안내만 수정할 수 있습니다.",
            fields=locked,
        )
    for field in ("title", "description", "employment_type", "location", "salary_note"):
        if field in changes and changes[field] is None:
            raise AppError(422, "FIELD_REQUIRED", "이 항목은 비울 수 없습니다.", fields=[field])
    if "deadline" in changes:
        _check_deadline(changes["deadline"])
    for field, value in changes.items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


def publish(db: Session, job: JobPosting) -> JobPosting:
    from app.services.criteria_service import assert_publishable  # criteria_service imports this module

    if job.status != JobStatus.DRAFT:
        raise AppError(409, "JOB_NOT_DRAFT", "작성 중인 공고만 게시할 수 있습니다.")
    if not job.description.strip():
        raise AppError(422, "JOB_INCOMPLETE", "공고 내용(직무 설명)을 입력해야 게시할 수 있습니다.", fields=["description"])
    if job.category is None:
        raise AppError(422, "FIELD_REQUIRED", "직무 분야를 선택해야 게시할 수 있습니다.", fields=["category"])
    _check_deadline(job.deadline)
    assert_publishable(job)
    job.status = JobStatus.PUBLISHED
    job.published_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job


def close(db: Session, job: JobPosting) -> JobPosting:
    if job.status != JobStatus.PUBLISHED:
        raise AppError(409, "JOB_NOT_PUBLISHED", "게시 중인 공고만 마감할 수 있습니다.")
    job.status = JobStatus.CLOSED
    job.closed_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job


def delete(db: Session, job: JobPosting) -> None:
    if job.status != JobStatus.DRAFT:
        raise AppError(409, "JOB_NOT_DRAFT", "작성 중인 공고만 삭제할 수 있습니다.")
    db.delete(job)
    db.commit()


# ── Tags (D45) ──


def tags(job: JobPosting) -> list[str]:
    """Skills the job's criteria and JD name, computed on read (not stored); display and search only, never scored."""
    criteria = [f"{c.name}: {c.description}".strip() for c in job.criteria]
    return job_tags(criteria, f"{job.title}\n{job.description}", ai_runtime.skills(), settings.JOB_TAGS_MAX)


# ── Lists ──


def _region_filter(region: str):
    prefixes = settings.JOB_REGIONS.get(region)
    if prefixes is None:
        raise AppError(422, "REGION_INVALID", "지원하지 않는 지역입니다.", regions=list(settings.JOB_REGIONS))
    return or_(*(func.ltrim(JobPosting.location).like(f"{p}%") for p in prefixes))


def list_public(
    db: Session, q: str | None, category: str | None, region: str | None, limit: int, offset: int
) -> tuple[list[JobPosting], int]:
    """Published jobs whose deadline has not passed, newest first, filtered by category and region (D45).

    `q` matches the title, the company name or a tag. Tags are computed, not stored, so with `q` the matching jobs
    are filtered in Python and paged there; that reads every job passing the other filters (fine at demo scale).
    """
    where = [
        JobPosting.status == JobStatus.PUBLISHED,
        or_(JobPosting.deadline.is_(None), JobPosting.deadline >= date.today()),
    ]
    if category:
        where.append(JobPosting.category == category)
    if region:
        where.append(_region_filter(region))
    newest = (JobPosting.published_at.desc(), JobPosting.id.desc())
    text = (q or "").strip()
    if not text:
        total = db.scalar(select(func.count()).select_from(JobPosting).where(*where))
        jobs = db.scalars(select(JobPosting).where(*where).order_by(*newest).limit(limit).offset(offset)).all()
        return list(jobs), total
    candidates = db.scalars(
        select(JobPosting).where(*where).options(selectinload(JobPosting.criteria), selectinload(JobPosting.company)).order_by(*newest)
    ).all()
    needle, skills = text.casefold(), ai_runtime.skills()
    hits = [
        j for j in candidates
        if needle in j.title.casefold() or needle in j.company.name.casefold() or matches_tag(text, tags(j), skills)
    ]
    return hits[offset:offset + limit], len(hits)


def list_mine(db: Session, user: User) -> list[JobPosting]:
    return list(
        db.scalars(select(JobPosting).where(JobPosting.company_id == user.company_id).order_by(JobPosting.id.desc())).all()
    )
