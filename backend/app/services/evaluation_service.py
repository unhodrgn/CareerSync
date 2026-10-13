"""Run the AI evaluation of one CV profile against one job's criteria, and read Fit from stored scores.

An evaluation is keyed by (job, CV profile). Scores are stored per criterion without weights;
Fit is computed when read, with the weights `criteria_service.load_for_scoring` returns, so a
weight edit after publish re-ranks applicants without another AI call.

Queue rules (PROJECT_DOCUMENTATION.md §6.1, issues 2 and 25): `claim()` queues an evaluation only
when it is new, failed or stale pending, in one conditional UPDATE, so concurrent requests queue it
once. The run gets the `queued_at` it was queued with and writes its result only while that is
still the row's `queued_at`, so an older run never overwrites a newer one.
"""
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai.parsing.extract import PROMPT_VERSION
from ai.scoring.fit import STRONG_SCORE, aggregate_fit, score_candidate
from ai.scoring.types import Candidate, Criterion, JobContext
from app.core.config import settings
from app.models import CriterionScore, CvProfile, Evaluation, JobPosting
from app.models.application import EvaluationStatus
from app.services import ai_runtime, criteria_service, cv_service

log = logging.getLogger(__name__)


def _find(db: Session, job_id: int, cv_profile_id: int) -> Evaluation | None:
    return db.scalars(
        select(Evaluation).where(Evaluation.job_id == job_id, Evaluation.cv_profile_id == cv_profile_id)
    ).first()


def ensure(db: Session, job_id: int, cv_profile_id: int) -> Evaluation:
    """The evaluation for (job, profile), created as pending if missing. Does not commit.

    A concurrent request may insert the same (job, profile) first; the unique constraint then
    fails inside a savepoint and the existing row is returned instead of an error.
    """
    ev = _find(db, job_id, cv_profile_id)
    if ev is not None:
        return ev
    try:
        with db.begin_nested():
            ev = Evaluation(job_id=job_id, cv_profile_id=cv_profile_id, status=EvaluationStatus.PENDING)
            db.add(ev)
    except IntegrityError:
        ev = _find(db, job_id, cv_profile_id)
    return ev


def claim(db: Session, ev: Evaluation, *, reset_attempts: bool) -> datetime | None:
    """Queue `ev` for scoring if no live run owns it: new (`queued_at` NULL), failed, or pending for
    longer than EVALUATION_STALE_MINUTES. Returns the token (the new `queued_at`) for the run, or
    None when it must not be queued. Does not commit; the caller commits before starting the run.

    Apply and 다시 분석 reset `attempts` (they are not limited by it); other paths add one.
    """
    now = datetime.now(UTC)
    stale = now - timedelta(minutes=settings.EVALUATION_STALE_MINUTES)
    claimable = or_(
        Evaluation.status == EvaluationStatus.FAILED,
        and_(
            Evaluation.status == EvaluationStatus.PENDING,
            or_(Evaluation.queued_at.is_(None), Evaluation.queued_at < stale),
        ),
    )
    result = db.execute(
        update(Evaluation)
        .where(Evaluation.id == ev.id, claimable)
        .values(
            status=EvaluationStatus.PENDING,
            error="",
            queued_at=now,
            attempts=1 if reset_attempts else Evaluation.attempts + 1,
        )
        .execution_options(synchronize_session=False)
    )
    db.expire(ev)
    return now if result.rowcount == 1 else None


def _write_if_owner(db: Session, evaluation_id: int, token: datetime, **values) -> bool:
    """Update the row only while this run's token is its `queued_at` (fencing)."""
    result = db.execute(
        update(Evaluation)
        .where(Evaluation.id == evaluation_id, Evaluation.queued_at == token)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def evaluate(db: Session, ev: Evaluation, token: datetime) -> None:
    """Score every usable criterion and store the results, unless the evaluation was re-queued
    meanwhile (then this run's results are discarded). Failures are recorded, never raised."""
    evaluation_id = ev.id
    try:
        job = db.get(JobPosting, ev.job_id)
        profile_row = db.get(CvProfile, ev.cv_profile_id)
        loaded = criteria_service.load_for_scoring(db, ev.job_id)
        criteria = [Criterion(c.id, c.name, c.description, c.category, c.effective_weight) for c in loaded.items]
        candidate = Candidate(cv_service.to_profile_data(profile_row), profile_row.document.masked_text)
        context = JobContext(
            title=job.title,
            description=job.description,
            min_experience_years=job.min_experience_years,
            company_name=job.company.name,
            talent_profile=job.company.talent_profile,
        )
        skills, embedder, llm = ai_runtime.skills(), ai_runtime.embedder(), ai_runtime.llm()
        results = score_candidate(criteria, candidate, context, skills=skills, embedder=embedder, llm=llm)

        owner = _write_if_owner(
            db,
            evaluation_id,
            token,
            status=EvaluationStatus.DONE,
            error="",
            llm_model=llm.model if llm is not None else "",
            embedding_model=embedder.name,
            prompt_version=PROMPT_VERSION,
            skills_version=skills.version,
            finished_at=datetime.now(UTC),
        )
        if not owner:
            db.rollback()
            log.info("evaluation %s was re-queued; discarding this run's results", evaluation_id)
            return
        db.execute(delete(CriterionScore).where(CriterionScore.evaluation_id == evaluation_id))
        db.add_all(
            CriterionScore(
                evaluation_id=evaluation_id,
                job_criteria_id=r.criterion_id,
                score=r.score,
                level=r.level,
                reason=r.reason,
                evidence=list(r.evidence),
                method=r.method,
            )
            for r in results
        )
        db.commit()
    except Exception as e:  # noqa: BLE001  (the evaluation must end in a state the recruiter can see)
        log.exception("evaluation %s failed", evaluation_id)
        db.rollback()
        error = f"{type(e).__name__}: {e}"[:500]
        if _write_if_owner(db, evaluation_id, token, status=EvaluationStatus.FAILED, error=error, finished_at=datetime.now(UTC)):
            db.commit()
        else:
            db.rollback()


def run_in_background(session_factory: Callable[[], Session], evaluation_id: int, token: datetime) -> None:
    """Entry point for FastAPI BackgroundTasks: its own session, never the request's.
    `token` is the `queued_at` returned by `claim()`."""
    db = session_factory()
    try:
        ev = db.get(Evaluation, evaluation_id)
        if ev is not None:
            evaluate(db, ev, token)
    finally:
        db.close()


def fit_of(ev: Evaluation | None, weights: dict[int, float]) -> tuple[float | None, int]:
    """(Fit, number of strong criteria) from stored scores and the current weights; Fit is None until done."""
    if ev is None or ev.status != EvaluationStatus.DONE:
        return None, 0
    scores = {s.job_criteria_id: s.score for s in ev.scores}
    strong = sum(1 for cid in weights if scores.get(cid, 0) >= STRONG_SCORE)
    return aggregate_fit(scores, weights), strong
