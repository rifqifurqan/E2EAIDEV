"""OpenFGA: the source of truth for sharing (PRD T4). Checks fail closed (NFR-19)."""

import hashlib
import json
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import Settings
from .db import Setting, TeamMember, User, UserRole

log = logging.getLogger("e2eai.authz")

_GRANTEES = [
    {"type": "user"}, {"type": "team", "relation": "member"}, {"type": "division", "relation": "member"},
    {"type": "role", "relation": "member"}, {"type": "org", "relation": "member"},
    {"type": "user", "condition": "non_expired"}, {"type": "team", "relation": "member", "condition": "non_expired"},
]


def _group(name: str) -> dict:
    return {"type": name, "relations": {"member": {"this": {}}},
            "metadata": {"relations": {"member": {"directly_related_user_types": [{"type": "user"}]}}}}


def _shareable(name: str) -> dict:
    inherit = lambda rel: {"tupleToUserset": {"tupleset": {"relation": "parent"}, "computedUserset": {"relation": rel}}}  # noqa: E731
    return {
        "type": name,
        "relations": {
            "parent": {"this": {}},
            "owner": {"this": {}},
            "editor": {"union": {"child": [{"this": {}}, {"computedUserset": {"relation": "owner"}}, inherit("editor")]}},
            "viewer": {"union": {"child": [{"this": {}}, {"computedUserset": {"relation": "editor"}}, inherit("viewer")]}},
        },
        "metadata": {"relations": {
            "parent": {"directly_related_user_types": [{"type": "folder"}]},
            "owner": {"directly_related_user_types": [{"type": "user"}]},
            "editor": {"directly_related_user_types": _GRANTEES},
            "viewer": {"directly_related_user_types": _GRANTEES},
        }},
    }


# The DSL in PRD T4, in the JSON form the OpenFGA API accepts. Single source of truth for the model.
MODEL = {
    "schema_version": "1.1",
    "type_definitions": [
        {"type": "user"}, _group("org"), _group("division"), _group("team"), _group("role"),
        {"type": "guest"},  # reserved for external sharing (Q5)
        _shareable("folder"), _shareable("document"),
        {"type": "bot",
         "relations": {"admin": {"this": {}}, "user": {"union": {"child": [{"this": {}}, {"computedUserset": {"relation": "admin"}}]}}},
         "metadata": {"relations": {"admin": {"directly_related_user_types": [{"type": "user"}]},
                                    "user": {"directly_related_user_types": _GRANTEES[:5]}}}},
    ],
    "conditions": {"non_expired": {
        "name": "non_expired", "expression": "current_time < expires_at",
        "parameters": {"current_time": {"type_name": "TYPE_NAME_TIMESTAMP"}, "expires_at": {"type_name": "TYPE_NAME_TIMESTAMP"}},
    }},
}
MODEL_HASH = hashlib.sha256(json.dumps(MODEL, sort_keys=True).encode()).hexdigest()


@dataclass
class Authz:
    client: httpx.AsyncClient
    store_id: str
    model_id: str

    async def write(self, writes: list[dict] = (), deletes: list[dict] = ()) -> None:
        body: dict = {"authorization_model_id": self.model_id}
        if writes:
            body["writes"] = {"tuple_keys": list(writes)}
        if deletes:
            body["deletes"] = {"tuple_keys": list(deletes)}
        r = await self.client.post(f"/stores/{self.store_id}/write", json=body)
        r.raise_for_status()

    async def check(self, user: str, relation: str, obj: str, context: dict | None = None) -> bool:
        """True only on an explicit 'allowed'. Timeouts, errors and outages deny (fail closed)."""
        body = {"tuple_key": {"user": user, "relation": relation, "object": obj}, "authorization_model_id": self.model_id}
        if context:
            body["context"] = context
        try:
            r = await self.client.post(f"/stores/{self.store_id}/check", json=body)
            r.raise_for_status()
            return r.json().get("allowed") is True
        except Exception as e:
            log.warning("authz check failed closed: %s %s %s (%s)", user, relation, obj, e)
            return False


def client(settings: Settings, timeout: float = 3.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.openfga_url, timeout=timeout,
                             headers={"Authorization": f"Bearer {settings.openfga_key}"})


async def connect(settings: Settings, session: AsyncSession) -> Authz:
    """Find or create the store, and write the model when it changed. IDs are remembered in `settings`."""
    http = client(settings)
    saved = await session.get(Setting, "openfga")
    value = dict(saved.value) if saved else {}
    if value.get("store") != settings.openfga_store or not value.get("store_id"):
        stores_response = await http.get("/stores")
        stores_response.raise_for_status()
        stores = stores_response.json()["stores"]
        match = next((s for s in stores if s["name"] == settings.openfga_store), None)
        if match:
            store_id = match["id"]
        else:
            create_response = await http.post("/stores", json={"name": settings.openfga_store})
            create_response.raise_for_status()
            store_id = create_response.json()["id"]
        value = {"store": settings.openfga_store, "store_id": store_id}
    if value.get("model_hash") != MODEL_HASH:
        model_response = await http.post(f"/stores/{value['store_id']}/authorization-models", json=MODEL)
        model_response.raise_for_status()
        value |= {"model_id": model_response.json()["authorization_model_id"], "model_hash": MODEL_HASH}
    if saved:
        saved.value = value
    else:
        session.add(Setting(key="openfga", value=value))
    await session.commit()
    return Authz(http, value["store_id"], value["model_id"])


async def principals(session: AsyncSession, user: User) -> set[str]:
    """Who this user is for permission purposes (PRD T4). Disabled users are nobody."""
    if user.status != "active":
        return set()
    out = {f"user:{user.id}", f"org:{user.org_id}"}
    if user.division_id:
        out.add(f"division:{user.division_id}")
    out |= {f"team:{t}" for t in await session.scalars(select(TeamMember.team_id).where(TeamMember.user_id == user.id))}
    out |= {f"role:{r}" for r in await session.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id))}
    return out


def membership_tuples(user: User, team_ids: list, role_ids: list) -> list[dict]:
    """Group memberships OpenFGA needs, mirrored from the org tables."""
    u = f"user:{user.id}"
    tuples = [{"user": u, "relation": "member", "object": f"org:{user.org_id}"}]
    if user.division_id:
        tuples.append({"user": u, "relation": "member", "object": f"division:{user.division_id}"})
    tuples += [{"user": u, "relation": "member", "object": f"team:{t}"} for t in team_ids]
    tuples += [{"user": u, "relation": "member", "object": f"role:{r}"} for r in role_ids]
    return tuples
