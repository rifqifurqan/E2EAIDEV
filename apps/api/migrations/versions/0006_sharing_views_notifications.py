"""Folder sharing read-index and in-app notifications (FR-S3, FR-C10/FR-F11).

Revision ID: 0006_sharing_views_notifications
Revises: 0005_conversations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_sharing_views_notifications"
down_revision: str | Sequence[str] | None = "0005_conversations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "folder_principals",
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("principal", sa.String(80), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("folder_id", "principal"),
    )
    op.create_index("folder_principals_by_principal", "folder_principals", ["principal", "folder_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("notifications_user_created", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("folder_principals_by_principal", table_name="folder_principals")
    op.drop_table("folder_principals")
