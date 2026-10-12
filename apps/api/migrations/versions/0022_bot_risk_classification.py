"""AI risk classification per bot (FR-P2).

Revision ID: 0022_bot_risk_classification
Revises: 0021_use_case_intakes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_bot_risk_classification"
down_revision: str | Sequence[str] | None = "0021_use_case_intakes"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_risk_classifications",
        sa.Column("bot_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("eu_ai_act_tier", sa.String(32), nullable=False),
        sa.Column("nist_ai_rmf_profile", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("uu_pdp_data_impact", sa.Text(), nullable=False, server_default=""),
        sa.Column("pdp_impact_level", sa.String(32), nullable=False, server_default="none"),
        sa.Column("required_release_gates", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("classified_by", sa.String(80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bot_risk_classifications")
