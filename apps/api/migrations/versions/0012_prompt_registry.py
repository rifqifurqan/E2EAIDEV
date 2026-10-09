"""Prompt registry with versions, labels, diffs, and playground preview (FR-B1).

Revision ID: 0012_prompt_registry
Revises: 0011_quotas
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_prompt_registry"
down_revision: str | Sequence[str] | None = "0011_quotas"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("prompts_owner_name", "prompts", ["owner_id", "name"], unique=True)

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("prompt_versions_prompt_version", "prompt_versions", ["prompt_id", "version"], unique=True)

    op.create_table(
        "prompt_labels",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("prompt_id", "label", name="prompt_labels_prompt_label"),
    )


def downgrade() -> None:
    op.drop_table("prompt_labels")
    op.drop_index("prompt_versions_prompt_version", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("prompts_owner_name", table_name="prompts")
    op.drop_table("prompts")
