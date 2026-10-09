"""Access requests for document sharing (FR-S5).

Revision ID: 0009_access_requests
Revises: 0008_bot_release
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_access_requests"
down_revision: str | Sequence[str] | None = "0008_bot_release"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status in ('pending', 'approved', 'denied')", name="access_requests_status"),
    )
    op.create_index("access_requests_document_requester", "access_requests", ["document_id", "requester_id"])


def downgrade() -> None:
    op.drop_index("access_requests_document_requester", table_name="access_requests")
    op.drop_table("access_requests")
