"""Parser interface + ingest service for Phase 1 (FR-D1, FR-D3, FR-D4).

The ingest step is the worker stage F1.4 run inline (no heavy Docker worker yet; the Docker VM is
5 GB and Docling ships models). It is callable as an API step, a service function, and an operator
command (`e2eai-api ingest-version`). It reads the stored object by `object_key`, picks a parser by
mime, produces structure-aware chunks, writes them (idempotent per `version_id`), sets `parse_status`
ready/failed with an audit row, then indexes embeddings through the existing `index_document_chunks`
path. Retrieval filtering is unchanged: it stays permission-filtered before scoring.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .core.errors import AppError
from .db import Chunk, Document, DocumentVersion
from .documents import LocalObjectStorage, get_storage
from .retrieval import Embedder, index_document_chunks
from .scan import ScanPolicy, Scanner, select_scanner

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    page: int | None
    section_path: str
    kind: str = "text"


class Parser(Protocol):
    def parse(self, data: bytes, *, mime: str) -> list[ParsedChunk]: ...


@dataclass(frozen=True)
class TextMarkdownParser:
    """Structure-aware parsing for text/markdown: split on ATX headings, carry the heading trail as
    `section_path`, and count form-feed page breaks (FR-D3 headings + page anchors, FR-D4 structure-aware)."""

    def parse(self, data: bytes, *, mime: str = "text/plain") -> list[ParsedChunk]:
        text = data.decode("utf-8", errors="ignore")
        chunks: list[ParsedChunk] = []
        stack: list[tuple[int, str]] = []
        page = 1
        buf: list[str] = []
        buf_page = 1

        def flush() -> None:
            body = "\n".join(buf).strip()
            if body:
                chunks.append(ParsedChunk(text=body, page=buf_page, section_path=" > ".join(t for _, t in stack)))
            buf.clear()

        for raw in text.splitlines():
            if "\f" in raw:
                page += raw.count("\f")
                raw = raw.replace("\f", "")
            heading = _HEADING.match(raw)
            if heading:
                flush()
                level, title = len(heading.group(1)), heading.group(2).strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                buf_page = page
                continue
            if not buf:
                buf_page = page
            buf.append(raw)
        flush()

        if not chunks and text.strip():
            chunks.append(ParsedChunk(text=text.strip(), page=1, section_path=""))
        return chunks


@dataclass(frozen=True)
class DoclingParser:
    """Adapter boundary for rich documents (PDF/DOCX/PPTX/XLSX/images), FR-D3.

    If Docling is installed we convert to markdown and reuse the text parser; otherwise we raise a
    clear AppError so the ingest step records a failed parse. Real Docling wiring lands with the
    worker image (out of scope here: the 5 GB Docker VM can't host it yet)."""

    def parse(self, data: bytes, *, mime: str = "application/octet-stream") -> list[ParsedChunk]:
        try:
            from docling.document_converter import DocumentConverter  # noqa: F401
        except ImportError as exc:
            raise AppError(
                503,
                "Rich document parser unavailable",
                "Parsing PDF/DOCX/PPTX/XLSX/image files needs the Docling worker, not installed in this deployment.",
            ) from exc
        # ponytail: Docling present but worker not wired. Defer real conversion to the worker image
        # milestone rather than download parser models on this 5 GB VM.
        raise AppError(503, "Rich document parser not wired", "Docling is installed but the ingest worker is not wired yet.")


def select_parser(mime: str) -> Parser:
    if mime.startswith("text/"):
        return TextMarkdownParser()
    return DoclingParser()


async def ingest_version(
    session: AsyncSession,
    *,
    embedder: Embedder,
    version_id: uuid.UUID,
    storage: LocalObjectStorage | None = None,
    scanner: Scanner | None = None,
    policy: ScanPolicy | None = None,
) -> dict:
    """Scan, then parse the stored object for one version, (re)write chunks, index embeddings, set status.

    Malware scan runs before any parse/index (FR-D14, PRD F1.4): an infected file is quarantined
    (scan_status=infected, parse_status=skipped, no chunks/embeddings), so it is never parsed, indexed,
    or retrieved and leaks no title/content/citation/existence. If a configured scanner is unavailable,
    the safe policy decides — fail closed (blocked, skipped) or pending (retry later). Idempotent per
    `version_id` (PRD F1.6): existing chunks are deleted before a reparse. On a parser error the version
    is marked `failed` with no chunks — nothing reaches an unauthorised reader because none is produced."""
    storage = storage or get_storage()
    policy = policy or ScanPolicy.from_settings()
    scanner = scanner or select_scanner(policy)
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        raise AppError(404, "Document version not found")
    target = f"document:{version.document_id}"

    data = await storage.get_bytes(version.object_key)
    scan = await scanner.scan(data)
    if scan.verdict == "infected":
        version.scan_status = "infected"
        version.parse_status = "skipped"
        await audit.record(session, "system:scan", "document.scan.infected", target,
                           {"version_id": str(version_id), "signature": scan.signature})
        await session.commit()
        return {"status": "quarantined", "scan_status": "infected", "chunks": 0, "signature": scan.signature}
    if scan.verdict == "unavailable":
        decision = "pending" if policy.on_unavailable == "pending" else "fail_closed"
        version.scan_status = "pending" if decision == "pending" else "unavailable"
        version.parse_status = "pending" if decision == "pending" else "skipped"
        await audit.record(session, "system:scan", "document.scan.unavailable", target,
                           {"version_id": str(version_id), "decision": decision})
        await session.commit()
        status = "pending" if decision == "pending" else "blocked"
        return {"status": status, "scan_status": version.scan_status, "chunks": 0}
    version.scan_status = "clean"
    await audit.record(session, "system:scan", "document.scan.clean", target, {"version_id": str(version_id)})

    try:
        parsed = select_parser(version.mime).parse(data, mime=version.mime)
    except AppError as exc:
        version.parse_status = "failed"
        await audit.record(session, "system:ingest", "document.parse.failed", target,
                           {"version_id": str(version_id), "reason": exc.title})
        await session.commit()
        return {"status": "failed", "scan_status": "clean", "chunks": 0, "reason": exc.title}

    await session.execute(delete(Chunk).where(Chunk.version_id == version_id))
    for ordinal, pc in enumerate(parsed):
        session.add(Chunk(document_id=version.document_id, version_id=version_id, ordinal=ordinal,
                          kind=pc.kind, text=pc.text, page=pc.page, section_path=pc.section_path))
    version.parse_status = "ready"
    version.parse_confidence = 1.0
    await audit.record(session, "system:ingest", "document.parse", target,
                       {"version_id": str(version_id), "chunks": len(parsed)})
    await session.commit()

    indexed = await index_document_chunks(session, embedder=embedder, document_id=version.document_id)
    return {"status": "ready", "scan_status": "clean", "chunks": len(parsed), "indexed": indexed}
