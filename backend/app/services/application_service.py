"""Applications: apply, the recruiter's ranked list, per-criterion evaluation, status changes.

Status changes are recruiter actions only; the AI never accepts or rejects anyone (README).
"""
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.parsing.extract import total_experience_months
from ai.parsing.profile import CvProfile as ProfileData
from ai.scoring.fit import RankItem, rank, summary_comment
from app.core.errors import AppError
from app.models import Application, Evaluation, JobPosting, User
from app.models.application import EvaluationStatus
from app.schemas.application import (
    ApplicantList,
    ApplicantRow,
    ApplicationOut,
    CriterionBrief,
    CriterionEvaluation,
    EvaluationOut,
    ExcludedBrief,
    ScoreBrief,
)
from app.services import criteria_service, cv_service, evaluation_service, job_service


def _not_found() -> AppError:
    return AppError(404, "APPLICATION_NOT_FOUND", "지원 내역을 찾을 수 없습니다.")


def _evaluation(db: Session, app: Application) -> Evaluation | None:
    return db.scalars(
        select(Evaluation).where(Evaluation.job_id == app.job_id, Evaluation.cv_profile_id == app.cv_profile_id)
    ).first()


def to_out(db: Session, app: Application) -> ApplicationOut:
    job = db.get(JobPosting, app.job_id)
    ev = _evaluation(db, app)
    return ApplicationOut(
        id=app.id,
        job_id=job.id,
        job_title=job.title,
        company_name=job.company.name,
        status=app.status,
        evaluation_status=ev.status if ev else None,
        created_at=app.created_at,
    )


# ── Seeker ──


def apply(db: Session, user: User, job_id: int) -> tuple[Application, Evaluation]:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 지원할 수 있습니다.")
    job = job_service.get_published_job(db, job_id)
    if job.deadline is not None and job.deadline < date.today():
        raise AppError(409, "JOB_EXPIRED", "마감된 공고입니다.")
    if user.consent_ai_at is None:
        raise AppError(409, "AI_CONSENT_REQUIRED", "AI 분석 동의 후 지원할 수 있습니다.")
    try:
        profile = cv_service.latest_confirmed(db, user)
    except AppError:
        profile = None
    if profile is None:
        raise AppError(409, "CV_NOT_CONFIRMED", "이력서 분석 결과를 확인(저장)한 뒤 지원할 수 있습니다.")
    exists = db.scalars(select(Application).where(Application.job_id == job.id, Application.seeker_id == user.id)).first()
    if exists is not None:
        raise AppError(409, "ALREADY_APPLIED", "이미 지원한 공고입니다.")
    app = Application(job_id=job.id, seeker_id=user.id, cv_profile_id=profile.id)
    db.add(app)
    ev = evaluation_service.ensure(db, job.id, profile.id)
    db.commit()
    db.refresh(app)
    return app, ev


def list_mine(db: Session, user: User) -> list[Application]:
    return list(db.scalars(select(Application).where(Application.seeker_id == user.id).order_by(Application.id.desc())))


# ── Recruiter ──


def get_owned(db: Session, user: User, application_id: int) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise _not_found()
    try:
        job_service.get_owned_job(db, app.job_id, user)
    except AppError:
        raise _not_found() from None
    return app


def ranked(db: Session, user: User, job_id: int) -> ApplicantList:
    job = job_service.get_owned_job(db, job_id, user)
    loaded = criteria_service.load_for_scoring(db, job.id)
    weights = {c.id: c.effective_weight for c in loaded.items}
    apps = list(db.scalars(select(Application).where(Application.job_id == job.id)))
    evs = {
        e.cv_profile_id: e
        for e in db.scalars(
            select(Evaluation).where(Evaluation.job_id == job.id, Evaluation.cv_profile_id.in_([a.cv_profile_id for a in apps]))
        )
    } if apps else {}
    today = date.today().strftime("%Y-%m")
    rows, rank_items = {}, []
    for a in apps:
        ev = evs.get(a.cv_profile_id)
        fit, strong = evaluation_service.fit_of(ev, weights)
        profile = ProfileData.model_validate(a.cv_profile.profile)
        rows[a.id] = ApplicantRow(
            application_id=a.id,
            rank=None,
            name=a.seeker.display_name or "(이름 없음)",
            email=a.seeker.email,
            status=a.status,
            applied_at=a.created_at,
            experience_months=total_experience_months(profile.experiences, today),
            evaluation_status=ev.status if ev else EvaluationStatus.PENDING,
            fit=fit,
            strong_count=strong,
            scores=[ScoreBrief(criterion_id=s.job_criteria_id, score=s.score) for s in ev.scores if s.job_criteria_id in weights]
            if fit is not None
            else [],
        )
        if fit is not None:
            rank_items.append(RankItem(a.id, fit, strong, a.created_at.timestamp()))
    ordered = []
    for i, item in enumerate(rank(rank_items), start=1):
        rows[item.key].rank = i
        ordered.append(rows[item.key])
    # Pending and failed evaluations after the ranked ones, oldest application first
    ordered += sorted((r for r in rows.values() if r.rank is None), key=lambda r: r.applied_at)
    return ApplicantList(
        job_id=job.id,
        job_title=job.title,
        criteria=[CriterionBrief(id=c.id, name=c.name, category=c.category, weight=round(c.effective_weight, 1)) for c in loaded.items],
        excluded_criteria=[ExcludedBrief(id=x.id, name=x.name) for x in loaded.excluded],
        items=ordered,
    )


def evaluation(db: Session, user: User, application_id: int) -> EvaluationOut:
    app = get_owned(db, user, application_id)
    loaded = criteria_service.load_for_scoring(db, app.job_id)
    weights = {c.id: c.effective_weight for c in loaded.items}
    ev = _evaluation(db, app)
    fit, _ = evaluation_service.fit_of(ev, weights)
    by_id = {s.job_criteria_id: s for s in ev.scores} if ev else {}
    items = []
    for c in loaded.items:
        s = by_id.get(c.id)
        if s is None:
            continue
        items.append(
            CriterionEvaluation(
                criterion_id=c.id,
                name=c.name,
                description=c.description,
                category=c.category,
                weight=round(c.effective_weight, 1),
                score=s.score,
                level=s.level,
                reason=s.reason,
                evidence=list(s.evidence or []),
                method=s.method,
            )
        )
    summary = (
        summary_comment({c.id: c.name for c in loaded.items}, {i.criterion_id: i.score for i in items}, weights)
        if fit is not None
        else ""
    )
    return EvaluationOut(
        application_id=app.id,
        job_id=app.job_id,
        name=app.seeker.display_name or "(이름 없음)",
        status=ev.status if ev else EvaluationStatus.PENDING,
        error=ev.error if ev else "",
        fit=fit,
        summary=summary,
        items=items,
        excluded_criteria=[ExcludedBrief(id=x.id, name=x.name) for x in loaded.excluded],
        llm_model=ev.llm_model if ev else "",
        embedding_model=ev.embedding_model if ev else "",
        prompt_version=ev.prompt_version if ev else "",
        finished_at=ev.finished_at if ev else None,
    )


def set_status(db: Session, user: User, application_id: int, status: str) -> Application:
    app = get_owned(db, user, application_id)
    app.status = status
    app.status_updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(app)
    return app


def retry(db: Session, user: User, application_id: int) -> Evaluation:
    app = get_owned(db, user, application_id)
    ev = evaluation_service.ensure(db, app.job_id, app.cv_profile_id)
    if ev.status == EvaluationStatus.DONE:
        raise AppError(409, "EVALUATION_DONE", "이미 완료된 평가입니다.")
    ev.status, ev.error = EvaluationStatus.PENDING, ""
    db.commit()
    return ev
