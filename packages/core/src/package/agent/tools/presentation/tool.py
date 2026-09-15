from typing import Any

from package.agent.tools.contracts import ToolArtifact, ToolInvocationResult
from package.agent.tools.presentation.models import PresentationSpec


class PresentationTool:
    name = "present_result"
    description = (
        "Declare a validated table or chart that should accompany the final answer. "
        "Use only data already obtained during this execution; do not invent or aggregate values here."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "version": {
                "type": "integer",
                "enum": [1],
                "description": "Presentation contract version.",
            },
            "data": {
                "type": "object",
                "properties": {
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 64,
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                        "minItems": 1,
                        "maxItems": 500,
                    },
                },
                "required": ["columns", "rows"],
                "additionalProperties": False,
            },
            "visualization": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["table", "bar", "line", "scatter"],
                    },
                    "title": {"type": "string"},
                    "x": {"type": "string"},
                    "y": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 8,
                    },
                    "hue": {"type": "string"},
                    "x_label": {"type": "string"},
                    "y_label": {"type": "string"},
                    "orientation": {
                        "type": "string",
                        "enum": ["vertical", "horizontal"],
                    },
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
        "required": ["data", "visualization"],
        "additionalProperties": False,
    }

    async def invoke(self, arguments: dict[str, Any]) -> ToolInvocationResult:
        presentation = PresentationSpec.model_validate(arguments).normalized()
        payload = presentation.model_dump(mode="json")
        visualization = presentation.visualization
        return ToolInvocationResult(
            observation={
                "accepted": True,
                "type": visualization.type,
                "title": visualization.title,
                "row_count": len(presentation.data.rows),
            },
            artifacts=(ToolArtifact(kind="presentation", payload=payload),),
        )
