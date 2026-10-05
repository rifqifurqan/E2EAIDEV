"""Documents, sharing read-index, and permission-filtered retrieval groundwork for Phase 1.

This is the first backend tracer bullet for US1/US3/US4: seed/upload document metadata and chunks,
share by writing OpenFGA first then the local read-index, filter chunks by the caller's effective
principals, and revoke by deleting the read-index first (tighten first) before OpenFGA.
"""

import hashlib
import uuid
from collections.abc import Iterable
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session
from .authz import principals
from .core.config import repo_root
from .core.errors import AppError
from .db import Chunk, DocPrincipal, Document, DocumentVersion, Folder, User
from .db import get_session


def _document_object(document_id: uuid.UUID) -> str:
    return f"document:{document_id}"


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
) -> None:
    """Grant access. Loosen last: OpenFGA tuple first, local read-index row second (PRD T4)."""
    relation = "viewer" if level == "viewer" else "editor" if level == "editor" else "owner"
    await authz.write(writes=[{"user": principal, "relation": relation, "object": _document_object(document_id)}])
    await session.merge(DocPrincipal(document_id=document_id, principal=principal, level=level))
    await audit.record(session, f"user:{actor.id}", "document.share", _document_object(document_id), {"principal": principal, "level": level})
    await session.commit()


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


async def visible_chunks(session: AsyncSession, principals: Iterable[str]) -> list[tuple[str, str, int | None]]:
    """Return only chunks from active documents whose current version is visible to one principal.

    Result tuples are (document title, chunk text, page). No rows means no existence hints to the caller.
    """
    principal_list = sorted(set(principals))
    if not principal_list:
        return []
    rows = await session.execute(
        select(Document.title, Chunk.text, Chunk.page)
        .join(Chunk, Chunk.document_id == Document.id)
        .join(DocPrincipal, DocPrincipal.document_id == Document.id)
        .where(
            Document.status == "active",
            Chunk.version_id == Document.current_version_id,
            DocPrincipal.principal.in_(principal_list),
        )
        .order_by(Document.title, Chunk.ordinal)
    )
    return list(rows.all())


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class ShareIn(BaseModel):
    principal: str
    level: str = "viewer"


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
    return {"document_id": str(doc.id), "title": doc.title, "parse_status": result["status"], "chunks": result["chunks"]}


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
    owner_row = await db.scalar(select(DocPrincipal).where(DocPrincipal.document_id == document_id,
                                                           DocPrincipal.principal == f"user:{user.id}",
                                                           DocPrincipal.level == "owner"))
    if owner_row is None:
        raise AppError(403, "Not allowed")
    await share_document(db, await connect(get_settings(), db), actor=user, document_id=document_id,
                         principal=body.principal, level=body.level)
    return {"status": "ok"}


@router.get("/documents/visible-chunks")
async def visible_chunks_api(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    user = await _current_user(db, sess)
    rows = await visible_chunks(db, await principals(db, user))
    return {"chunks": [{"title": title, "text": text, "page": page} for title, text, page in rows]}
