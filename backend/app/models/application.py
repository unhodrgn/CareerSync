"""Applications, and the AI evaluation of a CV profile against a job's criteria.

An evaluation is keyed by (job, CV profile), not by application, so a recommendation that already
scored a seeker is reused when they apply. Per-criterion scores are stored without weights; Fit is
computed at read time from the current weights.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.cv import JsonType


class ApplicationStatus:
    SUBMITTED = "submitted"  # 검토 전
    REVIEWING = "reviewing"  # 서류 검토
    INTERVIEW = "interview"  # 면접 예정
    ON_HOLD = "on_hold"  # 보류
    PASSED = "passed"  # 합격
    REJECTED = "rejected"  # 불합격


APPLICATION_STATUSES = ("submitted", "reviewing", "interview", "on_hold", "passed", "rejected")
_STATUS_SQL = ", ".join(f"'{s}'" for s in APPLICATION_STATUSES)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", "seeker_id", name="uq_applications_job_seeker"),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_applications_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cv_profile_id: Mapped[int] = mapped_column(ForeignKey("cv_profiles.id", ondelete="RESTRICT"))
    # Changed only by a recruiter's action; the AI never changes it
    status: Mapped[str] = mapped_column(String(20), default=ApplicationStatus.SUBMITTED, server_default="submitted")
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    seeker: Mapped["User"] = relationship()  # noqa: F821
    cv_profile: Mapped["CvProfile"] = relationship()  # noqa: F821


class EvaluationStatus:
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("job_id", "cv_profile_id", name="uq_evaluations_job_profile"),
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="ck_evaluations_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    cv_profile_id: Mapped[int] = mapped_column(ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default=EvaluationStatus.PENDING, server_default="pending")
    error: Mapped[str] = mapped_column(Text, default="", server_default="")
    # What produced the scores, stored with every result (README design rules)
    llm_model: Mapped[str] = mapped_column(String(60), default="", server_default="")
    embedding_model: Mapped[str] = mapped_column(String(100), default="", server_default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="", server_default="")
    skills_version: Mapped[str] = mapped_column(String(20), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scores: Mapped[list["CriterionScore"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")


class CriterionScore(Base):
    __tablename__ = "criterion_scores"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "job_criteria_id", name="uq_criterion_scores_eval_criterion"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_criterion_scores_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"), index=True)
    job_criteria_id: Mapped[int] = mapped_column(ForeignKey("job_criteria.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(SmallInteger)
    level: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str] = mapped_column(Text)
    # Quotes from the masked CV text
    evidence: Mapped[list] = mapped_column(JsonType, default=list)
    # "rule:skill", "llm:<model>", "retrieval", ...
    method: Mapped[str] = mapped_column(String(60))

    evaluation: Mapped[Evaluation] = relationship(back_populates="scores")
