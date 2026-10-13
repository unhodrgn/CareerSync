"""Career preparation content for seekers: skill roadmap (interview questions follow) (docs/DECISIONS.md D21).

Any published, unexpired job; same seeker checks as job recommendation (AI consent at
RECO_MIN_CONSENT_VERSION or later, newest CV confirmed). Gaps are computed in code from the job's public
information and the masked CV text, never from the company's scores. Results are cached per seeker × job ×
CV version × kind × PROMPT_VERSION × method in `career_contents`.

AI_MODE=rules: the template, cached. AI_MODE=llm: a cached LLM result if any; otherwise one new LLM generation
under a lock on the seeker's `users` row, within CAREER_DAILY_LLM_GENERATIONS per day (KST). Over the limit, or
when the LLM fails, the template is returned and not cached.
"""
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai.career.gaps import Gap, find_gaps
from ai.career.roadmap import Step, make_roadmap, roadmap_rules
from ai.parsing.extract import PROMPT_VERSION
from app.core.config import settings
from app.core.errors import AppError
from app.models import CareerContent, CvProfile, JobPosting, User
from app.models.career import CareerContentKind
from app.models.job import JobStatus
from app.schemas.career import RoadmapOut
from app.services import ai_runtime, criteria_service, recommendation_service

KST = timezone(timedelta(hours=9))
NO_GAP_MESSAGE = "이 공고에서 요구하는 기술과 자격증을 모두 갖추고 있습니다."


def _open_job(db: Session, job_id: int) -> JobPosting:
    job = db.get(JobPosting, job_id)
    if job is None or job.status != JobStatus.PUBLISHED or (job.deadline is not None and job.deadline < date.today()):
        raise AppError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")
    return job


def _cached(db: Session, seeker_id: int, job_id: int, cv_id: int, kind: str, llm_mode: bool) -> CareerContent | None:
    q = select(CareerContent).where(
        CareerContent.seeker_id == seeker_id,
        CareerContent.job_id == job_id,
        CareerContent.cv_profile_id == cv_id,
        CareerContent.kind == kind,
        CareerContent.prompt_version == PROMPT_VERSION,
        CareerContent.method.like("llm:%") if llm_mode else CareerContent.method == "rules",
    )
    return db.scalars(q.order_by(CareerContent.created_at.desc(), CareerContent.id.desc())).first()


def llm_generations_today(db: Session, seeker_id: int) -> int:
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return db.scalar(
        select(func.count())
        .select_from(CareerContent)
        .where(CareerContent.seeker_id == seeker_id, CareerContent.method.like("llm:%"), CareerContent.created_at >= start)
    )


def _store(db: Session, seeker_id: int, job_id: int, cv_id: int, kind: str, method: str, content: dict) -> None:
    try:
        with db.begin_nested():
            db.add(
                CareerContent(
                    seeker_id=seeker_id,
                    job_id=job_id,
                    cv_profile_id=cv_id,
                    kind=kind,
                    prompt_version=PROMPT_VERSION,
                    method=method,
                    content=content,
                    created_at=datetime.now(UTC),
                )
            )
    except IntegrityError:
        pass  # an identical result was stored by a concurrent request


def _context(db: Session, job: JobPosting, profile: CvProfile) -> tuple[list[str], str, str]:
    """(criteria lines, JD text, masked CV text); criteria without weights, blocked ones left out."""
    criteria = [f"{c.name} ({c.category}): {c.description}".strip() for c in criteria_service.load_for_scoring(db, job.id).items]
    return criteria, f"{job.title}\n{job.description}", profile.document.masked_text


# ── Roadmap ──


def _roadmap_content(gaps: list[Gap], steps: list[Step]) -> dict:
    return {
        "gaps": [{"name": g.name, "kind": g.kind} for g in gaps],
        "steps": [
            {
                "order": s.order,
                "skill": s.skill,
                "kind": s.kind,
                "goal": s.goal,
                "activities": list(s.activities),
                "resources": [{"title": r.title, "url": r.url} for r in s.resources],
            }
            for s in steps
        ],
    }


def roadmap(db: Session, user: User, job_id: int) -> RoadmapOut:
    profile = recommendation_service.check_seeker(db, user)
    job = _open_job(db, job_id)
    criteria, job_text, cv_text = _context(db, job, profile)
    skills = ai_runtime.skills()
    gaps = find_gaps(criteria, job_text, cv_text, skills)
    if not gaps:
        # Nothing to learn: no LLM call, nothing cached, not counted
        return RoadmapOut(job_id=job.id, method="rules", gaps=[], steps=[], message=NO_GAP_MESSAGE)

    kind, llm_mode = CareerContentKind.ROADMAP, ai_runtime.mode() == "llm"
    if (hit := _cached(db, user.id, job.id, profile.id, kind, llm_mode)) is not None:
        return RoadmapOut(job_id=job.id, method=hit.method, **hit.content)

    resources = ai_runtime.resources()
    if not llm_mode:
        content = _roadmap_content(gaps, roadmap_rules(gaps, resources))
        _store(db, user.id, job.id, profile.id, kind, "rules", content)
        db.commit()
        return RoadmapOut(job_id=job.id, method="rules", **content)

    # One generation per seeker at a time: the limit holds and parallel calls do not pay twice
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    if (hit := _cached(db, user.id, job.id, profile.id, kind, llm_mode)) is not None:
        db.commit()
        return RoadmapOut(job_id=job.id, method=hit.method, **hit.content)
    if llm_generations_today(db, user.id) >= settings.CAREER_DAILY_LLM_GENERATIONS:
        db.commit()
        content = _roadmap_content(gaps, roadmap_rules(gaps, resources))
        return RoadmapOut(job_id=job.id, method="rules", limited=True, **content)

    steps, method = make_roadmap(gaps, job.title, job.description, criteria, skills.find_in_text(cv_text), resources, ai_runtime.llm())
    content = _roadmap_content(gaps, steps)
    if method != "rules":  # a template fallback after an LLM failure is not cached, so the next call retries
        _store(db, user.id, job.id, profile.id, kind, method, content)
    db.commit()
    return RoadmapOut(job_id=job.id, method=method, **content)
