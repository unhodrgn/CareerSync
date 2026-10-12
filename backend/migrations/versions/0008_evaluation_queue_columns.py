"""Add queue columns to evaluations.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "evaluations",
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.create_check_constraint("ck_evaluations_attempts", "evaluations", "attempts >= 0")

    op.execute("UPDATE evaluations SET queued_at = created_at, attempts = 1")


def downgrade() -> None:
    op.drop_constraint("ck_evaluations_attempts", "evaluations", type_="check")
    op.drop_column("evaluations", "attempts")
    op.drop_column("evaluations", "queued_at")
