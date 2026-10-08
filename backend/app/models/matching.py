"""Seeker preferences, talent discovery offers, and company projects.

These tables are DB groundwork for the planned two-way recommendation flow:
- seeker preferences are used to compute the seeker-side preference (Pref) score;
- only seekers who opt in via ``profile_public`` may appear in talent discovery;
- contact details remain in ``users`` and should only be returned by the API after an
  offer has been accepted;
- company projects provide structured context that recommendation/scoring can use later.
"""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SeekerPreference(Base):
    __tablename__ = "seeker_preferences"
    __table_args__ = (UniqueConstraint("seeker_id", name="uq_seeker_preferences_seeker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Opt-in for anonymous appearance in the future talent-recommendation feature.
    profile_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Audit timestamp for the most recent opt-in; null when never opted in / currently off.
    profile_public_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    seeker: Mapped["User"] = relationship()  # noqa: F821
    locations: Mapped[list["SeekerPreferredLocation"]] = relationship(
        back_populates="preference", cascade="all, delete-orphan", order_by="SeekerPreferredLocation.id"
    )
    employment_types: Mapped[list["SeekerPreferredEmploymentType"]] = relationship(
        back_populates="preference", cascade="all, delete-orphan", order_by="SeekerPreferredEmploymentType.id"
    )
    job_keywords: Mapped[list["SeekerJobKeyword"]] = relationship(
        back_populates="preference", cascade="all, delete-orphan", order_by="SeekerJobKeyword.id"
    )


class SeekerPreferredLocation(Base):
    __tablename__ = "seeker_preferred_locations"
    __table_args__ = (
        UniqueConstraint("preference_id", "location", name="uq_seeker_preferred_locations_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preference_id: Mapped[int] = mapped_column(
        ForeignKey("seeker_preferences.id", ondelete="CASCADE"), index=True
    )
    location: Mapped[str] = mapped_column(String(100))

    preference: Mapped[SeekerPreference] = relationship(back_populates="locations")


class SeekerPreferredEmploymentType(Base):
    __tablename__ = "seeker_preferred_employment_types"
    __table_args__ = (
        UniqueConstraint("preference_id", "employment_type", name="uq_seeker_preferred_employment_types_value"),
        CheckConstraint(
            "employment_type IN ('full_time', 'contract', 'intern')",
            name="ck_seeker_preferred_employment_types_value",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preference_id: Mapped[int] = mapped_column(
        ForeignKey("seeker_preferences.id", ondelete="CASCADE"), index=True
    )
    employment_type: Mapped[str] = mapped_column(String(20))

    preference: Mapped[SeekerPreference] = relationship(back_populates="employment_types")


class SeekerJobKeyword(Base):
    __tablename__ = "seeker_job_keywords"
    __table_args__ = (
        UniqueConstraint("preference_id", "keyword", name="uq_seeker_job_keywords_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preference_id: Mapped[int] = mapped_column(
        ForeignKey("seeker_preferences.id", ondelete="CASCADE"), index=True
    )
    keyword: Mapped[str] = mapped_column(String(100))

    preference: Mapped[SeekerPreference] = relationship(back_populates="job_keywords")


class TalentOfferStatus:
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class TalentOffer(Base):
    __tablename__ = "talent_offers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'cancelled')",
            name="ck_talent_offers_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # An offer may be general, so a job is optional. Keep the offer if the job is deleted.
    job_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=TalentOfferStatus.PENDING, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship()  # noqa: F821
    seeker: Mapped["User"] = relationship()  # noqa: F821
    job: Mapped["JobPosting | None"] = relationship()  # noqa: F821


class CompanyProject(Base):
    __tablename__ = "company_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()  # noqa: F821
    techs: Mapped[list["CompanyProjectTech"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="CompanyProjectTech.id"
    )


class CompanyProjectTech(Base):
    __tablename__ = "company_project_techs"
    __table_args__ = (
        UniqueConstraint("company_project_id", "tech_name", name="uq_company_project_techs_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_project_id: Mapped[int] = mapped_column(
        ForeignKey("company_projects.id", ondelete="CASCADE"), index=True
    )
    tech_name: Mapped[str] = mapped_column(String(100))

    project: Mapped[CompanyProject] = relationship(back_populates="techs")
