"""Data flywheel triage queue (FR-I1).

Revision ID: 0030_flywheel_items
Revises: 0029_ai_incidents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_flywheel_items"
down_revision: str | Sequence[str] | None = "0029_ai_incidents"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    uuid_t = sa.dialects.postgresql.UUID(as_uuid=True)
    op.create_table(
        "flywheel_items",
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("message_id", uuid_t, sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("trace_id", sa.String(120), nullable=True),
        sa.Column("question_masked", sa.Text(), nullable=False),
        sa.Column("correction_masked", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("target", sa.String(16), nullable=True),
        sa.Column("dataset_id", uuid_t, sa.ForeignKey("eval_datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("eval_run_id", uuid_t, sa.ForeignKey("eval_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("release_ref", sa.String(200), nullable=True),
        sa.Column("triaged_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source in ('thumbs_down', 'low_online_score', 'reviewer_flag')", name="flywheel_items_source"
        ),
        sa.CheckConstraint(
            "status in ('queued', 'accepted', 'dismissed', 'exported', 'reevaluated', 'released')",
            name="flywheel_items_status",
        ),
    )
    op.create_index("flywheel_items_status_idx", "flywheel_items", ["status"])


def downgrade() -> None:
    op.drop_index("flywheel_items_status_idx", table_name="flywheel_items")
    op.drop_table("flywheel_items")
