from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.job import EmploymentType

MAX_ITEMS = 10


def _dedupe(values: list[str]) -> list[str]:
    """Trim, collapse whitespace and drop case-insensitive duplicates, keeping the first spelling."""
    seen, out = set(), []
    for v in values:
        v = " ".join(v.split())
        if v.casefold() not in seen:
            seen.add(v.casefold())
            out.append(v)
    return out


class PreferenceIn(BaseModel):
    """The whole preference set; PUT replaces it. Empty lists mean "no preference" for that field."""

    locations: list[str] = Field(default_factory=list, max_length=MAX_ITEMS, description='희망 근무지, e.g. "서울"')
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=3)
    job_keywords: list[str] = Field(
        default_factory=list, max_length=MAX_ITEMS, description='희망 직무 키워드, e.g. "백엔드", "Java"'
    )
    profile_public: bool = Field(False, description="Opt-in to appear anonymously in talent recommendation")

    @field_validator("locations", "job_keywords")
    @classmethod
    def _text_items(cls, values: list[str]) -> list[str]:
        values = _dedupe(values)
        for v in values:
            if not 2 <= len(v) <= 100:
                raise ValueError("each item must be 2 to 100 characters")
        return values

    @field_validator("employment_types")
    @classmethod
    def _unique_types(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class PreferenceOut(BaseModel):
    locations: list[str]
    employment_types: list[EmploymentType]
    job_keywords: list[str]
    profile_public: bool
    # Set when profile_public was last turned on; null while it is off
    profile_public_at: datetime | None
    updated_at: datetime | None
