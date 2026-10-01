"""Evaluation criteria per job and the guardrail audit log

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CATEGORIES = "'skill', 'experience', 'project', 'certificate', 'education', 'other'"


def upgrade() -> None:
    op.create_table(
        "job_criteria",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, server_default="", nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("weight", sa.SmallInteger, nullable=False),
        sa.Column("position", sa.SmallInteger, server_default="0", nullable=False),
        sa.Column("guardrail_version", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weight BETWEEN 1 AND 100", name="ck_job_criteria_weight"),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name="ck_job_criteria_category"),
        sa.CheckConstraint("length(description) <= 500", name="ck_job_criteria_description_len"),
    )
    op.create_index("ix_job_criteria_job_id", "job_criteria", ["job_id"])
    op.create_index("uq_job_criteria_job_name", "job_criteria", ["job_id", sa.text("lower(trim(name))")], unique=True)

    op.create_table(
        "criteria_guardrail_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("job_postings.id", ondelete="SET NULL")),
        sa.Column("input_name", sa.Text, nullable=False),
        sa.Column("input_description", sa.Text, nullable=False),
        sa.Column("rule_id", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("law_ref", sa.String(100), nullable=False),
        sa.Column("blocklist_version", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_criteria_guardrail_logs_company_id", "criteria_guardrail_logs", ["company_id"])


def downgrade() -> None:
    op.drop_table("criteria_guardrail_logs")
    op.drop_table("job_criteria")
