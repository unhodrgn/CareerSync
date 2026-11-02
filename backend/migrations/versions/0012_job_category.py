"""Add job_postings.category: the job's field for the public category filter (docs/DECISIONS.md D45).

Nullable: jobs published before this migration keep no category; publishing a new job requires one.
The allowed codes (dev, data_ai, design, marketing, planning) are checked by the API schema.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("category", sa.String(20), nullable=True))
    op.create_index("ix_job_postings_category", "job_postings", ["category"])


def downgrade() -> None:
    op.drop_index("ix_job_postings_category", table_name="job_postings")
    op.drop_column("job_postings", "category")
