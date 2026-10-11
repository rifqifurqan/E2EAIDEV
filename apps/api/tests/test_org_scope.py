"""FR-F2: org hierarchy and project-scoped roles.

TDD RED: project containers and scoped role matching must exist before FR-F2 is complete.
"""

import uuid
from pathlib import Path

from e2eai.db import Project, UserRole
from e2eai.org import role_applies_to_project, visible_role_names


class RoleRow:
    def __init__(self, name: str, project_id=None):
        self.name = name
        self.project_id = project_id


def test_project_model_and_migration_capture_role_scope():
    assert Project.__tablename__ == "projects"
    assert "organizations.id" in str(Project.__table__.c.org_id.foreign_keys)
    assert "teams.id" in str(Project.__table__.c.owner_team_id.foreign_keys)
    assert "divisions.id" in str(Project.__table__.c.owner_division_id.foreign_keys)
    assert hasattr(UserRole, "project_id")

    migration = Path("migrations/versions/0020_project_role_scope.py").read_text(encoding="utf-8")
    assert '"projects"' in migration
    assert '"project_id"' in migration
    assert 'op.drop_column("user_roles", "project_id")' in migration
    assert 'op.drop_table("projects")' in migration


def test_role_scope_keeps_org_wide_roles_and_filters_project_roles():
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    grants = [
        RoleRow("admin", None),
        RoleRow("evaluator", project_a),
        RoleRow("ai_engineer", project_b),
    ]

    assert role_applies_to_project(None, project_a) is True
    assert role_applies_to_project(project_a, project_a) is True
    assert role_applies_to_project(project_b, project_a) is False
    assert visible_role_names(grants, project_id=project_a) == {"admin", "evaluator"}
    assert visible_role_names(grants, project_id=None) == {"admin"}
