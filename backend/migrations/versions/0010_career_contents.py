"""Add career_contents: cached skill roadmaps and interview questions.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "career_contents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seeker_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_profile_id", sa.Integer(), sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("method", sa.String(80), nullable=False),
        sa.Column("content", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "seeker_id", "job_id", "cv_profile_id", "kind", "prompt_version", "method", name="uq_career_contents_key"
        ),
        sa.CheckConstraint("kind IN ('roadmap', 'interview')", name="ck_career_contents_kind"),
    )
    op.create_index("ix_career_contents_seeker_id", "career_contents", ["seeker_id"])
    op.create_index("ix_career_contents_job_id", "career_contents", ["job_id"])
    op.create_index("ix_career_contents_cv_profile_id", "career_contents", ["cv_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_career_contents_cv_profile_id", table_name="career_contents")
    op.drop_index("ix_career_contents_job_id", table_name="career_contents")
    op.drop_index("ix_career_contents_seeker_id", table_name="career_contents")
    op.drop_table("career_contents")
