"""Docling conversion for rich documents (FR-D3). Imports Docling at load time, so it only works in an environment that
has it (the worker). `DoclingParser` imports this lazily and reports "parser unavailable" everywhere else.

Docling gives layout-aware structure (headings, tables with their cells, figure captions), OCR for scanned pages, and a
per-page confidence score. `rich_parse` turns that into chunks; this module only owns the library calls.
"""

import logging
import tempfile
from functools import lru_cache
from pathlib import Path

from docling.document_converter import DocumentConverter

from .core.errors import AppError
from .ingest import ParsedChunk
from .rich_parse import blocks_to_chunks, docling_blocks, sniff_suffix

log = logging.getLogger("e2eai.docling")
MAX_PAGES = 500  # one runaway file must not occupy the worker for hours


@lru_cache(maxsize=1)
def converter() -> DocumentConverter:
    """Built once per process: loading the layout, table and OCR models is the expensive part."""
    return DocumentConverter()


def page_confidence(result) -> dict[int, float]:
    """Docling's per-page mean score (0..1). NaN (e.g. no OCR needed on a digital page) is ignored."""
    pages = getattr(getattr(result, "confidence", None), "pages", None) or {}
    scores: dict[int, float] = {}
    for number, report in pages.items():
        score = getattr(report, "mean_score", None)
        if isinstance(score, (int, float)) and score == score:
            scores[int(number)] = float(score)
    return scores


def convert_bytes(data: bytes, mime: str) -> list[ParsedChunk]:
    suffix = sniff_suffix(data, mime)
    if suffix is None:
        raise AppError(415, "Unsupported file type", "Upload a PDF, Word, PowerPoint, Excel, HTML or image file.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"document{suffix}"
        path.write_bytes(data)
        try:
            result = converter().convert(path, max_num_pages=MAX_PAGES)
        except Exception as exc:  # noqa: BLE001 - Docling raises many types for damaged / encrypted / oversized files
            log.warning("docling could not convert a %s file: %s", suffix, type(exc).__name__)
            raise AppError(422, "Document could not be parsed", "The file is damaged, protected, or too large.") from exc
    chunks = blocks_to_chunks(docling_blocks(result.document), page_confidence=page_confidence(result))
    if not chunks:
        raise AppError(422, "No readable content", "No text, table or captioned figure could be read from this file.")
    return chunks
