"""Normalize CV profile into relational tables.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the existing profile JSON column for now.
    # Add summary separately so the relational structure can coexist safely.
    op.add_column(
        "cv_profiles",
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "cv_skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cv_profile_id",
            sa.Integer(),
            sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("skill_name", sa.String(length=100), nullable=False),
    )
    op.create_index(
        "ix_cv_skills_cv_profile_id",
        "cv_skills",
        ["cv_profile_id"],
    )

    op.create_table(
        "cv_experiences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cv_profile_id",
            sa.Integer(),
            sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("start", sa.String(length=7), nullable=True),
        sa.Column("end", sa.String(length=7), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=500), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_cv_experiences_cv_profile_id",
        "cv_experiences",
        ["cv_profile_id"],
    )

    op.create_table(
        "cv_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cv_profile_id",
            sa.Integer(),
            sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=500), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_cv_projects_cv_profile_id",
        "cv_projects",
        ["cv_profile_id"],
    )

    op.create_table(
        "cv_project_techs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cv_project_id",
            sa.Integer(),
            sa.ForeignKey("cv_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tech_name", sa.String(length=100), nullable=False),
    )
    op.create_index(
        "ix_cv_project_techs_cv_project_id",
        "cv_project_techs",
        ["cv_project_id"],
    )

    op.create_table(
        "cv_educations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cv_profile_id",
            sa.Integer(),
            sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("school", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("major", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("degree", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=500), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_cv_educations_cv_profile_id",
        "cv_educations",
        ["cv_profile_id"],
    )

    op.create_table(
        "cv_certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cv_profile_id",
            sa.Integer(),
            sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("date", sa.String(length=7), nullable=True),
        sa.Column("source", sa.String(length=500), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_cv_certificates_cv_profile_id",
        "cv_certificates",
        ["cv_profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cv_certificates_cv_profile_id",
        table_name="cv_certificates",
    )
    op.drop_table("cv_certificates")

    op.drop_index(
        "ix_cv_educations_cv_profile_id",
        table_name="cv_educations",
    )
    op.drop_table("cv_educations")

    op.drop_index(
        "ix_cv_project_techs_cv_project_id",
        table_name="cv_project_techs",
    )
    op.drop_table("cv_project_techs")

    op.drop_index(
        "ix_cv_projects_cv_profile_id",
        table_name="cv_projects",
    )
    op.drop_table("cv_projects")

    op.drop_index(
        "ix_cv_experiences_cv_profile_id",
        table_name="cv_experiences",
    )
    op.drop_table("cv_experiences")

    op.drop_index(
        "ix_cv_skills_cv_profile_id",
        table_name="cv_skills",
    )
    op.drop_table("cv_skills")

    op.drop_column("cv_profiles", "summary")