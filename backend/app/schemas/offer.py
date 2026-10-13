from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.job import EmploymentType
from app.schemas.talent import AnonymousProfile

OfferStatus = Literal["pending", "accepted", "rejected", "cancelled", "expired"]


class OfferCreate(BaseModel):
    job_id: int
    anonymous_id: str = Field(max_length=20, description="From GET /api/jobs/{job_id}/talent")
    message: str | None = Field(None, max_length=1000, description="Optional note to the seeker")

    @field_validator("message")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class OfferJob(BaseModel):
    job_id: int
    title: str
    location: str
    employment_type: EmploymentType


class Contact(BaseModel):
    display_name: str
    email: str


class SeekerOffer(BaseModel):
    """What the seeker sees about an offer they received."""

    offer_id: int
    company_name: str
    job: OfferJob | None
    message: str | None
    status: OfferStatus
    created_at: datetime
    expires_at: datetime
    responded_at: datetime | None


class SentOffer(BaseModel):
    """What the company sees about an offer it sent. `candidate` is null while the seeker is not public
    (opt-in off or AI consent withdrawn); `contact` only after the seeker accepted."""

    offer_id: int
    job_id: int | None
    job_title: str | None
    anonymous_id: str
    message: str | None
    status: OfferStatus
    created_at: datetime
    expires_at: datetime
    responded_at: datetime | None
    candidate: AnonymousProfile | None
    contact: Contact | None
