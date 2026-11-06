"""Job recommendation for seekers (PROJECT_DOCUMENTATION.md §6.1; docs/DECISIONS.md D2, D15, D16, D42, D43).

① candidates: published, unexpired jobs the seeker has not applied to → ② Pref, drop < RECO_MIN_PREF
→ ③ evaluation for (job, newest confirmed CV version): `done` ones give Fit; missing, failed or stale
ones are queued in the background within the caps → ④ Fit with current weights, drop < RECO_MIN_FIT
→ ⑤ Final = 0.5·Fit + 0.5·Pref → ⑥ sort. Seekers see the match score (Final rounded down) with its band
(매우 적합 / 적합 / 참고), the preference score and unweighted category scores (D42); never weights.

`matches` (job list) and `job_match` (job detail) give the same scores for jobs that already have a `done`
evaluation (D43). They only read: they never call `evaluation_service.ensure`/`claim`/`queue` and never commit.
"""
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from ai.scoring.pref import JobFacts, Preferences, pref_score
from app.core.config import settings
from app.core.errors import AppError
from app.models import Application, CvProfile, Evaluation, JobPosting, User
from app.models.application import EvaluationStatus
from app.models.job import JobStatus
from app.schemas.recommendation import (
    CategoryScore,
    CriterionMatch,
    JobMatch,
    JobScore,
    JobScoreList,
    RecommendationList,
    RecommendedJob,
)
from app.services import ai_runtime, criteria_service, cv_service, evaluation_service, job_service, preference_service
from app.services.criteria_service import ScoringCriterion

KST = timezone(timedelta(hours=9))  # no daylight saving in Korea

# Category scores are listed in this order (only the categories the job uses)
CATEGORY_ORDER = ("skill", "experience", "education", "certificate", "project", "other")


@dataclass(frozen=True)
class Recommendation:
    result: RecommendationList
    # (evaluation id, queue token) for the route to start in the background after the commit
    queued: list[tuple[int, datetime]]


def match_level(final: float) -> str:
    if final >= settings.RECO_BAND_HIGH:
        return "매우 적합"
    if final >= settings.RECO_BAND_MID:
        return "적합"
    return "참고"


def final_of(fit: float, pref: float) -> float:
    """Final = 0.5·Fit + 0.5·Pref, rounded to 6 decimals so float noise (79.999…) cannot put the shown number
    and its band on different sides of a threshold."""
    return round(settings.RECO_FIT_WEIGHT * fit + settings.RECO_PREF_WEIGHT * pref, 6)


def match_score(final: float) -> int:
    """Final rounded down to an integer 0–100 (D42). Rounding down never changes the band: floor(x) ≥ t ⇔ x ≥ t."""
    return min(100, max(0, math.floor(final)))


def band_or_none(final: float) -> str | None:
    """The band, or None below the lowest Final recommendation can show (40): such a number has no band (D42)."""
    lowest = settings.RECO_FIT_WEIGHT * settings.RECO_MIN_FIT + settings.RECO_PREF_WEIGHT * settings.RECO_MIN_PREF
    return match_level(final) if final >= lowest else None


def breakdown(ev: Evaluation, criteria: tuple[ScoringCriterion, ...]) -> tuple[list[CategoryScore], list[CriterionMatch]]:
    """(category scores, per-criterion scores) of a `done` evaluation over the criteria scoring uses. A category
    score is the plain mean of its criterion scores, rounded down: no weights, so none can be read from it (D42)."""
    stored = {s.job_criteria_id: s.score for s in ev.scores}
    by_category: dict[str, list[int]] = {}
    rows = []
    for c in criteria:
        if c.id not in stored:
            continue
        by_category.setdefault(c.category, []).append(stored[c.id])
        rows.append(
            CriterionMatch(
                criterion_id=c.id,
                name=c.name,
                category=c.category,
                importance=criteria_service.importance_level(c.weight),
                score=stored[c.id],
            )
        )
    categories = [
        CategoryScore(category=k, score=sum(v) // len(v)) for k in CATEGORY_ORDER if (v := by_category.get(k))
    ]
    return categories, rows


def _seeker_only(user: User) -> None:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")


def _has_ai_consent(user: User) -> bool:
    return user.consent_ai_at is not None and (user.consent_version or "") >= settings.RECO_MIN_CONSENT_VERSION


def _confirmed_cv(db: Session, user: User) -> CvProfile | None:
    try:
        return cv_service.latest_confirmed(db, user)
    except AppError:  # no CV at all
        return None


def check_seeker(db: Session, user: User) -> CvProfile:
    """Seeker, AI consent at RECO_MIN_CONSENT_VERSION or later, newest CV confirmed; returns that CV.
    Also used by career content (D21), which reads the CV for jobs the seeker has not applied to."""
    _seeker_only(user)
    if not _has_ai_consent(user):
        raise AppError(409, "AI_CONSENT_REQUIRED", "맞춤 추천을 받으려면 최신 AI 분석 동의가 필요합니다.")
    profile = _confirmed_cv(db, user)
    if profile is None:
        raise AppError(409, "CV_NOT_CONFIRMED", "이력서 분석 결과를 확인(저장)한 뒤 추천을 받을 수 있습니다.")
    return profile


def _candidates(db: Session, seeker_id: int) -> list[JobPosting]:
    applied = exists().where(Application.job_id == JobPosting.id, Application.seeker_id == seeker_id)
    return list(
        db.scalars(
            select(JobPosting).where(
                JobPosting.status == JobStatus.PUBLISHED,
                or_(JobPosting.deadline.is_(None), JobPosting.deadline >= date.today()),
                ~applied,
            )
        ).all()
    )


def queued_today(db: Session, seeker_id: int) -> int:
    """Evaluations of the seeker's CVs queued since 00:00 KST that no application references."""
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    applied = exists().where(Application.job_id == Evaluation.job_id, Application.cv_profile_id == Evaluation.cv_profile_id)
    return db.scalar(
        select(func.count())
        .select_from(Evaluation)
        .join(CvProfile, CvProfile.id == Evaluation.cv_profile_id)
        .where(CvProfile.seeker_id == seeker_id, Evaluation.queued_at >= start, ~applied)
    )


def recommend(db: Session, user: User, limit: int) -> Recommendation:
    profile = check_seeker(db, user)
    # One recommendation call per seeker at a time, so parallel calls cannot overrun the caps
    db.execute(select(User.id).where(User.id == user.id).with_for_update())

    prefs = preference_service.to_preferences(preference_service.get_mine(db, user))
    passed = []
    for job in _candidates(db, user.id):
        facts = JobFacts(title=job.title, description=job.description, location=job.location, employment_type=job.employment_type)
        pref = pref_score(prefs, facts).score
        if pref >= settings.RECO_MIN_PREF:
            passed.append((job, pref))
    # Queue order when the caps bite: highest Pref first, then newest
    passed.sort(key=lambda x: (-x[1], -(x[0].published_at.timestamp() if x[0].published_at else 0), -x[0].id))

    evaluations = {
        ev.job_id: ev
        for ev in db.scalars(
            select(Evaluation).where(
                Evaluation.cv_profile_id == profile.id, Evaluation.job_id.in_([job.id for job, _ in passed])
            )
        )
    }
    budget = settings.RECO_MAX_NEW_EVALUATIONS
    if ai_runtime.mode() == "llm":
        budget = min(budget, max(0, settings.RECO_DAILY_NEW_EVALUATIONS - queued_today(db, user.id)))

    ranked, queued, pending = [], [], 0
    for job, pref in passed:
        ev = evaluations.get(job.id)
        if ev is not None and ev.status == EvaluationStatus.DONE:
            criteria = criteria_service.load_for_scoring(db, job.id).items
            fit, _ = evaluation_service.fit_of(ev, {c.id: c.effective_weight for c in criteria})
            if fit is not None and fit >= settings.RECO_MIN_FIT:
                ranked.append((final_of(fit, pref), fit, job, pref, ev, criteria))
            continue
        if ev is not None and ev.status == EvaluationStatus.FAILED and ev.attempts >= settings.EVALUATION_MAX_ATTEMPTS:
            continue  # gave up on this one; apply or 다시 분석 can still re-run it
        pending += 1
        if budget > 0:
            ev = ev or evaluation_service.ensure(db, job.id, profile.id)
            token = evaluation_service.claim(db, ev, reset_attempts=False, max_attempts=settings.EVALUATION_MAX_ATTEMPTS)
            if token is not None:
                queued.append((ev.id, token))
                budget -= 1
    db.commit()

    ranked.sort(key=lambda x: (-x[0], -x[1], -(x[2].published_at.timestamp() if x[2].published_at else 0), -x[2].id))
    items = []
    for final, _, job, pref, ev, criteria in ranked[:limit]:
        categories, _ = breakdown(ev, criteria)
        items.append(
            RecommendedJob(
                job_id=job.id,
                title=job.title,
                company_name=job.company.name,
                location=job.location,
                employment_type=job.employment_type,
                deadline=job.deadline,
                match_score=match_score(final),
                match_level=match_level(final),
                preference_score=math.floor(pref),
                categories=categories,
            )
        )
    return Recommendation(RecommendationList(items=items, pending_count=pending), queued)


# ── Read-only scores (D43): never create, queue or commit ──


def _score(db: Session, job: JobPosting, ev: Evaluation, prefs: Preferences) -> tuple[JobScore, list[CriterionMatch]] | None:
    """Scores of a `done` evaluation with the current weights and the seeker's current preferences."""
    criteria = criteria_service.load_for_scoring(db, job.id).items
    fit, _ = evaluation_service.fit_of(ev, {c.id: c.effective_weight for c in criteria})
    if fit is None:
        return None
    facts = JobFacts(title=job.title, description=job.description, location=job.location, employment_type=job.employment_type)
    pref = pref_score(prefs, facts).score
    final = final_of(fit, pref)
    categories, rows = breakdown(ev, criteria)
    score = JobScore(
        job_id=job.id,
        match_score=match_score(final),
        match_level=band_or_none(final),
        preference_score=math.floor(pref),
        categories=categories,
    )
    return score, rows


def _applied(db: Session, user: User, job_ids: list[int]) -> set[int]:
    return set(
        db.scalars(select(Application.job_id).where(Application.seeker_id == user.id, Application.job_id.in_(job_ids)))
    )


def matches(db: Session, user: User, job_ids: list[int]) -> JobScoreList:
    """Scores of the listed published jobs that have a `done` evaluation for the newest confirmed CV, leaving out
    applied jobs, in the order asked; empty without a confirmed CV or current AI consent (D43)."""
    _seeker_only(user)
    ids = list(dict.fromkeys(job_ids))
    profile = _confirmed_cv(db, user)
    if not ids or profile is None or not _has_ai_consent(user):
        return JobScoreList(items=[])
    applied = _applied(db, user, ids)
    jobs = {
        job.id: job
        for job in db.scalars(select(JobPosting).where(JobPosting.id.in_(ids), JobPosting.status == JobStatus.PUBLISHED))
        if job.id not in applied
    }
    done = {
        ev.job_id: ev
        for ev in db.scalars(
            select(Evaluation).where(
                Evaluation.cv_profile_id == profile.id,
                Evaluation.job_id.in_(list(jobs)),
                Evaluation.status == EvaluationStatus.DONE,
            )
        )
    }
    prefs = preference_service.to_preferences(preference_service.get_mine(db, user))
    items = []
    for job_id in ids:
        if job_id in done and (scored := _score(db, jobs[job_id], done[job_id], prefs)) is not None:
            items.append(scored[0])
    return JobScoreList(items=items)


def job_match(db: Session, user: User, job_id: int) -> JobMatch:
    """The scores of one job the seeker can see, from an evaluation that already exists for (job, newest confirmed
    CV), with each criterion's score (D42, D43)."""
    _seeker_only(user)
    job = job_service.get_visible_job(db, job_id, user)
    none = JobMatch(job_id=job.id, status="none")
    profile = _confirmed_cv(db, user)
    if profile is None or not _has_ai_consent(user) or _applied(db, user, [job.id]):
        return none
    ev = db.scalars(select(Evaluation).where(Evaluation.job_id == job.id, Evaluation.cv_profile_id == profile.id)).first()
    if ev is None or ev.status == EvaluationStatus.FAILED:
        return none
    if ev.status != EvaluationStatus.DONE:
        return JobMatch(job_id=job.id, status="pending")
    prefs = preference_service.to_preferences(preference_service.get_mine(db, user))
    scored = _score(db, job, ev, prefs)
    if scored is None:
        return none
    score, rows = scored
    return JobMatch(status="done", criteria=rows, **score.model_dump())
