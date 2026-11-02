"""Saved jobs (공고 저장, docs/DECISIONS.md D45): seeker only; never visible to companies."""
from fastapi import APIRouter, Response, status

from app.api.v1.jobs import _items  # the same JobListItem rows as the job lists
from app.core.deps import CurrentUser, DbSession
from app.schemas.job import JobListItem
from app.services import saved_job_service as svc

router = APIRouter(tags=["saved jobs"])


@router.get("/saved-jobs/mine", response_model=list[JobListItem], summary="The seeker's saved jobs, newest saved first (closed and expired jobs included)")
def my_saved_jobs(db: DbSession, user: CurrentUser):
    return _items(db, svc.list_mine(db, user))


@router.put("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT, summary="Save a job the seeker can see (idempotent)")
def save_job(job_id: int, db: DbSession, user: CurrentUser):
    svc.save(db, user, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a saved job (idempotent)")
def unsave_job(job_id: int, db: DbSession, user: CurrentUser):
    svc.unsave(db, user, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
