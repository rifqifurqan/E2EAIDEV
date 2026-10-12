"""Dataset/index lineage (FR-D10).

Revision ID: 0026_index_lineage
Revises: 0025_document_lifecycle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_index_lineage"
down_revision: str | Sequence[str] | None = "0025_document_lifecycle"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "index_lineage",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parser", sa.String(80), nullable=False),
        sa.Column("chunker", sa.String(40), nullable=False),
        sa.Column("embedding_model", sa.String(160), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "embedding_model", name="index_lineage_version_model"),
    )
    op.create_index("index_lineage_document", "index_lineage", ["document_id"])


def downgrade() -> None:
    op.drop_index("index_lineage_document", table_name="index_lineage")
    op.drop_table("index_lineage")
