"""Run the AI evaluation of one CV profile against one job's criteria, and read Fit from stored scores.

An evaluation is keyed by (job, CV profile). Scores are stored per criterion without weights;
Fit is computed when read, with the weights `criteria_service.load_for_scoring` returns, so a
weight edit after publish re-ranks applicants without another AI call.
"""
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.parsing.extract import PROMPT_VERSION
from ai.scoring.fit import STRONG_SCORE, aggregate_fit, score_candidate
from ai.scoring.types import Candidate, Criterion, JobContext
from app.models import CriterionScore, CvProfile, Evaluation, JobPosting
from app.models.application import EvaluationStatus
from app.services import ai_runtime, criteria_service, cv_service

log = logging.getLogger(__name__)


def ensure(db: Session, job_id: int, cv_profile_id: int) -> Evaluation:
    """The evaluation for (job, profile), created as pending if missing. Does not commit."""
    ev = db.scalars(
        select(Evaluation).where(Evaluation.job_id == job_id, Evaluation.cv_profile_id == cv_profile_id)
    ).first()
    if ev is None:
        ev = Evaluation(job_id=job_id, cv_profile_id=cv_profile_id, status=EvaluationStatus.PENDING)
        db.add(ev)
        db.flush()
    return ev


def evaluate(db: Session, ev: Evaluation) -> Evaluation:
    """Score every usable criterion and store the results. Failures are recorded, never raised."""
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

        ev.scores.clear()
        db.flush()
        for r in results:
            ev.scores.append(
                CriterionScore(
                    job_criteria_id=r.criterion_id,
                    score=r.score,
                    level=r.level,
                    reason=r.reason,
                    evidence=list(r.evidence),
                    method=r.method,
                )
            )
        ev.status, ev.error = EvaluationStatus.DONE, ""
        ev.llm_model = llm.model if llm is not None else ""
        ev.embedding_model = embedder.name
        ev.prompt_version = PROMPT_VERSION
        ev.skills_version = skills.version
    except Exception as e:  # noqa: BLE001  (the evaluation must end in a state the recruiter can see)
        log.exception("evaluation %s failed", ev.id)
        db.rollback()
        ev = db.get(Evaluation, ev.id)
        ev.status, ev.error = EvaluationStatus.FAILED, f"{type(e).__name__}: {e}"[:500]
    ev.finished_at = datetime.now(UTC)
    db.commit()
    return ev


def run_in_background(session_factory: Callable[[], Session], evaluation_id: int) -> None:
    """Entry point for FastAPI BackgroundTasks: its own session, never the request's."""
    db = session_factory()
    try:
        ev = db.get(Evaluation, evaluation_id)
        if ev is not None:
            evaluate(db, ev)
    finally:
        db.close()


def fit_of(ev: Evaluation | None, weights: dict[int, float]) -> tuple[float | None, int]:
    """(Fit, number of strong criteria) from stored scores and the current weights; Fit is None until done."""
    if ev is None or ev.status != EvaluationStatus.DONE:
        return None, 0
    scores = {s.job_criteria_id: s.score for s in ev.scores}
    strong = sum(1 for cid in weights if scores.get(cid, 0) >= STRONG_SCORE)
    return aggregate_fit(scores, weights), strong
