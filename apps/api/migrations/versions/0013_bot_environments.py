"""Per-environment bot deployment pointers for dev -> staging -> prod promotion (FR-RL6).

Revision ID: 0013_bot_environments
Revises: 0012_prompt_registry
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_bot_environments"
down_revision: str | Sequence[str] | None = "0012_prompt_registry"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_environments",
        sa.Column("bot_id", sa.Uuid(), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=True),
        sa.Column("allow_production_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("bot_id", "environment"),
    )


def downgrade() -> None:
    op.drop_table("bot_environments")
