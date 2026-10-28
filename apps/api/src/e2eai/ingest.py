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
from dataclasses import dataclass, replace
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .core.errors import AppError
from .db import Chunk, Document, DocumentVersion
from .documents import ObjectStorage, get_storage
from .index_lineage import record_lineage
from .pii import PiiDetector, PiiPolicy, mask_text, pii_counts, select_detector
from .retrieval import _UNSET as _UNSET_STORE
from .retrieval import Embedder, index_document_chunks
from .scan import ScanPolicy, Scanner, select_scanner

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    page: int | None
    section_path: str
    kind: str = "text"
    table_json: dict | None = None      # tables: {"caption": str, "rows": [[str]]} (first row = header)
    confidence: float | None = None     # 0..1 per page when the parser knows it (OCR / layout quality)


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
    """Rich documents (PDF/DOCX/PPTX/XLSX/HTML/images), FR-D3, through Docling.

    Docling and PyTorch live in the worker environment (`workers/`), not in the API's. Where it is not installed this
    raises a clear AppError so the ingest step records a failed parse instead of losing the upload; when a worker is
    online, `dispatch_ingest` sends rich files there and this runs inside the worker."""

    def parse(self, data: bytes, *, mime: str = "application/octet-stream") -> list[ParsedChunk]:
        try:
            from .docling_runtime import convert_bytes
        except ImportError as exc:
            raise AppError(
                503,
                "Rich document parser unavailable",
                "Parsing PDF/DOCX/PPTX/XLSX/image files needs the Docling worker, which is not running or installed.",
            ) from exc
        return convert_bytes(data, mime)


def select_parser(mime: str) -> Parser:
    if mime.startswith("text/"):
        return TextMarkdownParser()
    return DoclingParser()


async def ingest_version(
    session: AsyncSession,
    *,
    embedder: Embedder,
    version_id: uuid.UUID,
    storage: ObjectStorage | None = None,
    scanner: Scanner | None = None,
    policy: ScanPolicy | None = None,
    pii_detector: PiiDetector | None = None,
    pii_policy: PiiPolicy | None = None,
    vector_store=_UNSET_STORE,
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
    pii_policy = pii_policy or PiiPolicy.from_settings()
    pii_detector = pii_detector or select_detector(pii_policy)
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
        parser = select_parser(version.mime)
        parsed = parser.parse(data, mime=version.mime)
    except AppError as exc:
        version.parse_status = "failed"
        await audit.record(session, "system:ingest", "document.parse.failed", target,
                           {"version_id": str(version_id), "reason": exc.title})
        await session.commit()
        return {"status": "failed", "scan_status": "clean", "chunks": 0, "reason": exc.title}

    pii_total = 0
    if pii_policy.detect:
        aggregate: dict[str, int] = {}
        redacted: list[ParsedChunk] = []
        for pc in parsed:
            findings = pii_detector.detect(pc.text)
            pii_total += len(findings)
            for typ, count in pii_counts(findings).items():
                aggregate[typ] = aggregate.get(typ, 0) + count
            text = mask_text(pc.text, findings) if pii_policy.redact_document_text and findings else pc.text
            redacted.append(replace(pc, text=text))  # keeps kind, table_json and confidence
        parsed = redacted
        if pii_total:
            # Only counts/types and policy decisions are audited — never raw matched values (FR-O12).
            await audit.record(session, "system:ingest", "document.pii.detected", target,
                               {"version_id": str(version_id), "counts": aggregate,
                                "redacted": pii_policy.redact_document_text,
                                "mask_traces": pii_policy.mask_traces})

    await session.execute(delete(Chunk).where(Chunk.version_id == version_id))
    for ordinal, pc in enumerate(parsed):
        session.add(Chunk(document_id=version.document_id, version_id=version_id, ordinal=ordinal,
                          kind=pc.kind, text=pc.text, page=pc.page, section_path=pc.section_path, table_json=pc.table_json))
    version.parse_status = "indexing"  # parsed and stored, but not searchable until the embeddings exist
    scores = [pc.confidence for pc in parsed if pc.confidence is not None]
    version.parse_confidence = min(scores) if scores else 1.0  # the worst page decides: low = "low-confidence parse"
    await audit.record(session, "system:ingest", "document.parse", target,
                       {"version_id": str(version_id), "chunks": len(parsed)})
    await session.commit()

    indexed = await index_document_chunks(
        session, embedder=embedder, document_id=version.document_id, vector_store=vector_store
    )
    await record_lineage(
        session, document_id=version.document_id, version_id=version_id,
        parser=type(parser).__name__, chunker="structure-aware",
        embedding_model=embedder.model, chunk_count=len(parsed),
    )
    version.parse_status = "ready"  # only now can a user's question find this document
    await session.commit()
    return {"status": "ready", "scan_status": "clean", "chunks": len(parsed), "indexed": indexed,
            "pii_findings": pii_total}
