"""Rate limits and quotas per user, team, and division (FR-F13).

Revision ID: 0011_quotas
Revises: 0010_api_keys
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_quotas"
down_revision: str | Sequence[str] | None = "0010_api_keys"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quota_policies",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(80), nullable=False),
        sa.Column("requests_per_minute", sa.Integer, nullable=False, server_default="60"),
        sa.Column("tokens_per_day", sa.Integer, nullable=False, server_default="500000"),
        sa.Column("storage_bytes", sa.BigInteger, nullable=False, server_default="21474836480"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("quota_policies_scope_scopeid", "quota_policies", ["scope", "scope_id"], unique=True)


def downgrade() -> None:
    op.drop_index("quota_policies_scope_scopeid", table_name="quota_policies")
    op.drop_table("quota_policies")
