"""Structured CV and JD profiles (schema cv_profile.v1 / jd_profile.v1).

The same Pydantic models are the LLM's JSON output schema, the DB payload and the API body,
so a seeker's edits go through the same validation as the model's output.
"""
from pydantic import BaseModel, Field

CV_SCHEMA_VERSION = "cv_profile.v1"
JD_SCHEMA_VERSION = "jd_profile.v1"

YEAR_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class Experience(BaseModel):
    org: str = Field("", max_length=100, description="Company or organization")
    role: str = Field("", max_length=100, description="Job title or role")
    start: str | None = Field(None, pattern=YEAR_MONTH, description="YYYY-MM")
    end: str | None = Field(None, pattern=YEAR_MONTH, description="YYYY-MM, null if current")
    description: str = Field("", max_length=2000)
    source: str = Field("", max_length=500, description="Line of the CV this item was read from, copied verbatim")


class Project(BaseModel):
    name: str = Field("", max_length=200)
    role: str = Field("", max_length=100)
    tech: list[str] = Field(default_factory=list, description="Technologies used")
    description: str = Field("", max_length=2000)
    source: str = Field("", max_length=500)


class Education(BaseModel):
    school: str = Field("", max_length=100)
    major: str = Field("", max_length=100)
    degree: str = Field("", max_length=20, description="고졸, 전문학사, 학사, 석사, 박사 or empty")
    source: str = Field("", max_length=500)


class Certificate(BaseModel):
    name: str = Field("", max_length=100)
    date: str | None = Field(None, pattern=YEAR_MONTH)
    source: str = Field("", max_length=500)


class CvProfile(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=100)
    experiences: list[Experience] = Field(default_factory=list, max_length=50)
    projects: list[Project] = Field(default_factory=list, max_length=50)
    education: list[Education] = Field(default_factory=list, max_length=10)
    certificates: list[Certificate] = Field(default_factory=list, max_length=30)
    summary: str = Field("", max_length=500, description="2 neutral sentences on the candidate's main skills, in Korean")


class JdProfile(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_years: int | None = Field(None, ge=0, le=30)
    duties: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    education: str = ""


class SuggestedCriterion(BaseModel):
    name: str = Field(max_length=50)
    description: str = Field("", max_length=500)
    category: str = Field(description="skill | experience | project | certificate | education | other")
    weight: int = Field(ge=1, le=100)


class JdAnalysis(BaseModel):
    profile: JdProfile
    criteria: list[SuggestedCriterion]
