"""Versioned bot bundles and bot access/scope tables (FR-RL1, FR-RL5, FR-RL7).

Revision ID: 0008_bot_release
Revises: 0007_eval_lab
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_bot_release"
down_revision: str | Sequence[str] | None = "0007_eval_lab"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("production_bundle_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bot_bundles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("released_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("bot_bundles_bot_version", "bot_bundles", ["bot_id", "version"], unique=True)

    op.create_table(
        "bot_grants",
        sa.Column("bot_id", sa.Uuid(), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("principal", sa.String(80), nullable=False),
        sa.Column("level", sa.String(32), nullable=False, server_default="user"),
        sa.PrimaryKeyConstraint("bot_id", "principal"),
    )

    op.create_table(
        "bot_scopes",
        sa.Column("bot_id", sa.Uuid(), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("bot_id", "target_type", "target_id"),
    )


def downgrade() -> None:
    op.drop_table("bot_scopes")
    op.drop_table("bot_grants")
    op.drop_index("bot_bundles_bot_version", table_name="bot_bundles")
    op.drop_table("bot_bundles")
    op.drop_table("bots")
