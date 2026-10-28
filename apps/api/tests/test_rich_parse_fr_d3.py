"""FR-D3: layout-aware parsing keeps headings, page anchors and tables. Pure logic: no Docling needed here;
`docling_blocks` is exercised with objects shaped like a DoclingDocument (the real library is tested in workers/)."""

from types import SimpleNamespace as NS

from e2eai.rich_parse import Block, blocks_to_chunks, docling_blocks


def H(text, level=1, page=1):
    return Block("heading", text, page, level=level)


def T(text, page=1):
    return Block("text", text, page)


def TABLE(rows, page=1, caption=""):
    return Block("table", "", page, rows=rows, caption=caption)


# --- blocks -> chunks ----------------------------------------------------------------------------------

def test_headings_form_the_section_path_and_text_stays_under_its_heading():
    chunks = blocks_to_chunks([H("Contract", 1), T("Intro."), H("Revenue share", 2), T("70/30 split."), H("Term", 2), T("Two years.")])
    assert [(c.section_path, c.text) for c in chunks] == [
        ("Contract", "Intro."), ("Contract > Revenue share", "70/30 split."), ("Contract > Term", "Two years.")]


def test_a_new_top_level_heading_replaces_the_whole_trail():
    chunks = blocks_to_chunks([H("A", 1), H("A1", 2), T("x"), H("B", 1), T("y")])
    assert [(c.text, c.section_path) for c in chunks] == [("A", ""), ("x", "A > A1"), ("y", "B")]


def test_a_heading_with_no_body_is_kept_as_its_own_small_chunk():
    chunks = blocks_to_chunks([H("Partnership Agreement", 0), H("1. Revenue share", 1), T("70/30.")])
    assert [(c.text, c.section_path) for c in chunks] == [
        ("Partnership Agreement", ""), ("70/30.", "Partnership Agreement > 1. Revenue share")]


def test_a_document_made_only_of_headings_is_not_empty():
    # A scanned form read by OCR often comes back as large "headings" only: that is still real content.
    chunks = blocks_to_chunks([H("Invoice number 20481", 1, page=1), H("Total payable 1500 dollars", 1, page=1)])
    assert [c.text for c in chunks] == ["Invoice number 20481", "Total payable 1500 dollars"]
    assert all(c.kind == "text" and c.page == 1 for c in chunks)


def test_a_heading_followed_by_a_table_or_figure_is_not_duplicated_as_text():
    chunks = blocks_to_chunks([H("Specs"), TABLE([["a"], ["1"]])])
    assert [c.kind for c in chunks] == ["table"]


def test_consecutive_paragraphs_merge_until_the_size_limit_and_never_cross_a_page():
    chunks = blocks_to_chunks([T("a" * 400, 1), T("b" * 400, 1), T("c" * 400, 1), T("d" * 100, 2)], max_chars=1000)
    assert [(c.page, len(c.text)) for c in chunks] == [(1, 802), (1, 400), (2, 100)]  # "a..\n\nb.." merged = 802 chars


def test_the_page_anchor_is_the_page_of_the_first_block_in_the_chunk():
    chunks = blocks_to_chunks([T("on page three", 3), T("also three", 3)])
    assert len(chunks) == 1 and chunks[0].page == 3


def test_one_oversized_paragraph_is_split_on_word_boundaries():
    words = " ".join(f"word{i}" for i in range(800))
    chunks = blocks_to_chunks([T(words)], max_chars=500)
    assert len(chunks) > 1 and all(len(c.text) <= 500 for c in chunks)
    assert " ".join(c.text for c in chunks).split() == words.split()  # nothing lost, nothing cut mid-word


def test_tables_become_their_own_structured_chunk_with_page_and_section():
    chunks = blocks_to_chunks([H("Specs"), T("Intro."), TABLE([["Part", "Torque"], ["Bolt A", "12 Nm"]], page=2, caption="Table 4-2")])
    table = chunks[-1]
    assert table.kind == "table" and table.page == 2 and table.section_path == "Specs"
    assert "Table 4-2" in table.text and "| Part | Torque |" in table.text and "| Bolt A | 12 Nm |" in table.text
    assert table.table_json == {"caption": "Table 4-2", "rows": [["Part", "Torque"], ["Bolt A", "12 Nm"]]}


def test_a_long_table_is_split_by_rows_and_every_part_repeats_the_header():
    rows = [["id", "value"]] + [[str(i), f"v{i}"] for i in range(70)]
    parts = [c for c in blocks_to_chunks([TABLE(rows)], table_rows_per_chunk=25) if c.kind == "table"]
    assert len(parts) == 3
    assert all("| id | value |" in c.text for c in parts)
    assert sum(len(c.table_json["rows"]) - 1 for c in parts) == 70


def test_a_table_cell_with_pipes_or_newlines_cannot_break_the_markdown_row():
    (table,) = blocks_to_chunks([TABLE([["a", "b"], ["x|y", "line1\nline2"]])])
    row = table.text.splitlines()[-1]
    assert row.replace("\\|", "").count("|") == 3  # only the 3 real column borders remain unescaped
    assert "x\\|y" in row and "line1 line2" in row


def test_figures_with_a_caption_are_indexed_by_that_caption_and_uncaptioned_ones_are_skipped():
    chunks = blocks_to_chunks([T("Before."), Block("figure", "Figure 3: bearing exploded view", 4), Block("figure", "", 5)])
    figs = [c for c in chunks if c.kind == "figure"]
    assert len(figs) == 1 and figs[0].page == 4 and "bearing exploded view" in figs[0].text


def test_page_headers_footers_and_empty_blocks_are_noise():
    chunks = blocks_to_chunks([Block("noise", "Page 1 of 9", 1), T("   "), T("Real content.")])
    assert [c.text for c in chunks] == ["Real content."]


def test_an_empty_document_yields_no_chunks():
    assert blocks_to_chunks([]) == []


def test_page_confidence_is_carried_onto_each_chunk():
    chunks = blocks_to_chunks([T("scan text", 1), T("clean text", 2)], page_confidence={1: 0.4, 2: 0.95})
    assert [c.confidence for c in chunks] == [0.4, 0.95]


# --- DoclingDocument -> blocks (duck-typed) ----------------------------------------------------------------

def _item(label, text="", page=1, level=None, caption="", rows=None):
    obj = NS(label=NS(value=label), text=text, prov=[NS(page_no=page)], level=level)
    obj.caption_text = lambda doc: caption
    if rows is not None:
        obj.export_to_dataframe = lambda doc=None: NS(columns=rows[0], values=[r for r in rows[1:]])
    return obj


def test_docling_items_map_to_headings_text_tables_and_figures():
    doc = NS(iterate_items=lambda: iter([
        (_item("title", "Partnership Agreement", level=0), 0),
        (_item("section_header", "Revenue", level=1), 1),
        (_item("text", "70/30.", page=2), 2),
        (_item("list_item", "net of fees", page=2), 2),
        (_item("table", page=3, caption="Table 1", rows=[["a", "b"], ["1", "2"]]), 2),
        (_item("picture", page=3, caption="Figure 1"), 2),
        (_item("page_footer", "7", page=3), 2),
    ]))
    blocks = docling_blocks(doc)
    assert [(b.kind, b.text or b.caption, b.page) for b in blocks] == [
        ("heading", "Partnership Agreement", 1), ("heading", "Revenue", 1), ("text", "70/30.", 2), ("text", "net of fees", 2),
        ("table", "Table 1", 3), ("figure", "Figure 1", 3), ("noise", "7", 3)]
    assert blocks[0].level == 0 and blocks[1].level == 1
    assert blocks[4].rows == [["a", "b"], ["1", "2"]]


def test_an_item_without_provenance_falls_back_to_the_previous_page():
    nopage = NS(label=NS(value="text"), text="orphan", prov=[], level=None, caption_text=lambda d: "")
    doc = NS(iterate_items=lambda: iter([(_item("text", "first", page=4), 0), (nopage, 0)]))
    assert [b.page for b in docling_blocks(doc)] == [4, 4]


# --- file type from the bytes (browsers often send application/octet-stream) -----------------------------------

import io
import zipfile

import pytest

from e2eai.rich_parse import sniff_suffix


def _zip(*names):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, "x")
    return buf.getvalue()


@pytest.mark.parametrize("data,mime,expected", [
    (b"%PDF-1.7\n...", "application/octet-stream", ".pdf"),
    (_zip("[Content_Types].xml", "word/document.xml"), "application/octet-stream", ".docx"),
    (_zip("[Content_Types].xml", "ppt/presentation.xml"), "", ".pptx"),
    (_zip("[Content_Types].xml", "xl/workbook.xml"), "application/zip", ".xlsx"),
    (b"\x89PNG\r\n\x1a\n....", "application/octet-stream", ".png"),
    (b"\xff\xd8\xff\xe0....", "application/octet-stream", ".jpg"),
    (b"II*\x00....", "application/octet-stream", ".tiff"),
    (b"%PDF-1.4", "application/pdf", ".pdf"),
    (b"anything", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),  # declared type wins when known
])
def test_file_type_is_detected_from_the_declared_type_or_the_bytes(data, mime, expected):
    assert sniff_suffix(data, mime) == expected


@pytest.mark.parametrize("data", [b"random bytes", b"", _zip("something/else.txt"), b"PK\x03\x04 broken zip"])
def test_unknown_or_broken_files_are_not_guessed(data):
    assert sniff_suffix(data, "application/octet-stream") is None
