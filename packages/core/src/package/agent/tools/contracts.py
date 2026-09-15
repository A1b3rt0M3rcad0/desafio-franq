from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolArtifact:
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolInvocationResult:
    observation: Any
    artifacts: tuple[ToolArtifact, ...] = ()


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]

    async def invoke(self, arguments: dict[str, Any]) -> Any: ...
