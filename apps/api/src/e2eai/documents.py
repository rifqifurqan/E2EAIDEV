"""Documents, sharing read-index, and permission-filtered retrieval groundwork for Phase 1.

This is the first backend tracer bullet for US1/US3/US4: seed/upload document metadata and chunks,
share by writing OpenFGA first then the local read-index, filter chunks by the caller's effective
principals, and revoke by deleting the read-index first (tighten first) before OpenFGA.
"""

import hashlib
import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .db import Chunk, DocPrincipal, Document, DocumentVersion, Folder, User


def _document_object(document_id: uuid.UUID) -> str:
    return f"document:{document_id}"


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
