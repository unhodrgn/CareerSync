"""Job routes. Only publishing for now; creating and editing jobs belongs to the job management feature."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import CompanyUser, DbSession
from app.models.job import JobStatus
from app.services import criteria_service

router = APIRouter(tags=["jobs"])


class JobStatusOut(BaseModel):
    id: int
    status: str


@router.post("/jobs/{job_id}/publish", response_model=JobStatusOut, summary="Publish a draft job (needs a valid criteria set)")
def publish_job(job_id: int, db: DbSession, user: CompanyUser):
    job = criteria_service.get_owned_job(db, job_id, user)
    if job.status != JobStatus.DRAFT:
        raise criteria_service.CriteriaError(409, "JOB_NOT_DRAFT", "작성 중인 공고만 게시할 수 있습니다.")
    criteria_service.assert_publishable(job)
    job.status = JobStatus.PUBLISHED
    db.commit()
    return JobStatusOut(id=job.id, status=job.status)
