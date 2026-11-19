"""Add the practice-interview tables: interview_sessions, interview_turns and the daily quota ledger interview_quota.

Schema only (M4 S1, docs/DECISIONS.md D51–D58). No existing table is changed.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('planning', 'created', 'live')"


def _json() -> sa.types.TypeEngine:
    # None is stored as SQL NULL, so the feedback lease and the stored-feedback checks can use IS NULL
    return sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), "postgresql")


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seeker_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_profile_id", sa.Integer(), sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("end_reason", sa.String(40), nullable=True),
        sa.Column("plan", _json(), nullable=True),
        sa.Column("plan_method", sa.String(80), nullable=True),
        sa.Column("plan_sha256", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("limits", _json(), nullable=False),
        sa.Column("coverage", _json(), nullable=True),
        sa.Column("consent_version", sa.String(20), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feedback", _json(), nullable=True),
        sa.Column("feedback_method", sa.String(80), nullable=True),
        sa.Column("feedback_prompt_version", sa.String(20), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback_attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("feedback_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback_lease_token", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "status IN ('planning', 'created', 'live', 'completed', 'aborted')", name="ck_interview_sessions_status"
        ),
        sa.CheckConstraint("feedback_attempts >= 0", name="ck_interview_sessions_feedback_attempts"),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback_method IS NOT NULL", name="ck_interview_sessions_feedback_method"
        ),
    )
    op.create_index("ix_interview_sessions_job_id", "interview_sessions", ["job_id"])
    op.create_index("ix_interview_sessions_cv_profile_id", "interview_sessions", ["cv_profile_id"])
    op.create_index("ix_interview_sessions_expires_at", "interview_sessions", ["expires_at"])
    op.create_index("ix_interview_sessions_seeker_created", "interview_sessions", ["seeker_id", "created_at"])
    # A seeker has at most one session that is planning, created or live
    op.create_index(
        "uq_interview_sessions_active",
        "interview_sessions",
        ["seeker_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
        sqlite_where=sa.text(ACTIVE),
    )

    op.create_table(
        "interview_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("item_index", sa.SmallInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("method", sa.String(80), server_default="rules", nullable=False),
        sa.Column("analysis", _json(), nullable=True),
        sa.Column("masked_kinds", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "seq", name="uq_interview_turns_session_seq"),
        sa.CheckConstraint("seq >= 1", name="ck_interview_turns_seq"),
        sa.CheckConstraint("role IN ('agent', 'candidate')", name="ck_interview_turns_role"),
        sa.CheckConstraint("item_index IS NULL OR item_index >= 0", name="ck_interview_turns_item_index"),
        sa.CheckConstraint("length(text) <= 4000", name="ck_interview_turns_text_len"),
    )

    # No foreign key to a session: deleting a session never gives a reservation back
    op.create_table(
        "interview_quota",
        sa.Column("seeker_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kst_day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(14), nullable=False),
        sa.Column("used", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("quota_limit", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("seeker_id", "kst_day", "kind"),
        sa.CheckConstraint("kind IN ('session', 'plan_model', 'feedback_model')", name="ck_interview_quota_kind"),
        sa.CheckConstraint("quota_limit >= 0", name="ck_interview_quota_limit"),
        sa.CheckConstraint("used >= 0 AND used <= quota_limit", name="ck_interview_quota_used"),
    )
    # For the global deletion of past days (WHERE kst_day < today); the primary key starts with the seeker
    op.create_index("ix_interview_quota_kst_day", "interview_quota", ["kst_day"])


def downgrade() -> None:
    # Reverse dependency order: the turns reference the sessions
    op.drop_index("ix_interview_quota_kst_day", table_name="interview_quota")
    op.drop_table("interview_quota")
    op.drop_table("interview_turns")
    op.drop_index("uq_interview_sessions_active", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_seeker_created", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_expires_at", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_cv_profile_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_job_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")
