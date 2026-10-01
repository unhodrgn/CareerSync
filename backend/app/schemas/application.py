from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ApplicationStatusT = Literal["submitted", "reviewing", "interview", "on_hold", "passed", "rejected"]
EvaluationStatusT = Literal["pending", "done", "failed"]

AI_NOTICE = "AI 분석은 참고용입니다. 채용 여부는 기업이 최종 판단합니다."


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    job_title: str
    company_name: str
    status: ApplicationStatusT
    evaluation_status: EvaluationStatusT | None
    created_at: datetime


class CriterionBrief(BaseModel):
    id: int
    name: str
    category: str
    # Effective weight used for Fit (criteria a newer blocklist blocks are left out and the rest rescaled)
    weight: float


class ScoreBrief(BaseModel):
    criterion_id: int
    score: int


class ApplicantRow(BaseModel):
    application_id: int
    rank: int | None  # None while the evaluation is pending or failed
    name: str
    email: str
    status: ApplicationStatusT
    applied_at: datetime
    experience_months: int
    evaluation_status: EvaluationStatusT
    fit: float | None
    strong_count: int
    scores: list[ScoreBrief]


class ExcludedBrief(BaseModel):
    id: int
    name: str


class ApplicantList(BaseModel):
    job_id: int
    job_title: str
    criteria: list[CriterionBrief]
    excluded_criteria: list[ExcludedBrief]
    items: list[ApplicantRow]
    notice: str = AI_NOTICE


class CriterionEvaluation(BaseModel):
    criterion_id: int
    name: str
    description: str
    category: str
    weight: float
    score: int
    level: int
    reason: str
    evidence: list[str]
    method: str


class EvaluationOut(BaseModel):
    application_id: int
    job_id: int
    name: str
    status: EvaluationStatusT
    error: str
    fit: float | None
    summary: str
    items: list[CriterionEvaluation]
    excluded_criteria: list[ExcludedBrief]
    llm_model: str
    embedding_model: str
    prompt_version: str
    finished_at: datetime | None
    notice: str = AI_NOTICE


class StatusUpdate(BaseModel):
    status: ApplicationStatusT
