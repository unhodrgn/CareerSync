from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ai.parsing.profile import CvProfile, JdAnalysis
from app.schemas.application import AI_NOTICE


class CvOut(BaseModel):
    id: int  # profile id
    document_id: int
    file_name: str
    pages: int
    version: int
    profile: CvProfile
    # "rules", "llm:<model>" or "seeker"
    method: str
    confirmed: bool
    confirmed_at: datetime | None
    # Personal data found and masked before analysis, e.g. ["email", "phone"]
    masked_kinds: list[str]
    total_experience_months: int
    created_at: datetime
    notice: str = AI_NOTICE


class CvUpdate(BaseModel):
    profile: CvProfile
    confirm: bool = True


class BlockedSuggestion(BaseModel):
    """A suggested criterion left out because saving it would fail (issue 7)."""

    name: str
    # CRITERIA_BLOCKED (legal guardrail) or CRITERIA_MAJOR_REQUIRED (education without a major, D13)
    code: str
    reason: str


class CvReviewItem(BaseModel):
    title: str
    detail: str
    # A line of the masked CV text (verified), or null
    cv_quote: str | None
    # True for rule findings that change what scoring can read; always shown
    affects_scoring: bool


class CvReviewOut(BaseModel):
    """AI self-check of one CV version: strengths and improvements, no score (D25)."""

    profile_id: int
    strengths: list[CvReviewItem]
    improvements: list[CvReviewItem]
    method: str
    # True when the daily LLM limit was reached and the rules review was returned
    limited: bool
    notice: str = AI_NOTICE


class JdAnalysisOut(BaseModel):
    job_id: int
    # Only suggestions that pass the guardrail and D13; weights rescaled to 100 after removing the others
    analysis: JdAnalysis
    blocked: list[BlockedSuggestion] = []
    method: str
    notice: str = AI_NOTICE


class JdDraftIn(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=10)
    notes: str = Field("", max_length=1000)
    # Own running projects used as context (D23)
    project_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, v: list[str]) -> list[str]:
        out = [" ".join(k.split()) for k in v]
        if any(not k or len(k) > 50 for k in out):
            raise ValueError("키워드는 1~50자여야 합니다.")
        return out


class JdDraftSections(BaseModel):
    intro: str
    responsibilities: list[str]
    requirements: list[str]
    preferred: list[str]


class DroppedSentence(BaseModel):
    text: str
    reason: str


class JdDraftOut(BaseModel):
    """An AI JD draft for the editor; nothing is saved (D24)."""

    job_id: int
    description: str
    sections: JdDraftSections
    dropped: list[DroppedSentence]
    method: str
    # True when the daily LLM limit was reached and the template was returned
    limited: bool
    notice: str = AI_NOTICE
