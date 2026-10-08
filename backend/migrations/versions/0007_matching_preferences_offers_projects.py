"""Add seeker preferences, talent offers, and company projects.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seeker_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "seeker_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("profile_public_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("seeker_id", name="uq_seeker_preferences_seeker"),
    )
    op.create_index("ix_seeker_preferences_seeker_id", "seeker_preferences", ["seeker_id"])

    op.create_table(
        "seeker_preferred_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "preference_id",
            sa.Integer(),
            sa.ForeignKey("seeker_preferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("location", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("preference_id", "location", name="uq_seeker_preferred_locations_value"),
    )
    op.create_index(
        "ix_seeker_preferred_locations_preference_id",
        "seeker_preferred_locations",
        ["preference_id"],
    )

    op.create_table(
        "seeker_preferred_employment_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "preference_id",
            sa.Integer(),
            sa.ForeignKey("seeker_preferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("employment_type", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "employment_type IN ('full_time', 'contract', 'intern')",
            name="ck_seeker_preferred_employment_types_value",
        ),
        sa.UniqueConstraint(
            "preference_id",
            "employment_type",
            name="uq_seeker_preferred_employment_types_value",
        ),
    )
    op.create_index(
        "ix_seeker_preferred_employment_types_preference_id",
        "seeker_preferred_employment_types",
        ["preference_id"],
    )

    op.create_table(
        "seeker_job_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "preference_id",
            sa.Integer(),
            sa.ForeignKey("seeker_preferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("preference_id", "keyword", name="uq_seeker_job_keywords_value"),
    )
    op.create_index("ix_seeker_job_keywords_preference_id", "seeker_job_keywords", ["preference_id"])

    op.create_table(
        "talent_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seeker_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("job_postings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'cancelled')",
            name="ck_talent_offers_status",
        ),
    )
    op.create_index("ix_talent_offers_company_id", "talent_offers", ["company_id"])
    op.create_index("ix_talent_offers_seeker_id", "talent_offers", ["seeker_id"])
    op.create_index("ix_talent_offers_job_id", "talent_offers", ["job_id"])

    op.create_table(
        "company_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_projects_company_id", "company_projects", ["company_id"])

    op.create_table(
        "company_project_techs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_project_id",
            sa.Integer(),
            sa.ForeignKey("company_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tech_name", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("company_project_id", "tech_name", name="uq_company_project_techs_value"),
    )
    op.create_index(
        "ix_company_project_techs_company_project_id",
        "company_project_techs",
        ["company_project_id"],
    )


def downgrade() -> None:
    op.drop_table("company_project_techs")
    op.drop_table("company_projects")
    op.drop_table("talent_offers")
    op.drop_table("seeker_job_keywords")
    op.drop_table("seeker_preferred_employment_types")
    op.drop_table("seeker_preferred_locations")
    op.drop_table("seeker_preferences")
