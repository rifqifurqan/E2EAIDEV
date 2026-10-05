"""Eval Lab datasets and runs (FR-T1, FR-T2, FR-D12, FR-T7, FR-T12).

Revision ID: 0007_eval_lab
Revises: 0006_sharing_views_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_eval_lab"
down_revision: str | Sequence[str] | None = "0006_sharing_views_notifications"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("eval_datasets_name_version", "eval_datasets", ["name", "version"], unique=True)

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("eval_datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("adapter", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("item_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("eval_runs_dataset_created", "eval_runs", ["dataset_id", "created_at"])


def downgrade() -> None:
    op.drop_index("eval_runs_dataset_created", table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index("eval_datasets_name_version", table_name="eval_datasets")
    op.drop_table("eval_datasets")
