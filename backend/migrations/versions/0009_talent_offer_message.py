"""Add an optional message to talent offers.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("talent_offers", sa.Column("message", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("talent_offers", "message")
