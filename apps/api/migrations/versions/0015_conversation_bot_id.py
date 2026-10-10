"""Add nullable bot_id to conversations for FinOps bot-level spend aggregation (FR-O6).

Existing rows receive NULL (no cost is backfilled). Conversations can be
optionally tagged with the bot they were answered by; aggregation groups on
this field when present.

Revision ID: 0015_conversation_bot_id
Revises: 0014_slo_alerts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_conversation_bot_id"
down_revision: str | Sequence[str] | None = "0014_slo_alerts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("bot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_bot_id",
        "conversations",
        "bots",
        ["bot_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_conversations_bot_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "bot_id")
