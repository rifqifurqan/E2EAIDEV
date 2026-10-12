"""Long-term user memory (FR-B2).

Revision ID: 0032_user_memory
Revises: 0031_connector_documents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_user_memory"
down_revision: str | Sequence[str] | None = "0031_connector_documents"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    uuid_t = sa.dialects.postgresql.UUID(as_uuid=True)
    op.create_table(
        "user_memory_settings",
        sa.Column("user_id", uuid_t, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_memories",
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("user_id", uuid_t, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("user_memories_user_idx", "user_memories", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("user_memories_user_idx", table_name="user_memories")
    op.drop_table("user_memories")
    op.drop_table("user_memory_settings")
