"""Backfill normalized CV tables and remove the legacy profile JSON column.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

JsonType = sa.JSON().with_variant(JSONB(), "postgresql")


def _profile_rows(bind):
    return bind.execute(
        sa.text("SELECT id, profile FROM cv_profiles ORDER BY id")
    ).mappings().all()


def upgrade() -> None:
    bind = op.get_bind()

    # 0005 introduced the relational tables while the legacy JSONB column still existed.
    # Copy any existing CV versions into the new tables before removing that column.
    for row in _profile_rows(bind):
        profile_id = row["id"]
        data = row["profile"] or {}

        bind.execute(
            sa.text("UPDATE cv_profiles SET summary = :summary WHERE id = :profile_id"),
            {"summary": data.get("summary", ""), "profile_id": profile_id},
        )

        # If 0005 was already running with temporary dual-write code, rebuild the
        # normalized rows from the legacy JSON once to avoid duplicates.
        for table in ("cv_skills", "cv_experiences", "cv_projects", "cv_educations", "cv_certificates"):
            bind.execute(
                sa.text(f"DELETE FROM {table} WHERE cv_profile_id = :profile_id"),
                {"profile_id": profile_id},
            )

        for skill in data.get("skills", []):
            bind.execute(
                sa.text(
                    "INSERT INTO cv_skills (cv_profile_id, skill_name) "
                    "VALUES (:profile_id, :skill_name)"
                ),
                {"profile_id": profile_id, "skill_name": skill},
            )

        for item in data.get("experiences", []):
            bind.execute(
                sa.text(
                    "INSERT INTO cv_experiences "
                    '(cv_profile_id, org, role, start, "end", description, source) '
                    "VALUES (:profile_id, :org, :role, :start, :end, :description, :source)"
                ),
                {
                    "profile_id": profile_id,
                    "org": item.get("org", ""),
                    "role": item.get("role", ""),
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "description": item.get("description", ""),
                    "source": item.get("source", ""),
                },
            )

        for item in data.get("projects", []):
            result = bind.execute(
                sa.text(
                    "INSERT INTO cv_projects "
                    "(cv_profile_id, name, role, description, source) "
                    "VALUES (:profile_id, :name, :role, :description, :source) "
                    "RETURNING id"
                ),
                {
                    "profile_id": profile_id,
                    "name": item.get("name", ""),
                    "role": item.get("role", ""),
                    "description": item.get("description", ""),
                    "source": item.get("source", ""),
                },
            )
            project_id = result.scalar_one()
            for tech in item.get("tech", []):
                bind.execute(
                    sa.text(
                        "INSERT INTO cv_project_techs (cv_project_id, tech_name) "
                        "VALUES (:project_id, :tech_name)"
                    ),
                    {"project_id": project_id, "tech_name": tech},
                )

        for item in data.get("education", []):
            bind.execute(
                sa.text(
                    "INSERT INTO cv_educations "
                    "(cv_profile_id, school, major, degree, source) "
                    "VALUES (:profile_id, :school, :major, :degree, :source)"
                ),
                {
                    "profile_id": profile_id,
                    "school": item.get("school", ""),
                    "major": item.get("major", ""),
                    "degree": item.get("degree", ""),
                    "source": item.get("source", ""),
                },
            )

        for item in data.get("certificates", []):
            bind.execute(
                sa.text(
                    "INSERT INTO cv_certificates "
                    "(cv_profile_id, name, date, source) "
                    "VALUES (:profile_id, :name, :date, :source)"
                ),
                {
                    "profile_id": profile_id,
                    "name": item.get("name", ""),
                    "date": item.get("date"),
                    "source": item.get("source", ""),
                },
            )

    op.drop_column("cv_profiles", "profile")


def downgrade() -> None:
    bind = op.get_bind()
    op.add_column("cv_profiles", sa.Column("profile", JsonType, nullable=True))

    profiles = sa.table(
        "cv_profiles",
        sa.column("id", sa.Integer()),
        sa.column("summary", sa.Text()),
        sa.column("profile", JsonType),
    )

    profile_rows = bind.execute(
        sa.text("SELECT id, summary FROM cv_profiles ORDER BY id")
    ).mappings().all()

    for row in profile_rows:
        profile_id = row["id"]
        skills = [
            r[0]
            for r in bind.execute(
                sa.text(
                    "SELECT skill_name FROM cv_skills "
                    "WHERE cv_profile_id = :profile_id ORDER BY id"
                ),
                {"profile_id": profile_id},
            ).all()
        ]
        experiences = [dict(r) for r in bind.execute(
            sa.text(
                'SELECT org, role, start, "end" AS end, description, source '
                "FROM cv_experiences WHERE cv_profile_id = :profile_id ORDER BY id"
            ),
            {"profile_id": profile_id},
        ).mappings().all()]

        projects = []
        for project in bind.execute(
            sa.text(
                "SELECT id, name, role, description, source FROM cv_projects "
                "WHERE cv_profile_id = :profile_id ORDER BY id"
            ),
            {"profile_id": profile_id},
        ).mappings().all():
            tech = [
                r[0]
                for r in bind.execute(
                    sa.text(
                        "SELECT tech_name FROM cv_project_techs "
                        "WHERE cv_project_id = :project_id ORDER BY id"
                    ),
                    {"project_id": project["id"]},
                ).all()
            ]
            projects.append(
                {
                    "name": project["name"],
                    "role": project["role"],
                    "tech": tech,
                    "description": project["description"],
                    "source": project["source"],
                }
            )

        education = [dict(r) for r in bind.execute(
            sa.text(
                "SELECT school, major, degree, source FROM cv_educations "
                "WHERE cv_profile_id = :profile_id ORDER BY id"
            ),
            {"profile_id": profile_id},
        ).mappings().all()]
        certificates = [dict(r) for r in bind.execute(
            sa.text(
                "SELECT name, date, source FROM cv_certificates "
                "WHERE cv_profile_id = :profile_id ORDER BY id"
            ),
            {"profile_id": profile_id},
        ).mappings().all()]

        data = {
            "skills": skills,
            "experiences": experiences,
            "projects": projects,
            "education": education,
            "certificates": certificates,
            "summary": row["summary"] or "",
        }
        bind.execute(
            profiles.update().where(profiles.c.id == profile_id).values(profile=data)
        )

    op.alter_column("cv_profiles", "profile", nullable=False)
