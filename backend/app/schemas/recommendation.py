from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.application import AI_NOTICE
from app.schemas.job import EmploymentType

MatchLevel = Literal["매우 적합", "적합", "참고"]


class RecommendedJob(BaseModel):
    """The match score is Final rounded to an integer (D42). No Fit, Pref, per-criterion scores or weights.
    Strengths and gaps come from the job's public text and the masked CV text, never from scores (D43)."""

    job_id: int
    title: str
    company_name: str
    location: str
    employment_type: EmploymentType
    deadline: date | None
    match_score: int
    match_level: MatchLevel
    strengths: list[str]
    gaps: list[str]


class RecommendationList(BaseModel):
    items: list[RecommendedJob]
    # Jobs that passed the Pref filter but whose evaluation is not done yet (queued, running, or left
    # for a later call by the caps); not in `items`
    pending_count: int
    notice: str = AI_NOTICE


class JobMatch(BaseModel):
    """The match score of one job for the job detail page (D44). Read only: `none` when no evaluation exists for
    (job, newest confirmed CV), when the seeker applied to the job, or without a confirmed CV or current AI consent."""

    job_id: int
    match_score: int | None
    match_level: MatchLevel | None
    status: Literal["done", "pending", "none"]
    notice: str = AI_NOTICE
