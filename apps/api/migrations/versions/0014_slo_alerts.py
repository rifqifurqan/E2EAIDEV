"""Safe SLO alert persistence table (FR-O5).

Stores only alert name, actual metric value, threshold, window metadata, and created_by.
Never stores message content, prompts, answers, document text, tokens, secrets, or credentials.

Revision ID: 0014_slo_alerts
Revises: 0013_bot_environments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_slo_alerts"
down_revision: str | Sequence[str] | None = "0013_bot_environments"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "slo_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_name", sa.String(80), nullable=False),
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
    op.drop_table("slo_alerts")
