from dataclasses import dataclass
from typing import Any


MAX_INLINE_VISUALIZATION_ROWS = 100
MAX_INLINE_VISUALIZATION_SERIES = 8


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


def prepare_inline_visualization(payload: dict[str, Any]) -> PreparedVisualization:
    if payload.get("version") != 1:
        raise ValueError("Visualization version must be 1")

    visualization_type = str(payload.get("type") or "").strip().lower()
    if visualization_type not in {"table", "bar", "line", "scatter"}:
        raise ValueError(f"Unsupported visualization type: {visualization_type or 'missing'}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Visualization data must be an object")

    columns = data.get("columns")
    rows = data.get("rows")
    if not isinstance(columns, list) or not columns:
        raise ValueError("Visualization data.columns must be a non-empty list")
    if len(columns) > 64 or not all(isinstance(column, str) for column in columns):
        raise ValueError("Visualization data.columns contains invalid values")

    normalized_columns = [column.strip() for column in columns]
    if any(not column for column in normalized_columns):
        raise ValueError("Visualization columns must be non-empty")
    if len(set(normalized_columns)) != len(normalized_columns):
        raise ValueError("Visualization columns must be unique")

    if not isinstance(rows, list) or not rows:
        raise ValueError("Visualization data.rows must be a non-empty list")
    if len(rows) > MAX_INLINE_VISUALIZATION_ROWS:
        raise ValueError(
            f"Visualization cannot contain more than {MAX_INLINE_VISUALIZATION_ROWS} rows"
        )
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Visualization rows must be objects")

    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        missing = [column for column in normalized_columns if column not in row]
        if missing:
            raise ValueError(f"Visualization row {index} is missing columns: {missing}")
        normalized_rows.append({column: row[column] for column in normalized_columns})

    title = _optional_text(payload.get("title"))
    x_label = _optional_text(payload.get("x_label"))
    y_label = _optional_text(payload.get("y_label"))

    if visualization_type == "table":
        return PreparedVisualization(
            type="table",
            title=title,
            rows=tuple(normalized_rows),
            x_label=x_label,
            y_label=y_label,
        )

    x = _required_text(payload.get("x"), "x")
    if x not in normalized_columns:
        raise ValueError(f"Visualization x field {x!r} does not exist in data")

    y = _normalize_y(payload.get("y"))
    if not y:
        raise ValueError("Chart visualization requires at least one y field")
    if len(y) > MAX_INLINE_VISUALIZATION_SERIES:
        raise ValueError(
            f"Visualization cannot contain more than {MAX_INLINE_VISUALIZATION_SERIES} series"
        )
    missing_y = [field for field in y if field not in normalized_columns]
    if missing_y:
        raise ValueError(f"Visualization y fields do not exist in data: {missing_y}")

    hue = _optional_text(payload.get("hue"))
    if hue is not None and hue not in normalized_columns:
        raise ValueError(f"Visualization hue field {hue!r} does not exist in data")
    if hue is not None and len(y) > 1:
        raise ValueError("Multiple y series cannot be combined with hue")

    orientation = str(payload.get("orientation") or "vertical").strip().lower()
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("Visualization orientation must be vertical or horizontal")
    if orientation == "horizontal" and visualization_type != "bar":
        raise ValueError("Horizontal orientation is supported only for bar visualizations")

    if visualization_type == "scatter" and len(y) != 1:
        raise ValueError("Scatter visualization requires exactly one y field")

    for field in y:
        _require_numeric_column(normalized_rows, field)
    if visualization_type == "scatter":
        _require_numeric_column(normalized_rows, x)

    if visualization_type in {"bar", "line"}:
        grain = [x, *([hue] if hue is not None else [])]
        _require_unique_grain(normalized_rows, grain)

    return PreparedVisualization(
        type=visualization_type,
        title=title,
        rows=tuple(normalized_rows),
        x=x,
        y=tuple(y),
        hue=hue,
        x_label=x_label,
        y_label=y_label,
        orientation=orientation,
    )


def prepare_visualization(result: dict[str, Any] | None) -> PreparedVisualization | None:
    """Backward-compatible parser for the original result visualization contract."""
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

    title = _optional_text(raw.get("title"))
    if visualization_type == "table":
        return PreparedVisualization(type="table", title=title, rows=rows)

    x = _optional_text(raw.get("x"))
    raw_y = raw.get("y")
    y = tuple(_normalize_y(raw_y))
    columns = set(rows[0])
    if x is None or x not in columns or not y or any(field not in columns for field in y):
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


def _normalize_y(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _required_text(value: Any, field: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"Visualization requires a non-empty {field} field")
    return normalized


def _require_numeric_column(rows: list[dict[str, Any]], field: str) -> None:
    found_numeric = False
    for row in rows:
        value = row[field]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Visualization field {field!r} must contain numeric values")
        found_numeric = True
    if not found_numeric:
        raise ValueError(f"Visualization field {field!r} has no numeric values")


def _require_unique_grain(rows: list[dict[str, Any]], fields: list[str]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row[field] for field in fields)
        try:
            if key in seen:
                names = ", ".join(fields)
                raise ValueError(
                    "Chart data must already be aggregated to the presentation grain; "
                    f"duplicate values were found for {names}"
                )
            seen.add(key)
        except TypeError as exc:
            raise ValueError("Chart grouping fields must contain scalar values") from exc
