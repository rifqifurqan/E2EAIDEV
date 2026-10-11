"""Add auth_mode and acting_user_id to mcp_tool_calls (FR-X3).

Stores delegated identity metadata per MCP tool call: auth_mode (delegated/token_exchange)
and acting_user_id. Never stores raw tokens, bearer values, passwords, API keys, or secrets.
SERVICE_ACCOUNT auth_mode is rejected at the application layer; it should never appear in rows.

Revision ID: 0018_delegated_identity
Revises: 0017_mcp_tool_calls
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_delegated_identity"
down_revision: str | Sequence[str] | None = "0017_mcp_tool_calls"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mcp_tool_calls", sa.Column("auth_mode", sa.String(32), nullable=True))
    op.add_column("mcp_tool_calls", sa.Column("acting_user_id", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("mcp_tool_calls", "acting_user_id")
    op.drop_column("mcp_tool_calls", "auth_mode")
