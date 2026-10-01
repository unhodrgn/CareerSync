from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

EmploymentType = Literal["full_time", "contract", "intern"]
JobStatusName = Literal["draft", "published", "closed"]


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=10000, description="JD text; required before publishing")
    employment_type: EmploymentType = "full_time"
    min_experience_years: int | None = Field(None, ge=0, le=30, description="None = 신입 가능")
    location: str = Field("", max_length=100)
    salary_note: str = Field("", max_length=100)
    deadline: date | None = None


class JobUpdate(BaseModel):
    """Partial update: only fields present in the request change. After publish only deadline, location, salary_note."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=10000)
    employment_type: EmploymentType | None = None
    min_experience_years: int | None = Field(None, ge=0, le=30)
    location: str | None = Field(None, max_length=100)
    salary_note: str | None = Field(None, max_length=100)
    deadline: date | None = None


class JobOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    description: str
    employment_type: EmploymentType
    min_experience_years: int | None
    location: str
    salary_note: str
    deadline: date | None
    expired: bool = Field(description="Deadline has passed (shown as 마감); status is unchanged")
    status: JobStatusName
    criteria_count: int
    published_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobListItem(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    employment_type: EmploymentType
    min_experience_years: int | None
    location: str
    deadline: date | None
    status: JobStatusName
    expired: bool
    criteria_count: int
    published_at: datetime | None


class JobPage(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int
