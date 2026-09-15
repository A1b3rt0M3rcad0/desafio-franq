from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


VisualizationType = Literal["table", "bar", "line", "scatter"]
Orientation = Literal["vertical", "horizontal"]


class PresentationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(min_length=1, max_length=64)
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_rows(self) -> "PresentationData":
        normalized_columns = [column.strip() for column in self.columns]
        if any(not column for column in normalized_columns):
            raise ValueError("Presentation columns must be non-empty strings")
        if len(set(normalized_columns)) != len(normalized_columns):
            raise ValueError("Presentation columns must be unique")

        column_pairs = list(zip(self.columns, normalized_columns, strict=True))
        for index, row in enumerate(self.rows):
            missing = [
                normalized
                for raw, normalized in column_pairs
                if raw not in row and normalized not in row
            ]
            if missing:
                raise ValueError(
                    f"Presentation row {index} is missing declared columns: {missing}"
                )
        return self

    def normalized_rows(self) -> list[dict[str, Any]]:
        normalized_columns = [column.strip() for column in self.columns]
        column_pairs = list(zip(self.columns, normalized_columns, strict=True))
        normalized_rows: list[dict[str, Any]] = []
        for row in self.rows:
            normalized_rows.append(
                {
                    normalized: row[raw] if raw in row else row[normalized]
                    for raw, normalized in column_pairs
                }
            )
        return normalized_rows


class VisualizationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: VisualizationType
    title: str | None = None
    x: str | None = None
    y: list[str] = Field(default_factory=list, max_length=8)
    hue: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    orientation: Orientation = "vertical"


class PresentationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    data: PresentationData
    visualization: VisualizationSpec

    @model_validator(mode="after")
    def validate_visualization(self) -> "PresentationSpec":
        visualization = self.visualization
        columns = [column.strip() for column in self.data.columns]

        if visualization.type == "table":
            return self

        x = _normalized_required_name(visualization.x, "x")
        y = [_normalized_required_name(name, "y") for name in visualization.y]
        if not y:
            raise ValueError("Chart visualizations require at least one y field")

        _require_column(x, columns, "x")
        for field in y:
            _require_column(field, columns, "y")

        hue = None
        if visualization.hue is not None:
            hue = _normalized_required_name(visualization.hue, "hue")
            _require_column(hue, columns, "hue")

        if visualization.type == "scatter" and len(y) != 1:
            raise ValueError("Scatter visualizations require exactly one y field")
        if visualization.orientation == "horizontal" and visualization.type != "bar":
            raise ValueError("Horizontal orientation is supported only for bar visualizations")
        if hue is not None and len(y) > 1:
            raise ValueError("Multiple y series cannot be combined with hue")

        rows = self.data.normalized_rows()
        for field in y:
            _validate_numeric_column(rows, field)

        if visualization.type == "scatter":
            _validate_numeric_column(rows, x)

        if visualization.type in {"bar", "line"}:
            _validate_unique_grain(rows, [x, *([hue] if hue is not None else [])])

        return self

    def normalized(self) -> "PresentationSpec":
        visualization = self.visualization.model_copy(
            update={
                "x": self.visualization.x.strip() if self.visualization.x else None,
                "y": [field.strip() for field in self.visualization.y],
                "hue": self.visualization.hue.strip() if self.visualization.hue else None,
                "title": self.visualization.title.strip() if self.visualization.title else None,
                "x_label": (
                    self.visualization.x_label.strip() if self.visualization.x_label else None
                ),
                "y_label": (
                    self.visualization.y_label.strip() if self.visualization.y_label else None
                ),
            }
        )
        data = PresentationData(
            columns=[column.strip() for column in self.data.columns],
            rows=self.data.normalized_rows(),
        )
        return self.model_copy(update={"data": data, "visualization": visualization})


def _normalized_required_name(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"Chart visualizations require a non-empty {field_name} field")
    return value.strip()


def _require_column(field: str, columns: list[str], role: str) -> None:
    if field not in columns:
        raise ValueError(f"Visualization {role} field {field!r} does not exist in the data")


def _validate_numeric_column(rows: list[dict[str, Any]], field: str) -> None:
    has_numeric_value = False
    for row in rows:
        value = row[field]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Visualization field {field!r} must contain numeric values")
        has_numeric_value = True
    if not has_numeric_value:
        raise ValueError(f"Visualization field {field!r} has no numeric values")


def _validate_unique_grain(rows: list[dict[str, Any]], fields: list[str]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row[field] for field in fields)
        try:
            duplicate = key in seen
        except TypeError as exc:
            raise ValueError(
                "Chart grouping fields must contain scalar, hashable values"
            ) from exc
        if duplicate:
            field_list = ", ".join(fields)
            raise ValueError(
                "Chart data must already be aggregated to the presentation grain; "
                f"duplicate values were found for {field_list}"
            )
        seen.add(key)
