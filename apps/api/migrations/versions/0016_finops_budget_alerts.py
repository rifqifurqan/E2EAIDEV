"""Safe FinOps budget alert persistence table (FR-O6).

Stores only the breaching dimension, entity id, actual spend, threshold, window metadata,
and created_by. Never stores message content, prompts, answers, document text, model names,
tokens, secrets, or credentials.

Revision ID: 0016_finops_budget_alerts
Revises: 0015_conversation_bot_id
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_finops_budget_alerts"
down_revision: str | Sequence[str] | None = "0015_conversation_bot_id"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finops_budget_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("actual", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("finops_budget_alerts")
