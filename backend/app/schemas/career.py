from typing import Literal

from pydantic import BaseModel

from app.schemas.application import AI_NOTICE


class CareerGap(BaseModel):
    """A skill or certificate the job names that the CV text does not show (no scores, D1, D21)."""

    name: str
    kind: Literal["skill", "certificate"]


class LearningResource(BaseModel):
    title: str
    url: str


class RoadmapStep(BaseModel):
    order: int
    skill: str
    kind: Literal["skill", "certificate"]
    goal: str
    activities: list[str]
    # Only from data/learning_resources.yaml; never written by the LLM
    resources: list[LearningResource]


class RoadmapOut(BaseModel):
    job_id: int
    # "rules" or "llm:<model>"
    method: str
    gaps: list[CareerGap]
    steps: list[RoadmapStep]
    # Shown instead of steps when nothing is missing
    message: str | None = None
    # True when the daily LLM limit was reached and the template was returned instead
    limited: bool = False
    notice: str = AI_NOTICE
