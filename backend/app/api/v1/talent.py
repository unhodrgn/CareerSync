"""Talent recommendation for companies: anonymous seekers who opted in. New evaluations run in the background."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.core.deps import CompanyUser, DbSession
from app.schemas.talent import TalentList
from app.services import evaluation_service, talent_service

router = APIRouter(tags=["talent"])


@router.get(
    "/jobs/{job_id}/talent",
    response_model=TalentList,
    summary="Anonymous opted-in seekers ranked by Fit for one of the company's published jobs",
)
def talent_for_job(
    job_id: int,
    background: BackgroundTasks,
    db: DbSession,
    user: CompanyUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    reco = talent_service.recommend(db, user, job_id, limit)
    for evaluation_id, token in reco.queued:
        evaluation_service.queue(background, db, evaluation_id, token)
    return reco.result
