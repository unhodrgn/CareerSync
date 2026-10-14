from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROJECT_MAX_TECHS = 20


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    intro: str
    talent_profile: str = Field(description="인재상")


class CompanyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    intro: str = Field("", max_length=1000)
    talent_profile: str = Field("", max_length=1000, description="인재상")


class CompanyProjectIn(BaseModel):
    """A running project of the company (D23): shown on the profile and used as context for JD drafts, never in scoring."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    techs: list[str] = Field(default_factory=list, max_length=PROJECT_MAX_TECHS)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("프로젝트 이름을 입력하세요.")
        return v

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        return v.strip()

    @field_validator("techs")
    @classmethod
    def _techs(cls, v: list[str]) -> list[str]:
        out = [" ".join(t.split()) for t in v]
        if any(not t or len(t) > 100 for t in out):
            raise ValueError("기술 이름은 1~100자여야 합니다.")
        return out


class CompanyProjectOut(BaseModel):
    id: int
    name: str
    description: str
    techs: list[str]
    created_at: datetime
    updated_at: datetime


class CompanyPublicOut(CompanyOut):
    """Public company profile: the profile plus its running projects (D23)."""

    projects: list[CompanyProjectOut]
