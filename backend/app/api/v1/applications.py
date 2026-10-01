"""Applications and AI evaluation routes.

Applying queues the evaluation as a background task; the recruiter's list shows it as pending
until it is done. Status changes are recruiter actions only.
"""
from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy.orm import sessionmaker

from app.core.deps import CompanyUser, CurrentUser, DbSession
from app.models.application import EvaluationStatus
from app.schemas.application import ApplicantList, ApplicationOut, EvaluationOut, StatusUpdate
from app.services import application_service as svc
from app.services import evaluation_service

router = APIRouter(tags=["applications"])


def _queue(background: BackgroundTasks, db, evaluation_id: int) -> None:
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    background.add_task(evaluation_service.run_in_background, factory, evaluation_id)


@router.post(
    "/jobs/{job_id}/applications",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Apply with the latest confirmed CV; the AI evaluation runs in the background",
)
def apply(job_id: int, background: BackgroundTasks, db: DbSession, user: CurrentUser):
    app, ev = svc.apply(db, user, job_id)
    if ev.status != EvaluationStatus.DONE:
        _queue(background, db, ev.id)
    return svc.to_out(db, app)


@router.get("/applications/mine", response_model=list[ApplicationOut], summary="The seeker's own applications")
def my_applications(db: DbSession, user: CurrentUser):
    return [svc.to_out(db, a) for a in svc.list_mine(db, user)]


@router.get(
    "/jobs/{job_id}/applications",
    response_model=ApplicantList,
    summary="Applicants ranked by Fit (recruiter only; Fit uses the current weights)",
)
def list_applicants(job_id: int, db: DbSession, user: CompanyUser):
    return svc.ranked(db, user, job_id)


@router.get(
    "/applications/{application_id}/evaluation",
    response_model=EvaluationOut,
    summary="Per-criterion score, reason and evidence (recruiter only)",
)
def get_evaluation(application_id: int, db: DbSession, user: CompanyUser):
    return svc.evaluation(db, user, application_id)


@router.post(
    "/applications/{application_id}/evaluation/retry",
    response_model=EvaluationOut,
    summary="Re-run a pending or failed evaluation",
)
def retry_evaluation(application_id: int, background: BackgroundTasks, db: DbSession, user: CompanyUser):
    ev = svc.retry(db, user, application_id)
    _queue(background, db, ev.id)
    return svc.evaluation(db, user, application_id)


@router.put("/applications/{application_id}/status", response_model=ApplicationOut, summary="Recruiter changes the status")
def set_status(application_id: int, body: StatusUpdate, db: DbSession, user: CompanyUser):
    return svc.to_out(db, svc.set_status(db, user, application_id, body.status))
