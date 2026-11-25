"""Store occupation-independent JD analysis snapshots."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_requirement_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("method", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_requirement_analyses_job_id", "job_requirement_analyses", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_requirement_analyses_job_id", table_name="job_requirement_analyses")
    op.drop_table("job_requirement_analyses")
