"""AI incident management (FR-O8).

Revision ID: 0029_ai_incidents
Revises: 0028_model_registry
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_ai_incidents"
down_revision: str | Sequence[str] | None = "0028_model_registry"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_incidents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="reported"),
        sa.Column("bot_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trace_ids", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("assignee_id", sa.String(80), nullable=True),
        sa.Column("fix_notes", sa.Text(), nullable=True),
        sa.Column("release_ref", sa.String(200), nullable=True),
        sa.Column("postmortem", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("reported_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("severity in ('sev1', 'sev2', 'sev3', 'sev4')", name="ai_incidents_severity"),
        sa.CheckConstraint(
            "status in ('reported', 'triaged', 'fixing', 'fixed', 'released', 'closed')", name="ai_incidents_status"
        ),
    )
    op.create_index("ai_incidents_status_idx", "ai_incidents", ["status"])


def downgrade() -> None:
    op.drop_index("ai_incidents_status_idx", table_name="ai_incidents")
    op.drop_table("ai_incidents")
