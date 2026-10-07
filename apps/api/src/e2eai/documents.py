"""Documents, sharing read-index, and permission-filtered retrieval groundwork for Phase 1.

This is the first backend tracer bullet for US1/US3/US4: seed/upload document metadata and chunks,
share by writing OpenFGA first then the local read-index, filter chunks by the caller's effective
principals, and revoke by deleting the read-index first (tighten first) before OpenFGA.
"""

import hashlib
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import case, delete, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session
from .authz import principals
from .core.config import repo_root
from .core.errors import AppError
from .db import Chunk, DocPrincipal, Document, DocumentVersion, Folder, FolderPrincipal, Notification, User
from .db import get_session
from .share_policy import SENSITIVITIES, SharePolicy, share_block_reason


def _document_object(document_id: uuid.UUID) -> str:
    return f"document:{document_id}"


def _relation(level: str) -> str:
    return level if level in ("owner", "editor") else "viewer"


class LocalObjectStorage:
    """Small P0 storage adapter used until the S3 client is wired.

    Files are content-addressed, matching the final S3 key shape (`sha256/<hash>`). The adapter boundary
    keeps the upload path testable and lets us swap in SeaweedFS/aioboto3 without changing routes.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or repo_root() / ".data" / "objects"

    async def put_bytes(self, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"sha256/{digest}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return key, digest

    async def get_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    async def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


def get_storage() -> LocalObjectStorage:
    return LocalObjectStorage()


async def create_seeded_document(
    session: AsyncSession,
    *,
    owner: User,
    title: str,
    text: str,
    page: int = 1,
    folder: Folder | None = None,
) -> Document:
    """Create document metadata, one current version, and one text chunk.

    The real upload/parser/embedding jobs will replace this helper later; for the Phase 1 tracer bullet
    it gives tests a deterministic chunk without invoking Docling or model servers.
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    doc = Document(folder_id=folder.id if folder else None, owner_id=owner.id, title=title, created_by=str(owner.id))
    session.add(doc)
    await session.flush()
    version = DocumentVersion(
        document_id=doc.id,
        object_key=f"seeded/{digest}.txt",
        sha256=digest,
        mime="text/plain",
        size=len(text.encode("utf-8")),
        parse_status="ready",
        scan_status="clean",
        created_by=str(owner.id),
    )
    session.add(version)
    await session.flush()
    doc.current_version_id = version.id
    session.add(Chunk(document_id=doc.id, version_id=version.id, ordinal=0, text=text, page=page, section_path="seed"))
    session.add(DocPrincipal(document_id=doc.id, principal=f"user:{owner.id}", level="owner"))
    await audit.record(session, f"user:{owner.id}", "document.seed", _document_object(doc.id), {"title": title})
    await session.commit()
    return doc


async def create_uploaded_document(
    session: AsyncSession,
    *,
    owner: User,
    title: str,
    data: bytes,
    mime: str,
    storage: LocalObjectStorage,
) -> Document:
    """Store the uploaded object and version metadata (PRD F1.2). Parsing/chunking is a separate
    ingest step (`e2eai.ingest.ingest_version`), so the version is created `pending`."""
    key, digest = await storage.put_bytes(data)
    doc = Document(title=title, owner_id=owner.id, created_by=str(owner.id))
    session.add(doc)
    await session.flush()
    version = DocumentVersion(
        document_id=doc.id,
        object_key=key,
        sha256=digest,
        mime=mime,
        size=len(data),
        parse_status="pending",
        scan_status="pending",
        created_by=str(owner.id),
    )
    session.add(version)
    await session.flush()
    doc.current_version_id = version.id
    session.add(DocPrincipal(document_id=doc.id, principal=f"user:{owner.id}", level="owner"))
    await audit.record(session, f"user:{owner.id}", "document.upload", _document_object(doc.id), {"title": title, "mime": mime})
    await session.commit()
    return doc


async def share_document(
    session: AsyncSession,
    authz,
    *,
    actor: User,
    document_id: uuid.UUID,
    principal: str,
    level: str = "viewer",
    policy: SharePolicy | None = None,
) -> None:
    """Grant access. Enforce sensitivity/admin guardrails *before* any write (FR-D5, FR-S7): a blocked
    share audits and raises without creating an OpenFGA tuple or a doc_principal. Otherwise loosen last:
    OpenFGA tuple first, local read-index row second (PRD T4)."""
    policy = policy or SharePolicy()
    doc = await _load_document(session, document_id)
    reason = share_block_reason(doc.sensitivity, principal, policy)
    if reason:
        await audit.record(session, f"user:{actor.id}", "document.share.blocked", _document_object(document_id),
                           {"principal": principal, "level": level, "sensitivity": doc.sensitivity, "reason": reason})
        await session.commit()
        raise AppError(403, "Share not allowed", reason)
    relation = "viewer" if level == "viewer" else "editor" if level == "editor" else "owner"
    await authz.write(writes=[{"user": principal, "relation": relation, "object": _document_object(document_id)}])
    await session.merge(DocPrincipal(document_id=document_id, principal=principal, level=level))
    await _notify_direct_user_share(session, actor=actor, principal=principal, title=doc.title, document_id=document_id)
    await audit.record(session, f"user:{actor.id}", "document.share", _document_object(document_id), {"principal": principal, "level": level})
    await session.commit()


async def share_folder(
    session: AsyncSession,
    authz,
    *,
    actor: User,
    folder_id: uuid.UUID,
    principal: str,
    level: str = "viewer",
) -> None:
    """Grant a folder principal (FR-S3). Loosen last: OpenFGA first, local read-index second."""
    folder = await session.get(Folder, folder_id)
    if folder is None:
        raise AppError(404, "Folder not found")
    await authz.write(writes=[{"user": principal, "relation": _relation(level), "object": f"folder:{folder_id}"}])
    await session.merge(FolderPrincipal(folder_id=folder_id, principal=principal, level=level))
    await _notify_direct_user_share(session, actor=actor, principal=principal, title=folder.name, folder_id=folder_id)
    await audit.record(session, f"user:{actor.id}", "folder.share", f"folder:{folder_id}", {"principal": principal, "level": level})
    await session.commit()


async def revoke_folder(
    session: AsyncSession,
    authz,
    *,
    actor: User,
    folder_id: uuid.UUID,
    principal: str,
    level: str = "viewer",
) -> None:
    """Revoke a folder principal (FR-S3). Tighten first: local row delete before OpenFGA delete."""
    await session.execute(delete(FolderPrincipal).where(FolderPrincipal.folder_id == folder_id, FolderPrincipal.principal == principal))
    await audit.record(session, f"user:{actor.id}", "folder.revoke", f"folder:{folder_id}", {"principal": principal})
    await session.commit()
    await authz.write(deletes=[{"user": principal, "relation": _relation(level), "object": f"folder:{folder_id}"}])


async def _notify_direct_user_share(
    session: AsyncSession,
    *,
    actor: User,
    principal: str,
    title: str,
    document_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
) -> None:
    """Create an in-app notification only for a direct user principal.

    Group notifications stay represented in audit for now; the notification details intentionally carry
    safe metadata only (title/type/id), never document contents or snippets.
    """
    if not principal.startswith("user:"):
        await audit.record(session, f"user:{actor.id}", "notification.group.placeholder", principal,
                           {"target_type": "folder" if folder_id else "document"})
        return
    try:
        user_id = uuid.UUID(principal.split(":", 1)[1])
    except ValueError:
        return
    if user_id == actor.id:
        return
    details = {"title": title, "shared_by": str(actor.id)}
    if document_id:
        details |= {"document_id": str(document_id), "target_type": "document"}
    if folder_id:
        details |= {"folder_id": str(folder_id), "target_type": "folder"}
    session.add(Notification(user_id=user_id, kind="document.shared", details=details))


async def revoke_document(
    session: AsyncSession,
    authz,
    *,
    actor: User,
    document_id: uuid.UUID,
    principal: str,
    level: str = "viewer",
) -> None:
    """Revoke access. Tighten first: local read-index row deleted before OpenFGA tuple (PRD T4)."""
    relation = "viewer" if level == "viewer" else "editor" if level == "editor" else "owner"
    await session.execute(delete(DocPrincipal).where(DocPrincipal.document_id == document_id, DocPrincipal.principal == principal))
    await audit.record(session, f"user:{actor.id}", "document.revoke", _document_object(document_id), {"principal": principal})
    await session.commit()
    await authz.write(deletes=[{"user": principal, "relation": relation, "object": _document_object(document_id)}])


async def _load_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.status == "purged":
        raise AppError(404, "Document not found")
    return doc


async def update_sensitivity(
    session: AsyncSession, *, actor: User, document_id: uuid.UUID, sensitivity: str
) -> Document:
    """Set a document's sensitivity label (FR-D5). Audited so the label history is traceable."""
    if sensitivity not in SENSITIVITIES:
        raise AppError(400, "Invalid sensitivity", f"Use one of: {', '.join(SENSITIVITIES)}")
    doc = await _load_document(session, document_id)
    old = doc.sensitivity
    doc.sensitivity = sensitivity
    await audit.record(session, f"user:{actor.id}", "document.sensitivity", _document_object(document_id),
                       {"from": old, "to": sensitivity})
    await session.commit()
    return doc


async def trash_document(session: AsyncSession, *, actor: User, document_id: uuid.UUID) -> None:
    """Move a document to trash (FR-D9). Retrieval filters `status = 'active'`, so it disappears
    immediately from everyone's retrieval/chat/citations — no separate cache purge needed yet."""
    doc = await _load_document(session, document_id)
    doc.status = "trashed"
    doc.trashed_at = datetime.now(UTC)
    await audit.record(session, f"user:{actor.id}", "document.trash", _document_object(document_id), {})
    await session.commit()


async def restore_document(
    session: AsyncSession, *, actor: User, document_id: uuid.UUID, retention_days: int = 30
) -> None:
    """Restore from trash within the retention window (FR-D9, NFR-10 default 30 days)."""
    doc = await _load_document(session, document_id)
    if doc.status != "trashed":
        raise AppError(409, "Document is not in trash")
    if doc.trashed_at and datetime.now(UTC) - doc.trashed_at > timedelta(days=retention_days):
        raise AppError(410, "Trash retention expired", "This document can no longer be restored and may be purged.")
    doc.status = "active"
    doc.trashed_at = None
    await audit.record(session, f"user:{actor.id}", "document.restore", _document_object(document_id), {})
    await session.commit()


async def purge_document(
    session: AsyncSession, authz, *, actor: User, document_id: uuid.UUID, storage: LocalObjectStorage | None = None
) -> None:
    """Permanently delete derived content and the stored object (FR-D9). Legal hold blocks it (FR-D13).

    Tighten first (PRD T4): delete the local read-index and derived rows, then delete the OpenFGA tuples.
    The document row survives as a `purged` tombstone (so citations in old chats resolve to a gone-doc,
    not a dangling id). Content-addressed objects are only unlinked when no other version still refers
    to them."""
    doc = await _load_document(session, document_id)
    if doc.legal_hold:
        raise AppError(409, "Legal hold blocks purge", "This document is under legal hold and cannot be permanently deleted.")
    storage = storage or get_storage()

    grants = (await session.execute(
        select(DocPrincipal.principal, DocPrincipal.level).where(DocPrincipal.document_id == document_id)
    )).all()
    object_keys = set(await session.scalars(
        select(DocumentVersion.object_key).where(DocumentVersion.document_id == document_id)
    ))

    # Tighten first: local read-index + derived rows go before OpenFGA. Chunks cascade to embeddings.
    await session.execute(delete(DocPrincipal).where(DocPrincipal.document_id == document_id))
    await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await session.execute(delete(DocumentVersion).where(DocumentVersion.document_id == document_id))
    doc.status = "purged"
    doc.current_version_id = None
    await audit.record(session, f"user:{actor.id}", "document.purge", _document_object(document_id),
                       {"principals": len(grants), "objects": len(object_keys)})
    await session.commit()

    deletes = [{"user": p, "relation": _relation(level), "object": _document_object(document_id)} for p, level in grants]
    if deletes:
        await authz.write(deletes=deletes)

    for key in object_keys:
        still_used = await session.scalar(
            select(func.count()).select_from(DocumentVersion).where(DocumentVersion.object_key == key)
        )
        if not still_used:
            await storage.delete(key)


async def visible_chunks(session: AsyncSession, principals: Iterable[str]) -> list[tuple[str, str, int | None]]:
    """Return only chunks from active documents visible to at least one principal.

    Direct document shares and inherited folder shares are both checked in SQL before rows are returned.
    No rows means no existence hints to the caller.
    """
    principal_list = sorted(set(principals))
    if not principal_list:
        return []
    allowed = _visible_document_clause(principal_list)
    rows = await session.execute(
        select(Document.title, Chunk.text, Chunk.page)
        .join(Chunk, Chunk.document_id == Document.id)
        .where(
            Document.status == "active",
            Chunk.version_id == Document.current_version_id,
            allowed,
        )
        .order_by(Document.title, Chunk.ordinal)
    )
    return list(rows.all())


def _visible_document_clause(principal_list: list[str]):
    direct = exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal.in_(principal_list))
    folder = exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal.in_(principal_list))
    return or_(direct, folder)


async def list_documents_view(session: AsyncSession, *, user: User, view: str = "all") -> list[dict]:
    """Permission-filtered document metadata views (FR-S6).

    Returns only documents the user is allowed to know about. Metadata is intentionally small and contains
    no snippets/content.
    """
    user_principals = await principals(session, user)
    principal_list = sorted(user_principals)
    if not principal_list:
        return []
    stmt = select(Document.id, Document.title, Document.owner_id, Document.sensitivity).where(
        Document.status == "active", _visible_document_clause(principal_list)
    )
    if view == "my_documents":
        stmt = stmt.where(Document.owner_id == user.id)
    elif view == "shared_with_me":
        direct_user = f"user:{user.id}"
        user_share = or_(
            exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal == direct_user),
            exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal == direct_user),
        )
        stmt = stmt.where(Document.owner_id != user.id, user_share)
    elif view == "my_team":
        teams = sorted(p for p in user_principals if p.startswith("team:"))
        if not teams:
            return []
        team_share = or_(
            exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal.in_(teams)),
            exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal.in_(teams)),
        )
        stmt = stmt.where(team_share)
    elif view not in ("all", "everything"):
        raise AppError(400, "Invalid document view")
    stmt = stmt.order_by(Document.title)
    return [
        {"id": str(doc_id), "title": title, "owner_id": str(owner_id), "sensitivity": sensitivity}
        for doc_id, title, owner_id, sensitivity in (await session.execute(stmt)).all()
    ]


async def search_documents(
    session: AsyncSession,
    *,
    user: User,
    query: str,
    sensitivity: str | None = None,
    status: str | None = None,
    view: str = "all",
) -> list[dict]:
    """Permission-filtered document search by title and chunk content (FR-S10).

    Permission is enforced in the SQL WHERE clause via `_visible_document_clause` — the same predicate
    used by `visible_chunks` and `list_documents_view`. Unshared documents never appear, and no title,
    snippet, or existence hint is returned to unauthorized callers (FR-C12).

    Returns safe fields only: document_id, title, sensitivity, status, owner_id, match_kind.
    """
    query = query.strip()
    if not query:
        return []
    user_principals = await principals(session, user)
    principal_list = sorted(user_principals)
    if not principal_list:
        return []

    like_pattern = f"%{query}%"

    title_match = Document.title.ilike(like_pattern)
    content_match = exists().where(
        Chunk.document_id == Document.id,
        Chunk.version_id == Document.current_version_id,
        Chunk.text.ilike(like_pattern),
    )

    effective_status = status or "active"
    filters = [
        Document.status == effective_status,
        _visible_document_clause(principal_list),
        or_(title_match, content_match),
    ]

    if sensitivity:
        filters.append(Document.sensitivity == sensitivity)

    if view == "my_documents":
        filters.append(Document.owner_id == user.id)
    elif view == "shared_with_me":
        direct_user = f"user:{user.id}"
        user_share = or_(
            exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal == direct_user),
            exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal == direct_user),
        )
        filters.append(Document.owner_id != user.id)
        filters.append(user_share)
    elif view == "my_team":
        teams = sorted(p for p in user_principals if p.startswith("team:"))
        if not teams:
            return []
        team_share = or_(
            exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal.in_(teams)),
            exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal.in_(teams)),
        )
        filters.append(team_share)
    elif view not in ("all", "everything"):
        raise AppError(400, "Invalid document view")

    match_kind_expr = case(
        (title_match, literal("title")),
        else_=literal("content"),
    )

    stmt = (
        select(
            Document.id,
            Document.title,
            Document.sensitivity,
            Document.status,
            Document.owner_id,
            match_kind_expr.label("match_kind"),
        )
        .where(*filters)
        .order_by(Document.title)
    )

    return [
        {
            "document_id": str(doc_id),
            "title": title,
            "sensitivity": sens,
            "status": st,
            "owner_id": str(owner_id),
            "match_kind": mk,
        }
        for doc_id, title, sens, st, owner_id, mk in (await session.execute(stmt)).all()
    ]


async def list_notifications(session: AsyncSession, *, user: User, unread_only: bool = False) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class ShareIn(BaseModel):
    principal: str
    level: str = "viewer"


class SensitivityIn(BaseModel):
    sensitivity: str


router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
    storage: LocalObjectStorage = Depends(get_storage),
) -> dict:
    from .ingest import ingest_version
    from .retrieval import LiteLLMEmbedder

    user = await _current_user(db, sess)
    data = await file.read()
    if not data:
        raise AppError(400, "Empty upload")
    doc = await create_uploaded_document(
        db,
        owner=user,
        title=file.filename or "uploaded document",
        data=data,
        mime=file.content_type or "application/octet-stream",
        storage=storage,
    )
    result = await ingest_version(db, embedder=LiteLLMEmbedder.from_settings(), version_id=doc.current_version_id, storage=storage)
    return {"document_id": str(doc.id), "title": doc.title, "parse_status": result["status"],
            "scan_status": result.get("scan_status"), "chunks": result["chunks"]}


@router.post("/documents/{document_id}/shares")
async def share_document_api(
    document_id: uuid.UUID,
    body: ShareIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    from .authz import connect
    from .core.config import get_settings

    user = await _current_user(db, sess)
    await _require_owner(db, user, document_id)
    await share_document(db, await connect(get_settings(), db), actor=user, document_id=document_id,
                         principal=body.principal, level=body.level, policy=SharePolicy.from_settings())
    return {"status": "ok"}


@router.patch("/documents/{document_id}/sensitivity")
async def set_sensitivity_api(
    document_id: uuid.UUID,
    body: SensitivityIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Set a document's sensitivity label (FR-D5). Requires document ownership."""
    user = await _current_user(db, sess)
    await _require_owner(db, user, document_id)
    doc = await update_sensitivity(db, actor=user, document_id=document_id, sensitivity=body.sensitivity)
    return {"status": "ok", "sensitivity": doc.sensitivity}


async def _require_owner(db: AsyncSession, user: User, document_id: uuid.UUID) -> None:
    owner_row = await db.scalar(select(DocPrincipal).where(
        DocPrincipal.document_id == document_id, DocPrincipal.principal == f"user:{user.id}", DocPrincipal.level == "owner"))
    if owner_row is None:
        raise AppError(403, "Not allowed")


@router.delete("/documents/{document_id}")
async def delete_document_api(
    document_id: uuid.UUID,
    permanent: bool = False,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
    storage: LocalObjectStorage = Depends(get_storage),
) -> dict:
    """Trash by default; `?permanent=true` purges (FR-D9). Both require document ownership."""
    from .authz import connect
    from .core.config import get_settings

    user = await _current_user(db, sess)
    await _require_owner(db, user, document_id)
    if permanent:
        await purge_document(db, await connect(get_settings(), db), actor=user, document_id=document_id, storage=storage)
        return {"status": "purged"}
    await trash_document(db, actor=user, document_id=document_id)
    return {"status": "trashed"}


@router.post("/documents/{document_id}/restore")
async def restore_document_api(
    document_id: uuid.UUID,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await _current_user(db, sess)
    await _require_owner(db, user, document_id)
    await restore_document(db, actor=user, document_id=document_id)
    return {"status": "active"}


@router.get("/documents/search")
async def search_documents_api(
    q: str = "",
    sensitivity: str | None = None,
    view: str = "all",
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Permission-filtered document search (FR-S10). Returns safe metadata only."""
    user = await _current_user(db, sess)
    results = await search_documents(db, user=user, query=q, sensitivity=sensitivity, view=view)
    return {"results": results}


@router.get("/documents/visible-chunks")
async def visible_chunks_api(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    user = await _current_user(db, sess)
    rows = await visible_chunks(db, await principals(db, user))
    return {"chunks": [{"title": title, "text": text, "page": page} for title, text, page in rows]}
