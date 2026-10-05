"""Add chunk_embeddings for Phase 1 retrieval/index tracer bullet.

Revision ID: 0003_chunk_embeddings
Revises: 0002_documents
Create Date: 2026-10-05 13:00:00+07:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_chunk_embeddings"
down_revision: str | Sequence[str] | None = "0002_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_embeddings",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_model", sa.String(length=160), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("vector", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index("chunk_embeddings_model", "chunk_embeddings", ["embedding_model"])


def downgrade() -> None:
    op.drop_index("chunk_embeddings_model", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
