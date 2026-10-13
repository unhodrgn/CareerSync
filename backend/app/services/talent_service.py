"""Talent recommendation: anonymous seekers for one of the company's jobs (PROJECT_DOCUMENTATION.md §6.1;
docs/DECISIONS.md D3, D18, D19).

Candidates: `profile_public` seekers with AI consent at RECO_MIN_CONSENT_VERSION or later and a newest
CV version that is confirmed — checked on every request. Excluded: seekers who applied to the job,
seekers with a pending or accepted offer from the company, seekers who rejected an offer for this job.
Then Pref ≥ RECO_MIN_PREF → evaluation for (job, CV version): `done` gives Fit ≥ RECO_MIN_FIT;
missing, failed or stale ones are queued within the caps. Everything shown to the company is read from
the masked CV text (CLAUDE.md AI rule 14), never the seeker-edited profile alone.
"""
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from ai.parsing.extract import line_in_text, verified_experience
from ai.parsing.sections import split_sections
from ai.scoring.pref import JobFacts, pref_score
from app.core.config import settings
from app.core.errors import AppError
from app.models import Application, Company, CvProfile, Evaluation, JobPosting, SeekerPreference, TalentOffer, User
from app.models.application import EvaluationStatus
from app.models.job import JobStatus
from app.models.matching import TalentOfferStatus
from app.schemas.talent import TalentCandidate, TalentCriterionScore, TalentDesired, TalentEducation, TalentList
from app.services import ai_runtime, criteria_service, cv_service, evaluation_service, job_service, preference_service

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class TalentResult:
    result: TalentList
    # (evaluation id, queue token) for the route to start in the background after the commit
    queued: list[tuple[int, datetime]]


def anonymous_id(company_id: int, seeker_id: int) -> str:
    """Stable for one company, different across companies, not reversible without the server key."""
    digest = hmac.new(settings.JWT_SECRET_KEY.encode(), f"talent:{company_id}:{seeker_id}".encode(), hashlib.sha256)
    return "C-" + digest.hexdigest()[:10].upper()


def _published_own_job(db: Session, user: User, job_id: int) -> JobPosting:
    job = job_service.get_owned_job(db, job_id, user)
    if job.status != JobStatus.PUBLISHED:
        raise AppError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")
    return job


def _blocked_by_offers(db: Session, company_id: int, job_id: int) -> set[int]:
    """Seekers with a pending or accepted offer from the company (any job), or who rejected one for this job."""
    rows = db.execute(
        select(TalentOffer.seeker_id, TalentOffer.status, TalentOffer.job_id).where(TalentOffer.company_id == company_id)
    ).all()
    return {
        seeker_id
        for seeker_id, status, offer_job in rows
        if status in (TalentOfferStatus.PENDING, TalentOfferStatus.ACCEPTED)
        or (status == TalentOfferStatus.REJECTED and offer_job == job_id)
    }


def _candidates(db: Session, job: JobPosting) -> list[tuple[User, SeekerPreference, CvProfile]]:
    applied = exists().where(Application.job_id == job.id, Application.seeker_id == User.id)
    rows = db.execute(
        select(User, SeekerPreference)
        .join(SeekerPreference, SeekerPreference.seeker_id == User.id)
        .where(
            User.role == "seeker",
            SeekerPreference.profile_public.is_(True),
            User.consent_ai_at.is_not(None),
            User.consent_version >= settings.RECO_MIN_CONSENT_VERSION,
            ~applied,
        )
    ).all()
    blocked = _blocked_by_offers(db, job.company_id, job.id)
    out = []
    for user, pref in rows:
        if user.id in blocked:
            continue
        try:
            profile = cv_service.latest_confirmed(db, user)
        except AppError:
            profile = None
        if profile is not None:
            out.append((user, pref, profile))
    return out


def queued_today(db: Session, company_id: int) -> int:
    """Evaluations of the company's jobs queued since 00:00 KST that no application references.
    Counts the seekers' own job recommendations too, so it errs on the side of fewer new evaluations."""
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    applied = exists().where(Application.job_id == Evaluation.job_id, Application.cv_profile_id == Evaluation.cv_profile_id)
    return db.scalar(
        select(func.count())
        .select_from(Evaluation)
        .join(JobPosting, JobPosting.id == Evaluation.job_id)
        .where(JobPosting.company_id == company_id, Evaluation.queued_at >= start, ~applied)
    )


def _anonymous_profile(pref: SeekerPreference, profile: CvProfile, today: str) -> dict:
    data = cv_service.to_profile_data(profile)
    text = profile.document.masked_text
    skills = ai_runtime.skills()
    months, _ = verified_experience(text, data.experiences, today)
    project_text = "\n".join(s.text for s in split_sections(text) if s.key == "project")
    return {
        "skills": skills.find_in_text(text),
        "experience_years": months // 12,
        "roles": list(dict.fromkeys(
            e.role for e in data.experiences if e.role and line_in_text(e.source, text) and e.role.casefold() in e.source.casefold()
        )),
        "project_techs": skills.find_in_text(project_text) if project_text else [],
        "education": [
            TalentEducation(degree=e.degree, major=e.major)
            for e in data.education
            if e.major and line_in_text(e.source, text) and e.major.casefold() in e.source.casefold()
        ],
        "certificates": list(dict.fromkeys(
            [name for name, _ in skills.find_certificates(text)]
            + [c.name for c in data.certificates if c.name and line_in_text(c.source, text) and c.name.casefold() in c.source.casefold()]
        )),
        "desired": TalentDesired(
            locations=[x.location for x in pref.locations],
            employment_types=[x.employment_type for x in pref.employment_types],
            job_keywords=[x.keyword for x in pref.job_keywords],
        ),
    }


def _last_offer_status(db: Session, company_id: int, seeker_id: int) -> str | None:
    return db.scalar(
        select(TalentOffer.status)
        .where(TalentOffer.company_id == company_id, TalentOffer.seeker_id == seeker_id)
        .order_by(TalentOffer.created_at.desc(), TalentOffer.id.desc())
        .limit(1)
    )


def recommend(db: Session, user: User, job_id: int, limit: int) -> TalentResult:
    job = _published_own_job(db, user, job_id)
    # One talent call per company at a time, so parallel calls cannot overrun the caps
    db.execute(select(Company.id).where(Company.id == job.company_id).with_for_update())

    facts = JobFacts(title=job.title, description=job.description, location=job.location, employment_type=job.employment_type)
    passed = []
    for seeker, pref, profile in _candidates(db, job):
        score = pref_score(preference_service.to_preferences(pref), facts).score
        if score >= settings.RECO_MIN_PREF:
            passed.append((seeker, pref, profile, score))
    # Queue order when the caps bite: highest Pref first, then the most recently confirmed CV
    passed.sort(key=lambda x: (-x[3], -(x[2].confirmed_at.timestamp() if x[2].confirmed_at else 0), -x[2].id))

    evaluations = {
        ev.cv_profile_id: ev
        for ev in db.scalars(
            select(Evaluation).where(Evaluation.job_id == job.id, Evaluation.cv_profile_id.in_([p.id for _, _, p, _ in passed]))
        )
    }
    budget = settings.TALENT_MAX_NEW_EVALUATIONS
    if ai_runtime.mode() == "llm":
        budget = min(budget, max(0, settings.TALENT_DAILY_NEW_EVALUATIONS - queued_today(db, job.company_id)))

    loaded = criteria_service.load_for_scoring(db, job.id)
    weights = {c.id: c.effective_weight for c in loaded.items}
    names = {c.id: c.name for c in loaded.items}
    today = date.today().strftime("%Y-%m")
    ranked, queued, pending = [], [], 0
    for seeker, pref, profile, _ in passed:
        ev = evaluations.get(profile.id)
        if ev is not None and ev.status == EvaluationStatus.DONE:
            fit, strong = evaluation_service.fit_of(ev, weights)
            if fit is not None and fit >= settings.RECO_MIN_FIT:
                ranked.append((fit, strong, pref, seeker, profile, ev))
            continue
        if ev is not None and ev.status == EvaluationStatus.FAILED and ev.attempts >= settings.EVALUATION_MAX_ATTEMPTS:
            continue
        pending += 1
        if budget > 0:
            ev = ev or evaluation_service.ensure(db, job.id, profile.id)
            token = evaluation_service.claim(db, ev, reset_attempts=False, max_attempts=settings.EVALUATION_MAX_ATTEMPTS)
            if token is not None:
                queued.append((ev.id, token))
                budget -= 1

    ranked.sort(key=lambda x: (-x[0], -x[1], -(x[2].profile_public_at.timestamp() if x[2].profile_public_at else 0), -x[3].id))
    items = [
        TalentCandidate(
            anonymous_id=anonymous_id(job.company_id, seeker.id),
            fit=fit,
            criteria=[
                TalentCriterionScore(criterion_id=s.job_criteria_id, name=names[s.job_criteria_id], score=s.score, level=s.level)
                for s in sorted(ev.scores, key=lambda s: s.job_criteria_id)
                if s.job_criteria_id in names
            ],
            offer_status=_last_offer_status(db, job.company_id, seeker.id),
            **_anonymous_profile(pref, profile, today),
        )
        for fit, _, pref, seeker, profile, ev in ranked[:limit]
    ]
    db.commit()
    return TalentResult(TalentList(job_id=job.id, items=items, pending_count=pending), queued)
