"""created/updated by and at on every record (NFR-20).

Revision ID: 0035_audit_columns
Revises: 0034_dsr_last_reminder
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_audit_columns"
down_revision: str | Sequence[str] | None = "0034_dsr_last_reminder"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# (table, columns that were missing). Existing rows get created_at/updated_at = now(); *_by stay NULL (system).
GAPS: list[tuple[str, tuple[str, ...]]] = [
    ("access_requests", ("updated_at", "created_by", "updated_by")),
    ("ai_incidents", ("created_by", "updated_by")),
    ("ai_inventory_entries", ("created_by",)),
    ("api_keys", ("updated_at", "created_by", "updated_by")),
    ("bot_approvals", ("updated_at", "created_by", "updated_by")),
    ("bot_bundles", ("updated_at", "created_by", "updated_by")),
    ("bot_environments", ("created_at", "created_by", "updated_by")),
    ("bot_grants", ("created_at", "updated_at", "created_by", "updated_by")),
    ("bot_risk_classifications", ("created_at", "created_by", "updated_by")),
    ("bot_scopes", ("created_at", "updated_at", "created_by", "updated_by")),
    ("bots", ("created_by", "updated_by")),
    ("chunk_embeddings", ("updated_at", "created_by", "updated_by")),
    ("chunks", ("created_at", "updated_at", "created_by", "updated_by")),
    ("connector_documents", ("created_at", "updated_at", "created_by", "updated_by")),
    ("conversations", ("created_by", "updated_by")),
    ("data_subject_requests", ("updated_at", "created_by", "updated_by")),
    ("doc_principals", ("created_at", "updated_at", "created_by", "updated_by")),
    ("eval_datasets", ("updated_at", "updated_by")),
    ("eval_runs", ("updated_at", "updated_by")),
    ("finops_budget_alerts", ("updated_at", "updated_by")),
    ("flywheel_items", ("created_by", "updated_by")),
    ("folder_principals", ("created_at", "updated_at", "created_by", "updated_by")),
    ("index_lineage", ("created_at", "updated_at", "created_by", "updated_by")),
    ("local_credentials", ("created_at", "created_by", "updated_by")),
    ("mcp_tool_calls", ("updated_at", "created_by", "updated_by")),
    ("message_citations", ("created_at", "updated_at", "created_by", "updated_by")),
    ("message_feedback", ("updated_at", "created_by", "updated_by")),
    ("messages", ("updated_at", "created_by", "updated_by")),
    ("model_registry_entries", ("created_by", "updated_by")),
    ("notifications", ("updated_at", "created_by", "updated_by")),
    ("prompt_labels", ("created_at", "created_by")),
    ("prompt_versions", ("updated_at", "updated_by")),
    ("prompts", ("created_by", "updated_by")),
    ("roles", ("created_at", "updated_at", "created_by", "updated_by")),
    ("settings", ("created_at", "updated_at", "created_by", "updated_by")),
    ("slo_alerts", ("updated_at", "updated_by")),
    ("system_grants", ("created_at", "updated_at", "created_by", "updated_by")),
    ("team_members", ("created_at", "updated_at", "created_by", "updated_by")),
    ("user_memories", ("updated_at", "created_by", "updated_by")),
    ("user_memory_settings", ("created_at", "created_by", "updated_by")),
    ("user_roles", ("created_at", "updated_at", "created_by", "updated_by")),
]


def _column(name: str) -> sa.Column:
    if name in ("created_at", "updated_at"):
        return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    return sa.Column(name, sa.String(80), nullable=True)


def upgrade() -> None:
    for table, cols in GAPS:
        for col in cols:
            op.add_column(table, _column(col))


def downgrade() -> None:
    for table, cols in reversed(GAPS):
        for col in reversed(cols):
            op.drop_column(table, col)
