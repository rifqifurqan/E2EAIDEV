"""Bot approval workflow (FR-P4).

Revision ID: 0024_bot_approvals
Revises: 0023_ai_inventory
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_bot_approvals"
down_revision: str | Sequence[str] | None = "0023_ai_inventory"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_approvals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bot_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approval_type", sa.String(32), nullable=False, server_default="high_risk_release"),
        sa.Column("risk_tier", sa.String(32), nullable=False, server_default="minimal"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_by", sa.String(80), nullable=False),
        sa.Column("decided_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("approval_type in ('high_risk_release')", name="bot_approvals_type"),
        sa.CheckConstraint("status in ('pending', 'approved', 'rejected')", name="bot_approvals_status"),
    )
    op.create_index("bot_approvals_bot_status", "bot_approvals", ["bot_id", "status"])


def downgrade() -> None:
    op.drop_index("bot_approvals_bot_status", table_name="bot_approvals")
    op.drop_table("bot_approvals")
