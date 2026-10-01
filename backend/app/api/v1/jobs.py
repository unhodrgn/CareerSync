"""Job posting routes."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from ai.parsing.extract import analyze_jd
from app.core.deps import CompanyUser, CurrentUser, DbSession
from app.models import JobPosting
from app.schemas.job import JobCreate, JobListItem, JobOut, JobPage, JobUpdate
from app.schemas.cv import JdAnalysisOut
from app.services import ai_runtime, job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _expired(job: JobPosting) -> bool:
    return job.deadline is not None and job.deadline < date.today()


def _out(job: JobPosting) -> JobOut:
    return JobOut(
        id=job.id,
        company_id=job.company_id,
        company_name=job.company.name,
        title=job.title,
        description=job.description,
        employment_type=job.employment_type,
        min_experience_years=job.min_experience_years,
        location=job.location,
        salary_note=job.salary_note,
        deadline=job.deadline,
        expired=_expired(job),
        status=job.status,
        criteria_count=len(job.criteria),
        published_at=job.published_at,
        closed_at=job.closed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _items(db, jobs: list[JobPosting]) -> list[JobListItem]:
    counts = job_service.criteria_counts(db, [j.id for j in jobs])
    return [
        JobListItem(
            id=j.id,
            company_id=j.company_id,
            company_name=j.company.name,
            title=j.title,
            employment_type=j.employment_type,
            min_experience_years=j.min_experience_years,
            location=j.location,
            deadline=j.deadline,
            status=j.status,
            expired=_expired(j),
            criteria_count=counts.get(j.id, 0),
            published_at=j.published_at,
        )
        for j in jobs
    ]


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED, summary="Create a draft job")
def create_job(body: JobCreate, db: DbSession, user: CompanyUser):
    return _out(job_service.create(db, user, body))


@router.get("", response_model=JobPage, summary="Published jobs, newest first (deadline not passed)")
def list_jobs(
    db: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100, description="Search in title")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    jobs, total = job_service.list_public(db, q, limit, offset)
    return JobPage(items=_items(db, jobs), total=total, limit=limit, offset=offset)


# Declared before /{job_id} so "mine" is not parsed as an id
@router.get("/mine", response_model=list[JobListItem], summary="Own company's jobs in every status")
def list_my_jobs(db: DbSession, user: CompanyUser):
    return _items(db, job_service.list_mine(db, user))


@router.get("/{job_id}", response_model=JobOut, summary="Job detail (owner also sees drafts and closed jobs)")
def get_job(job_id: int, db: DbSession, user: CurrentUser):
    return _out(job_service.get_visible_job(db, job_id, user))


@router.patch("/{job_id}", response_model=JobOut, summary="Edit a job (after publish: deadline, location, salary only)")
def update_job(job_id: int, body: JobUpdate, db: DbSession, user: CompanyUser):
    job = job_service.get_owned_job(db, job_id, user)
    return _out(job_service.update(db, job, body))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a draft job")
def delete_job(job_id: int, db: DbSession, user: CompanyUser):
    job_service.delete(db, job_service.get_owned_job(db, job_id, user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/publish", response_model=JobOut, summary="Publish a draft (needs a JD and a valid criteria set)")
def publish_job(job_id: int, db: DbSession, user: CompanyUser):
    job = job_service.get_owned_job(db, job_id, user)
    return _out(job_service.publish(db, job))


@router.post("/{job_id}/close", response_model=JobOut, summary="Close a published job (final)")
def close_job(job_id: int, db: DbSession, user: CompanyUser):
    job = job_service.get_owned_job(db, job_id, user)
    return _out(job_service.close(db, job))


@router.post("/{job_id}/analyze", response_model=JdAnalysisOut, summary="AI parses the JD and suggests a criteria draft (not saved)")
def analyze_job(job_id: int, db: DbSession, user: CompanyUser):
    job = job_service.get_owned_job(db, job_id, user)
    analysis, method = analyze_jd(job.title, job.description, job.min_experience_years, ai_runtime.skills(), ai_runtime.llm())
    return JdAnalysisOut(job_id=job.id, analysis=analysis, method=method)
