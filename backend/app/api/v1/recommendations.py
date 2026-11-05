"""Job recommendation and match scores for seekers. New evaluations run in the background; the call never waits.
The two score endpoints only read existing evaluations (docs/DECISIONS.md D43)."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.recommendation import JobMatch, JobScoreList, RecommendationList
from app.services import evaluation_service, recommendation_service

router = APIRouter(tags=["recommendations"])

MAX_JOB_IDS = 100
# 1–100 comma-separated ids; anything else is a 422 from validation
JOB_IDS_PATTERN = rf"^\d{{1,9}}(,\d{{1,9}}){{0,{MAX_JOB_IDS - 1}}}$"


@router.get(
    "/recommendations/jobs",
    response_model=RecommendationList,
    summary="Jobs ranked by Final = 0.5·Fit + 0.5·Pref with the match score, band, preference score and category "
    "scores; jobs still being analyzed are counted in pending_count",
)
def recommend_jobs(
    background: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    reco = recommendation_service.recommend(db, user, limit)
    for evaluation_id, token in reco.queued:
        evaluation_service.queue(background, db, evaluation_id, token)
    return reco.result


@router.get(
    "/recommendations/matches",
    response_model=JobScoreList,
    summary="Scores of the listed jobs from existing evaluations (job list); never creates or queues one",
)
def job_scores(
    db: DbSession,
    user: CurrentUser,
    job_ids: Annotated[str, Query(pattern=JOB_IDS_PATTERN, description="1–100 job ids, comma-separated")],
):
    return recommendation_service.matches(db, user, [int(i) for i in job_ids.split(",")])


@router.get(
    "/jobs/{job_id}/match",
    response_model=JobMatch,
    summary="Scores of one job from an existing evaluation, with each criterion's score; never creates or queues one",
)
def job_match(job_id: int, db: DbSession, user: CurrentUser):
    return recommendation_service.job_match(db, user, job_id)
