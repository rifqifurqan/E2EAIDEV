"""Layout-aware parsing for rich documents (FR-D3): headings, page anchors, tables and figure captions.

Two small, pure steps, so the logic is testable without Docling:
  docling_blocks(document)  - a DoclingDocument (duck-typed) -> ordered `Block`s
  blocks_to_chunks(blocks)  - blocks -> `ParsedChunk`s that ingest stores and indexes
Citations need an honest page, so a chunk never spans two pages; the anchor is the page of its first block.
"""

from dataclasses import dataclass

from .ingest import ParsedChunk

MAX_CHARS = 1200
TABLE_ROWS_PER_CHUNK = 25
_TEXT_LABELS = {"text", "paragraph", "list_item", "footnote", "code", "formula", "reference", "checkbox_selected", "checkbox_unselected"}
_NOISE_LABELS = {"page_header", "page_footer"}


@dataclass(frozen=True)
class Block:
    kind: str                            # heading | text | table | figure | noise
    text: str                            # heading / paragraph text, or a figure's caption
    page: int
    level: int = 1                       # headings only; a document title is 0
    rows: list[list[str]] | None = None  # tables only; the first row is the header
    caption: str = ""                    # tables only


# --- DoclingDocument -> blocks ------------------------------------------------------------------------------------

def _label(item) -> str:
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label))


def _table_rows(item, document) -> list[list[str]]:
    frame = item.export_to_dataframe(document)
    columns = list(frame.columns)
    header_is_real = not all(isinstance(c, int) for c in columns)  # no detected header -> integer columns 0..n-1
    body = [[str(cell) for cell in row] for row in frame.values]
    return ([[str(c) for c in columns]] if header_is_real else []) + body


def docling_blocks(document) -> list[Block]:
    blocks: list[Block] = []
    last_page = 1
    for item, _depth in document.iterate_items():
        label = _label(item)
        prov = getattr(item, "prov", None) or []
        page = prov[0].page_no if prov else last_page  # an item without provenance stays on the previous page
        last_page = page
        text = (getattr(item, "text", "") or "").strip()
        if label == "title":
            blocks.append(Block("heading", text, page, level=0))
        elif label == "section_header":
            blocks.append(Block("heading", text, page, level=max(1, int(getattr(item, "level", 1) or 1))))
        elif label == "table":
            blocks.append(Block("table", "", page, rows=_table_rows(item, document), caption=(item.caption_text(document) or "").strip()))
        elif label == "picture":
            blocks.append(Block("figure", (item.caption_text(document) or "").strip(), page))
        elif label in _NOISE_LABELS:
            blocks.append(Block("noise", text, page))
        elif label in _TEXT_LABELS:
            blocks.append(Block("text", text, page))
        # "caption" items are kept through their table / figure, not as free text
    return blocks


# --- blocks -> chunks --------------------------------------------------------------------------------------------

def _cell(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def _markdown(rows: list[list[str]], caption: str) -> str:
    width = max(len(r) for r in rows)
    padded = [list(r) + [""] * (width - len(r)) for r in rows]
    lines = [f"| {' | '.join(_cell(c) for c in padded[0])} |", f"| {' | '.join('---' for _ in padded[0])} |"]
    lines += [f"| {' | '.join(_cell(c) for c in r)} |" for r in padded[1:]]
    return (caption + "\n" if caption else "") + "\n".join(lines)


def _split_words(text: str, limit: int) -> list[str]:
    parts, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > limit:
            parts.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return parts + ([current] if current else [])


def blocks_to_chunks(
    blocks: list[Block], *, max_chars: int = MAX_CHARS, table_rows_per_chunk: int = TABLE_ROWS_PER_CHUNK,
    page_confidence: dict[int, float] | None = None,
) -> list[ParsedChunk]:
    confidence = page_confidence or {}
    chunks: list[ParsedChunk] = []
    trail: list[tuple[int, str]] = []
    buffer: list[str] = []
    size = 0
    buffer_page = 1

    def section() -> str:
        return " > ".join(title for _, title in trail)

    bare_heading: tuple[str, int, str] | None = None  # (title, page, parent path) of a heading with no body yet

    def flush() -> None:
        nonlocal size
        if buffer:
            chunks.append(ParsedChunk(text="\n\n".join(buffer), page=buffer_page, section_path=section(),
                                      confidence=confidence.get(buffer_page)))
        buffer.clear()
        size = 0

    def emit_bare_heading() -> None:
        """A heading nothing follows (a title, a scanned form's big text) is content too: keep it as a small chunk."""
        nonlocal bare_heading
        if bare_heading:
            title, page, parent = bare_heading
            chunks.append(ParsedChunk(text=title, page=page, section_path=parent, confidence=confidence.get(page)))
        bare_heading = None

    for b in blocks:
        if b.kind == "noise":
            continue
        if b.kind == "heading":
            flush()
            emit_bare_heading()
            while trail and trail[-1][0] >= b.level:
                trail.pop()
            if b.text:
                bare_heading = (b.text, b.page, section())
                trail.append((b.level, b.text))
        elif b.kind == "text":
            text = b.text.strip()
            if not text:
                continue
            bare_heading = None
            if buffer and b.page != buffer_page:
                flush()
            for piece in ([text] if len(text) <= max_chars else _split_words(text, max_chars)):
                if buffer and size + 2 + len(piece) > max_chars:
                    flush()
                if not buffer:
                    buffer_page = b.page
                size += len(piece) + (2 if buffer else 0)
                buffer.append(piece)
        elif b.kind == "table" and b.rows:
            flush()
            bare_heading = None
            header, body = b.rows[0], b.rows[1:]
            for start in range(0, max(len(body), 1), table_rows_per_chunk):
                rows = [header] + body[start:start + table_rows_per_chunk]
                chunks.append(ParsedChunk(text=_markdown(rows, b.caption), page=b.page, section_path=section(), kind="table",
                                          table_json={"caption": b.caption, "rows": rows}, confidence=confidence.get(b.page)))
        elif b.kind == "figure" and b.text:
            flush()
            bare_heading = None
            chunks.append(ParsedChunk(text=b.text, page=b.page, section_path=section(), kind="figure",
                                      confidence=confidence.get(b.page)))
    flush()
    emit_bare_heading()
    return chunks


# --- file type ---------------------------------------------------------------------------------------------------

_MIME_SUFFIX = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png", "image/jpeg": ".jpg", "image/tiff": ".tiff", "image/bmp": ".bmp", "image/webp": ".webp",
    "text/html": ".html",
}


def sniff_suffix(data: bytes, mime: str = "") -> str | None:
    """File extension Docling needs: from the declared type when it is a known one, else from the bytes.
    Browsers send application/octet-stream (or application/zip) for many real PDFs and Office files."""
    declared = _MIME_SUFFIX.get(mime.split(";")[0].strip().lower())
    if declared:
        return declared
    if data.startswith(b"%PDF"):
        return ".pdf"
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tiff"
    if data.startswith(b"PK\x03\x04"):
        import io
        import zipfile

        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return None
        for prefix, suffix in (("word/", ".docx"), ("ppt/", ".pptx"), ("xl/", ".xlsx")):
            if any(n.startswith(prefix) for n in names):
                return suffix
    return None
