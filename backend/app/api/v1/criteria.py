"""Evaluation criteria routes: one set per job posting, saved whole."""
from fastapi import APIRouter

from app.core.deps import CompanyUser, CurrentUser, DbSession
from app.models import JobPosting
from app.schemas.criteria import (
    CheckRequest,
    CheckResult,
    CriteriaSetIn,
    CriteriaSetOut,
    CriterionOut,
    SeekerCriteriaSetOut,
    SeekerCriterionOut,
)
from app.services import criteria_service as svc

router = APIRouter(tags=["criteria"])


def _company_view(job: JobPosting) -> CriteriaSetOut:
    return CriteriaSetOut(
        job_id=job.id,
        items=[
            CriterionOut(
                id=c.id,
                name=c.name,
                description=c.description,
                category=c.category,
                weight=c.weight,
                position=c.position,
                importance=svc.importance_level(c.weight),
            )
            for c in job.criteria
        ],
        total_weight=sum(c.weight for c in job.criteria),
        blocklist_version=svc.blocklist().version,
    )


@router.get(
    "/jobs/{job_id}/criteria",
    response_model=CriteriaSetOut | SeekerCriteriaSetOut,
    summary="Read a job's criteria (owner: full rows; seeker: name + importance only)",
)
def get_criteria(job_id: int, db: DbSession, user: CurrentUser):
    if user.role == "company":
        return _company_view(svc.get_owned_job(db, job_id, user))
    job = svc.get_published_job(db, job_id)
    return SeekerCriteriaSetOut(
        job_id=job.id,
        items=[
            SeekerCriterionOut(name=c.name, category=c.category, importance=svc.importance_level(c.weight))
            for c in job.criteria
        ],
    )


@router.put(
    "/jobs/{job_id}/criteria",
    response_model=CriteriaSetOut,
    summary="Replace the whole criteria set (after publish: weights and order only)",
)
def put_criteria(job_id: int, body: CriteriaSetIn, db: DbSession, user: CompanyUser):
    job = svc.get_owned_job(db, job_id, user)
    return _company_view(svc.replace_set(db, job, body.items))


@router.post(
    "/jobs/{job_id}/criteria/copy-from/{source_job_id}",
    response_model=CriteriaSetOut,
    summary="Copy another of the company's jobs' criteria into a draft job",
)
def copy_criteria(job_id: int, source_job_id: int, db: DbSession, user: CompanyUser):
    target = svc.get_owned_job(db, job_id, user)
    source = svc.get_owned_job(db, source_job_id, user)
    return _company_view(svc.copy_set(db, target, source))


@router.post(
    "/criteria/check",
    response_model=CheckResult,
    summary="Live guardrail check for one criterion while typing; saves nothing",
)
def check_criterion(body: CheckRequest, user: CompanyUser):
    result = svc.check(body.name, body.description)
    return CheckResult(
        allowed=result.allowed,
        hits=[svc.hit_dict(h) for h in result.hits],
        blocklist_version=result.blocklist_version,
    )
