"""FR-R10 structured-data questions over spreadsheets/CSV with computation.

Deterministic/offline: a CSV table is parsed, a structured query (filter / group-by / aggregate / compare)
is executed by plain code (never eval), and the result carries the computed table plus the source file.
"""

import pytest

CSV = (
    "region,product,units,price\n"
    "north,apple,10,2.5\n"
    "north,pear,4,3.0\n"
    "south,apple,7,2.5\n"
    "south,pear,,3.0\n"
    "east,apple,1,2.5\n"
)


def test_parse_table_infers_numeric_columns_and_blanks():
    from e2eai.table_qa import parse_table

    t = parse_table(CSV, source="sales.csv")
    assert t.columns == ["region", "product", "units", "price"]
    assert t.types == {"region": "text", "product": "text", "units": "number", "price": "number"}
    assert len(t.rows) == 5 and t.rows[3]["units"] is None and t.rows[0]["units"] == 10.0
    with pytest.raises(ValueError):
        parse_table("", source="x.csv")


def test_total_with_filter_and_source():
    from e2eai.table_qa import parse_table, run_query

    t = parse_table(CSV, source="sales.csv")
    res = run_query(t, {"aggregate": {"op": "sum", "column": "units"}, "filters": [{"column": "product", "op": "eq", "value": "apple"}]})
    assert res["source"] == "sales.csv"
    assert res["columns"] == ["sum_units"] and res["rows"] == [[18.0]]
    assert res["row_count_used"] == 3


def test_group_by_avg_count_sorted_and_limited():
    from e2eai.table_qa import parse_table, run_query

    t = parse_table(CSV, source="sales.csv")
    res = run_query(t, {"group_by": ["region"], "aggregate": {"op": "sum", "column": "units"}, "sort": "desc", "limit": 2})
    assert res["columns"] == ["region", "sum_units"]
    assert res["rows"] == [["north", 14.0], ["south", 7.0]]
    cnt = run_query(t, {"group_by": ["product"], "aggregate": {"op": "count"}})
    assert dict((r[0], r[1]) for r in cnt["rows"]) == {"apple": 3, "pear": 2}
    avg = run_query(t, {"aggregate": {"op": "avg", "column": "units"}})
    assert avg["rows"] == [[5.5]]  # blanks are ignored, not treated as zero


def test_numeric_filters_and_min_max():
    from e2eai.table_qa import parse_table, run_query

    t = parse_table(CSV, source="sales.csv")
    res = run_query(t, {"aggregate": {"op": "max", "column": "units"}, "filters": [{"column": "units", "op": "lt", "value": 10}]})
    assert res["rows"] == [[7.0]]
    mn = run_query(t, {"aggregate": {"op": "min", "column": "price"}})
    assert mn["rows"] == [[2.5]]


def test_compare_two_groups():
    from e2eai.table_qa import compare_groups, parse_table

    t = parse_table(CSV, source="sales.csv")
    res = compare_groups(t, column="region", a="north", b="south", metric={"op": "sum", "column": "units"})
    assert res["a"] == 14.0 and res["b"] == 7.0 and res["difference"] == 7.0 and res["ratio"] == 2.0
    assert res["source"] == "sales.csv"
    zero = compare_groups(t, column="region", a="north", b="nowhere", metric={"op": "sum", "column": "units"})
    assert zero["b"] == 0.0 and zero["ratio"] is None


def test_invalid_queries_are_rejected():
    from e2eai.table_qa import parse_table, run_query

    t = parse_table(CSV, source="sales.csv")
    for bad in (
        {"aggregate": {"op": "sum", "column": "nope"}},
        {"aggregate": {"op": "sum", "column": "region"}},  # non-numeric
        {"aggregate": {"op": "eval", "column": "units"}},
        {"aggregate": {"op": "count"}, "filters": [{"column": "region", "op": "regex", "value": "x"}]},
        {"group_by": ["nope"], "aggregate": {"op": "count"}},
        {},
    ):
        with pytest.raises(ValueError):
            run_query(t, bad)


def test_formula_injection_cells_are_neutralized_in_output():
    from e2eai.table_qa import parse_table, run_query

    t = parse_table("name,amt\n=HYPERLINK(\"x\"),1\n+cmd,2\n", source="evil.csv")
    res = run_query(t, {"group_by": ["name"], "aggregate": {"op": "sum", "column": "amt"}})
    assert all(not str(r[0]).startswith(("=", "+", "-", "@")) for r in res["rows"])


def test_size_limits_and_route_wired():
    from e2eai.main import app
    from e2eai.table_qa import MAX_ROWS, parse_table

    with pytest.raises(ValueError):
        parse_table("a\n" + "1\n" * (MAX_ROWS + 1), source="big.csv")
    assert "post" in app.openapi()["paths"]["/api/v1/data/table-query"]
