"""CVs, applications, evaluations and per-criterion scores

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATUSES = "'submitted', 'reviewing', 'interview', 'on_hold', 'passed', 'rejected'"


def _now() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "cv_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("seeker_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("pages", sa.SmallInteger, nullable=False),
        sa.Column("masked_text", sa.Text, nullable=False),
        sa.Column("masked_kinds", JSONB, nullable=False),
        _now(),
    )
    op.create_index("ix_cv_documents_seeker_id", "cv_documents", ["seeker_id"])

    op.create_table(
        "cv_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cv_document_id", sa.Integer, sa.ForeignKey("cv_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seeker_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("profile", JSONB, nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("method", sa.String(60), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        _now(),
        sa.UniqueConstraint("cv_document_id", "version", name="uq_cv_profiles_document_version"),
    )
    op.create_index("ix_cv_profiles_cv_document_id", "cv_profiles", ["cv_document_id"])
    op.create_index("ix_cv_profiles_seeker_id", "cv_profiles", ["seeker_id"])

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seeker_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_profile_id", sa.Integer, sa.ForeignKey("cv_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), server_default="submitted", nullable=False),
        sa.Column("status_updated_at", sa.DateTime(timezone=True)),
        _now(),
        sa.UniqueConstraint("job_id", "seeker_id", name="uq_applications_job_seeker"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_applications_status"),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_seeker_id", "applications", ["seeker_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_profile_id", sa.Integer, sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), server_default="pending", nullable=False),
        sa.Column("error", sa.Text, server_default="", nullable=False),
        sa.Column("llm_model", sa.String(60), server_default="", nullable=False),
        sa.Column("embedding_model", sa.String(100), server_default="", nullable=False),
        sa.Column("prompt_version", sa.String(20), server_default="", nullable=False),
        sa.Column("skills_version", sa.String(20), server_default="", nullable=False),
        _now(),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", "cv_profile_id", name="uq_evaluations_job_profile"),
        sa.CheckConstraint("status IN ('pending', 'done', 'failed')", name="ck_evaluations_status"),
    )
    op.create_index("ix_evaluations_job_id", "evaluations", ["job_id"])
    op.create_index("ix_evaluations_cv_profile_id", "evaluations", ["cv_profile_id"])

    op.create_table(
        "criterion_scores",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("evaluation_id", sa.Integer, sa.ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_criteria_id", sa.Integer, sa.ForeignKey("job_criteria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("method", sa.String(60), nullable=False),
        sa.UniqueConstraint("evaluation_id", "job_criteria_id", name="uq_criterion_scores_eval_criterion"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_criterion_scores_score"),
    )
    op.create_index("ix_criterion_scores_evaluation_id", "criterion_scores", ["evaluation_id"])
    op.create_index("ix_criterion_scores_job_criteria_id", "criterion_scores", ["job_criteria_id"])


def downgrade() -> None:
    for table in ("criterion_scores", "evaluations", "applications", "cv_profiles", "cv_documents"):
        op.drop_table(table)
