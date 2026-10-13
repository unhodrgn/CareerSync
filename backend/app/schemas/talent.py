from pydantic import BaseModel, Field

from app.schemas.application import AI_NOTICE


class TalentCriterionScore(BaseModel):
    """Score and level only: `reason` and `evidence` quote or paraphrase CV lines (issue 24)."""

    criterion_id: int
    name: str
    score: int
    level: int


class TalentEducation(BaseModel):
    degree: str
    major: str


class TalentDesired(BaseModel):
    locations: list[str]
    employment_types: list[str]
    job_keywords: list[str]


class TalentCandidate(BaseModel):
    """Anonymous profile (PROJECT_DOCUMENTATION.md §6.1). Never: name, email, school, organization names,
    project names or descriptions, dates, CV text, summary, reasons or evidence."""

    anonymous_id: str = Field(description="Stable within one company, different across companies")
    fit: float
    criteria: list[TalentCriterionScore]
    skills: list[str]
    experience_years: int = Field(description="Verified against the CV text, rounded down")
    roles: list[str]
    project_techs: list[str]
    education: list[TalentEducation]
    certificates: list[str]
    desired: TalentDesired
    # Latest offer from this company to this seeker, if any (offers are added in a later step)
    offer_status: str | None = None


class TalentList(BaseModel):
    job_id: int
    items: list[TalentCandidate]
    # Candidates that passed the filters but whose evaluation is not done yet; not in `items`
    pending_count: int
    notice: str = AI_NOTICE
