"""FR-D4 Complete selectable chunking modes: recursive, semantic, parent-child."""

from collections import deque
from collections.abc import Callable, Sequence

from .ingest import ParsedChunk, TextMarkdownParser


def _text_chunks(chunks: Sequence[ParsedChunk]) -> list[ParsedChunk]:
    return [b for b in chunks if b.kind in ("text", "heading", "vlm")]


def recursive_chunk(text: str, *, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Fixed-size recursive chunking with overlap."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not text:
        return []
    overlap = min(chunk_overlap, chunk_size - 1) if chunk_overlap >= chunk_size else chunk_overlap
    step = max(1, chunk_size - overlap)
    return [text[i : i + chunk_size] for i in range(0, len(text), step)]


def semantic_chunk(chunks: Sequence[ParsedChunk], *, max_chars: int = 1500) -> list[ParsedChunk]:
    """Group structure-aware chunks into parent/child semantic units.

    Parent chunks hold the full section content; child chunks are the original sections. This keeps
    whole sections retrievable while allowing fine-grained citation at the child level.
    """
    parents: list[ParsedChunk] = []
    for child in _text_chunks(chunks):
        if not parents:
            parents.append(child)
        else:
            parent = parents[-1]
            combined_len = len(parent.text) + 1 + len(child.text)
            same_section = parent.section_path == child.section_path
            if same_section and len(parent.text) + 1 + len(child.text) <= max_chars:
                parents[-1] = ParsedChunk(
                    text=parent.text + "\n" + child.text,
                    page=parent.page,
                    section_path=parent.section_path,
                    kind=parent.kind,
                )
            else:
                parents.append(child)
    return parents


def parent_child_chunk(chunks: Sequence[ParsedChunk], *, max_parent_chars: int = 2000) -> tuple[list[ParsedChunk], list[ParsedChunk]]:
    """Emit explicit parent (summary) and child (source sections) chunk pairs."""
    parents: list[ParsedChunk] = []
    children: list[ParsedChunk] = []
    buffer: deque[ParsedChunk] = deque()

    def flush() -> None:
        if not buffer:
            return
        children.extend(buffer)
        summary = " ".join(c.text for c in buffer)
        parents.append(ParsedChunk(
            text=summary[:max_parent_chars],
            page=buffer[0].page,
            section_path=buffer[0].section_path,
            kind="parent",
        ))
        buffer.clear()

    for chunk in _text_chunks(chunks):
        if not buffer:
            buffer.append(chunk)
            continue
        parent_text = " ".join(c.text for c in buffer)
        projected = len(parent_text) + 1 + len(chunk.text)
        if chunk.section_path == buffer[-1].section_path and projected <= max_parent_chars:
            buffer.append(chunk)
        else:
            flush()
            buffer.append(chunk)
    flush()
    return parents, children


def select_chunker(mode: str) -> Callable:
    """Return the chunking callable for a configured mode (FR-D4)."""
    table: dict[str, Callable] = {
        "structure-aware": lambda data, mime="text/plain": TextMarkdownParser().parse(data, mime=mime),
        "recursive": _recursive_wrapper,
        "semantic": _semantic_wrapper,
        "parent-child": _parent_child_wrapper,
    }
    if mode not in table:
        raise ValueError(f"Unknown chunking mode: {mode}")
    return table[mode]


def _recursive_wrapper(data: bytes, *, mime: str = "text/plain") -> list[ParsedChunk]:
    chunks = TextMarkdownParser().parse(data, mime=mime)
    out: list[ParsedChunk] = []
    for chunk in _text_chunks(chunks):
        for piece in recursive_chunk(chunk.text):
            out.append(ParsedChunk(text=piece, page=chunk.page, section_path=chunk.section_path, kind=chunk.kind))
    return out


def _semantic_wrapper(data: bytes, *, mime: str = "text/plain") -> list[ParsedChunk]:
    chunks = TextMarkdownParser().parse(data, mime=mime)
    return semantic_chunk(chunks)


def _parent_child_wrapper(data: bytes, *, mime: str = "text/plain") -> list[ParsedChunk]:
    chunks = TextMarkdownParser().parse(data, mime=mime)
    parents, children = parent_child_chunk(chunks)
    return parents + children
