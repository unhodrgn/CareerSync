"""Career preparation for seekers: skill roadmap and interview questions for a job."""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.career import InterviewOut, RoadmapOut
from app.services import career_service

router = APIRouter(tags=["career"])


@router.post(
    "/jobs/{job_id}/roadmap",
    response_model=RoadmapOut,
    summary="Skills and certificates the job names that your CV does not show, with a learning plan (cached)",
)
def roadmap(job_id: int, db: DbSession, user: CurrentUser):
    return career_service.roadmap(db, user, job_id)


@router.post(
    "/jobs/{job_id}/interview-questions",
    response_model=InterviewOut,
    summary="Interview practice questions for a job, from its posting, criteria and your CV (cached)",
)
def interview_questions(job_id: int, db: DbSession, user: CurrentUser):
    return career_service.interview_questions(db, user, job_id)
