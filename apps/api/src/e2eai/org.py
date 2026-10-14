"""Organization, team, role, and project-scope helpers (FR-F2/FR-F3)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Division, Organization, Project, Role, Team, TeamMember, User, UserRole, get_session


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


async def _get(session: AsyncSession, model, obj_id: uuid.UUID, label: str):
    obj = await session.get(model, obj_id)
    if obj is None:
        raise AppError(404, f"{label} not found")
    return obj


async def create_division(session: AsyncSession, *, org_id: uuid.UUID, name: str, actor: str) -> Division:
    await _get(session, Organization, org_id, "Organization")
    division = Division(org_id=org_id, name=name, created_by=actor)
    session.add(division)
    await session.flush()
    await audit.record(session, actor, "org.division.create", f"division:{division.id}", {"org_id": str(org_id)})
    return division


async def create_team(session: AsyncSession, *, division_id: uuid.UUID, name: str, actor: str) -> Team:
    await _get(session, Division, division_id, "Division")
    team = Team(division_id=division_id, name=name, created_by=actor)
    session.add(team)
    await session.flush()
    await audit.record(session, actor, "org.team.create", f"team:{team.id}", {"division_id": str(division_id)})
    return team


async def create_user(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    email: str,
    display_name: str,
    division_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    actor: str,
) -> User:
    await _get(session, Organization, org_id, "Organization")
    if division_id is not None:
        await _get(session, Division, division_id, "Division")
    if manager_id is not None:
        await _get(session, User, manager_id, "Manager")
    existing = await session.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if existing is not None:
        raise AppError(409, "User already exists")
    user = User(
        org_id=org_id,
        email=email,
        display_name=display_name,
        division_id=division_id,
        manager_id=manager_id,
        created_by=actor,
    )
    session.add(user)
    await session.flush()
    await audit.record(session, actor, "org.user.create", f"user:{user.id}", {"org_id": str(org_id)})
    return user


async def add_team_member(session: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID, actor: str) -> TeamMember:
    await _get(session, Team, team_id, "Team")
    await _get(session, User, user_id, "User")
    membership = await session.get(TeamMember, {"team_id": team_id, "user_id": user_id})
    if membership is None:
        membership = TeamMember(team_id=team_id, user_id=user_id)
        session.add(membership)
        await session.flush()
        await audit.record(session, actor, "org.team_member.add", f"team:{team_id}", {"user_id": str(user_id)})
    return membership


async def remove_team_member(session: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID, actor: str) -> None:
    membership = await session.get(TeamMember, {"team_id": team_id, "user_id": user_id})
    if membership is not None:
        await session.delete(membership)
        await session.flush()
        await audit.record(session, actor, "org.team_member.remove", f"team:{team_id}", {"user_id": str(user_id)})


async def _validate_project_owner(
    session: AsyncSession, *, owner_team_id: uuid.UUID | None, owner_division_id: uuid.UUID | None
) -> None:
    if owner_team_id is not None and owner_division_id is not None:
        raise AppError(422, "Project owner must be a team or division, not both")
    if owner_team_id is not None:
        await _get(session, Team, owner_team_id, "Owner team")
    if owner_division_id is not None:
        await _get(session, Division, owner_division_id, "Owner division")


async def create_project(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    name: str,
    actor: str,
    owner_team_id: uuid.UUID | None = None,
    owner_division_id: uuid.UUID | None = None,
) -> Project:
    await _validate_project_owner(session, owner_team_id=owner_team_id, owner_division_id=owner_division_id)
    await _get(session, Organization, org_id, "Organization")
    project = Project(
        org_id=org_id,
        name=name,
        owner_team_id=owner_team_id,
        owner_division_id=owner_division_id,
        created_by=actor,
    )
    session.add(project)
    await session.flush()
    await audit.record(session, actor, "org.project.create", f"project:{project.id}", {"org_id": str(org_id)})
    return project


async def update_project_owner(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    actor: str,
    owner_team_id: uuid.UUID | None = None,
    owner_division_id: uuid.UUID | None = None,
) -> Project:
    await _validate_project_owner(session, owner_team_id=owner_team_id, owner_division_id=owner_division_id)
    project = await _get(session, Project, project_id, "Project")
    project.owner_team_id = owner_team_id
    project.owner_division_id = owner_division_id
    project.updated_by = actor
    await session.flush()
    await audit.record(
        session,
        actor,
        "org.project.owner_update",
        f"project:{project.id}",
        {"owner_team_id": str(owner_team_id) if owner_team_id else None, "owner_division_id": str(owner_division_id) if owner_division_id else None},
    )
    return project


async def grant_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role_name: str,
    actor: str,
    project_id: uuid.UUID | None = None,
) -> UserRole:
    await _get(session, User, user_id, "User")
    if project_id is not None:
        await _get(session, Project, project_id, "Project")
    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise AppError(404, "Role not found")
    grant = await session.scalar(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id, UserRole.project_id == project_id)
    )
    if grant is None:
        grant = UserRole(user_id=user_id, role_id=role.id, project_id=project_id)
        session.add(grant)
        await session.flush()
        await audit.record(
            session,
            actor,
            "org.role.grant",
            f"user:{user_id}",
            {"role": role_name, "project_id": str(project_id) if project_id else None},
        )
    return grant


async def revoke_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role_name: str,
    actor: str,
    project_id: uuid.UUID | None = None,
) -> None:
    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        return
    grant = await session.scalar(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id, UserRole.project_id == project_id)
    )
    if grant is not None:
        await session.delete(grant)
        await session.flush()
        await audit.record(
            session,
            actor,
            "org.role.revoke",
            f"user:{user_id}",
            {"role": role_name, "project_id": str(project_id) if project_id else None},
        )


async def org_snapshot(session: AsyncSession, *, org_id: uuid.UUID, project_id: uuid.UUID | None = None) -> dict:
    divisions = list(await session.scalars(select(Division).where(Division.org_id == org_id).order_by(Division.name)))
    division_ids = [d.id for d in divisions]
    teams = []
    if division_ids:
        teams = list(await session.scalars(select(Team).where(Team.division_id.in_(division_ids)).order_by(Team.name)))
    users = list(await session.scalars(select(User).where(User.org_id == org_id).order_by(User.email)))
    projects = list(await session.scalars(select(Project).where(Project.org_id == org_id).order_by(Project.name)))

    role_rows = []
    if users:
        role_rows = (
            await session.execute(
                select(UserRole.user_id, Role.name, UserRole.project_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id.in_([u.id for u in users]))
            )
        ).all()
    role_grants: dict[str, list[str]] = {}
    for user_id, role_name, grant_project_id in role_rows:
        if role_applies_to_project(grant_project_id, project_id):
            role_grants.setdefault(str(user_id), []).append(role_name)
    for value in role_grants.values():
        value.sort()

    projects_by_id = {str(p.id): _project_dict(p) for p in projects}
    return {
        "org_id": str(org_id),
        "divisions": [_division_dict(d) for d in divisions],
        "teams": [_team_dict(t) for t in teams],
        "users": [_user_dict(u) for u in users],
        "projects": [_project_dict(p) for p in projects],
        "projects_by_id": projects_by_id,
        "role_grants": role_grants,
    }


def _division_dict(d: Division) -> dict:
    return {"id": str(d.id), "org_id": str(d.org_id), "name": d.name}


def _team_dict(t: Team) -> dict:
    return {"id": str(t.id), "division_id": str(t.division_id), "name": t.name}


def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "org_id": str(u.org_id),
        "email": u.email,
        "display_name": u.display_name,
        "status": u.status,
        "division_id": str(u.division_id) if u.division_id else None,
        "manager_id": str(u.manager_id) if u.manager_id else None,
    }


def _project_dict(p: Project) -> dict:
    return {
        "id": str(p.id),
        "org_id": str(p.org_id),
        "name": p.name,
        "owner_team_id": str(p.owner_team_id) if p.owner_team_id else None,
        "owner_division_id": str(p.owner_division_id) if p.owner_division_id else None,
    }


class DivisionIn(BaseModel):
    org_id: uuid.UUID
    name: str
    actor: str = "admin:api"


class TeamIn(BaseModel):
    division_id: uuid.UUID
    name: str
    actor: str = "admin:api"


class UserIn(BaseModel):
    org_id: uuid.UUID
    email: EmailStr
    display_name: str
    division_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    actor: str = "admin:api"


class TeamMembershipIn(BaseModel):
    team_id: uuid.UUID
    user_id: uuid.UUID
    actor: str = "admin:api"


class RoleGrantIn(BaseModel):
    user_id: uuid.UUID
    role_name: str
    project_id: uuid.UUID | None = None
    actor: str = "admin:api"


class ProjectIn(BaseModel):
    org_id: uuid.UUID
    name: str
    owner_team_id: uuid.UUID | None = None
    owner_division_id: uuid.UUID | None = None
    actor: str = "admin:api"


class ProjectOwnerIn(BaseModel):
    owner_team_id: uuid.UUID | None = None
    owner_division_id: uuid.UUID | None = None
    actor: str = "admin:api"


router = APIRouter(prefix="/api/v1/admin/org", tags=["admin"])


async def _org_admin_user(sess: dict = Depends(current_session), session: AsyncSession = Depends(get_session)) -> User:
    """Authenticate and require an org-wide admin role (FR-F2)."""
    require_scope(sess, "admin")
    user = await session.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    role = await session.scalar(select(Role).where(Role.name == "admin"))
    granted = role is not None and await session.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id, UserRole.project_id.is_(None))
    )
    if not granted:
        raise AppError(403, "Not allowed")
    return user


async def _org_admin(user: User = Depends(_org_admin_user)) -> str:
    """Audit actor derived from the session, never from the request body."""
    return f"user:{user.id}"



@router.post("/divisions")
async def create_division_route(body: DivisionIn, session: AsyncSession = Depends(get_session), actor: str = Depends(_org_admin)) -> dict:
    division = await create_division(session, org_id=body.org_id, name=body.name, actor=actor)
    await session.commit()
    return _division_dict(division)


@router.post("/teams")
async def create_team_route(body: TeamIn, session: AsyncSession = Depends(get_session), actor: str = Depends(_org_admin)) -> dict:
    team = await create_team(session, division_id=body.division_id, name=body.name, actor=actor)
    await session.commit()
    return _team_dict(team)


@router.post("/users")
async def create_user_route(body: UserIn, session: AsyncSession = Depends(get_session), actor: str = Depends(_org_admin)) -> dict:
    user = await create_user(
        session,
        org_id=body.org_id,
        email=str(body.email),
        display_name=body.display_name,
        division_id=body.division_id,
        manager_id=body.manager_id,
        actor=actor,
    )
    await session.commit()
    return _user_dict(user)


@router.post("/team-memberships")
async def add_team_member_route(body: TeamMembershipIn, session: AsyncSession = Depends(get_session), actor: str = Depends(_org_admin)) -> dict:
    membership = await add_team_member(session, team_id=body.team_id, user_id=body.user_id, actor=actor)
    await session.commit()
    return {"team_id": str(membership.team_id), "user_id": str(membership.user_id)}


@router.post("/role-grants")
async def grant_role_route(body: RoleGrantIn, session: AsyncSession = Depends(get_session), actor: str = Depends(_org_admin)) -> dict:
    grant = await grant_role(
        session,
        user_id=body.user_id,
        role_name=body.role_name,
        project_id=body.project_id,
        actor=actor,
    )
    await session.commit()
    return {"user_id": str(grant.user_id), "role_name": body.role_name, "project_id": str(grant.project_id) if grant.project_id else None}


@router.post("/projects")
async def create_project_route(body: ProjectIn, session: AsyncSession = Depends(get_session), actor: str = Depends(_org_admin)) -> dict:
    project = await create_project(
        session,
        org_id=body.org_id,
        name=body.name,
        owner_team_id=body.owner_team_id,
        owner_division_id=body.owner_division_id,
        actor=actor,
    )
    await session.commit()
    return _project_dict(project)


@router.patch("/projects/{project_id}/owner")
async def update_project_owner_route(
    project_id: uuid.UUID, body: ProjectOwnerIn, session: AsyncSession = Depends(get_session),
    actor: str = Depends(_org_admin),
) -> dict:
    project = await update_project_owner(
        session,
        project_id=project_id,
        owner_team_id=body.owner_team_id,
        owner_division_id=body.owner_division_id,
        actor=actor,
    )
    await session.commit()
    return _project_dict(project)


@router.get("/snapshot")
async def org_snapshot_route(
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_org_admin_user),
) -> dict:
    """Org snapshot; ``org_id`` defaults to the admin's own organization and may not name another."""
    if org_id is not None and org_id != admin.org_id:
        raise AppError(403, "Not allowed")
    return await org_snapshot(session, org_id=admin.org_id, project_id=project_id)
