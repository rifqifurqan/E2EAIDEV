"""AI inventory with model/system cards (FR-P3).

Revision ID: 0023_ai_inventory
Revises: 0022_bot_risk_classification
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_ai_inventory"
down_revision: str | Sequence[str] | None = "0022_bot_risk_classification"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_inventory_entries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("bot_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=True, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("risk_tier", sa.String(32), nullable=False, server_default="minimal"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("approval_status", sa.String(16), nullable=False, server_default="not_required"),
        sa.Column("model_card", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("system_card", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.CheckConstraint("kind in ('bot', 'model')", name="ai_inventory_entries_kind"),
        sa.CheckConstraint("status in ('draft', 'active', 'retired')", name="ai_inventory_entries_status"),
        sa.CheckConstraint(
            "approval_status in ('not_required', 'pending', 'approved', 'rejected')",
            name="ai_inventory_entries_approval_status",
        ),
    )
    op.create_index("ai_inventory_entries_kind_name", "ai_inventory_entries", ["kind", "name"])


def downgrade() -> None:
    op.drop_index("ai_inventory_entries_kind_name", table_name="ai_inventory_entries")
    op.drop_table("ai_inventory_entries")
