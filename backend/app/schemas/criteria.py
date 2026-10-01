from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["skill", "experience", "project", "certificate", "education", "other"]
Importance = Literal["높음", "보통", "낮음"]


class CriterionIn(BaseModel):
    id: int | None = Field(None, description="Existing criterion id; omit to add a new one (draft jobs only)")
    name: str = Field(min_length=1, max_length=50)
    description: str = Field("", max_length=500)
    category: Category
    weight: int = Field(ge=1, le=100)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class CriteriaSetIn(BaseModel):
    """The whole set, in display order. Count, unique names and the weight total are checked by the service."""

    items: list[CriterionIn]


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    category: Category
    weight: int
    position: int
    importance: Importance


class CriteriaSetOut(BaseModel):
    job_id: int
    items: list[CriterionOut]
    total_weight: int
    blocklist_version: str


class SeekerCriterionOut(BaseModel):
    """What a seeker may see: no raw weights (README scoring rules)."""

    name: str
    category: Category
    importance: Importance


class SeekerCriteriaSetOut(BaseModel):
    job_id: int
    items: list[SeekerCriterionOut]


class CheckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = Field("", max_length=500)


class GuardrailHitOut(BaseModel):
    index: int | None = None
    field: str
    rule_id: str
    category: str
    matched: str
    reason: str
    law_ref: str


class CheckResult(BaseModel):
    allowed: bool
    hits: list[GuardrailHitOut]
    blocklist_version: str
