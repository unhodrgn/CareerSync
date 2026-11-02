"""Job recommendation for seekers (PROJECT_DOCUMENTATION.md §6.1; docs/DECISIONS.md D2, D15, D16, D42–D44).

① candidates: published, unexpired jobs the seeker has not applied to → ② Pref, drop < RECO_MIN_PREF
→ ③ evaluation for (job, newest confirmed CV version): `done` ones give Fit; missing, failed or stale
ones are queued in the background within the caps → ④ Fit with current weights, drop < RECO_MIN_FIT
→ ⑤ Final = 0.5·Fit + 0.5·Pref → ⑥ sort. Seekers see the match score (Final rounded to an integer) with its band
(매우 적합 / 적합 / 참고), and strengths and gaps computed from the job's public text and the masked CV text (D43);
never Fit, Pref, per-criterion scores or weights.

`job_match` gives the score of one job for the job detail page (D44). It only reads: it never creates or queues
an evaluation.
"""
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from ai.career.gaps import match_skills
from ai.scoring.pref import JobFacts, pref_score
from app.core.config import settings
from app.core.errors import AppError
from app.models import Application, CvProfile, Evaluation, JobPosting, User
from app.models.application import EvaluationStatus
from app.models.job import JobStatus
from app.schemas.recommendation import JobMatch, RecommendationList, RecommendedJob
from app.services import ai_runtime, criteria_service, cv_service, evaluation_service, job_service, preference_service
from app.services.criteria_service import ScoringCriterion

KST = timezone(timedelta(hours=9))  # no daylight saving in Korea


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


def match_score(final: float) -> int:
    """Final rounded half up to an integer 0–100 (D42). The band is taken from this number, so the two agree."""
    return min(100, max(0, math.floor(final + 0.5)))


def job_skill_texts(items: tuple[ScoringCriterion, ...], job: JobPosting) -> tuple[list[str], str]:
    """(criteria lines, JD text): the job's public text that strengths and gaps (D43) and the roadmap (D21) read;
    criteria without weights, blocked ones already left out by `load_for_scoring`."""
    return [f"{c.name} ({c.category}): {c.description}".strip() for c in items], f"{job.title}\n{job.description}"


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
                final = settings.RECO_FIT_WEIGHT * fit + settings.RECO_PREF_WEIGHT * pref
                ranked.append((final, fit, job, criteria))
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
    cv_text, skills, cap = profile.document.masked_text, ai_runtime.skills(), settings.RECO_MAX_SKILL_ITEMS
    items = []
    for final, _, job, criteria in ranked[:limit]:
        strengths, gaps = match_skills(*job_skill_texts(criteria, job), cv_text, skills)
        score = match_score(final)
        items.append(
            RecommendedJob(
                job_id=job.id,
                title=job.title,
                company_name=job.company.name,
                location=job.location,
                employment_type=job.employment_type,
                deadline=job.deadline,
                match_score=score,
                match_level=match_level(score),
                strengths=[g.name for g in strengths[:cap]],
                gaps=[g.name for g in gaps[:cap]],
            )
        )
    return Recommendation(RecommendationList(items=items, pending_count=pending), queued)


def job_match(db: Session, user: User, job_id: int) -> JobMatch:
    """The match score of a job the seeker can see, from an evaluation that already exists for (job, newest confirmed
    CV) (D44). Reads only: never calls `evaluation_service.ensure`/`claim`/`queue` and never commits."""
    _seeker_only(user)
    job = job_service.get_visible_job(db, job_id, user)
    none = JobMatch(job_id=job.id, match_score=None, match_level=None, status="none")
    profile = _confirmed_cv(db, user)
    if not _has_ai_consent(user) or profile is None:
        return none
    if db.scalar(select(exists().where(Application.job_id == job.id, Application.seeker_id == user.id))):
        return none  # applied jobs show no score (D44)
    ev = db.scalars(select(Evaluation).where(Evaluation.job_id == job.id, Evaluation.cv_profile_id == profile.id)).first()
    if ev is None or ev.status == EvaluationStatus.FAILED:
        return none
    if ev.status != EvaluationStatus.DONE:
        return JobMatch(job_id=job.id, match_score=None, match_level=None, status="pending")
    weights = {c.id: c.effective_weight for c in criteria_service.load_for_scoring(db, job.id).items}
    fit, _ = evaluation_service.fit_of(ev, weights)
    if fit is None:
        return none
    prefs = preference_service.to_preferences(preference_service.get_mine(db, user))
    facts = JobFacts(title=job.title, description=job.description, location=job.location, employment_type=job.employment_type)
    score = match_score(settings.RECO_FIT_WEIGHT * fit + settings.RECO_PREF_WEIGHT * pref_score(prefs, facts).score)
    return JobMatch(job_id=job.id, match_score=score, match_level=match_level(score), status="done")
