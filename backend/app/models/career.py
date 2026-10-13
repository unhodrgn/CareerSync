"""Cached career-preparation content (skill roadmap, interview questions) per seeker × job × CV version.

Cached so a reload shows the same content and the daily LLM limit can be counted (docs/DECISIONS.md D21).
`method` is "rules" or "llm:<model>"; template fallbacks after an LLM failure or over the limit are not stored.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.cv import JsonType


class CareerContentKind:
    ROADMAP = "roadmap"
    INTERVIEW = "interview"


class CareerContent(Base):
    __tablename__ = "career_contents"
    __table_args__ = (
        UniqueConstraint(
            "seeker_id", "job_id", "cv_profile_id", "kind", "prompt_version", "method", name="uq_career_contents_key"
        ),
        CheckConstraint("kind IN ('roadmap', 'interview')", name="ck_career_contents_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    cv_profile_id: Mapped[int] = mapped_column(ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
