"""Structured-data questions over spreadsheets/CSV with computation (FR-R10).

Deterministic/offline: a CSV is parsed into a typed table and a *structured* query (filters, group-by,
one aggregate, sort, limit) is executed by plain Python. Nothing is ever passed to eval/exec/SQL, so a
question cannot run code. Results carry the computed table plus the source file name. Cells that could
be spreadsheet formulas are neutralised in output.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.errors import AppError

MAX_ROWS = 20_000
MAX_COLUMNS = 100
MAX_CHARS = 5_000_000
MAX_RESULT_ROWS = 500

AGG_OPS = {"sum", "avg", "min", "max", "count"}
FILTER_OPS = {"eq", "ne", "lt", "lte", "gt", "gte", "contains"}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass
class Table:
    source: str
    columns: list[str]
    rows: list[dict[str, Any]]
    types: dict[str, str] = field(default_factory=dict)


def _to_number(raw: str) -> float | None:
    try:
        return float(raw.strip().replace(",", ""))
    except ValueError:
        return None


def parse_table(text: str, *, source: str) -> Table:
    if not text or not text.strip():
        raise ValueError("table is empty")
    if len(text) > MAX_CHARS:
        raise ValueError("table is too large")
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration as exc:
        raise ValueError("table is empty") from exc
    if not header or any(not h for h in header) or len(set(header)) != len(header):
        raise ValueError("header must have unique non-empty column names")
    if len(header) > MAX_COLUMNS:
        raise ValueError("too many columns")
    raw_rows: list[list[str]] = []
    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue
        raw_rows.append(row)
        if len(raw_rows) > MAX_ROWS:
            raise ValueError("table has too many rows")
    types: dict[str, str] = {}
    for i, col in enumerate(header):
        cells = [r[i].strip() for r in raw_rows if i < len(r) and r[i].strip()]
        types[col] = "number" if cells and all(_to_number(c) is not None for c in cells) else "text"
    rows: list[dict[str, Any]] = []
    for r in raw_rows:
        rec: dict[str, Any] = {}
        for i, col in enumerate(header):
            cell = r[i].strip() if i < len(r) else ""
            if types[col] == "number":
                rec[col] = _to_number(cell) if cell else None
            else:
                rec[col] = cell if cell else None
        rows.append(rec)
    return Table(source=source, columns=header, rows=rows, types=types)


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _col(table: Table, name: Any) -> str:
    if not isinstance(name, str) or name not in table.columns:
        raise ValueError("unknown column")
    return name


def _match(value: Any, op: str, target: Any, numeric: bool) -> bool:
    if value is None:
        return False
    if op == "contains":
        return str(target).lower() in str(value).lower()
    if numeric:
        try:
            target = float(target)
        except (TypeError, ValueError) as exc:
            raise ValueError("numeric filter needs a number") from exc
    else:
        target = str(target)
        value = str(value)
    return {
        "eq": value == target, "ne": value != target, "lt": value < target,
        "lte": value <= target, "gt": value > target, "gte": value >= target,
    }[op]


def _aggregate(values: list[Any], op: str, n_rows: int) -> float | int | None:
    if op == "count":
        return n_rows
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    if op == "sum":
        return float(sum(nums))
    if op == "avg":
        return float(sum(nums)) / len(nums)
    return float(min(nums) if op == "min" else max(nums))


def run_query(table: Table, query: dict[str, Any]) -> dict[str, Any]:
    agg = query.get("aggregate")
    if not isinstance(agg, dict):
        raise ValueError("aggregate is required")
    op = agg.get("op")
    if op not in AGG_OPS:
        raise ValueError("unsupported aggregate")
    agg_col: str | None = None
    if op != "count":
        agg_col = _col(table, agg.get("column"))
        if table.types[agg_col] != "number":
            raise ValueError("aggregate column must be numeric")
    elif agg.get("column") is not None:
        agg_col = _col(table, agg.get("column"))
    group_by = [_col(table, c) for c in (query.get("group_by") or [])]

    rows = table.rows
    for f in query.get("filters") or []:
        if not isinstance(f, dict) or f.get("op") not in FILTER_OPS:
            raise ValueError("unsupported filter")
        fc = _col(table, f.get("column"))
        numeric = table.types[fc] == "number" and f["op"] != "contains"
        rows = [r for r in rows if _match(r[fc], f["op"], f.get("value"), numeric)]

    label = f"{op}_{agg_col}" if agg_col else op
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(tuple(r[c] for c in group_by), []).append(r)
    if not group_by and not groups:
        groups[()] = []
    out = []
    for key, members in groups.items():
        value = _aggregate([m[agg_col] for m in members] if agg_col else [], op, len(members))
        out.append([*key, value])
    sort = query.get("sort")
    if sort in ("asc", "desc"):
        out.sort(key=lambda r: (r[-1] is None, r[-1] if r[-1] is not None else 0), reverse=sort == "desc")
        if sort == "desc":
            out.sort(key=lambda r: r[-1] is None)  # keep blanks last
    elif group_by:
        out.sort(key=lambda r: tuple("" if v is None else str(v) for v in r[:-1]))
    limit = query.get("limit")
    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        out = out[:limit]
    out = out[:MAX_RESULT_ROWS]
    return {
        "source": table.source,
        "columns": [*group_by, label],
        "rows": [[_safe_cell(c) for c in r] for r in out],
        "row_count_used": len(rows),
    }


def compare_groups(table: Table, *, column: str, a: str, b: str, metric: dict[str, Any]) -> dict[str, Any]:
    res = run_query(table, {"group_by": [column], "aggregate": metric})
    values = {str(r[0]): r[1] for r in res["rows"]}
    va = float(values.get(a) or 0.0)
    vb = float(values.get(b) or 0.0)
    return {
        "source": table.source, "column": column, "a_label": _safe_cell(a), "b_label": _safe_cell(b),
        "a": va, "b": vb, "difference": va - vb, "ratio": (va / vb) if vb else None,
    }


class FilterIn(BaseModel):
    column: str
    op: str
    value: Any = None


class AggregateIn(BaseModel):
    op: str
    column: str | None = None


class TableQueryIn(BaseModel):
    csv_text: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=200)
    aggregate: AggregateIn
    group_by: list[str] = []
    filters: list[FilterIn] = []
    sort: str | None = None
    limit: int | None = None


router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.post("/table-query")
async def table_query_api(body: TableQueryIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-R10: compute an answer over a CSV table; returns the computed table and the source file."""
    require_scope(sess, "chat")
    try:
        table = parse_table(body.csv_text, source=body.source)
        return run_query(table, body.model_dump(exclude={"csv_text", "source"}))
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
