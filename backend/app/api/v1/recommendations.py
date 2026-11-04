"""Job recommendation for seekers. New evaluations run in the background; the call never waits."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.recommendation import RecommendationList
from app.services import evaluation_service, recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get(
    "/jobs",
    response_model=RecommendationList,
    summary="Jobs ranked by Final = 0.5·Fit + 0.5·Pref (band only); jobs still being analyzed are counted in pending_count",
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
