"""Add job_postings.headcount: 모집 인원 (number of hires) on the job form (docs/DECISIONS.md D47).

Nullable and optional; 1–999 when set (also checked by the API schema). Shown on the job, never a scoring input.
batch_alter_table adds the check constraint on SQLite too (it rebuilds the table there).

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_postings") as batch:
        batch.add_column(sa.Column("headcount", sa.SmallInteger(), nullable=True))
        batch.create_check_constraint("ck_job_postings_headcount", "headcount BETWEEN 1 AND 999")


def downgrade() -> None:
    with op.batch_alter_table("job_postings") as batch:
        batch.drop_constraint("ck_job_postings_headcount", type_="check")
        batch.drop_column("headcount")
