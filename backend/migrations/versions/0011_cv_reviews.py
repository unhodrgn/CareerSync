"""Add cv_reviews: cached LLM CV self-checks per CV document (docs/DECISIONS.md D25).

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cv_document_id", sa.Integer(), sa.ForeignKey("cv_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seeker_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("method", sa.String(80), nullable=False),
        sa.Column("content", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cv_document_id", "prompt_version", "method", name="uq_cv_reviews_key"),
    )
    op.create_index("ix_cv_reviews_cv_document_id", "cv_reviews", ["cv_document_id"])
    op.create_index("ix_cv_reviews_seeker_id", "cv_reviews", ["seeker_id"])


def downgrade() -> None:
    op.drop_index("ix_cv_reviews_seeker_id", table_name="cv_reviews")
    op.drop_index("ix_cv_reviews_cv_document_id", table_name="cv_reviews")
    op.drop_table("cv_reviews")
