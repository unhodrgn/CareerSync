"""Job postings.

Minimal stub: only the columns the criteria feature needs. The job management work extends this table.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class JobStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (CheckConstraint("status IN ('draft', 'published', 'closed')", name="ck_job_postings_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.DRAFT, server_default=JobStatus.DRAFT)
    # Bumped on every criteria save, so cached rankings know to recompute weighted totals
    criteria_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    criteria: Mapped[list["JobCriterion"]] = relationship(  # noqa: F821
        back_populates="job", order_by="JobCriterion.position", cascade="all, delete-orphan"
    )
