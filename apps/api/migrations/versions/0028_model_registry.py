"""Model registry with lineage, eval scores, approval status (FR-M7).

Revision ID: 0028_model_registry
Revises: 0027_conversation_legal_hold
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_model_registry"
down_revision: str | Sequence[str] | None = "0027_conversation_legal_hold"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_registry_entries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("parent_version", sa.String(64), nullable=True),
        sa.Column("lineage", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("eval_scores", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("approval_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.String(80), nullable=True),
        sa.Column("registered_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", "version", name="model_registry_name_version"),
        sa.CheckConstraint("approval_status in ('pending', 'approved', 'rejected')", name="model_registry_approval_status"),
    )


def downgrade() -> None:
    op.drop_table("model_registry_entries")
