"""FR-D4 Complete selectable chunking modes: recursive, semantic, parent-child."""

import pytest

from e2eai.chunking import (
    parent_child_chunk,
    recursive_chunk,
    semantic_chunk,
    select_chunker,
)
from e2eai.ingest import ParsedChunk


def test_recursive_chunk_fixed_size_with_overlap():
    text = "abcdef"
    out = recursive_chunk(text, chunk_size=3, chunk_overlap=1)
    assert out == ["abc", "cde", "ef"]
    assert recursive_chunk("", chunk_size=4) == []
    with pytest.raises(ValueError):
        recursive_chunk("x", chunk_size=0)


def test_semantic_chunk_merges_same_section_children():
    chunks = [
        ParsedChunk(text="first", page=1, section_path="S1", kind="text"),
        ParsedChunk(text="second", page=1, section_path="S1", kind="text"),
        ParsedChunk(text="third", page=2, section_path="S2", kind="text"),
    ]
    parents = semantic_chunk(chunks, max_chars=100)
    assert len(parents) == 2
    assert parents[0].text == "first\nsecond"
    assert parents[1].text == "third"
    assert parents[1].section_path == "S2"


def test_semantic_chunk_splits_when_max_chars_exceeded():
    big = "x" * 80
    chunks = [
        ParsedChunk(text=big, page=1, section_path="S1", kind="text"),
        ParsedChunk(text=big, page=1, section_path="S1", kind="text"),
    ]
    parents = semantic_chunk(chunks, max_chars=100)
    assert len(parents) == 2
    assert parents[0].text == big


def test_parent_child_chunk_emits_pairs():
    chunks = [
        ParsedChunk(text="alpha", page=1, section_path="S1", kind="text"),
        ParsedChunk(text="beta", page=1, section_path="S1", kind="text"),
        ParsedChunk(text="gamma", page=2, section_path="S2", kind="text"),
    ]
    parents, children = parent_child_chunk(chunks, max_parent_chars=1000)
    assert children == chunks
    assert len(parents) == 2
    assert parents[0].kind == "parent"
    assert parents[0].text == "alpha beta"
    assert parents[1].text == "gamma"


def test_select_chunker_structure_aware_returns_bytes_parser():
    parser = select_chunker("structure-aware")
    assert parser(b"heading\n\ntext", mime="text/plain")


def test_select_chunker_recursive_parses_bytes():
    parser = select_chunker("recursive")
    out = parser(b"hello world ", mime="text/plain")
    assert isinstance(out, list)


def test_select_chunker_semantic_parses_bytes():
    parser = select_chunker("semantic")
    out = parser(b"section one\nsection two", mime="text/plain")
    assert isinstance(out, list)
    assert len(out) >= 1


def test_select_chunker_parent_child_parses_bytes():
    parser = select_chunker("parent-child")
    out = parser(b"parent content", mime="text/plain")
    assert isinstance(out, list)


def test_select_chunker_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Unknown chunking mode"):
        select_chunker("nope")
