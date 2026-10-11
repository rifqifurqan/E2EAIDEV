"""Organization, team, role, and project-scope helpers (FR-F2/FR-F3)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Protocol


class RoleGrant(Protocol):
    name: str
    project_id: uuid.UUID | None


def role_applies_to_project(grant_project_id: uuid.UUID | None, requested_project_id: uuid.UUID | None) -> bool:
    """Org-wide grants apply everywhere; project grants apply only to their project."""
    if grant_project_id is None:
        return True
    return requested_project_id is not None and grant_project_id == requested_project_id


def visible_role_names(grants: Iterable[RoleGrant], *, project_id: uuid.UUID | None) -> set[str]:
    """Return role names effective for the requested project scope.

    Passing ``project_id=None`` asks for only org-wide roles. It never widens a project-scoped grant
    into org-wide access.
    """
    return {grant.name for grant in grants if role_applies_to_project(grant.project_id, project_id)}
