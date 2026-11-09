from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.application import AI_NOTICE
from app.schemas.criteria import Category, Importance
from app.schemas.gate import RequiredGateOut
from app.schemas.job import EmploymentType

MatchLevel = Literal["매우 적합", "적합", "참고"]


class CategoryScore(BaseModel):
    """Plain mean (no weights) of the job's criterion scores in one category, rounded down (D42)."""

    category: Category
    score: int


class RecommendedJob(BaseModel):
    """What a seeker sees of a recommended job (D42): the match score (Final rounded down) with its band, the
    preference score (Pref rounded down) and the category scores. Never Fit as its own number, weights or the
    per-criterion reason/evidence."""

    job_id: int
    title: str
    company_name: str
    location: str
    employment_type: EmploymentType
    deadline: date | None
    match_score: int
    match_level: MatchLevel
    preference_score: int
    categories: list[CategoryScore]
    # Required criteria gate (D50): PASS or REVIEW here (FAIL jobs are not recommended); the seeker's own CV lines
    required_gate: RequiredGateOut | None = None


class RecommendationList(BaseModel):
    items: list[RecommendedJob]
    # Jobs that passed the Pref filter but whose evaluation is not done yet (queued, running, or left
    # for a later call by the caps); not in `items`
    pending_count: int
    notice: str = AI_NOTICE


class JobScore(BaseModel):
    """The scores of one job read from an existing evaluation (D43). `match_level` is null below 40: the number is
    shown without a band."""

    job_id: int
    match_score: int
    match_level: MatchLevel | None
    preference_score: int
    categories: list[CategoryScore]


class JobScoreList(BaseModel):
    """`GET /api/recommendations/matches`: only the listed jobs that have scores; the others are left out."""

    items: list[JobScore]
    notice: str = AI_NOTICE


class CriterionMatch(BaseModel):
    """One criterion's score for the job detail page (D42): no weight, reason or evidence."""

    criterion_id: int
    name: str
    category: Category
    importance: Importance
    score: int


class JobMatch(BaseModel):
    """`GET /api/jobs/{job_id}/match` (D43). Read only. `done`: the scores below; `pending`: an evaluation is queued or
    running; `none`: no evaluation, a failed one, an applied job, no confirmed CV or no current AI consent."""

    job_id: int
    status: Literal["done", "pending", "none"]
    match_score: int | None = None
    match_level: MatchLevel | None = None
    preference_score: int | None = None
    categories: list[CategoryScore] = []
    criteria: list[CriterionMatch] = []
    # Required criteria gate (D50) for this seeker and job, also while no score exists; null without a confirmed CV,
    # without current AI consent, or for an applied job
    required_gate: RequiredGateOut | None = None
    notice: str = AI_NOTICE
