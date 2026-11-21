"""Practice interviews: sessions, the masked transcript and the daily quota ledger (docs/DECISIONS.md D51–D58, D61–D63).

Schema only (M4 S1). Nothing here is read or written by an endpoint yet.

- `InterviewSession`: one practice interview of one seeker for one job. Holds the canonical plan the engine runs
  (`plan`: validated, no CV quote, no raw CV, no weight), the validated coverage snapshot, the consent record, the
  lifecycle (`status`, `active_until`, `expires_at`) and the final feedback with its lease. The public feedback status is
  derived (`feedback IS NOT NULL` means ready); expiry is derived from `expires_at`.
- `InterviewTurn`: one line of the transcript, masked text only (D53). Never audio or video.
- `InterviewQuota`: the daily quota ledger. One row per seeker, KST day and kind, with the limit that was in force when the
  row was created. It has no foreign key to a session, so deleting a session cannot give a reservation back.

JSON columns store None as SQL NULL (`none_as_null`): the feedback lease and the stored-feedback checks use `IS NULL`.
"""
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

InterviewJson = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class InterviewStatus:
    PLANNING = "planning"  # the session is reserved and its plan is being made (a lease, `active_until`)
    CREATED = "created"  # the plan is ready; the candidate has until `active_until` to join
    LIVE = "live"  # the first turn arrived; `active_until` is the end of the time budget
    COMPLETED = "completed"  # the engine ended the interview
    ABORTED = "aborted"  # the seeker ended it, or it went stale, or planning failed
    ALL = (PLANNING, CREATED, LIVE, COMPLETED, ABORTED)
    ACTIVE = (PLANNING, CREATED, LIVE)  # at most one per seeker


class QuotaKind:
    SESSION = "session"
    PLAN_MODEL = "plan_model"
    FEEDBACK_MODEL = "feedback_model"
    ALL = (SESSION, PLAN_MODEL, FEEDBACK_MODEL)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


# One literal, used by the model and written out again in migration 0012; the migration tests compare the two
ACTIVE_SQL = _in("status", InterviewStatus.ACTIVE)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(_in("status", InterviewStatus.ALL), name="ck_interview_sessions_status"),
        CheckConstraint("feedback_attempts >= 0", name="ck_interview_sessions_feedback_attempts"),
        CheckConstraint("feedback IS NULL OR feedback_method IS NOT NULL", name="ck_interview_sessions_feedback_method"),
        Index("ix_interview_sessions_seeker_created", "seeker_id", "created_at"),
        # A seeker has at most one session that is planning, created or live
        Index(
            "uq_interview_sessions_active",
            "seeker_id",
            unique=True,
            postgresql_where=sql_text(ACTIVE_SQL),
            sqlite_where=sql_text(ACTIVE_SQL),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    cv_profile_id: Mapped[int] = mapped_column(ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(10))
    # A code ("seeker_ended", "not_joined", "planning_lost", "stale_live", or the engine's reason); never text
    end_reason: Mapped[str | None] = mapped_column(String(40))

    # The canonical plan (InterviewPlan.to_dict after validate_plan(cv_text=None)); null until planning finishes
    plan: Mapped[dict | None] = mapped_column(InterviewJson)
    # How the question bank was made: "rules" or "llm:<model>"
    plan_method: Mapped[str | None] = mapped_column(String(80))
    plan_sha256: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(20))
    # The InterviewLimits the session runs with
    limits: Mapped[dict] = mapped_column(InterviewJson)
    # coverage_snapshot of the engine (codes only), as validated by the backend
    coverage: Mapped[dict | None] = mapped_column(InterviewJson)

    consent_version: Mapped[str] = mapped_column(String(20))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # By status: planning, the end of the planning lease; created, the join deadline; live, the end of the time budget;
    # completed and aborted, null
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # created_at + 30 days (D53); never extended
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    feedback: Mapped[dict | None] = mapped_column(InterviewJson)
    feedback_method: Mapped[str | None] = mapped_column(String(80))
    feedback_prompt_version: Mapped[str | None] = mapped_column(String(20))
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Model attempts only (each one is also a reservation in the daily ledger)
    feedback_attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=sql_text("0"))
    feedback_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback_lease_token: Mapped[str | None] = mapped_column(String(32))

    turns: Mapped[list["InterviewTurn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="InterviewTurn.seq"
    )


class InterviewTurn(Base):
    """One line of the transcript. `text` is masked (D53); nothing else about the speaker is kept."""

    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_interview_turns_session_seq"),
        CheckConstraint("seq >= 1", name="ck_interview_turns_seq"),
        CheckConstraint(_in("role", ("agent", "candidate")), name="ck_interview_turns_role"),
        CheckConstraint("item_index IS NULL OR item_index >= 0", name="ck_interview_turns_item_index"),
        CheckConstraint("length(text) <= 4000", name="ck_interview_turns_text_len"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))
    # question | follow_up | clarify | repeat | redirect | nudge | closing | answer
    kind: Mapped[str] = mapped_column(String(20))
    item_index: Mapped[int | None] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    # "rules" or "llm:<model>" (D54)
    method: Mapped[str] = mapped_column(String(80), default="rules", server_default="rules")
    analysis: Mapped[dict | None] = mapped_column(InterviewJson)
    # Which kinds of data were masked, counts only
    masked_kinds: Mapped[dict | None] = mapped_column(InterviewJson)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[InterviewSession] = relationship(back_populates="turns")


class InterviewQuota(Base):
    """The daily quota ledger: reservations per seeker, KST day and kind (see `interview_quota_service`).

    `quota_limit` is the limit in force when the row was created, so changing a setting mid-day does not change a day that
    has started. The database keeps `used` within it. No foreign key to a session: deleting a session never gives a
    reservation back.
    """

    __tablename__ = "interview_quota"
    __table_args__ = (
        CheckConstraint(_in("kind", QuotaKind.ALL), name="ck_interview_quota_kind"),
        CheckConstraint("quota_limit >= 0", name="ck_interview_quota_limit"),
        CheckConstraint("used >= 0 AND used <= quota_limit", name="ck_interview_quota_used"),
    )

    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, autoincrement=False)
    # Indexed for the global deletion of past days (`WHERE kst_day < today`), which the primary key cannot serve: its
    # first column is the seeker
    kst_day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    kind: Mapped[str] = mapped_column(String(14), primary_key=True)
    used: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=sql_text("0"))
    quota_limit: Mapped[int] = mapped_column(SmallInteger)
