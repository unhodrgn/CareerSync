"""Minimal users, companies and job_postings (extended by the auth and job features)

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('seeker', 'company')", name="ck_users_role"),
        sa.CheckConstraint("role <> 'company' OR company_id IS NOT NULL", name="ck_users_company_has_company"),
    )
    op.create_table(
        "job_postings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(10), server_default="draft", nullable=False),
        sa.Column("criteria_updated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'published', 'closed')", name="ck_job_postings_status"),
    )
    op.create_index("ix_job_postings_company_id", "job_postings", ["company_id"])


def downgrade() -> None:
    op.drop_table("job_postings")
    op.drop_table("users")
    op.drop_table("companies")
