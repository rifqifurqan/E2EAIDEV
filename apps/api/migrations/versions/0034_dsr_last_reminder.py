"""Data-subject request reminder state (NFR-10).

Revision ID: 0034_dsr_last_reminder
Revises: 0033_data_subject_requests
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_dsr_last_reminder"
down_revision: str | Sequence[str] | None = "0033_data_subject_requests"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("data_subject_requests", sa.Column("last_reminder", sa.String(10)))


def downgrade() -> None:
    op.drop_column("data_subject_requests", "last_reminder")
