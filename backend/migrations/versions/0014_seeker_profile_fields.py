"""Add the self-declared seeker profile fields (docs/DECISIONS.md D46): seeker_preferences.experience_level and
seeker_profile_skills. Display only: never read by Fit, Pref or any scorer.

experience_level codes (new, junior, mid, senior) are checked by the API schema.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("seeker_preferences", sa.Column("experience_level", sa.String(20), nullable=True))
    op.create_table(
        "seeker_profile_skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "preference_id", sa.Integer(), sa.ForeignKey("seeker_preferences.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("skill", sa.String(100), nullable=False),
        sa.UniqueConstraint("preference_id", "skill", name="uq_seeker_profile_skills_value"),
    )
    op.create_index("ix_seeker_profile_skills_preference_id", "seeker_profile_skills", ["preference_id"])


def downgrade() -> None:
    op.drop_index("ix_seeker_profile_skills_preference_id", table_name="seeker_profile_skills")
    op.drop_table("seeker_profile_skills")
    op.drop_column("seeker_preferences", "experience_level")
