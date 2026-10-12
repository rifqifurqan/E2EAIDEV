"""Knowledge connector document map (FR-X1).

Revision ID: 0031_connector_documents
Revises: 0030_flywheel_items
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_connector_documents"
down_revision: str | Sequence[str] | None = "0030_flywheel_items"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    uuid_t = sa.dialects.postgresql.UUID(as_uuid=True)
    op.create_table(
        "connector_documents",
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("document_id", uuid_t, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="connector_documents_source_external"),
    )


def downgrade() -> None:
    op.drop_table("connector_documents")
