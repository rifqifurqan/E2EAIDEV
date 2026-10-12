"""Knowledge connectors with permission mirroring (FR-X1).

A connector yields `SourceDocument`s (text + the source system's ACL). `sync_connector` mirrors them
into local documents:

- ACL entries map to local principals; anything that cannot be mapped is dropped (fail closed):
  unknown users, groups without an admin-provided `group_map` entry, and public/"anyone" links.
- Mirrored access is read-only (`viewer`), whatever the source role was.
- The syncing admin gets no implicit access (no owner principal is created).
- Tighten first: revoked principals are removed locally before OpenFGA; loosening writes OpenFGA first.
- Content changes add a new document version; documents removed at the source are trashed.
- Credentials never enter this module; real Drive/SharePoint/Nextcloud/Confluence connectors run
  outside the API and feed it through the `Connector` protocol or the push route.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Chunk, ConnectorDocument, DocPrincipal, Document, DocumentVersion, User, get_session
from .legal_hold import is_admin

MAX_DOCUMENTS = 500
MAX_TEXT = 200_000
MAX_ACL = 200


@dataclass
class SourceDocument:
    external_id: str
    title: str
    text: str
    acl: list[dict[str, Any]] = field(default_factory=list)


class Connector(Protocol):
    source: str

    def list_documents(self) -> Sequence[SourceDocument]: ...


class FakeConnector:
    """In-memory connector used by tests and the push route."""

    def __init__(self, source: str, documents: Sequence[SourceDocument]):
        self.source = source
        self.documents = list(documents)

    def list_documents(self) -> Sequence[SourceDocument]:
        return list(self.documents)


def _document_object(document_id) -> str:
    return f"document:{document_id}"


async def _map_principals(
    session: AsyncSession, acl: Sequence[dict[str, Any]], group_map: dict[str, str], dropped: dict[str, int]
) -> set[str]:
    out: set[str] = set()
    for entry in list(acl)[:MAX_ACL]:
        kind = str(entry.get("type", "")).lower()
        if kind == "user":
            email = str(entry.get("email", "")).strip().lower()
            user = await session.scalar(select(User).where(func.lower(User.email) == email, User.status == "active")) if email else None
            if user is None:
                dropped["unknown_user"] += 1
            else:
                out.add(f"user:{user.id}")
        elif kind == "group":
            principal = group_map.get(str(entry.get("id", "")))
            if principal and principal.split(":", 1)[0] in ("user", "team", "division", "role"):
                out.add(principal)
            else:
                dropped["unmapped_group"] += 1
        else:  # anyone / domain / link-sharing: never mirrored
            dropped["public"] += 1
    return out


async def _add_version(session: AsyncSession, doc: Document, text: str, digest: str, actor: User) -> None:
    version = DocumentVersion(
        document_id=doc.id, object_key=f"connector/{digest}.txt", sha256=digest, mime="text/plain",
        size=len(text.encode("utf-8")), parse_status="ready", scan_status="clean", created_by=str(actor.id),
    )
    session.add(version)
    await session.flush()
    doc.current_version_id = version.id
    session.add(Chunk(document_id=doc.id, version_id=version.id, ordinal=0, text=text, section_path="connector"))


async def sync_connector(
    session: AsyncSession,
    authz,
    *,
    actor: User,
    connector: Connector,
    group_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    if actor.status != "active" or not await is_admin(session, actor):
        raise AppError(403, "Not allowed")
    source = connector.source
    docs = list(connector.list_documents())
    if len(docs) > MAX_DOCUMENTS:
        raise AppError(400, "Too many documents in one sync")
    seen_ids = [d.external_id for d in docs]
    if len(set(seen_ids)) != len(seen_ids):
        raise AppError(400, "Duplicate external ids")
    group_map = group_map or {}
    dropped = {"unmapped_group": 0, "public": 0, "unknown_user": 0}
    mapped_total = 0
    counts = {"created": 0, "updated": 0, "unchanged": 0, "trashed": 0}
    existing = {
        c.external_id: c
        for c in (await session.scalars(select(ConnectorDocument).where(ConnectorDocument.source == source))).all()
    }
    authz_deletes: list[dict] = []
    authz_writes: list[dict] = []

    for src in docs:
        if not src.external_id or len(src.text) > MAX_TEXT:
            raise AppError(400, "Invalid source document")
        desired = await _map_principals(session, src.acl, group_map, dropped)
        mapped_total += len(desired)
        digest = hashlib.sha256(src.text.encode("utf-8")).hexdigest()
        link = existing.get(src.external_id)
        if link is None:
            doc = Document(owner_id=actor.id, title=src.title[:500], created_by=str(actor.id))
            session.add(doc)
            await session.flush()
            await _add_version(session, doc, src.text, digest, actor)
            session.add(ConnectorDocument(source=source, external_id=src.external_id, document_id=doc.id, content_sha256=digest))
            current: set[str] = set()
            counts["created"] += 1
            changed = True
        else:
            doc = await session.get(Document, link.document_id)
            current = set(
                (await session.scalars(select(DocPrincipal.principal).where(DocPrincipal.document_id == doc.id))).all()
            )
            changed = False
            if doc.status != "active":
                doc.status, doc.trashed_at = "active", None
                changed = True
            if link.content_sha256 != digest:
                await _add_version(session, doc, src.text, digest, actor)
                link.content_sha256 = digest
                changed = True
            if doc.title != src.title[:500]:
                doc.title = src.title[:500]
                changed = True
            link.last_synced_at = datetime.now(UTC)
        revoked, granted = current - desired, desired - current
        if revoked or granted:
            changed = True
        if link is not None:
            counts["updated" if changed else "unchanged"] += 1
        if revoked:  # tighten first: local read-index now, OpenFGA after commit
            await session.execute(
                delete(DocPrincipal).where(DocPrincipal.document_id == doc.id, DocPrincipal.principal.in_(revoked))
            )
            authz_deletes += [{"user": p, "relation": "viewer", "object": _document_object(doc.id)} for p in sorted(revoked)]
        for p in sorted(granted):
            authz_writes.append({"user": p, "relation": "viewer", "object": _document_object(doc.id)})

    for external_id, link in existing.items():
        if external_id in set(seen_ids):
            continue
        doc = await session.get(Document, link.document_id)
        if doc is not None and doc.status == "active":
            doc.status, doc.trashed_at = "trashed", datetime.now(UTC)
            counts["trashed"] += 1

    await session.flush()
    await session.commit()  # local tightening is durable before any loosening
    if authz_deletes:
        await authz.write(deletes=authz_deletes)
    if authz_writes:
        await authz.write(writes=authz_writes)
        for w in authz_writes:
            doc_id = uuid.UUID(w["object"].split(":", 1)[1])
            await session.merge(DocPrincipal(document_id=doc_id, principal=w["user"], level="viewer"))
    report = {
        **counts, "principals_mapped": mapped_total, "principals_dropped": dropped,
    }
    await audit.record(
        session, f"user:{actor.id}", "connector.sync", f"connector:{source}",
        {"source": source, **counts, "principals_mapped": mapped_total, "principals_dropped": dropped},
    )
    await session.commit()
    return report


class SourceDocIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(max_length=MAX_TEXT)
    acl: list[dict[str, Any]] = []


class SyncIn(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    documents: list[SourceDocIn] = Field(max_length=MAX_DOCUMENTS)
    group_map: dict[str, str] = {}


router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


@router.post("/sync")
async def sync_api(
    body: SyncIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """FR-X1: push a connector's documents + source ACLs for permission-mirrored sync (admin only)."""
    from .authz import connect
    from .core.config import get_settings

    require_scope(sess, "admin")
    actor = await db.get(User, uuid.UUID(sess["user_id"]))
    if actor is None or actor.status != "active":
        raise AppError(401, "Not authenticated")
    connector = FakeConnector(
        body.source, [SourceDocument(d.external_id, d.title, d.text, d.acl) for d in body.documents]
    )
    return await sync_connector(db, await connect(get_settings(), db), actor=actor, connector=connector, group_map=body.group_map)
