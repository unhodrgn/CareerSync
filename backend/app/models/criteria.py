"""Company evaluation criteria: per job posting, weights summing to 100.

Per-criterion AI scores reference job_criteria.id; weighted totals are computed at read time
from the current weights, so weights may change after publish but criteria may not be added or removed.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

CRITERION_CATEGORIES = ("skill", "experience", "project", "certificate", "education", "other")
_CATEGORY_SQL = ", ".join(f"'{c}'" for c in CRITERION_CATEGORIES)


class JobCriterion(Base):
    __tablename__ = "job_criteria"
    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 100", name="ck_job_criteria_weight"),
        CheckConstraint(f"category IN ({_CATEGORY_SQL})", name="ck_job_criteria_category"),
        CheckConstraint("length(description) <= 500", name="ck_job_criteria_description_len"),
        Index("uq_job_criteria_job_name", "job_id", text("lower(trim(name))"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    # Rubric: what a strong candidate looks like for this item; fed to the scoring prompt
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    category: Mapped[str] = mapped_column(String(20))
    weight: Mapped[int] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # Blocklist version that approved this criterion
    guardrail_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped["JobPosting"] = relationship(back_populates="criteria")  # noqa: F821


class CriteriaGuardrailLog(Base):
    """Audit trail of criteria the guardrail blocked (one row per hit)."""

    __tablename__ = "criteria_guardrail_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id", ondelete="SET NULL"))
    input_name: Mapped[str] = mapped_column(Text)
    input_description: Mapped[str] = mapped_column(Text, default="")
    rule_id: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(50))
    law_ref: Mapped[str] = mapped_column(String(100))
    blocklist_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
