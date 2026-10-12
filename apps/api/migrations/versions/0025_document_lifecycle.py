"""Document review owner / review date / expiry (FR-D8).

Revision ID: 0025_document_lifecycle
Revises: 0024_bot_approvals
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_document_lifecycle"
down_revision: str | Sequence[str] | None = "0024_bot_approvals"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("review_owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("documents", sa.Column("review_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("documents_review_due", "documents", ["review_owner_id", "review_at"])


def downgrade() -> None:
    op.drop_index("documents_review_due", table_name="documents")
    op.drop_column("documents", "expires_at")
    op.drop_column("documents", "review_at")
    op.drop_column("documents", "review_owner_id")
