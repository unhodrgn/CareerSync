"""Job postings: draft → published → closed (closed is final; only drafts can be deleted)."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class JobStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


EMPLOYMENT_TYPES = ("full_time", "contract", "intern")
# Applicant scores are computed from the other fields, so only these may change after publish
EDITABLE_AFTER_PUBLISH = frozenset({"deadline", "location", "salary_note"})


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'closed')", name="ck_job_postings_status"),
        CheckConstraint(
            "employment_type IN ('full_time', 'contract', 'intern')", name="ck_job_postings_employment_type"
        ),
        CheckConstraint("min_experience_years BETWEEN 0 AND 30", name="ck_job_postings_min_experience"),
        CheckConstraint("length(description) <= 10000", name="ck_job_postings_description_len"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    # JD text
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    employment_type: Mapped[str] = mapped_column(String(20), default="full_time", server_default="full_time")
    # None = 신입 가능
    min_experience_years: Mapped[int | None] = mapped_column(SmallInteger)
    location: Mapped[str] = mapped_column(String(100), default="", server_default="")
    salary_note: Mapped[str] = mapped_column(String(100), default="", server_default="")
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.DRAFT, server_default=JobStatus.DRAFT)
    # Bumped on every criteria save, so cached rankings know to recompute weighted totals
    criteria_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship()  # noqa: F821
    criteria: Mapped[list["JobCriterion"]] = relationship(  # noqa: F821
        back_populates="job", order_by="JobCriterion.position", cascade="all, delete-orphan"
    )
