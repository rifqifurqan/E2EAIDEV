"""Data-subject request ledger (NFR-10).

Revision ID: 0033_data_subject_requests
Revises: 0032_user_memory
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_data_subject_requests"
down_revision: str | Sequence[str] | None = "0032_user_memory"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    uuid_t = sa.dialects.postgresql.UUID(as_uuid=True)
    op.create_table(
        "data_subject_requests",
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("subject_id", uuid_t, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("opened_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind in ('export', 'erase')", name="dsr_kind"),
        sa.CheckConstraint("status in ('open', 'completed')", name="dsr_status"),
    )
    op.create_index("dsr_created_idx", "data_subject_requests", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("dsr_created_idx", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
