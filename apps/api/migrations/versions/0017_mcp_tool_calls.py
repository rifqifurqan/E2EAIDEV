"""Safe MCP tool-call records table (FR-X2).

Persists planned/executed question-time MCP tool calls with safe metadata only:
system_id, operation_id, method, path, read_only, needs_confirmation, status, safe_result.
Never stores auth secrets, server URLs, raw user question text, bearer tokens, API keys, or payloads.

Revision ID: 0017_mcp_tool_calls
Revises: 0016_finops_budget_alerts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_mcp_tool_calls"
down_revision: str | Sequence[str] | None = "0016_finops_budget_alerts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_calls",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("system_id", sa.String(80), nullable=False),
        sa.Column("operation_id", sa.String(200), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False),
        sa.Column("needs_confirmation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("safe_result", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("mcp_tool_calls_message_id", "mcp_tool_calls", ["message_id"])


def downgrade() -> None:
    op.drop_index("mcp_tool_calls_message_id", table_name="mcp_tool_calls")
    op.drop_table("mcp_tool_calls")
