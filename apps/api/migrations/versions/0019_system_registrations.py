"""Admin-registered external systems and grants (FR-X4).

Creates system_registrations and system_grants tables for the admin flow
to register systems, upload OpenAPI specs, configure auth, and grant access.
Stores safe metadata only — never raw credentials, bearer tokens, API keys,
passwords, or server URLs.

Revision ID: 0019_system_registrations
Revises: 0018_delegated_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_system_registrations"
down_revision: str | Sequence[str] | None = "0018_delegated_identity"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_registrations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="registered"),
        sa.Column("spec_hash", sa.String(64), nullable=True),
        sa.Column("discovered_operations", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("allowed_operations", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("auth_config", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "system_grants",
        sa.Column("system_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("system_registrations.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("principal", sa.String(80), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("system_grants")
    op.drop_table("system_registrations")
