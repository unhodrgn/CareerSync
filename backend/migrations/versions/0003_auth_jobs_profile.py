"""Login, consent, company profile and job posting fields

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.add_column("users", sa.Column("password_hash", sa.String(255), server_default="", nullable=False))
    op.alter_column("users", "password_hash", server_default=None)
    op.add_column("users", sa.Column("display_name", sa.String(50), server_default="", nullable=False))
    op.add_column("users", sa.Column("consent_privacy_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("consent_ai_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("consent_version", sa.String(20)))
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    # companies
    op.add_column("companies", sa.Column("intro", sa.Text, server_default="", nullable=False))
    op.add_column("companies", sa.Column("talent_profile", sa.Text, server_default="", nullable=False))
    op.add_column(
        "companies", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    op.create_check_constraint("ck_companies_intro_len", "companies", "length(intro) <= 1000")
    op.create_check_constraint("ck_companies_talent_profile_len", "companies", "length(talent_profile) <= 1000")

    # job_postings
    op.add_column("job_postings", sa.Column("description", sa.Text, server_default="", nullable=False))
    op.add_column(
        "job_postings", sa.Column("employment_type", sa.String(20), server_default="full_time", nullable=False)
    )
    op.add_column("job_postings", sa.Column("min_experience_years", sa.SmallInteger))
    op.add_column("job_postings", sa.Column("location", sa.String(100), server_default="", nullable=False))
    op.add_column("job_postings", sa.Column("salary_note", sa.String(100), server_default="", nullable=False))
    op.add_column("job_postings", sa.Column("deadline", sa.Date))
    op.add_column("job_postings", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.add_column("job_postings", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "job_postings",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint(
        "ck_job_postings_employment_type", "job_postings", "employment_type IN ('full_time', 'contract', 'intern')"
    )
    op.create_check_constraint("ck_job_postings_min_experience", "job_postings", "min_experience_years BETWEEN 0 AND 30")
    op.create_check_constraint("ck_job_postings_description_len", "job_postings", "length(description) <= 10000")


def downgrade() -> None:
    for name in ("ck_job_postings_description_len", "ck_job_postings_min_experience", "ck_job_postings_employment_type"):
        op.drop_constraint(name, "job_postings", type_="check")
    for col in (
        "updated_at", "closed_at", "published_at", "deadline", "salary_note",
        "location", "min_experience_years", "employment_type", "description",
    ):
        op.drop_column("job_postings", col)

    op.drop_constraint("ck_companies_talent_profile_len", "companies", type_="check")
    op.drop_constraint("ck_companies_intro_len", "companies", type_="check")
    for col in ("updated_at", "talent_profile", "intro"):
        op.drop_column("companies", col)

    op.drop_index("uq_users_email_lower", "users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    for col in ("consent_version", "consent_ai_at", "consent_privacy_at", "display_name", "password_hash"):
        op.drop_column("users", col)
