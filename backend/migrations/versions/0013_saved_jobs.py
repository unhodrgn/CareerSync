"""Add saved_jobs: jobs a seeker saved (공고 저장, docs/DECISIONS.md D45).

Seeker-only data: companies never see who saved their jobs, and saving never creates an evaluation.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_jobs",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "job_id", name="pk_saved_jobs"),
    )


def downgrade() -> None:
    op.drop_table("saved_jobs")
