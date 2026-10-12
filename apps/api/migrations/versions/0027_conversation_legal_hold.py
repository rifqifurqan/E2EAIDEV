"""Conversation legal hold (FR-D13).

Revision ID: 0027_conversation_legal_hold
Revises: 0026_index_lineage
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_conversation_legal_hold"
down_revision: str | Sequence[str] | None = "0026_index_lineage"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index("conversations_legal_hold", "conversations", ["legal_hold"], postgresql_where=sa.text("legal_hold"))


def downgrade() -> None:
    op.drop_index("conversations_legal_hold", table_name="conversations")
    op.drop_column("conversations", "legal_hold")
