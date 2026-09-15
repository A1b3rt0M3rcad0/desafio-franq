from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PreparedVisualization:
    type: str
    title: str | None
    rows: tuple[dict[str, Any], ...]
    x: str | None = None
    y: tuple[str, ...] = ()


def prepare_visualization(result: dict[str, Any] | None) -> PreparedVisualization | None:
    if not result:
        return None

    rows = tuple(extract_rows(result))
    if not rows:
        return None

    raw = result.get("visualization")
    if not isinstance(raw, dict):
        return PreparedVisualization(type="table", title=None, rows=rows)

    visualization_type = str(raw.get("type") or "table").strip().lower()
    if visualization_type == "none":
        return None
    if visualization_type not in {"table", "bar", "line", "scatter"}:
        visualization_type = "table"

    title = str(raw["title"]).strip() if raw.get("title") else None
    if visualization_type == "table":
        return PreparedVisualization(type="table", title=title, rows=rows)

    x = raw.get("x")
    if not isinstance(x, str) or not x.strip():
        return PreparedVisualization(type="table", title=title, rows=rows)
    x = x.strip()

    raw_y = raw.get("y")
    if isinstance(raw_y, str):
        y = (raw_y.strip(),) if raw_y.strip() else ()
    elif isinstance(raw_y, list):
        y = tuple(str(item).strip() for item in raw_y if str(item).strip())
    else:
        y = ()

    columns = set(rows[0])
    if x not in columns or not y or any(column not in columns for column in y):
        return PreparedVisualization(type="table", title=title, rows=rows)

    if visualization_type == "scatter" and len(y) > 1:
        y = (y[0],)

    return PreparedVisualization(
        type=visualization_type,
        title=title,
        rows=rows,
        x=x,
        y=y,
    )


def extract_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [result.get("data"), result]
    for candidate in candidates:
        rows = _rows_from_candidate(candidate)
        if rows:
            return rows
    return []


def _rows_from_candidate(candidate: Any) -> list[dict[str, Any]]:
    if isinstance(candidate, list):
        return _normalize_mapping_rows(candidate)
    if not isinstance(candidate, dict):
        return []

    rows = candidate.get("rows")
    columns = candidate.get("columns")
    if not isinstance(rows, list):
        return []

    normalized = _normalize_mapping_rows(rows)
    if normalized:
        return normalized

    if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != len(columns):
            return []
        result.append(dict(zip(columns, row, strict=True)))
    return result


def _normalize_mapping_rows(rows: list[Any]) -> list[dict[str, Any]]:
    if not rows or not all(isinstance(row, dict) for row in rows):
        return []
    return [dict(row) for row in rows]
