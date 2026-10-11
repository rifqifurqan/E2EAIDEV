"""Project containers and scoped user roles (FR-F2/FR-F3).

Revision ID: 0020_project_role_scope
Revises: 0019_system_registrations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_project_role_scope"
down_revision: str | Sequence[str] | None = "0019_system_registrations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_team_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("owner_division_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("divisions.id"), nullable=True),
        sa.UniqueConstraint("org_id", "name", name="projects_org_name_unique"),
    )
    op.add_column(
        "user_roles",
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("user_roles_project_id", "user_roles", ["project_id"])


def downgrade() -> None:
    op.drop_index("user_roles_project_id", table_name="user_roles")
    op.drop_column("user_roles", "project_id")
    op.drop_table("projects")
