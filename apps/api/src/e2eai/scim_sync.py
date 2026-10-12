"""Org-change-driven access updates from SCIM (FR-S8).

Applies SCIM-style user and group payloads (pushed by the identity provider / HR system, or by a small
bridge) to the org model. Principals are computed from the org tables (`authz.principals`), so a division
or team change takes effect on the next request; the matching OpenFGA membership tuples are corrected in
the same sync (removals first, tighten-first).

- Users are matched by email. Department -> division by case-insensitive name; an unknown department
  fails closed (division cleared, nothing granted) and is reported as a warning.
- `active=false` deprovisions through the FR-F18 offboarding flow (assets go to the manager, else the
  syncing admin). Never-seen inactive users are skipped, not created.
- Groups map to teams by display name; membership is mirrored exactly (members by email).
- Audit rows carry counts and ids only (no emails or names).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Division, Team, TeamMember, User, get_session
from .legal_hold import is_admin
from .offboarding import deactivate_user

ENTERPRISE_KEY = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
MAX_USERS = 1000
MAX_GROUPS = 500


def _email(payload: dict[str, Any]) -> str:
    emails = payload.get("emails") or []
    primary = next((e for e in emails if isinstance(e, dict) and e.get("primary")), None)
    candidate = (primary or (emails[0] if emails and isinstance(emails[0], dict) else {})).get("value") or payload.get("userName")
    value = str(candidate or "").strip().lower()
    if "@" not in value or len(value) > 320:
        raise AppError(400, "Invalid SCIM user: a valid email or userName is required")
    return value


async def _division_id(session: AsyncSession, org_id: uuid.UUID, dept: str | None) -> tuple[uuid.UUID | None, bool]:
    """Return (division_id, unmapped). Empty/absent department clears the division without a warning."""
    if not dept or not dept.strip():
        return None, False
    div = await session.scalar(
        select(Division).where(Division.org_id == org_id, func.lower(Division.name) == dept.strip().lower())
    )
    return (div.id, False) if div else (None, True)


def _membership(user_id: uuid.UUID, kind: str, obj_id: uuid.UUID) -> dict[str, str]:
    return {"user": f"user:{user_id}", "relation": "member", "object": f"{kind}:{obj_id}"}


async def _apply_user(
    session: AsyncSession, redis, authz, *, actor: User, payload: dict[str, Any],
    writes: list[dict], deletes: list[dict],
) -> dict[str, Any]:
    email = _email(payload)
    active = payload.get("active", True) is not False
    dept = (payload.get(ENTERPRISE_KEY) or {}).get("department") if isinstance(payload.get(ENTERPRISE_KEY), dict) else None
    name = str(payload.get("displayName") or email)[:200]
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    entry: dict[str, Any] = {"user_id": str(user.id) if user else None, "warnings": []}

    if not active:
        if user is None:
            return {**entry, "action": "skipped_inactive"}
        if user.status != "active":
            return {**entry, "action": "unchanged"}
        transfer_to = user.manager_id
        mgr = await session.get(User, transfer_to) if transfer_to else None
        if mgr is None or mgr.status != "active" or mgr.id == user.id:
            transfer_to = actor.id
        await deactivate_user(session, redis, authz, admin=actor, target_user_id=user.id, transfer_to_id=transfer_to)
        return {**entry, "action": "deactivated"}

    division_id, unmapped = await _division_id(session, actor.org_id, dept)
    if unmapped:
        entry["warnings"].append("unmapped_department")
    if user is None:
        user = await _create(session, actor, email, name, division_id)
        entry.update(user_id=str(user.id), action="created", division_changed=division_id is not None)
        if division_id:
            writes.append(_membership(user.id, "division", division_id))
        return entry

    changed = False
    if user.status != "active":
        user.status = "active"
        changed = True
    old_div = user.division_id
    division_changed = old_div != division_id
    if division_changed:
        if old_div:
            deletes.append(_membership(user.id, "division", old_div))  # lose the old division first
        if division_id:
            writes.append(_membership(user.id, "division", division_id))
        user.division_id = division_id
        changed = True
    if user.display_name != name:
        user.display_name = name
        changed = True
    entry["action"] = "updated" if changed else "unchanged"
    if division_changed:
        entry["division_changed"] = True
    return entry


async def _create(session: AsyncSession, actor: User, email: str, name: str, division_id: uuid.UUID | None) -> User:
    user = User(org_id=actor.org_id, email=email, display_name=name, division_id=division_id, created_by=f"scim:{actor.id}")
    session.add(user)
    await session.flush()
    return user


async def _apply_group(
    session: AsyncSession, *, group: dict[str, Any], writes: list[dict], deletes: list[dict], org_id: uuid.UUID
) -> dict[str, Any]:
    name = str(group.get("displayName") or "").strip()
    out = {"group": name, "added": 0, "removed": 0, "unknown_members": 0}
    team = await session.scalar(
        select(Team).join(Division, Division.id == Team.division_id)
        .where(Division.org_id == org_id, func.lower(Team.name) == name.lower())
    ) if name else None
    if team is None:
        return {**out, "warnings": ["unmapped_group"]}
    wanted: set[uuid.UUID] = set()
    for member in group.get("members") or []:
        value = str((member or {}).get("value", "")).strip().lower() if isinstance(member, dict) else ""
        user = await session.scalar(select(User).where(func.lower(User.email) == value, User.status == "active")) if value else None
        if user is None:
            out["unknown_members"] += 1
        else:
            wanted.add(user.id)
    current = set((await session.scalars(select(TeamMember.user_id).where(TeamMember.team_id == team.id))).all())
    for uid in current - wanted:
        member_row = await session.get(TeamMember, {"team_id": team.id, "user_id": uid})
        if member_row is not None:
            await session.delete(member_row)
        deletes.append(_membership(uid, "team", team.id))
        out["removed"] += 1
    for uid in wanted - current:
        session.add(TeamMember(team_id=team.id, user_id=uid))
        writes.append(_membership(uid, "team", team.id))
        out["added"] += 1
    return out


async def sync_scim(
    session: AsyncSession,
    redis,
    authz,
    *,
    actor: User,
    users: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if actor.status != "active" or not await is_admin(session, actor):
        raise AppError(403, "Not allowed")
    users, groups = users or [], groups or []
    if len(users) > MAX_USERS or len(groups) > MAX_GROUPS:
        raise AppError(400, "SCIM payload too large")
    writes: list[dict] = []
    deletes: list[dict] = []
    user_results = [
        await _apply_user(session, redis, authz, actor=actor, payload=p, writes=writes, deletes=deletes) for p in users
    ]
    group_results = [
        await _apply_group(session, group=g, writes=writes, deletes=deletes, org_id=actor.org_id) for g in groups
    ]
    summary = {
        "created": sum(r["action"] == "created" for r in user_results),
        "updated": sum(r["action"] == "updated" for r in user_results),
        "unchanged": sum(r["action"] == "unchanged" for r in user_results),
        "deactivated": sum(r["action"] == "deactivated" for r in user_results),
        "skipped": sum(r["action"] == "skipped_inactive" for r in user_results),
        "warnings": sum(len(r["warnings"]) for r in user_results) + sum(len(g.get("warnings", [])) for g in group_results),
    }
    await audit.record(session, f"user:{actor.id}", "scim.sync", "scim", summary)
    await session.commit()  # local principals tightened/loosened first; OpenFGA follows
    if deletes:
        await authz.write(deletes=deletes)
    if writes:
        await authz.write(writes=writes)
    return {**summary, "users": user_results, "groups": group_results}


class ScimSyncIn(BaseModel):
    users: list[dict[str, Any]] = Field(default=[], max_length=MAX_USERS)
    groups: list[dict[str, Any]] = Field(default=[], max_length=MAX_GROUPS)


router = APIRouter(prefix="/api/v1/scim", tags=["scim"])


@router.post("/sync")
async def scim_sync_api(
    body: ScimSyncIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """FR-S8: apply SCIM-style users/groups so access follows org changes (admin only)."""
    from .auth import redis_client
    from .authz import connect
    from .core.config import get_settings

    require_scope(sess, "admin")
    actor = await db.get(User, uuid.UUID(sess["user_id"]))
    if actor is None or actor.status != "active":
        raise AppError(401, "Not authenticated")
    return await sync_scim(db, redis_client(), await connect(get_settings(), db), actor=actor, users=body.users, groups=body.groups)
