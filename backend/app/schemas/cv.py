from datetime import datetime

from pydantic import BaseModel

from ai.parsing.profile import CvProfile, JdAnalysis


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


class CvUpdate(BaseModel):
    profile: CvProfile
    confirm: bool = True


class JdAnalysisOut(BaseModel):
    job_id: int
    analysis: JdAnalysis
    method: str
