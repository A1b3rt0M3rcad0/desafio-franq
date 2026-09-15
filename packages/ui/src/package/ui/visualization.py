from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PreparedVisualization:
    type: str
    title: str | None
    rows: tuple[dict[str, Any], ...]
    x: str | None = None
    y: tuple[str, ...] = ()
    hue: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    orientation: str = "vertical"


def prepare_visualization(result: dict[str, Any] | None) -> PreparedVisualization | None:
    if not result:
        return None

    payload = _presentation_payload(result)
    rows = tuple(extract_rows(payload))
    if not rows:
        return None

    raw = payload.get("visualization")
    if not isinstance(raw, dict):
        return PreparedVisualization(type="table", title=None, rows=rows)

    visualization_type = str(raw.get("type") or "table").strip().lower()
    if visualization_type == "none":
        return None
    if visualization_type not in {"table", "bar", "line", "scatter"}:
        visualization_type = "table"

    title = _optional_text(raw.get("title"))
    x_label = _optional_text(raw.get("x_label"))
    y_label = _optional_text(raw.get("y_label"))

    if visualization_type == "table":
        return PreparedVisualization(
            type="table",
            title=title,
            rows=rows,
            x_label=x_label,
            y_label=y_label,
        )

    x = _optional_text(raw.get("x"))
    if x is None:
        return PreparedVisualization(type="table", title=title, rows=rows)

    raw_y = raw.get("y")
    if isinstance(raw_y, str):
        y = (raw_y.strip(),) if raw_y.strip() else ()
    elif isinstance(raw_y, list):
        y = tuple(str(item).strip() for item in raw_y if str(item).strip())
    else:
        y = ()

    hue = _optional_text(raw.get("hue"))
    orientation = str(raw.get("orientation") or "vertical").strip().lower()
    if orientation not in {"vertical", "horizontal"}:
        orientation = "vertical"
    if visualization_type != "bar":
        orientation = "vertical"

    required_columns = {x, *y}
    if hue is not None:
        required_columns.add(hue)
    if not y or any(any(column not in row for column in required_columns) for row in rows):
        return PreparedVisualization(type="table", title=title, rows=rows)

    if visualization_type == "scatter" and len(y) != 1:
        return PreparedVisualization(type="table", title=title, rows=rows)
    if hue is not None and len(y) > 1:
        return PreparedVisualization(type="table", title=title, rows=rows)

    if not all(_numeric_or_none(row[column]) for row in rows for column in y):
        return PreparedVisualization(type="table", title=title, rows=rows)
    if visualization_type == "scatter" and not all(
        _numeric_or_none(row[x]) for row in rows
    ):
        return PreparedVisualization(type="table", title=title, rows=rows)

    return PreparedVisualization(
        type=visualization_type,
        title=title,
        rows=rows,
        x=x,
        y=y,
        hue=hue,
        x_label=x_label,
        y_label=y_label,
        orientation=orientation,
    )


def extract_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _presentation_payload(result)
    candidates = [payload.get("data"), payload]
    for candidate in candidates:
        rows = _rows_from_candidate(candidate)
        if rows:
            return rows
    return []


def _presentation_payload(result: dict[str, Any]) -> dict[str, Any]:
    presentation = result.get("presentation")
    if isinstance(presentation, dict):
        return presentation
    return result


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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _numeric_or_none(value: Any) -> bool:
    return value is None or (
        not isinstance(value, bool) and isinstance(value, (int, float))
    )
