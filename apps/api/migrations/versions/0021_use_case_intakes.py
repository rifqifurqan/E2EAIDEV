"""FR-P1 use-case intake forms.

Revision ID: 0021_use_case_intakes
Revises: 0020_project_role_scope
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_use_case_intakes"
down_revision: str | Sequence[str] | None = "0020_project_role_scope"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "use_case_intakes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("users", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("success_metrics", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_sources", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("systems_to_integrate", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="submitted"),
        sa.CheckConstraint("status in ('draft', 'submitted')", name="use_case_intakes_status"),
    )
    op.create_index("use_case_intakes_owner_created", "use_case_intakes", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("use_case_intakes_owner_created", table_name="use_case_intakes")
    op.drop_table("use_case_intakes")
