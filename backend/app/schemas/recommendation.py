from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.application import AI_NOTICE
from app.schemas.job import EmploymentType

MatchLevel = Literal["매우 적합", "적합", "참고"]


class RecommendedJob(BaseModel):
    """No Fit, Pref, Final, per-criterion scores or weights: seekers see the band only (D1)."""

    job_id: int
    title: str
    company_name: str
    location: str
    employment_type: EmploymentType
    deadline: date | None
    match_level: MatchLevel


class RecommendationList(BaseModel):
    items: list[RecommendedJob]
    # Jobs that passed the Pref filter but whose evaluation is not done yet (queued, running, or left
    # for a later call by the caps); not in `items`
    pending_count: int
    notice: str = AI_NOTICE
